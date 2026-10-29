"""Verify compiled exports against unmodified installed firmware module imports."""
from pathlib import Path
import json, sys

symvers,manifest_path,out=map(Path,sys.argv[1:4])
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
exports={cols[1]:int(cols[0],16) for line in symvers.read_text().splitlines()
         if len(cols:=line.split())>=3 and cols[2]=='vmlinux'}
expected={name:int(value,16) for name,value in manifest['unique_vmlinux_import_crc_expected'].items()}
missing=sorted(set(expected)-set(exports))
mismatch={name:{'module_expected':f'{crc:08x}','kernel_actual':f'{exports[name]:08x}'}
          for name,crc in expected.items() if name in exports and exports[name]!=crc}
report={'status':'FAIL' if missing or mismatch else 'PASS_ALL_FIRMWARE_KERNEL_IMPORT_CRCS',
        'firmware_scope':manifest['scope'],'modules':len(manifest['modules']),
        'unique_kernel_imports_checked':len(expected),'missing':missing,'mismatches':mismatch,
        'module_validation_disabled':False,'crc_overrides_used':False,
        'physical_load_boot_wifi_or_other_roms_tested':False}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['firmware_scope']},ensure_ascii=False))
assert not missing and not mismatch,'Compiled ABI does not match installed firmware imports'
