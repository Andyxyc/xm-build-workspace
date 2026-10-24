#!/usr/bin/env python3
"""Restore real stock options where the locked source actually implements them."""
from pathlib import Path
import json,re,sys

root=Path(sys.argv[1]).resolve()
profile=json.loads((Path(__file__).parent/'stock-profile.json').read_text())
declared=set()
for p in root.rglob('*Kconfig*'):
    if p.is_file():
        text=p.read_text(errors='replace')
        declared.update(re.findall(r'^\s*(?:menuconfig|config)\s+(\w+)',text,re.M))
assert (root/'drivers/misc/mediatek/gpu/gpu_mali/mali_valhall/mali-r32p1').is_dir()
config=root/'arch/arm64/configs/chopin_user_defconfig'
lines=config.read_text().splitlines()
missing=[]
for key,value in profile.items():
    if key.removeprefix('CONFIG_') not in declared:
        missing.append(key)
        continue
    replacement=f'# {key} is not set' if value=='n' else f'{key}={value}'
    indices=[i for i,l in enumerate(lines) if l.startswith(key+'=') or l==f'# {key} is not set']
    assert len(indices)<=1,(key,indices)
    if indices:
        lines[indices[0]]=replacement
    else:
        lines.append(replacement)
config.write_text('\n'.join(lines)+'\n')
evidence={'applied':{k:v for k,v in profile.items() if k not in missing},
          'not_implemented_in_pinned_source':missing,
          'stock_gpu':'mali valhall r32p1',
          'status':'Source profile alignment only; no driver or ABI acceptance implied'}
(root.parent/'stock-profile-application.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence,indent=2))
