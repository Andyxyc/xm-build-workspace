#!/usr/bin/env bash
set -euo pipefail
: "${ANDROID_NDK_HOME:?ANDROID_NDK_HOME not set}"
: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE not set}"
mkdir -p out
mkdir -p source/userspace/ksud/bin/aarch64 source/userspace/ksud/bin/x86_64
cp lkms/aarch64/*_kernelsu.ko source/userspace/ksud/bin/aarch64/
cp lkms/x86_64/*_kernelsu.ko source/userspace/ksud/bin/x86_64/
test "$(find source/userspace/ksud/bin/aarch64 -name '*_kernelsu.ko' | wc -l)" -eq 8
test "$(find source/userspace/ksud/bin/x86_64 -name '*_kernelsu.ko' | wc -l)" -eq 8
cd source
export KSU_PACKAGE_NAME=com.moksu.manager
export CARGO_NET_GIT_FETCH_WITH_CLI=true
rustup target add aarch64-linux-android x86_64-linux-android
for triple in aarch64-linux-android x86_64-linux-android; do
  arch="${triple%%-*}"
  source .github/scripts/setup-rust-build.sh "$triple" 26
  BUILTINS="$($CLANG_PATH --print-resource-dir)/lib/linux/libclang_rt.builtins-${arch}-android.a"
  test -s "$BUILTINS"
  export RUSTFLAGS="-C target-feature=+crt-static -C link-arg=-Wl,-z,max-page-size=16384 -C link-arg=-Wno-unused-command-line-argument -C link-arg=$BUILTINS"
  cargo build --locked --package ksuinit --target="$triple" --release
  test -s "target/$triple/release/ksuinit"
  cp "target/$triple/release/ksuinit" "userspace/ksud/bin/$arch/ksuinit"
  unset RUSTFLAGS
done
for triple in aarch64-linux-android x86_64-linux-android; do
  source .github/scripts/setup-rust-build.sh "$triple" 26
  cargo build --locked --target "$triple" --release --manifest-path userspace/ksud/Cargo.toml
  test -s "target/$triple/release/ksud"
  "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "target/$triple/release/ksud"
  mkdir -p "$GITHUB_WORKSPACE/out/$triple"
  cp "target/$triple/release/ksud" "$GITHUB_WORKSPACE/out/$triple/ksud"
  sha256sum "target/$triple/release/ksud"
done
echo "MOKSU331_KSUD_BUILD_COMPLETED"
