SKIPUNZIP=1
[ "$BOOTMODE" = true ] || abort "Use the recovery ZIP entry";
[ -f "$ZIPFILE" ] && [ -d "$TMPDIR" ] || abort "Installation ZIP is unavailable";
chopin_bridge=$(mktemp -d "$TMPDIR/chopin-ak3.XXXXXXXX") || abort "Cannot create installer workspace";
unzip -p "$ZIPFILE" tools/ak3-update-binary.sh > "$chopin_bridge/backend.sh" || abort "Cannot extract AnyKernel3";
mkdir -p "$MODPATH" || abort "Cannot save installer receipt";
unzip -p "$ZIPFILE" module.prop > "$MODPATH/module.prop" || abort "Cannot save installer receipt";
touch "$MODPATH/skip_mount";
if CHOPIN_UI_STDOUT=1 AKHOME="$chopin_bridge/runtime" /system/bin/sh "$chopin_bridge/backend.sh" 3 1 "$ZIPFILE"; then
  ui_print "Kernel installed.";
else
  abort "Kernel installation failed; keep the backup and installation log";
fi;
