"""Small source-checked updater output adapter for booted manager sockets."""
OLD_UI = b'''ui_print() {
  until [ ! "$1" ]; do
    echo "ui_print $1
      ui_print" >> /proc/self/fd/$OUTFD;
    shift;
  done;
}'''
NEW_UI = b'''ui_print() {
  until [ ! "$1" ]; do
    if [ "$CHOPIN_UI_STDOUT" = 1 ] && [ -z "${POSTINSTALL:-}" ]; then
      printf '%s\\n' "$1";
    else
      printf 'ui_print %s\\n      ui_print\\n' "$1" >&$OUTFD;
    fi;
    shift;
  done;
}'''
BOOT_ANCHOR=b'\nDIR=/sdcard;'
BOOT_ADAPTER=b'\nexport CHOPIN_UI_STDOUT=${CHOPIN_UI_STDOUT:-0};\ncase "$OUTFD" in ""|*[!0-9]*) echo "Invalid updater output descriptor" >&2; exit 1;; esac;\n'
OLD_PROGRESS=b'show_progress() { echo "progress $1 $2" >> /proc/self/fd/$OUTFD; }'
NEW_PROGRESS=b'show_progress() { [ "$CHOPIN_UI_STDOUT" = 1 ] || [ -n "${POSTINSTALL:-}" ] || printf "progress %s %s\\n" "$1" "$2" >&$OUTFD; }'
OLD_UNZIP=b'unzip -o "$ZIPFILE";'
NEW_UNZIP=b'unzip -qo "$ZIPFILE";'
def output_adapter(core,backend):
    assert backend.count(OLD_UNZIP)==1
    assert core.count(OLD_UI)==1 and backend.count(OLD_UI)==1
    assert backend.count(BOOT_ANCHOR)==1 and backend.count(OLD_PROGRESS)==1
    return (core.replace(OLD_UI,NEW_UI,1),backend.replace(OLD_UI,NEW_UI,1)
            .replace(BOOT_ANCHOR,BOOT_ADAPTER+BOOT_ANCHOR,1)
            .replace(OLD_PROGRESS,NEW_PROGRESS,1).replace(OLD_UNZIP,NEW_UNZIP,1))
