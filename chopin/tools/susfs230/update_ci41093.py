"""Bind this build to official CI41093; never use the runtime version spoof API."""
from pathlib import Path
import hashlib,json,re,sys
root=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
pin=json.loads((here/'ci41093-source.json').read_text())
up=here.parents[1]/'upstream-ci'
for name,h in pin['unchanged_upstream_files'].items():
 assert hashlib.sha256((up/name).read_bytes()).hexdigest()==h,name
p=root/'KernelSU/kernel/Makefile';s=p.read_text()
assert s.count('KSU_VERSION := 41085')==1 and s.count('6397fcb5@builtin+536c173c')==1
s=s.replace('KSU_VERSION := 41085','KSU_VERSION := 41093',1).replace('6397fcb5@builtin+536c173c','6397fcb5@builtin+d8fec9b6',1)
p.write_text(s,encoding='utf-8',newline='\n')
p=root/'chopin-ci-port.json';r=json.loads(p.read_text());assert r['manager_ci_commit']=='536c173c885bfc68ca33410dbc5c10f6270f4a09' and r['uapi_version']==6
r.update(manager_ci_commit=pin['main_commit'],version_code=41093,current_ci_source_verification=pin,version_spoof_default_mask=0)
p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print('Build metadata follows official CI41093; unchanged kernel sources byte-verified; UAPI6; no runtime version spoof')
