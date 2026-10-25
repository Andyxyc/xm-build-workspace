"""Independently check every absolute kallsyms slot against the linker map.

This port has CONFIG_KALLSYMS_BASE_RELATIVE=n with ARM64 RELATIVE relocations.
The postprocessor's relative-offset probe warning must not hide a partial or
incorrect fallback. This validates link-time addresses, not KASLR at runtime.
"""
from pathlib import Path
import collections,hashlib,re,struct
if not __debug__:raise SystemExit('Resolver checks require normal Python mode')

def verify(image,system_map,log):
    lookup=collections.defaultdict(set)
    for line in system_map.splitlines():
        addr,kind,name=line.split();lookup[name].add(int(addr,16))
    assert len(lookup['_text'])==1
    base=next(iter(lookup['_text']))
    def offset(name):
        assert len(lookup[name])==1,('Ambiguous linker symbol',name)
        out=next(iter(lookup[name]))-base
        assert 0<=out<len(image)
        return out
    addresses=offset('kallsyms_addresses');number=offset('kallsyms_num_syms');names=offset('kallsyms_names')
    table=offset('kallsyms_token_table');index=offset('kallsyms_token_index')
    count=struct.unpack_from('<Q',image,number)[0]
    assert 100000<=count<=1000000 and addresses+count*8<=len(image)
    matches=re.findall(r'arm64 relocation table range: \[0x([0-9a-f]+), 0x([0-9a-f]+)\)',log)
    assert len(matches)==1
    rs,relo_end=(int(x,16) for x in matches[0]);assert 0<=rs<relo_end<=len(image) and (relo_end-rs)%24==0
    reloc={}
    for addr,kind,addend in struct.iter_unpack('<QQQ',image[rs:relo_end]):
        if base+addresses<=addr<base+addresses+count*8:
            assert kind==0x403 and addr not in reloc and (addr-base-addresses)%8==0
            reloc[addr]=addend
    assert len(reloc)==count,'Every absolute table slot must have an independently identified relocation'
    tokens=[]
    for t in struct.unpack_from('<256H',image,index):
        end=image.index(b'\0',table+t);assert end-table<65536
        tokens.append(image[table+t:end].decode('ascii'))
    pos=names
    for i in range(count):
        length=image[pos];pos+=1
        assert length and pos+length<=len(image)
        text=''.join(tokens[t] for t in image[pos:pos+length]);pos+=length
        assert text and text[0].isalpha()
        raw=struct.unpack_from('<Q',image,addresses+8*i)[0]
        assert raw==0,'This verified port expects link-time absolute addresses supplied by RELATIVE relocations'
        value=reloc[base+addresses+8*i]
        assert value in lookup[text[1:]],(i,text,'Resolved address differs from independently built System.map')
    assert pos<=offset('kallsyms_markers')
    return dict(status='PASS_ALL_LINK_TIME_KALLSYMS_AGAINST_SYSTEM_MAP',symbols_checked=count,relative_relocations_checked=len(reloc),before_sha256=hashlib.sha256(image).hexdigest(),system_map_sha256=hashlib.sha256(system_map.encode()).hexdigest(),limitation='Link-time resolver check only; real boot, KASLR and KPM operation remain unverified')
