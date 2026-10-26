# Backups and real write results only. No ROM/driver/header identity binding.
chopin_sha() {
  local value;
  value=$(sha256sum "$1") || return 1;
  printf '%s\n' "${value%% *}";
}

chopin_backup_boot() {
  local backup_dir backup_file;
  CHOPIN_BOOT_BYTES=$(blockdev --getsize64 "$BLOCK") || abort "Cannot read boot size";
  [ "$(wc -c < "$BOOTIMG")" -eq "$CHOPIN_BOOT_BYTES" ] || abort "Boot backup is incomplete";
  CHOPIN_BACKUP_SHA=$(chopin_sha "$BOOTIMG") || abort "Cannot read boot backup";
  backup_dir=/data/adb/chopin-kernel-backups;
  umask 077;
  mkdir -p "$backup_dir" || abort "Cannot create boot backup directory";
  backup_file="$backup_dir/boot${SLOT}-${CHOPIN_BACKUP_SHA}.img";
  if [ ! -e "$backup_file" ]; then
    (set -C; cat "$BOOTIMG" > "$backup_file") || abort "Cannot save boot backup";
  fi;
  [ -f "$backup_file" ] && [ ! -L "$backup_file" ] && [ "$(chopin_sha "$backup_file")" = "$CHOPIN_BACKUP_SHA" ] || abort "Boot backup is damaged";
  CHOPIN_DETAIL_LOG=$(mktemp "$backup_dir/install${SLOT}.log.XXXXXXXX") || abort "Cannot save installation log";
  cat "$AKHOME/install-detail.log" >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save installation log";
  printf 'backup=%s\n' "$backup_file" >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save backup location";
}

chopin_clean_ramdisk() {
  local cpio state;
  cpio=$1;
  [ -f "$cpio" ] || abort "Boot ramdisk is unavailable";
  if magiskboot cpio "$cpio" test; then state=0; else state=$?; fi;
  case "$state" in
    0) ;;
    1)
      magiskboot cpio "$cpio" restore || abort "Cannot restore this boot ramdisk";
      magiskboot cpio "$cpio" test || abort "Stock ramdisk backup is incomplete";
      ;;
    *) abort "A matching stock ramdisk is required";;
  esac;
  magiskboot cpio "$cpio" 'exists init' || abort "Boot ramdisk has no init";
}

chopin_preflash_verify() {
  local size pad;
  [ "$(getprop ro.boot.slot_suffix)" = "$SLOT" ] || abort "Active slot changed";
  [ "$(chopin_sha "$BLOCK")" = "$CHOPIN_BACKUP_SHA" ] || abort "Boot changed during installation";
  size=$(wc -c < "$AKHOME/boot-new.img");
  [ "$size" -ge 1660 ] && [ "$size" -le "$CHOPIN_BOOT_BYTES" ] || abort "Repacked boot does not fit";
  pad=$((CHOPIN_BOOT_BYTES - size));
  if [ "$pad" -gt 0 ]; then
    head -c "$pad" /dev/zero >> "$AKHOME/boot-new.img" || abort "Cannot finish boot padding";
  fi;
  CHOPIN_NEW_IMAGE_SHA=$(chopin_sha "$AKHOME/boot-new.img");
}

# Kept as the core's logging callback. Historical attempts never block a new
# user-initiated installation, and no historical journal is removed or reset.
chopin_record_attempt() {
  printf 'phase=writing\ntarget=%s\nimage_sha256=%s\n' "$BLOCK" "$CHOPIN_NEW_IMAGE_SHA" >> "$CHOPIN_DETAIL_LOG";
}

chopin_write_boot() {
  blockdev --setrw "$BLOCK" || return 1;
  if dd if="$AKHOME/boot-new.img" of="$BLOCK" bs=1048576 conv=fsync,notrunc; then
    printf 'phase=write_and_flush_completed\n' >> "$CHOPIN_DETAIL_LOG";
  else
    printf 'phase=write_or_flush_failed\n' >> "$CHOPIN_DETAIL_LOG";
    return 1;
  fi;
}

chopin_postflash_verify() {
  sync;
  [ "$(chopin_sha "$BLOCK")" = "$CHOPIN_NEW_IMAGE_SHA" ] || abort "Boot write verification failed; keep the backup and log";
  printf 'phase=full_partition_readback_verified\n' >> "$CHOPIN_DETAIL_LOG";
}
