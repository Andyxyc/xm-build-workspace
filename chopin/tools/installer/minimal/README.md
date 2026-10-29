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
the /tmp/sideload workspace is not a recoverable backup location.

Recovery can also use an already mounted, writable persistent /cache. A ZIP
inside /cache puts its backup beside the ZIP; a ZIP in RAM can fall back to
/cache/chopin-kernel-backups. Android never gets this cache fallback. If the
caller did not export BOOTMODE, the fallback requires TWRP properties, a
successful process-list read and no running zygote. An unknown context is
rejected. Symlinked, read-only, tmpfs and unmounted cache paths are rejected.

New cache backups use gzip because some cache partitions cannot hold a full
boot image. Existing complete raw backups remain usable. Before allocating
the gzip, the installer measures its stream and checks free space with 1 MiB
left for logs. It decompresses the temporary file to check the full raw size
and SHA-256, propagates gzip failures, then publishes it with a hard link so
an existing backup cannot be overwritten. Cache filesystems without hard-link
support are rejected before a boot write. A failed attempt retains its log
and any partial file; it does not automatically retry or delete earlier logs.
Backup and log sync failures stop installation before the target writer. The
attempt log is also synced before the writer is called.
The installer never proceeds without a complete, verified persistent backup.

The installation log records backup_format, backup path, backup_raw_sha256
and backup_raw_bytes. A .img.gz backup is an archive, so decompress it on the
computer before using the normal boot restoration procedure. For example,
with Python already installed, copy it to a separate new file:

```python
import gzip, hashlib, shutil
from pathlib import Path
source = Path("boot_a-HASH.img.gz")  # Use the actual backup filename.
restored = Path("boot-restore.img")
with gzip.open(source, "rb") as src, restored.open("xb") as dst:
    shutil.copyfileobj(src, dst, 1024 * 1024)
print(restored.stat().st_size)
with restored.open("rb") as stream:
    print(hashlib.file_digest(stream, "sha256").hexdigest())
```

Both values must match backup_raw_bytes and backup_raw_sha256 in the log.
A decompression error or mismatch means stop; do not flash that output. This
change does not decrypt /data, repair a filesystem or remove UFS protection.

Slot confirmation accepts matching ro.boot.slot_suffix, ro.boot.slot and
androidboot.slot(_suffix) cmdline values. Missing sources are allowed; invalid
or conflicting values and an actual slot change are rejected. Only the active
A/B slot is written. Recovery fixture cases exercise these branches on ordinary
files; they do not establish a successful physical recovery flash.
The added cache cases also use ordinary files in a disposable Linux chroot.
They check corruption, decompressor status, space and publication failures,
and verify that rejected backups never invoke the target writer. Their sync
function is mocked, including a failure case; they do not prove a physical
filesystem flush or power-loss recovery.

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

The direct ZIP entry emits the standard recovery ui_print protocol, including
the indented empty sentinel expected by Kernel Flasher. Only the Magisk module
bridge explicitly requests plain output. Neither path reopens /proc/self/fd.
