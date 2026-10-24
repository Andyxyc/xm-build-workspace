#!/usr/bin/env python3
"""Use the ROM's external connectivity modules rather than duplicate builtins."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
f=root/'drivers/misc/mediatek/connectivity/Makefile'
s=f.read_text()
old='    export CONFIG_WLAN_DRV_BUILD_IN=y'
assert s.count(old)==1, 'Audited vendor connectivity Makefile changed'
s=s.replace(old, '    # chopin MIUI 14 supplies these as /vendor/lib/modules/*.ko.\n    export CONFIG_WLAN_DRV_BUILD_IN=n',1)
f.write_text(s)
print('Retained built-in connectivity adapters; use existing vendor WLAN/BT/FM/GPS modules')
