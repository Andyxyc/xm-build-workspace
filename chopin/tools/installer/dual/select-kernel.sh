# Select only from the real vendor ELF __versions records, never framework SDK.
chopin_abi_is_mounted() {
  awk -v point="$1" '$2 == point { found=1 } END { exit !found }' /proc/mounts;
}

chopin_abi_is_readonly() {
  awk -v point="$1" '$2 == point && ("," $4 ",") ~ /,ro,/ { found=1 } END { exit !found }' /proc/mounts;
}

chopin_abi_try_mount() {
  local name point block;
  name=$1; point=/$name;
  chopin_abi_is_mounted "$point" && return 0;
  [ ! -L "$point" ] || return 1;
  [ -d "$point" ] || mkdir -p "$point" 2>> "$CHOPIN_DETAIL_LOG" || return 1;
  if mount -o ro "$point" 2>> "$CHOPIN_DETAIL_LOG"; then
    if chopin_abi_is_mounted "$point"; then
      CHOPIN_ABI_MOUNTS="$point $CHOPIN_ABI_MOUNTS";
      chopin_abi_is_readonly "$point" || return 2;
      return 0;
    fi;
  fi;
  for block in /dev/block/mapper/"$name$SLOT" /dev/block/mapper/"$name" \
               /dev/block/by-name/"$name$SLOT" /dev/block/by-name/"$name"; do
    [ -b "$block" ] || continue;
    if mount -t auto -o ro "$block" "$point" 2>> "$CHOPIN_DETAIL_LOG"; then
      CHOPIN_ABI_MOUNTS="$point $CHOPIN_ABI_MOUNTS";
      chopin_abi_is_readonly "$point" || return 2;
      return 0;
    fi;
  done;
  return 1;
}

chopin_abi_release_mounts() {
  local point failed;
  failed=0;
  for point in $CHOPIN_ABI_MOUNTS; do
    umount "$point" 2>> "$CHOPIN_DETAIL_LOG" || failed=1;
  done;
  CHOPIN_ABI_MOUNTS=;
  [ "$failed" = 0 ];
}

chopin_select_kernel_abi() {
  local dir mod profile selector bootmode name selector_status;
  selector="$AKHOME/tools/chopin-abi-select";
  [ -x "$selector" ] || abort "Kernel ABI selector is unavailable";
  CHOPIN_ABI_MOUNTS=;
  set --;
  for dir in /vendor/lib/modules /vendor_dlkm/lib/modules /odm/lib/modules /odm_dlkm/lib/modules; do
    for mod in "$dir"/conninfra.ko "$dir"/met.ko \
               "$dir"/*/conninfra.ko "$dir"/*/met.ko; do
      [ -f "$mod" ] && set -- "$@" "$mod";
    done;
  done;
  bootmode=${BOOTMODE:-};
  if [ -z "$bootmode" ]; then
    bootmode=false;
    ps | grep zygote | grep -v grep >/dev/null && bootmode=true;
    [ "$bootmode" = true ] || { ps -A 2>/dev/null | grep zygote | grep -v grep >/dev/null && bootmode=true; };
  fi;
  if [ "$#" -eq 0 ] && [ "$bootmode" = false ]; then
    for name in vendor odm vendor_dlkm odm_dlkm; do
      if chopin_abi_try_mount "$name"; then :;
      elif [ "$?" = 2 ]; then
        chopin_abi_release_mounts || :;
        abort "Cannot mount vendor read-only";
      fi;
    done;
    for dir in /vendor/lib/modules /vendor_dlkm/lib/modules /odm/lib/modules /odm_dlkm/lib/modules; do
      for mod in "$dir"/conninfra.ko "$dir"/met.ko \
                 "$dir"/*/conninfra.ko "$dir"/*/met.ko; do
        [ -f "$mod" ] && set -- "$@" "$mod";
      done;
    done;
  fi;
  if [ "$#" -eq 0 ]; then
    chopin_abi_release_mounts || :;
    abort "Cannot read vendor modules; mount vendor and try again";
  fi;
  selector_status=0;
  profile=$("$selector" "$@" 2> "$AKHOME/abi-detail.log") || selector_status=$?;
  cat "$AKHOME/abi-detail.log" >> "$CHOPIN_DETAIL_LOG" || { chopin_abi_release_mounts || :; abort "Cannot save ABI selection log"; };
  chopin_abi_release_mounts || abort "Cannot release temporary read-only vendor mounts";
  [ "$selector_status" = 0 ] || abort "Vendor kernel ABI is not supported by this package";
  case "$profile" in
    t)
      [ -f "$AKHOME/Image" ] && [ -s "$AKHOME/Image" ] || abort "Matching kernel is unavailable";
      ;;
    legacy|early)
      [ -f "$AKHOME/images/$profile/Image" ] && [ -s "$AKHOME/images/$profile/Image" ] || abort "Matching kernel is unavailable";
      cp "$AKHOME/images/$profile/Image" "$AKHOME/Image" || abort "Cannot prepare matching kernel";
      ;;
    *) abort "Invalid kernel ABI selection";;
  esac;
  printf 'selected_abi_profile=%s\n' "$profile" >> "$CHOPIN_DETAIL_LOG" || abort "Cannot save ABI selection log";
  CHOPIN_SELECTED_ABI=$profile;
  ui_print "Kernel profile: $profile";
}
