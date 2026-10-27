This installer is for chopin Android 13/14 across compatible firmware variants.
Android 13 MIUI14 has actual boot evidence. Android 14 acceptance remains
pending; accepting its installer entry is not proof of driver/ROM compatibility.
It keeps the current slot, backs up boot, preserves its own DTB/ramdisk,
propagates write errors and checks the actual write result. It does not bind
the package to a firmware increment, vendor-module hashes or a fixed header.
Old failed-install records are preserved as evidence and never permanently
block a later user-initiated installation.

The recovery ZIP entry remains META-INF/com/google/android/update-binary.
The boot backup uses /data/adb when /data is a real writable persistent mount.
If that path is unavailable, it uses chopin-kernel-backups beside the ZIP on
decrypted internal storage, SD card or USB OTG. An unmounted /data, tmpfs or
the /tmp/sideload workspace is not a recoverable backup location. A sideload
session therefore needs writable decrypted /data; otherwise use a ZIP from
persistent storage. The installer never proceeds without a complete backup.

Slot confirmation accepts matching ro.boot.slot_suffix, ro.boot.slot and
androidboot.slot(_suffix) cmdline values. Missing sources are allowed; invalid
or conflicting values and an actual slot change are rejected. Only the active
A/B slot is written. Recovery fixture cases exercise these branches on ordinary
files; they do not establish a successful physical recovery flash.

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
