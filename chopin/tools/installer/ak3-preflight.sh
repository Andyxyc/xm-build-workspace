# Sourced by the chopin installer. All preflight writes stay inside AKHOME.
chopin_sha() { sha256sum "$1" | cut -d' ' -f1; }

chopin_preflash_verify() {
  local v sz digest;
  v="$AKHOME/chopin-verify";
  [ ! -e "$v" ] || abort "Preflight directory already exists";
  mkdir -m 700 "$v" || abort "Cannot create preflight directory";
  [ "$(blockdev --getsize64 "$BLOCK")" = 134217728 ] || abort "Boot target changed";
  [ "$(chopin_sha "$BLOCK")" = "$CHOPIN_BACKUP_SHA" ] || abort "Boot changed since backup";
  sz=$(wc -c < "$AKHOME/boot-new.img");
  [ "$sz" -ge 1660 ] && [ "$sz" -le 134217728 ] || abort "Invalid repacked boot size";
  dd if="$AKHOME/boot-new.img" of="$v/header" bs=1 count=1660 2>/dev/null || abort "Cannot read header";
  [ "$(wc -c < "$v/header")" = 1660 ] || abort "Short header";
  # Normalize only variable kernel/ramdisk lengths and the boot component ID.
  dd if=/dev/zero of="$v/header" bs=1 seek=8 count=4 conv=notrunc 2>/dev/null || abort "Cannot normalize header";
  dd if=/dev/zero of="$v/header" bs=1 seek=16 count=4 conv=notrunc 2>/dev/null || abort "Cannot normalize header";
  dd if=/dev/zero of="$v/header" bs=1 seek=576 count=32 conv=notrunc 2>/dev/null || abort "Cannot normalize header";
  [ "$(chopin_sha "$v/header")" = "$(cat "$AKHOME/expected/header.sha256")" ] || abort "Stock boot header parameters changed";
  (
    cd "$v" || exit 1;
    magiskboot unpack -h "$AKHOME/boot-new.img" > unpack.log 2>&1 || exit 1;
    [ "$(chopin_sha kernel)" = "$(cat "$AKHOME/expected/kernel.sha256")" ] || exit 2;
    [ "$(chopin_sha ramdisk.cpio)" = 58e70342f8d631f26c95546f787933b744f8fbb67412ca22be561c0a30b42095 ] || exit 3;
    [ "$(chopin_sha dtb)" = d6aa88bad3591b62473a2b753ccd19dc371dbb30bd8e1efa487c651fdefd27fc ] || exit 4;
  ) || abort "Repacked kernel, stock ramdisk or DTB verification failed";
  CHOPIN_NEW_IMAGE_SHA=$(chopin_sha "$AKHOME/boot-new.img");
  [ ${#CHOPIN_NEW_IMAGE_SHA} = 64 ] || abort "Cannot hash repacked boot";
  ui_print "Repacked header/kernel/ramdisk/DTB verified";
}

chopin_record_attempt() {
  local marker payload;
  [ "$backup_dir" = /data/adb/chopin-kernel-backups ] || abort "Unexpected backup directory";
  case "$SLOT" in _a|_b) ;; *) abort "Unknown slot before write";; esac;
  [ ${#CHOPIN_NEW_IMAGE_SHA} = 64 ] || abort "Unverified repacked image";
  payload=$(cat "$AKHOME/expected/kernel.sha256");
  [ ${#payload} = 64 ] || abort "Invalid candidate identity";
  case "$payload" in *[!0-9a-f]*) abort "Invalid candidate digest";; esac;
  marker="$backup_dir/attempt${SLOT}-${payload}.txt";
  # Refuse a second automatic write of the same kernel even if repacking differs.
  CHOPIN_ATTEMPT_MARKER=$marker;
  (set -C; printf 'phase=prepared\ntarget=%s\nkernel_sha256=%s\nimage_sha256=%s\nbackup_sha256=%s\n' "$BLOCK" "$payload" "$CHOPIN_NEW_IMAGE_SHA" "$CHOPIN_BACKUP_SHA" > "$marker") || abort "Write attempt already recorded; diagnose before another attempt";
  sync;
}

chopin_postflash_verify() {
  local sz pad expected actual;
  sync;
  [ "$(chopin_sha "$AKHOME/boot-new.img")" = "$CHOPIN_NEW_IMAGE_SHA" ] || abort "Repacked file changed during write";
  sz=$(wc -c < "$AKHOME/boot-new.img");
  pad=$((134217728 - sz));
  [ "$pad" -ge 0 ] || abort "Invalid verification length";
  expected=$({ cat "$AKHOME/boot-new.img"; head -c "$pad" /dev/zero; } | sha256sum | cut -d' ' -f1);
  actual=$(chopin_sha "$BLOCK");
  [ ${#expected} = 64 ] && [ "$actual" = "$expected" ] || abort "Boot readback failed; stop and restore saved backup, do not retry";
  [ -f "$CHOPIN_ATTEMPT_MARKER" ] && [ ! -L "$CHOPIN_ATTEMPT_MARKER" ] || abort "Attempt journal is unavailable after write";
  printf 'phase=full_partition_readback_verified\nreadback_sha256=%s\n' "$actual" >> "$CHOPIN_ATTEMPT_MARKER" || abort "Cannot persist completed readback journal";
  sync;
  ui_print "Full boot partition readback verified";
}

# Write one complete, verified boot image; fsync must report success.
# No preliminary erase, ignored I/O error, or secondary partition target.
chopin_write_boot() {
  case "$SLOT" in _a|_b) ;; *) abort "Unknown boot slot before write";; esac;
  [ "$BLOCK" = "/dev/block/by-name/boot$SLOT" ] || abort "Unexpected boot target before write";
  [ "$(wc -c < "$AKHOME/boot-new.img")" = 134217728 ] || abort "A complete boot partition image is required";
  [ -f "$CHOPIN_ATTEMPT_MARKER" ] && [ ! -L "$CHOPIN_ATTEMPT_MARKER" ] || abort "Write attempt journal is unavailable";
  blockdev --setrw "$BLOCK" || abort "Boot target cannot be opened for writing";
  if dd if="$AKHOME/boot-new.img" of="$BLOCK" bs=1048576 conv=fsync,notrunc; then
    printf 'phase=write_and_flush_completed\n' >> "$CHOPIN_ATTEMPT_MARKER" || abort "Cannot preserve write result";
  else
    printf 'phase=write_or_flush_failed\n' >> "$CHOPIN_ATTEMPT_MARKER" || abort "Cannot preserve write failure";
    abort "Boot write or flush failed; keep the backup and use the verified Fastboot path";
  fi;
}
