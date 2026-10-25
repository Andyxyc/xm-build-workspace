# Only chopin / MIUI 14 / Android 13 with the independently audited driver ABI.
# No account, Android ID, UID, IMEI, serial number or device UUID binding.
chopin_family_rom() {
  [ "$(getprop ro.product.device)" = chopin ] || abort "This package supports chopin only";
  [ "$(getprop ro.build.version.sdk)" = 33 ] || abort "Android 13 is required";
  case "$(getprop ro.miui.ui.version.name)" in V14|V140|14|140) ;; *) abort "MIUI 14 is required";; esac;
}

chopin_family_modules() {
  local root manifest hash name extra count found;
  root=$1; manifest=$2; count=0;
  [ -d "$root" ] && [ -f "$manifest" ] || abort "Vendor driver information is unavailable";
  while read -r hash name extra; do
    [ -z "$extra" ] && [ ${#hash} = 64 ] || abort "Invalid driver compatibility manifest";
    case "$hash" in *[!0-9a-f]*) abort "Invalid driver digest";; esac;
    case "$name" in ''|*[!A-Za-z0-9_.-]*|.*) abort "Invalid driver name";; esac;
    [ -f "$root/$name" ] || abort "Required driver is missing: $name";
    [ "$(sha256sum "$root/$name" | cut -d' ' -f1)" = "$hash" ] || abort "Driver ABI needs a separate build: $name";
    count=$((count + 1));
  done < "$manifest";
  [ "$count" = 10 ] || abort "Incomplete driver compatibility manifest";
  # Reject unexamined additional modules; never use force-load flags.
  found=$(find "$root" -name '*.ko' | wc -l);
  [ "$found" -eq "$count" ] || abort "Additional vendor drivers require verification";
  for root in /odm/lib/modules /system/lib/modules /system_dlkm/lib/modules /vendor_dlkm/lib/modules; do
    [ ! -d "$root" ] || [ -z "$(find "$root" -name '*.ko' -print -quit)" ] || abort "Additional driver partition requires verification";
  done;
}

chopin_family_header() {
  local boot header;
  boot=$1; header=$2;
  [ ! -e "$header" ] || abort "Header workspace already exists";
  dd if="$boot" of="$header" bs=1 count=1660 2>/dev/null || abort "Cannot inspect boot header";
  [ "$(wc -c < "$header")" = 1660 ] || abort "Incomplete boot header";
  dd if=/dev/zero of="$header" bs=1 seek=8 count=4 conv=notrunc 2>/dev/null || abort "Header normalization failed";
  dd if=/dev/zero of="$header" bs=1 seek=16 count=4 conv=notrunc 2>/dev/null || abort "Header normalization failed";
  dd if=/dev/zero of="$header" bs=1 seek=576 count=32 conv=notrunc 2>/dev/null || abort "Header normalization failed";
  CHOPIN_EXPECTED_HEADER_SHA=$(sha256sum "$header" | cut -d' ' -f1);
  # Across MIUI 14 builds retain each boot's OS/security stamp and DTB length.
  dd if=/dev/zero of="$header" bs=1 seek=44 count=4 conv=notrunc 2>/dev/null || abort "Header normalization failed";
  dd if=/dev/zero of="$header" bs=1 seek=1648 count=4 conv=notrunc 2>/dev/null || abort "Header normalization failed";
  [ "$(sha256sum "$header" | cut -d' ' -f1)" = "$(cat "$AKHOME/expected/family-header.sha256")" ] || abort "Boot layout needs a separate build";
}

chopin_family_ramdisk() {
  local cpio state;
  cpio=$1;
  [ -f "$cpio" ] || abort "Current boot ramdisk is unavailable";
  if magiskboot cpio "$cpio" test; then state=0; else state=$?; fi;
  case "$state" in
    0) ;;
    1)
      # Restore THIS boot's embedded Magisk backup in the workspace only.
      # A missing backup can yield an empty archive; verify init afterwards.
      magiskboot cpio "$cpio" restore || abort "Cannot restore this boot's stock ramdisk";
      magiskboot cpio "$cpio" test || abort "Restored ramdisk is not clean";
      ;;
    *) abort "Unsupported ramdisk patch; restore a matching stock boot first";;
  esac;
  [ "$(wc -c < "$cpio")" -ge 128 ] && magiskboot cpio "$cpio" 'exists init' || abort "Stock ramdisk backup is incomplete";
  CHOPIN_EXPECTED_RAMDISK_SHA=$(sha256sum "$cpio" | cut -d' ' -f1);
}

chopin_family_dtb() {
  local dtb size magic;
  dtb=$1; [ -f "$dtb" ] || abort "Current DTB is unavailable";
  size=$(wc -c < "$dtb");
  [ "$size" -ge 40 ] && [ "$size" -le 4194304 ] || abort "Unexpected DTB size";
  magic=$(od -An -tx1 -N4 "$dtb" | tr -d ' \n');
  case "$magic" in d7b7ab1e|d00dfeed) ;; *) abort "Unsupported DTB container";; esac;
  CHOPIN_EXPECTED_DTB_SHA=$(sha256sum "$dtb" | cut -d' ' -f1);
}
