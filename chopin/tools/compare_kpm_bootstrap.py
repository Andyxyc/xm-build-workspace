"""Inspect the source-built KP map code and compare with the booted reference."""
from pathlib import Path
import argparse,hashlib,json,struct
p=argparse.ArgumentParser();p.add_argument('--elf',type=Path,required=True);p.add_argument('--payload',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
b=a.elf.read_bytes();assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
off=struct.unpack_from('<Q',b,40)[0];es,num=struct.unpack_from('<HH',b,58);hs=[struct.unpack_from('<IIQQQQIIQQ',b,off+i*es) for i in range(num)]
symbols={}
for h in hs:
    if h[1]!=2:continue
    strings=b[hs[h[6]][4]:hs[h[6]][4]+hs[h[6]][5]]
    for i in range(h[4],h[4]+h[5],24):
        n,info,other,section,va,size=struct.unpack_from('<IBBHQQ',b,i);name=strings[n:].split(b'\0',1)[0].decode();symbols[name]=(va,size,info&15)
payload=a.payload.read_bytes();reference=a.reference.read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest()
base=symbols['_link_base'][0];start,end=symbols['_map_start'][0],symbols['_map_end'][0]
assert 0<start-base<end-base<=len(payload) and end-start<4096
assert payload[:8]==reference[:8]==b'KP1158\0\0'
external=[]
for name,(va,size,kind) in symbols.items():
    if kind!=2 or not size or not start<=va<end:continue
    assert va+size<=end
    for pc in range(va,va+size,4):
        op=struct.unpack_from('<I',payload,pc-base)[0]
        if op&0x7c000000!=0x14000000:continue
        delta=op&0x3ffffff
        if delta&(1<<25):delta-=1<<26
        target=pc+4*delta
        if not start<=target<end:external.append({'caller':name,'pc':hex(pc),'target':hex(target)})
assert not external,external
current=payload[start-base:end-base];prior=reference[start-base:end-base]
record={'status':'PASS_SELF_CONTAINED_MAP_CODE_ONLY','payload_sha256':sha(payload),'reference_sha256':sha(reference),'map_start':hex(start),'map_end':hex(end),'map_bytes':len(current),'map_sha256':sha(current),'reference_same_range_sha256':sha(prior),'map_bytes_equal_reference':current==prior,'changed_bytes':sum(x!=y for x,y in zip(current,prior)),'external_direct_branches':external,'hardware_boot_tested':False}
assert not a.report.exists();a.report.write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
