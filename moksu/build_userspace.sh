#!/usr/bin/env bash
set -euo pipefail
: "${ANDROID_NDK_HOME:?Missing Android NDK}"
mkdir -p out
cp lkms/aarch64/*.ko source/userspace/ksud/bin/aarch64/
cp lkms/x86_64/*.ko source/userspace/ksud/bin/x86_64/
test "$(find source/userspace/ksud/bin/aarch64 -name '*_sevenk.ko' | wc -l)" -eq 8
test "$(find source/userspace/ksud/bin/x86_64 -name '*_sevenk.ko' | wc -l)" -eq 8
cd source
export KSU_PACKAGE_NAME=com.moksu.manager
for triple in aarch64-linux-android x86_64-linux-android; do
 arch="${triple%%-*}"
 source .github/scripts/setup-rust-build.sh "$triple" 26
 BUILTINS="$($CLANG_PATH --print-resource-dir)/lib/linux/libclang_rt.builtins-${arch}-android.a"
 test -s "$BUILTINS"
 export RUSTFLAGS="-C target-feature=+crt-static -C link-arg=-Wl,-z,max-page-size=16384 -C link-arg=-Wno-unused-command-line-argument -C link-arg=$BUILTINS"
 cargo build --locked --package ksuinit --target="$triple" --release
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
done
