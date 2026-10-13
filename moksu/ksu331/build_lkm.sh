#!/usr/bin/env bash
set -euo pipefail
: "${KMI:?KMI not set}"
: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE not set}"
cd source/kernel
# DDK image provides the matching kernel headers and clang/llvm toolchain.
CONFIG_KSU=m CC=clang make
mkdir -p "$GITHUB_WORKSPACE/out/aarch64" "$GITHUB_WORKSPACE/out/x86_64"
test -s kernelsu.ko
cp kernelsu.ko "$GITHUB_WORKSPACE/out/aarch64/${KMI}_kernelsu.ko"
llvm-strip -d "$GITHUB_WORKSPACE/out/aarch64/${KMI}_kernelsu.ko"
make clean
unset ARCH CROSS_COMPILE
export ARCH=x86_64
export KDIR="/opt/ddk/kdir-x64/$KMI"
mkdir -p /opt/ddk/kdir-x64
pushd "/opt/ddk/src/$KMI"
MODPOST=scripts/mod/modpost.c
sed -i -E 's/^([[:space:]]*)check_exports\(mod\);/\1\/\/ check_exports(mod);/' "$MODPOST"
sed -i -E 's/^([[:space:]]*)s->module = exp->module;/\1\/\/ s->module = exp->module;/' "$MODPOST"
sed -i 's/^static void check_exports(/static void __attribute__((unused)) check_exports(/' "$MODPOST"
make O="$KDIR" gki_defconfig
scripts/config --file "$KDIR/.config" -d LTO_CLANG -e LTO_NONE -d LTO_CLANG_THIN -d LTO_CLANG_FULL -d THINLTO
if [[ "$KMI" == android16-6.12 || "$KMI" == android17-6.18 ]]; then
  scripts/config --file "$KDIR/.config" -e CONFIG_CFI_ICALL_NORMALIZE_INTEGERS
fi
make O="$KDIR" modules_prepare
make O="$KDIR" security/selinux/built-in.a
popd
MDIR="$(realpath .)"
if [[ "$KMI" == android17-6.18 ]]; then
  make -C "$KDIR" M="$MDIR" MO="$MDIR" compile_commands.json modules CONFIG_KSU=m CONFIG_KSU_X86_PATCH_SYSCALL_DISPATCHER=y
else
  make -C "$KDIR" M="$MDIR" src="$MDIR" compile_commands.json modules CONFIG_KSU=m CONFIG_KSU_X86_PATCH_SYSCALL_DISPATCHER=y
fi
test -s kernelsu.ko
cp kernelsu.ko "$GITHUB_WORKSPACE/out/x86_64/${KMI}_kernelsu.ko"
llvm-strip -d "$GITHUB_WORKSPACE/out/x86_64/${KMI}_kernelsu.ko"
echo "BUILT_KMI $KMI: $(sha256sum "$GITHUB_WORKSPACE/out/aarch64/${KMI}_kernelsu.ko")"
