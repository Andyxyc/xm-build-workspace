# Backups and real write results only. No ROM/driver/header identity binding.
chopin_sha() {
  local value;
  value=$(sha256sum "$1") || return 1;
  printf '%s\n' "${value%% *}";
}

chopin_persistent_path() {
  local path source point kind options rest selected selected_kind selected_options;
  [ -d "$1" ] || return 1;
  [ -r /proc/mounts ] || return 1;
  path=$(readlink -f "$1") || return 1;
  case "$path" in /tmp|/tmp/*|/dev|/dev/*|/proc|/proc/*|/sys|/sys/*|/sideload|/sideload/*|/postinstall/tmp|/postinstall/tmp/*) return 1;; esac;
  # The deepest mount wins; an unmounted /data is only part of the recovery RAM disk.
  while read -r source point kind options rest; do
    point=$(printf '%b' "$point");
    case "$path/" in "$point/"*|"$point") ;;
      *) [ "$point" = / ] || continue;;
    esac;
    if [ -z "$selected" ] || [ "${#point}" -gt "${#selected}" ]; then
      selected=$point; selected_kind=$kind; selected_options=$options;
    fi;
  done < /proc/mounts;
  [ "$selected" != / ] || return 1;
  case "$selected_kind" in ext4|f2fs|vfat|exfat|ntfs|ntfs3|fuse|fuseblk|sdcardfs) ;;
    *) return 1;;
  esac;
  case ",$selected_options," in *,rw,*) return 0;; *) return 1;; esac;
}

chopin_backup_directory() {
  local parent folder;
  if chopin_persistent_path /data; then
    folder=/data/adb/chopin-kernel-backups;
    if [ ! -L "$folder" ] && mkdir -p "$folder" 2>/dev/null && chopin_persistent_path "$folder"; then
      printf '%s\n' "$folder"; return 0;
    fi;
  fi;
  # Decrypted internal storage, USB OTG and SD cards can hold a recovery backup.
  [ -n "${ZIPFILE:-}" ] || return 1;
  parent=$(dirname "$ZIPFILE") || return 1;
  parent=$(readlink -f "$parent") || return 1;
  chopin_persistent_path "$parent" || return 1;
  folder=$parent/chopin-kernel-backups;
  [ ! -L "$folder" ] && mkdir -p "$folder" 2>/dev/null && chopin_persistent_path "$folder" || return 1;
  printf '%s\n' "$folder";
}

chopin_current_slot() {
  local value resolved;
  # Recovery can expose only ro.boot.slot or a cmdline value. Reject disagreement.
  for value in $(getprop ro.boot.slot_suffix 2>/dev/null; getprop ro.boot.slot 2>/dev/null;
    awk '{ for (i=1; i<=NF; i++) if ($i ~ /^androidboot\.slot(_suffix)?=/) { sub(/^[^=]*=/,"",$i); print $i; } }' /proc/cmdline); do
    case "$value" in a|_a) value=_a;; b|_b) value=_b;; *) return 1;; esac;
    [ -z "$resolved" ] || [ "$resolved" = "$value" ] || return 1;
    resolved=$value;
  done;
  [ -n "$resolved" ] || return 1;
  printf '%s\n' "$resolved";
}

chopin_backup_boot() {
  local backup_dir backup_file;
  CHOPIN_BOOT_BYTES=$(blockdev --getsize64 "$BLOCK") || abort "Cannot read boot size";
  [ "$(wc -c < "$BOOTIMG")" -eq "$CHOPIN_BOOT_BYTES" ] || abort "Boot backup is incomplete";
  CHOPIN_BACKUP_SHA=$(chopin_sha "$BOOTIMG") || abort "Cannot read boot backup";
  umask 077;
  backup_dir=$(chopin_backup_directory) || abort "A writable persistent location is required for the boot backup";
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
  [ "$(chopin_current_slot)" = "$SLOT" ] || abort "Cannot confirm the active boot slot";
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
  CHOPIN_ALREADY_INSTALLED=0;
  if [ "$CHOPIN_NEW_IMAGE_SHA" = "$CHOPIN_BACKUP_SHA" ]; then
    CHOPIN_ALREADY_INSTALLED=1;
    printf 'phase=already_installed_no_partition_write\n' >> "$CHOPIN_DETAIL_LOG";
    return 0;
  fi;
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
