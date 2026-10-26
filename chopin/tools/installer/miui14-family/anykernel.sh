### chopin / MIUI 14 / Android 13 compatible driver family
properties() { '
kernel.string=小莫
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
. "$AKHOME/tools/miui14-compat.sh";

ui_print " " "小莫" " ";
ui_print "Checking compatibility...";
chopin_family_rom;
case "$SLOT" in _a|_b) ;; *) abort "Unknown active boot slot";; esac;
[ "$BLOCK" = "/dev/block/by-name/boot$SLOT" ] || abort "Unexpected active boot target";
[ "$(blockdev --getsize64 "$BLOCK")" = 134217728 ] || abort "Unexpected boot partition size";
cd "$AKHOME" || abort "Installer workspace is unavailable";
sha256sum -c payload.sha256 > "$AKHOME/payload-check.log" 2>&1 || abort "Package checksum verification failed";
chopin_family_modules /vendor/lib/modules "$AKHOME/expected/vendor-modules.sha256";

ui_print "Saving boot backup...";
split_boot 2>> "$AKHOME/install-detail.log";
[ "$(wc -c < "$BOOTIMG")" -eq 134217728 ] || abort "Incomplete boot readback";
CHOPIN_BACKUP_SHA=$(sha256sum "$BOOTIMG" | cut -d' ' -f1);
[ ${#CHOPIN_BACKUP_SHA} = 64 ] || abort "Cannot verify current boot";
backup_dir=/data/adb/chopin-kernel-backups;
umask 077;
mkdir -p "$backup_dir" || abort "Private boot backup storage is unavailable";
backup_file="$backup_dir/boot${SLOT}-${CHOPIN_BACKUP_SHA}.img";
if [ ! -e "$backup_file" ]; then
  (set -C; cat "$BOOTIMG" > "$backup_file") || abort "Cannot save complete boot backup";
fi;
[ -f "$backup_file" ] && [ ! -L "$backup_file" ] && [ "$(sha256sum "$backup_file" | cut -d' ' -f1)" = "$CHOPIN_BACKUP_SHA" ] || abort "Boot backup verification failed";
CHOPIN_DETAIL_LOG=$(mktemp "$backup_dir/install${SLOT}.log.XXXXXXXX") || abort "Cannot create installation log";
cat "$AKHOME/install-detail.log" >> "$CHOPIN_DETAIL_LOG";

chopin_previous_attempt;
if [ "$CHOPIN_ALREADY_INSTALLED" = 1 ]; then
  ui_print "Already installed. Full boot readback matches.";
  exit 0;
fi;

ui_print "Preparing boot image...";
chopin_family_header "$BOOTIMG" "$AKHOME/current-header";
chopin_family_ramdisk "$SPLITIMG/ramdisk.cpio" 2>> "$CHOPIN_DETAIL_LOG";
chopin_family_dtb "$SPLITIMG/dtb";

ui_print "Writing boot$SLOT...";
flash_boot 2>> "$CHOPIN_DETAIL_LOG";
chopin_postflash_verify;

ui_print "Backup: $backup_file" "Log: $CHOPIN_DETAIL_LOG" "Done. Reboot when ready.";
