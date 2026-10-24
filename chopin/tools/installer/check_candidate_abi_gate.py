"""Read-only candidate gate tied to real Image bytes and exact vendor modules."""
from pathlib import Path
import argparse,hashlib,json,struct,sys
if not __debug__:raise SystemExit('Safety gates require normal Python mode; -O is forbidden')
p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--modules',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
ev=a.candidate/'release-evidence';images=list((a.candidate/'kernel_workspace').rglob('Image'));assert len(images)==1
image=images[0];data=image.read_bytes();assert data[56:60]==b'ARMd'
sha=lambda b:hashlib.sha256(b).hexdigest()
symvers={}
for line in (ev/'ported.Module.symvers').read_text().splitlines():
    q=line.split();assert len(q)>=4 and q[1] not in symvers
    symvers[q[1]]=dict(crc=int(q[0],16),owner=q[2],kind=q[3])
symbols={q[2]:int(q[0],16) for l in (ev/'System.map').read_text().splitlines() if len(q:=l.split())==3}
base=symbols['_text'];checked=0
for kind,suffix in [('EXPORT_SYMBOL',''),('EXPORT_SYMBOL_GPL','_gpl'),('EXPORT_SYMBOL_GPL_FUTURE','_gpl_future'),('EXPORT_UNUSED_SYMBOL','_unused'),('EXPORT_UNUSED_SYMBOL_GPL','_unused_gpl')]:
    names=sorted(n for n,v in symvers.items() if v['owner']=='vmlinux' and v['kind']==kind)
    if not names:continue
    start=symbols['__start___kcrctab'+suffix]-base;end=symbols['__stop___kcrctab'+suffix]-base
    assert end-start==4*len(names) and 0<=start<end<=len(data)
    for i,n in enumerate(names):
        assert struct.unpack_from('<I',data,start+4*i)[0]==symvers[n]['crc'],('Image CRC table disagrees with Module.symvers',n)
        checked+=1
mods={};providers={}
for file in sorted(a.modules.glob('*.ko')):
    assert not file.is_symlink();b=file.read_bytes();assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
    off=struct.unpack_from('<Q',b,40)[0];es,num,si=struct.unpack_from('<3H',b,58);assert es==64 and off+es*num<=len(b)
    hs=[struct.unpack_from('<IIQQQQIIQQ',b,off+i*es) for i in range(num)]
    ss=b[hs[si][4]:hs[si][4]+hs[si][5]]
    sections={ss[h[0]:].split(b'\0',1)[0].decode():b[h[4]:h[4]+h[5]] for h in hs if h[1]!=8}
    blob=sections['__versions'];assert blob and len(blob)%64==0
    versions={blob[i+8:i+64].split(b'\0',1)[0].decode():struct.unpack_from('<Q',blob,i)[0] for i in range(0,len(blob),64)}
    vermagic=[v.decode().removeprefix('vermagic=') for v in sections['.modinfo'].split(b'\0') if v.startswith(b'vermagic=')];assert len(vermagic)==1 and 'modversions' in vermagic[0].split()
    mods[file.name]=dict(sha256=sha(b),versions=versions,vermagic=vermagic[0])
    for h in hs:
        if h[1]!=2:continue
        strings=b[hs[h[6]][4]:hs[h[6]][4]+hs[h[6]][5]];assert h[9]==24
        for i in range(h[4],h[4]+h[5],h[9]):
            no,info,other,ndx,value,size=struct.unpack_from('<IBBHQQ',b,i)
            name=strings[no:].split(b'\0',1)[0].decode()
            if name.startswith('__crc_'):
                assert ndx==65521 and name[6:] not in providers
                providers[name[6:]]=dict(owner=file.name,crc=value)
assert len(mods)==10,'Exactly the audited ten original modules are required'
errors=[];count=0
for module,v in mods.items():
    for name,expected in v['versions'].items():
        if name in providers:
            got=providers[name]
            if name in symvers and symvers[name]['owner']=='vmlinux':errors.append(dict(module=module,symbol=name,reason='duplicate builtin provider'))
        else:got=symvers.get(name)
        if got is None:errors.append(dict(module=module,symbol=name,reason='unresolved'))
        elif got['crc']!=expected:errors.append(dict(module=module,symbol=name,reason='CRC mismatch',expected=f'{expected:08x}',actual=f'{got["crc"]:08x}'))
        count+=1
record=dict(status='PASS_VENDOR_MODULE_ABI_ONLY' if not errors else 'FAIL_DO_NOT_FLASH',
    image_sha256=sha(data),image_size=len(data),actual_image_export_crcs_checked=checked,
    system_map_sha256=sha((ev/'System.map').read_bytes()),symvers_sha256=sha((ev/'ported.Module.symvers').read_bytes()),
    modules={k:dict(sha256=v['sha256'],vermagic=v['vermagic'],required_symbols=len(v['versions'])) for k,v in mods.items()},
    imports_checked=count,errors=errors,hardware_validated=False,
    limitation='Only original module import compatibility; boot, camera, power, root, SUSFS and KPM runtime remain separate requirements')
a.output.write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k not in ['modules','system_map_sha256','symvers_sha256']},indent=2))
raise SystemExit(bool(errors))
