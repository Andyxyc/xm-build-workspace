SKIPUNZIP=1

# Magisk/KernelSU module-entry adapter. The actual operation remains the same
# guarded AnyKernel3 boot installer used by recovery and SukiSU's kernel page.
[ "$BOOTMODE" = true ] || abort "Use the AnyKernel3 recovery entry for recovery installation";
[ "$(getprop ro.product.device)" = chopin ] || abort "Device is not chopin";
[ "$(getprop ro.build.version.sdk)" = 33 ] || abort "Android 13 is required";
case "$(getprop ro.miui.ui.version.name)" in V14|14) ;; *) abort "MIUI 14 is required";; esac;
[ -n "$ZIPFILE" ] && [ -f "$ZIPFILE" ] || abort "Installation ZIP is unavailable";
[ -d "$TMPDIR" ] || abort "Installer temporary directory is unavailable";
chopin_bridge=$(mktemp -d "$TMPDIR/xiaomo-ak3.XXXXXX") || abort "Cannot create installer workspace";
unzip -p "$ZIPFILE" tools/ak3-update-binary.sh > "$chopin_bridge/backend.sh" || abort "Cannot extract AnyKernel3 backend";
unzip -p "$ZIPFILE" expected/backend.sha256 > "$chopin_bridge/backend.sha256" || abort "Backend checksum is unavailable";
chopin_bridge_expected=$(cat "$chopin_bridge/backend.sha256");
[ "$(sha256sum "$chopin_bridge/backend.sh" | cut -d' ' -f1)" = "$chopin_bridge_expected" ] || abort "Backend checksum mismatch";
case "$MODPATH" in /data/adb/modules/xiaomo_chopin_ak3|/data/adb/modules_update/xiaomo_chopin_ak3) ;; *) abort "Unexpected module receipt path";; esac;
# A tiny inert receipt satisfies the module installer; it executes no boot code.
mkdir -p "$MODPATH" || abort "Cannot save installer receipt";
unzip -p "$ZIPFILE" module.prop > "$MODPATH/module.prop" || abort "Cannot save installer receipt";
touch "$MODPATH/skip_mount" || abort "Cannot mark inert installer receipt";

if AKHOME="$chopin_bridge/runtime" /system/bin/sh "$chopin_bridge/backend.sh" 3 1 "$ZIPFILE"; then
  ui_print "Kernel installation and full partition readback completed";
else
  abort "AnyKernel3 installation failed; preserve the boot backup and installation log";
fi;
