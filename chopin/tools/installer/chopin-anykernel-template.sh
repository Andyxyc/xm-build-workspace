### chopin / MIUI 14 Android 13 source-built test candidate
properties() { '
kernel.string=chopin SukiSU SUSFS155 KPM TEST CANDIDATE
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=chopin
supported.versions=13
'; }

BLOCK=/dev/block/by-name/boot;
IS_SLOT_DEVICE=1;
SLOT_SELECT=active;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=0;
NO_VBMETA_PARTITION_PATCH=1;
NO_MAGISK_CHECK=1;
. tools/ak3-core.sh;
. "$AKHOME/tools/chopin-preflight.sh";

[ "$(getprop ro.product.device)" = chopin ] || abort "Device is not chopin";
[ "$(getprop ro.build.version.incremental)" = V14.0.8.0.TKPCNXM ] || abort "ROM baseline mismatch";
case "$SLOT" in _a|_b) ;; *) abort "Unknown active slot";; esac;
[ "$SLOT" = _a ] || abort "This test package requires the independently backed-up slot a";
[ "$BLOCK" = "/dev/block/by-name/boot$SLOT" ] || abort "Unexpected boot target";
[ "$(blockdev --getsize64 "$BLOCK")" = 134217728 ] || abort "Unexpected boot size";

cd "$AKHOME";
sha256sum -c payload.sha256 || abort "Candidate payload checksum mismatch";
split_boot;
[ "$(wc -c < "$BOOTIMG")" = 134217728 ] || abort "Incomplete boot readback";
digest=$(sha256sum "$BOOTIMG" | cut -d' ' -f1);
[ ${#digest} = 64 ] || abort "Invalid backup digest";
CHOPIN_BACKUP_SHA=$digest;
backup_dir=/data/adb/chopin-kernel-backups;
umask 077;
mkdir -p "$backup_dir" || abort "Persistent private backup directory unavailable";
backup_file="$backup_dir/boot${SLOT}-${digest}.img";
if [ ! -f "$backup_file" ]; then
  cp "$BOOTIMG" "$backup_file" || abort "Cannot create persistent boot backup";
fi;
[ "$(sha256sum "$backup_file" | cut -d' ' -f1)" = "$digest" ] || abort "Persistent backup checksum mismatch";

# Install the supplied stock ramdisk rather than retaining a second root backend.
# Keep all application data and existing /data/adb content available for rollback.
gzip -dc "$AKHOME/stock-ramdisk.cpio.gz" > "$SPLITIMG/ramdisk.cpio" || abort "Stock ramdisk decompression failed";
[ "$(sha256sum "$SPLITIMG/ramdisk.cpio" | cut -d' ' -f1)" = 58e70342f8d631f26c95546f787933b744f8fbb67412ca22be561c0a30b42095 ] || abort "Stock ramdisk mismatch";
cp "$AKHOME/stock-dtb.bin" "$SPLITIMG/dtb" || abort "Stock DTB copy failed";
[ "$(sha256sum "$SPLITIMG/dtb" | cut -d' ' -f1)" = d6aa88bad3591b62473a2b753ccd19dc371dbb30bd8e1efa487c651fdefd27fc ] || abort "Stock DTB mismatch";

ui_print "Test candidate: replacing only the confirmed active boot partition";
ui_print "Backup: $backup_file";
flash_boot;
chopin_postflash_verify;
