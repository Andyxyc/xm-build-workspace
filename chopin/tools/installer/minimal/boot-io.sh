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

chopin_recovery_backup_allowed() {
  local processes;
  case "${BOOTMODE:-}" in true) return 1;; false) return 0;; "") ;; *) return 1;; esac;
  # Some callers run anykernel.sh in a new shell without exporting BOOTMODE.
  [ "$(getprop ro.twrp.boot 2>/dev/null)" = 1 ] || [ -n "$(getprop ro.twrp.version 2>/dev/null)" ] || return 1;
  processes=$(ps -A 2>/dev/null) || processes=$(ps 2>/dev/null) || return 1;
  printf '%s\n' "$processes" | grep -q '[z]ygote' && return 1;
  return 0;
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
  if [ -n "${ZIPFILE:-}" ]; then
    parent=$(dirname "$ZIPFILE") || return 1;
    case "$parent" in /cache|/cache/*) [ ! -L /cache ] && [ ! -L "$parent" ] && [ "$(readlink -f "$parent")" = "$parent" ] || return 1;; esac;
    parent=$(readlink -f "$parent") || return 1;
    if chopin_persistent_path "$parent"; then
      case "$parent" in /cache|/cache/*) chopin_recovery_backup_allowed || return 1;; esac;
      folder=$parent/chopin-kernel-backups;
      [ ! -L "$folder" ] && mkdir -p "$folder" 2>/dev/null && chopin_persistent_path "$folder" || return 1;
      printf '%s\n' "$folder"; return 0;
    fi;
  fi;
  chopin_recovery_backup_allowed || return 1;
  [ ! -L /cache ] && chopin_persistent_path /cache || return 1;
  folder=/cache/chopin-kernel-backups;
  [ ! -L "$folder" ] && mkdir -p "$folder" 2>/dev/null && chopin_persistent_path "$folder" || return 1;
  printf '%s\n' "$folder";
}

chopin_verify_gzip_backup() {
  local bytes value;
  [ -f "$1" ] && [ ! -L "$1" ] || return 1;
  bytes=$(set -o pipefail || exit 1; gzip -dc "$1" | wc -c | awk '{ print $1 }') || return 1;
  [ "$bytes" = "$CHOPIN_BOOT_BYTES" ] || return 1;
  value=$(set -o pipefail || exit 1; gzip -dc "$1" | sha256sum) || return 1;
  [ "${value%% *}" = "$CHOPIN_BACKUP_SHA" ];
}

chopin_save_gzip_backup() {
  local backup_file folder bytes free_kib required_kib temporary;
  backup_file=$1; folder=$2;
  if [ -e "$backup_file" ] || [ -L "$backup_file" ]; then
    chopin_verify_gzip_backup "$backup_file" || abort "Boot backup is damaged";
    return 0;
  fi;
  # Measure the same stream before allocating it. Leave room for the log.
  bytes=$(set -o pipefail || exit 1; gzip -c "$BOOTIMG" | wc -c | awk '{ print $1 }') || abort "Cannot prepare compressed boot backup";
  case "$bytes" in ""|*[!0-9]*) abort "Cannot measure compressed boot backup";; esac;
  free_kib=$(set -o pipefail || exit 1; df -Pk "$folder" | awk 'NR > 1 { value=$4 } END { if (value ~ /^[0-9]+$/) print value; else exit 1 }') || abort "Cannot read backup storage space";
  case "$free_kib" in ""|*[!0-9]*) abort "Cannot read backup storage space";; esac;
  required_kib=$(((bytes + 1048576 + 1023) / 1024));
  [ "$free_kib" -ge "$required_kib" ] || abort "Not enough space for the boot backup";
  temporary=$(mktemp "$folder/.boot${SLOT}-${CHOPIN_BACKUP_SHA}.img.gz.partial.XXXXXXXX") || abort "Cannot create boot backup";
  printf 'backup_partial=%s\n' "$temporary" >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save backup location";
  gzip -c "$BOOTIMG" > "$temporary" 2>> "$CHOPIN_DETAIL_LOG" || abort "Cannot save compressed boot backup";
  chopin_verify_gzip_backup "$temporary" || abort "Compressed boot backup verification failed";
  [ "$(chopin_sha "$BOOTIMG")" = "$CHOPIN_BACKUP_SHA" ] || abort "Boot backup source changed";
  # A hard link publishes the validated file atomically without replacing a file.
  ln "$temporary" "$backup_file" || abort "Cannot publish boot backup";
  rm "$temporary" || abort "Cannot finish boot backup";
  chopin_verify_gzip_backup "$backup_file" || abort "Boot backup is damaged";
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
  local backup_dir backup_file format;
  CHOPIN_BOOT_BYTES=$(blockdev --getsize64 "$BLOCK") || abort "Cannot read boot size";
  [ "$(wc -c < "$BOOTIMG")" -eq "$CHOPIN_BOOT_BYTES" ] || abort "Boot backup is incomplete";
  CHOPIN_BACKUP_SHA=$(chopin_sha "$BOOTIMG") || abort "Cannot read boot backup";
  umask 077;
  backup_dir=$(chopin_backup_directory) || abort "A writable persistent location is required for the boot backup";
  backup_file="$backup_dir/boot${SLOT}-${CHOPIN_BACKUP_SHA}.img";
  format=raw;
  case "$backup_dir" in /cache|/cache/*)
    # Keep an existing complete raw backup; use gzip for a new cache backup.
    if [ ! -e "$backup_file" ] && [ ! -L "$backup_file" ]; then backup_file=$backup_file.gz; format=gzip; fi;
    ;;
  esac;
  CHOPIN_DETAIL_LOG=$(mktemp "$backup_dir/install${SLOT}.log.XXXXXXXX") || abort "Cannot save installation log";
  cat "$AKHOME/install-detail.log" >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save installation log";
  printf 'backup_format=%s\nbackup=%s\nbackup_raw_sha256=%s\nbackup_raw_bytes=%s\n' "$format" "$backup_file" "$CHOPIN_BACKUP_SHA" "$CHOPIN_BOOT_BYTES" >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save backup location";
  if [ "$format" = gzip ]; then
    chopin_save_gzip_backup "$backup_file" "$backup_dir";
  else
    if [ ! -e "$backup_file" ]; then
      (set -C; cat "$BOOTIMG" > "$backup_file") || abort "Cannot save boot backup";
    fi;
    [ -f "$backup_file" ] && [ ! -L "$backup_file" ] && [ "$(chopin_sha "$backup_file")" = "$CHOPIN_BACKUP_SHA" ] || abort "Boot backup is damaged";
  fi;
  sync || abort "Cannot flush boot backup";
  printf 'phase=boot_backup_verified\n' >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save backup result";
  sync || abort "Cannot flush backup log";
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
  printf 'phase=writing\ntarget=%s\nimage_sha256=%s\n' "$BLOCK" "$CHOPIN_NEW_IMAGE_SHA" >> "$CHOPIN_DETAIL_LOG" || return 1;
  sync;
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
