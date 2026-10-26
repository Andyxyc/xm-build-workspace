"""CI41095 compatibility with the actually boot-tested ABI1 KPM runtime.

The official ksud load_module_at_event falls back ONLY on EOPNOTSUPP.
An unknown op used to return EINVAL, preventing boot-stage KPM loading.
Do not switch the bridge ABI without rebuilding and testing its paired runtime.
"""
from pathlib import Path
import hashlib,json,sys
root=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
pin=json.loads((here/'ci41095-source.json').read_text());up=here.parents[1]/'upstream-ci'
for name,h in pin['upstream_files'].items():
 assert hashlib.sha256((up/name).read_bytes()).hexdigest()==h,name
p=root/'KernelSU/kernel/Makefile';s=p.read_text()
assert s.count('KSU_VERSION := 41085')==1 and s.count('6397fcb5@builtin+536c173c')==1
s=s.replace('KSU_VERSION := 41085','KSU_VERSION := 41095',1).replace('6397fcb5@builtin+536c173c','6397fcb5@builtin+96ceb4a4',1)
p.write_text(s,encoding='utf-8',newline='\n')
p=root/'KernelSU/kernel/extension/kpm/kpm.c';s=p.read_text()
needle='    if (cmd->control_code == SUKISU_KPM_NUM)'
assert s.count(needle)==1 and 'SUKISU_KPM_LOAD_EVENT' not in s
s=s.replace(needle,'    /* Optional ABI2 operation: official ksud falls back to LOAD on -95. */\n'
 '    if (cmd->control_code == SUKISU_KPM_LOAD_EVENT)\n'
 '        return -EOPNOTSUPP;\n\n'+needle,1)
p.write_text(s,encoding='utf-8',newline='\n')
assert '#define SUKISU_KPM_ABI_VERSION 1' in (p.parent/'bridge.h').read_text()
p=root/'chopin-ci-port.json';r=json.loads(p.read_text());assert r['version_code']==41085 and r['uapi_version']==6
r.update(manager_ci_commit=pin['main_commit'],version_code=41095,current_ci_source_verification=pin,version_spoof_default_mask=0)
p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8',newline='\n')
print('CI41095 compiled metadata; real -EOPNOTSUPP event fallback; tested KPM ABI1 retained; UAPI6')
