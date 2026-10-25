# Exact stock ramdisk selection for the slim package; never accepts a second
# root backend's modified ramdisk. The full ZIP provides a verified fallback.
chopin_stock_ramdisk() {
  local expected cache actual;
  expected=58e70342f8d631f26c95546f787933b744f8fbb67412ca22be561c0a30b42095;
  cache="$backup_dir/stock-ramdisk-${expected}.cpio.gz";
  actual=$(sha256sum "$SPLITIMG/ramdisk.cpio" | cut -d' ' -f1);
  if [ "$actual" != "$expected" ]; then
    if [ -f "$AKHOME/stock-ramdisk.cpio.gz" ]; then
      gzip -dc "$AKHOME/stock-ramdisk.cpio.gz" > "$SPLITIMG/ramdisk.cpio" || abort "Stock ramdisk decompression failed";
    elif [ -f "$cache" ] && [ ! -L "$cache" ]; then
      gzip -dc "$cache" > "$SPLITIMG/ramdisk.cpio" || abort "Cached stock ramdisk decompression failed";
    else
      abort "Current ramdisk is not stock; use the full XiaoMo AK3 fallback ZIP";
    fi;
  fi;
  [ "$(sha256sum "$SPLITIMG/ramdisk.cpio" | cut -d' ' -f1)" = "$expected" ] || abort "Stock ramdisk mismatch";
  # Cache only bytes already proven to be the exact original. Never overwrite
  # an existing cache until its decompressed digest has been checked.
  if [ -f "$cache" ]; then
    [ ! -L "$cache" ] && [ "$(gzip -dc "$cache" | sha256sum | cut -d' ' -f1)" = "$expected" ] || abort "Existing stock ramdisk cache is invalid";
  else
    (set -C; gzip -c "$SPLITIMG/ramdisk.cpio" > "$cache.tmp") || abort "Cannot cache verified stock ramdisk";
    [ "$(gzip -dc "$cache.tmp" | sha256sum | cut -d' ' -f1)" = "$expected" ] || abort "Stock ramdisk cache readback failed";
    mv "$cache.tmp" "$cache" || abort "Cannot retain verified stock ramdisk cache";
  fi;
}
