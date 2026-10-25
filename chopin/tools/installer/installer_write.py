"""A byte-checked replacement for AnyKernel3's generic block write branch."""
ORIGINAL_WRITE = b'''  blockdev --setrw $BLOCK 2>/dev/null;
  if [ -f "$BIN/flash_erase" -a -f "$BIN/nandwrite" ]; then
    flash_erase $BLOCK 0 0;
    nandwrite -p $BLOCK boot-new.img;
  elif [ "$CUSTOMDD" ]; then
    dd if=/dev/zero of=$BLOCK $CUSTOMDD 2>/dev/null;
    dd if=boot-new.img of=$BLOCK $CUSTOMDD;
  else
    cat boot-new.img /dev/zero > $BLOCK 2>/dev/null || true;
  fi;
  if [ $? != 0 ]; then
    abort "Flashing image failed. Aborting...";
  fi;'''
GUARDED_WRITE_CALL = b'''  chopin_write_boot || abort "Boot write or flush failed; keep the backup and use the verified Fastboot path";'''
def guarded_writer(core):
    assert core.count(ORIGINAL_WRITE)==1
    return core.replace(ORIGINAL_WRITE,GUARDED_WRITE_CALL,1)
