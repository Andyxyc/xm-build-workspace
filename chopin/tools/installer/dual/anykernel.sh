properties() { '
kernel.string=小莫
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=chopin
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
. "$AKHOME/tools/chopin-select-kernel.sh";
ui_print " " "小莫" " ";
case "$SLOT" in _a|_b) ;; *) abort "Cannot identify the active boot slot";; esac;
[ -b "$BLOCK" ] || abort "Boot partition is unavailable";
cd "$AKHOME" || abort "Installer workspace is unavailable";
ui_print "Backing up boot...";
split_boot 2>> "$AKHOME/install-detail.log";
chopin_backup_boot;
ui_print "Selecting vendor kernel...";
chopin_select_kernel_abi;
ui_print "Preparing kernel...";
chopin_clean_ramdisk "$SPLITIMG/ramdisk.cpio" 2>> "$CHOPIN_DETAIL_LOG";
ui_print "Installing boot$SLOT...";
flash_boot 2>> "$CHOPIN_DETAIL_LOG";
chopin_postflash_verify;
if [ "${CHOPIN_ALREADY_INSTALLED:-0}" = 1 ]; then
  ui_print "Already installed. No boot changes.";
else
  ui_print "Installed. Reboot when ready.";
fi;
