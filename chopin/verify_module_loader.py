#!/usr/bin/env python3
"""Check linked validation and normal module-init code, without loading a module."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--image', type=Path, required=True)
p.add_argument('--system-map', type=Path, required=True)
p.add_argument('--config', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
image = a.image.read_bytes()
config = a.config.read_text()
for flag in ['MODULES', 'MODULE_UNLOAD', 'MODVERSIONS']:
    assert '\nCONFIG_' + flag + '=y\n' in config, flag
assert '\n# CONFIG_MODULE_FORCE_LOAD is not set\n' in config
assert b'SMP preempt mod_unload modversions aarch64' in image, 'Linked module vermagic unavailable'
assert b"version magic '%s' should be '%s'" in image, 'Vermagic validation path was eliminated'
symbols = {v[2]: int(v[0], 16) for line in a.system_map.read_text().splitlines()
           if len(v := line.split()) == 3}
start, target, base = symbols['load_module'], symbols['do_init_module'], symbols['_text']
end = min(v for v in symbols.values() if v > start)
assert 0 <= start-base < end-base <= len(image)
calls = []
for pc in range(start, end, 4):
    op, = struct.unpack_from('<I', image, pc-base)
    if op & 0x7c000000 != 0x14000000:
        continue
    delta = op & 0x03ffffff
    if delta & 0x02000000:
        delta -= 0x04000000
    if pc + delta*4 == target:
        calls.append(hex(pc))
assert calls, 'Linked module-init success path is missing'
report = {'status': 'PASS_LINKED_MODULE_VALIDATION_AND_INIT_PATH_ONLY',
          'image_sha256': hashlib.sha256(image).hexdigest(),
          'module_init_call_sites': calls, 'forced_load_enabled': False,
          'hardware_module_loading': 'NOT_TESTED'}
a.report.write_text(json.dumps(report, indent=2))
print(report['status'])
