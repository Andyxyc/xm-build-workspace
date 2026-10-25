"""Verify real ARM64 KPM probe/control calls and the complete 4.14 hook window."""
from pathlib import Path
import argparse,hashlib,json,struct
p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--system-map',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
data=a.image.read_bytes();symbols={x[2]:int(x[0],16) for l in a.system_map.read_text().splitlines() if len(x:=l.split())==3};base=symbols['_text'];ordered=sorted(set(symbols.values()))
def body(name):
    start=symbols[name];end=next(x for x in ordered if x>start)
    assert 0<=start-base<end-base<=len(data),name
    return start,data[start-base:end-base]
def calls(caller,callee):
    start,b=body(caller);sites=[]
    for offset in range(0,len(b)-3,4):
        op=struct.unpack_from('<I',b,offset)[0]
        if op&0x7c000000!=0x14000000:continue
        d=op&0x3ffffff
        if d&(1<<25):d-=1<<26
        if start+offset+4*d==symbols[callee]:sites.append(hex(start+offset))
    assert sites,(caller,callee,'missing linked B/BL')
    return dict(caller=caller,callee=callee,sites=sites)
_,endpoint=body('ksu_kpm_bridge_trampoline')
assert len(endpoint)>=24 and struct.pack('<I',0xd503201f)*4 in endpoint,'Missing complete inline-hook window'
assert b'ksu_kpm_bridge_trampoline\0' in data
edges=[calls('ksu_extension_kpm_get','sukisu_kpm_bridge'),calls('do_kpm','sukisu_kpm_bridge')]
report=dict(status='PASS_REAL_KPM_PROBE_CONTROL_AND_414_ENDPOINT_LINKS',image_sha256=hashlib.sha256(data).hexdigest(),endpoint_bytes=len(endpoint),endpoint_sha256=hashlib.sha256(endpoint).hexdigest(),edges=edges,hardware_verified=False)
assert not a.report.exists();a.report.write_text(json.dumps(report,indent=2));print(json.dumps(report))
