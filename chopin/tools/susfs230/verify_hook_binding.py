"""Bind the real 4.14 LSM hook-table relocation to its native credential hook."""
from pathlib import Path
import argparse,hashlib,json,re,struct
p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--system-map',type=Path,required=True);p.add_argument('--log',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
data=a.image.read_bytes();syms={x[2]:int(x[0],16) for l in a.system_map.read_text().splitlines() if len(x:=l.split())==3}
base=syms['_text'];start=syms['ksu_hooks'];end=next(x for x in sorted(set(syms.values())) if x>start)
ranges=re.findall(r'arm64 relocation table range: \[0x([0-9a-f]+), 0x([0-9a-f]+)\)',a.log.read_text())
assert len(ranges)==1;r0,r1=(int(x,16) for x in ranges[0]);assert 0<=r0<r1<=len(data) and (r1-r0)%24==0
target=syms['chopin_native_task_fix_setuid'];hits=[]
for address,kind,addend in struct.iter_unpack('<QQQ',data[r0:r1]):
    if start<=address<end and addend==target:
        assert kind==0x403 and struct.unpack_from('<Q',data,address-base)[0]==0
        hits.append(hex(address))
assert len(hits)==1,('native credential callback not bound to the actual LSM table',hits)
report={'status':'PASS_REAL_NATIVE_LSM_HOOK_TABLE_RELOCATION','image_sha256':hashlib.sha256(data).hexdigest(),'hook_pointer_sites':hits,'callback':hex(target),'hardware_tested':False}
assert not a.report.exists();a.report.write_text(json.dumps(report,indent=2));print(json.dumps(report))
