# Suggested integration only; call after chopin_backup_boot and before
# flash_boot. AK3's normal split/repack path retains the owner's ramdisk/DTB.
chopin_select_kernel_abi() {
  local dir mod profile selector;
  selector="$AKHOME/tools/chopin-abi-select";
  [ -x "$selector" ] || abort "Kernel ABI selector is unavailable";
  set --;
  for dir in /vendor/lib/modules /vendor_dlkm/lib/modules /odm/lib/modules; do
    for mod in "$dir"/conninfra.ko "$dir"/met.ko \
               "$dir"/*/conninfra.ko "$dir"/*/met.ko; do
      [ -f "$mod" ] && set -- "$@" "$mod";
    done;
  done;
  [ "$#" -gt 0 ] || abort "Mount vendor before selecting the kernel";
  if profile=$("$selector" "$@" 2>"$AKHOME/abi-detail.log"); then
    case "$profile" in legacy|early|t) ;; *) abort "Invalid kernel ABI selection";; esac;
  else
    cat "$AKHOME/abi-detail.log" >> "$CHOPIN_DETAIL_LOG";
    abort "Vendor kernel ABI is not supported by this package";
  fi;
  [ -f "$AKHOME/images/$profile/Image" ] || abort "Matching kernel is unavailable";
  cp "$AKHOME/images/$profile/Image" "$AKHOME/Image" || abort "Cannot prepare matching kernel";
  printf 'selected_abi_profile=%s\n' "$profile" >> "$CHOPIN_DETAIL_LOG";
  ui_print "Kernel profile: $profile";
}
