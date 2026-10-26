This installer is for chopin Android 13 across compatible firmware variants.
It keeps the current slot, backs up boot, preserves its own DTB/ramdisk,
propagates write errors and checks the actual write result. It does not bind
the package to a firmware increment, vendor-module hashes or a fixed header.
Old failed-install records are preserved as evidence and never permanently
block a later user-initiated installation.

If the newly prepared full boot image already equals the current full boot,
the installer performs no partition write and says so explicitly. This does
not establish that Android can write a different image. On the tested phone,
UFS returned DATA PROTECT / hardware-write-protected during an actual official
manager installation. Root and blockdev --setrw did not remove that protection.
Do not suppress that failure or claim a successful update. Use a verified
Fastboot or compatible recovery route when Android rejects a real write.

For the original manager, open the ZIP as an AnyKernel3 kernel from a file
manager. The GKI image-patching option expects a boot image and is not an AK3
ZIP installer. Keep KPM in follow-kernel mode for an already patched Image.

The r10 kernel Image f280e96e failed a real boot test and was withdrawn.
Do not package that Image with these simplified scripts. Installer success
on ordinary files does not establish that a kernel will boot.
