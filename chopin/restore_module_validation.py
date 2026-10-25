#!/usr/bin/env python3
"""Restore normal caller-supplied module flags in the pinned vendor loader.

The vendor forces both IGNORE flags even for a normal finit_module(flags=0).
CONFIG_MODULE_FORCE_LOAD=n then rejects every module. Keep the standard CRC,
vermagic and force-load policy checks; remove only the forced flags.
"""
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1]).resolve()
p = root / 'kernel/module.c'
source = p.read_text()
old = '\t//FIXME\n\tflags |= MODULE_INIT_IGNORE_MODVERSIONS;\n\tflags |= MODULE_INIT_IGNORE_VERMAGIC;\n'
assert source.count(old) == 1, 'Pinned forced-flags anchor changed'
start = source.index('static int load_module(struct load_info *info,')
end = source.index('\n\terr = module_sig_check(info, flags);', start)
assert old in source[start:end]
fixed = source.replace(old, '\t/* Preserve caller flags: normal loads retain CRC/vermagic checks. */\n', 1)
assert 'flags |= MODULE_INIT_IGNORE_' not in fixed[start:fixed.index('\n\terr = module_sig_check(info, flags);', start)]
assert 'same_magic(modmagic, vermagic, info->index.vers)' in fixed
assert 'check_modstruct_version(info, mod)' in fixed
p.write_text(fixed)
report = {'status': 'RESTORED_NORMAL_MODULE_VALIDATION_SOURCE_ONLY',
          'before_sha256': hashlib.sha256(source.encode()).hexdigest(),
          'after_sha256': hashlib.sha256(fixed.encode()).hexdigest(),
          'forced_load_enabled': False, 'hardware_validation': False}
(root.parent / 'module-validation-restoration.json').write_text(json.dumps(report, indent=2))
print('Restored normal module flags; original CRC/vermagic/force-load checks remain')
