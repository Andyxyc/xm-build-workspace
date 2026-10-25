"""Use source-built kptools with an explicit pinned payload; never patch in place."""
from pathlib import Path
import argparse,hashlib,json,re,secrets,subprocess
from verify_image_entry import inspect,inspect_kpm
from verify_kpm_resolver import verify as verify_resolver
if not __debug__:raise SystemExit('Normal Python mode is required')
p=argparse.ArgumentParser();p.add_argument('--tool',type=Path,required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--kpimg',type=Path,required=True);p.add_argument('--system-map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--log',type=Path,required=True);a=p.parse_args()
assert not a.output.exists() and not a.report.exists() and not a.log.exists(),'Preserve earlier results'
before=a.before.read_bytes();kp=a.kpimg.read_bytes();inspect(before)
assert hashlib.sha256(kp).hexdigest()=='1d9a0d6772b14197313b4184e290ea7f627a340349430f58efe7600609cde7a4'
assert kp[:8]==b'KP1158\0\0' and kp[8:12]==bytes.fromhex('00090d00') and len(kp)==294144
# An unretained random root key is hashed in the payload. Never store a direct
# superkey or print it in argv/logs. SukiSU's authorized KPM API is independent.
key=(secrets.token_hex(24)+'\n').encode()
assert 0<len(key.strip())<64,'Pinned tool reserves one byte for the key terminator'
q=subprocess.run([str(a.tool.resolve()),'-p','-i',str(a.before.resolve()),'-k',str(a.kpimg.resolve()),'-o',str(a.output.resolve()),'--root-skey-fd','0'],input=key,capture_output=True,timeout=120)
log=q.stdout.decode('utf-8','replace')+q.stderr.decode('utf-8','replace')
assert key.strip().decode() not in log,'Root key leaked by tool'
a.log.write_text(log,encoding='utf-8');print(log)
assert q.returncode==0,'KPM postprocessor failed'
image=a.output.read_bytes();report=inspect_kpm(image,before,kp)
report['full_kallsyms_validation']=verify_resolver(before,a.system_map.read_text(),log)
symbols={s[2]:int(s[0],16) for line in a.system_map.read_text().splitlines() if len(s:=line.split())==3}
base=re.findall(r'kernel base address: 0x([0-9a-f]+)',log);assert len(base)==1
base=int(base[0],16);checked=[]
for name,offset in re.findall(r'^\[\+\] (\w+): type: \w, offset: 0x([0-9a-f]+)',log,re.M):
    assert name in symbols and symbols[name]-base==int(offset,16),(name,'KPM symbol offset differs from independently built System.map')
    checked.append(name)
assert len(set(checked))>=10,'Too few independently resolved KPM anchors'
report.update(symbols_checked=sorted(set(checked)),resolver_warnings=[l for l in log.splitlines() if l.startswith('[?]')],kptools_sha256=hashlib.sha256(a.tool.read_bytes()).hexdigest(),key_policy='unretained random hash-verification root key; SukiSU KPM API remains subject to real-device tests')
a.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
