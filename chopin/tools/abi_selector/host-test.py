"""Exercise the real compiled selector using only generated ELF64 file fixtures.

This script does not compile anything. Run it in disposable Linux CI against
the provided host or static AArch64 binary. No real module/device is required.
"""
from pathlib import Path
import argparse,hashlib,json,os,struct,subprocess,tempfile

LEGACY={'cpu_hwcaps':0xbe9f1a32,'cpu_hwcap_keys':0x77af701b,'remap_pfn_range':0xf79cd398,'find_vma':0x30e3495c}
T={'cpu_hwcaps':0xf2352f28,'cpu_hwcap_keys':0x37c71621,'remap_pfn_range':0x5cf0b028,'find_vma':0x40a015a7}
# Observed in all ten modules of MIUI14.0.6.0.TKPCNXM, pinned dump commit
# 9714227175010692d8374082ae98075abf18107c. These are CRC constants only;
# fixtures remain generated ELF files, never copies of vendor module bytes.
EARLY={'cpu_hwcaps':T['cpu_hwcaps'],'cpu_hwcap_keys':T['cpu_hwcap_keys'],'remap_pfn_range':LEGACY['remap_pfn_range'],'find_vma':LEGACY['find_vma']}
def record(name,crc):
    name=name.encode() if isinstance(name,str) else name
    assert len(name)<56
    return struct.pack('<Q',crc)+name+b'\0'+bytes(55-len(name))
def records(values):
    return b''.join(record(name,crc) for name,crc in values.items())
def elf(raw,*,data_offset=256,extra_gap=19,versions_name='__versions',duplicate=False,versions_type=1,versions_entsize=0,noise=b''):
    """A real ELF64 section table, without executing or linking this module."""
    names=b'\0.shstrtab\0'+versions_name.encode()+b'\0.noise\0'
    name_index=names.index(versions_name.encode()+b'\0')
    strtab_offset=data_offset+len(raw)+extra_gap
    noise_offset=strtab_offset+len(names)+7
    shoff=(noise_offset+len(noise)+15)//8*8
    count=5 if duplicate else 4
    result=bytearray(shoff+count*64)
    ident=b'\x7fELF'+bytes([2,1,1,0])+bytes(8)
    header=struct.pack('<16sHHIQQQIHHHHHH',ident,1,183,1,0,0,shoff,0,64,0,0,64,count,1)
    result[:64]=header
    result[data_offset:data_offset+len(raw)]=raw
    result[strtab_offset:strtab_offset+len(names)]=names
    result[noise_offset:noise_offset+len(noise)]=noise
    def section(index,name,kind,offset,size,entsize=0,align=1):
        struct.pack_into('<IIQQQQIIQQ',result,shoff+index*64,name,kind,0,0,offset,size,0,0,align,entsize)
    section(1,1,3,strtab_offset,len(names))
    section(2,name_index,versions_type,data_offset,len(raw),versions_entsize)
    section(3,names.index(b'.noise\0'),1,noise_offset,len(noise))
    if duplicate:section(4,name_index,1,data_offset,len(raw))
    return result
def replace(blob,offset,fmt,value):
    blob=bytearray(blob);struct.pack_into(fmt,blob,offset,value);return blob

p=argparse.ArgumentParser()
p.add_argument('--binary',type=Path,required=True)
p.add_argument('--runner',action='append',default=[],help='Executable prefix, e.g. --runner qemu-aarch64')
p.add_argument('--report',type=Path,required=True)
a=p.parse_args()
assert os.name=='posix','Disposable Linux CI only; no local Windows compilation or execution'
binary=a.binary.resolve();assert binary.is_file()
prefix=[*a.runner,str(binary)]
cases=[]
with tempfile.TemporaryDirectory(prefix='chopin-abi-selector-') as tmp:
    root=Path(tmp);fixtures={}
    def add(name,data):
        path=root/(name+'.ko');path.write_bytes(data);fixtures[name]=path;return path
    def test(name,inputs,code,stdout=''):
        q=subprocess.run(prefix+[str(x) for x in inputs],capture_output=True,timeout=5)
        assert q.returncode==code,(name,q.returncode,q.stdout,q.stderr)
        assert q.stdout.decode()==stdout,(name,q.stdout,q.stderr)
        if code:assert q.stderr.startswith(b'ABI selection:'),(name,q.stderr)
        cases.append({'case':name,'exit':code,'stdout':stdout.strip(),'stderr':q.stderr.decode().strip()})
    base=elf(records(LEGACY))
    legacy=add('legacy',base);modern=add('t',elf(records(T)))
    test('legacy-all-four', [legacy],0,'legacy\n')
    test('t-all-four', [modern],0,'t\n')
    test('legacy-three-required', [add('legacy-three',elf(records({k:v for k,v in LEGACY.items() if k!='find_vma'})))],0,'legacy\n')
    test('t-three-required', [add('t-three',elf(records({k:v for k,v in T.items() if k!='find_vma'})))],0,'t\n')
    test('shifted-section-offsets', [add('shifted',elf(records(T),data_offset=4103,extra_gap=137))],0,'t\n')
    test('one-byte-section-alignment', [add('unaligned',elf(records(LEGACY),data_offset=127,extra_gap=3))],0,'legacy\n')
    test('record-entsize64', [add('record-size',elf(records(T),versions_entsize=64))],0,'t\n')
    test('space-in-module-filename', [add('vendor module with spaces',elf(records(T)))],0,'t\n')
    split1=add('split-cpu',elf(records({k:LEGACY[k] for k in ['cpu_hwcaps','cpu_hwcap_keys']})))
    split2=add('split-memory',elf(records({'remap_pfn_range':LEGACY['remap_pfn_range']})))
    test('anchors-across-files', [split1,split2],0,'legacy\n')
    peer=add('peer',elf(records({'conninfra_sub_drv_ops_register':T['cpu_hwcaps'],'unrelated_peer':T['remap_pfn_range']})))
    test('peer-crc-values-are-not-anchors', [legacy,peer],0,'legacy\n')
    test('peer-only-incomplete', [peer],8)
    decoy=add('decoy-in-nonversion-section',elf(records(LEGACY),noise=records(T)))
    test('ignore-raw-decoy-records', [decoy],0,'legacy\n')
    repeated=add('repeated-same-anchor',elf(records(LEGACY)+record('cpu_hwcaps',LEGACY['cpu_hwcaps'])))
    test('repeated-consistent-anchor', [repeated],0,'legacy\n')
    test('mixed-across-modules', [legacy,modern],7)
    mixed=dict(LEGACY);mixed['cpu_hwcap_keys']=T['cpu_hwcap_keys']
    test('mixed-within-module', [add('mixed',elf(records(mixed)))],7)
    mixed=dict(LEGACY);mixed['find_vma']=T['find_vma']
    test('optional-find-vma-conflict', [add('mixed-find',elf(records(mixed)))],7)
    unknown=dict(LEGACY);unknown['cpu_hwcaps']=0x12345678
    test('unknown-anchor-crc', [add('unknown',elf(records(unknown)))],6)
    unknown=dict(LEGACY);unknown['find_vma']=0x12345678
    test('unknown-optional-find-vma-crc', [add('unknown-find',elf(records(unknown)))],6)
    test('missing-required-remap', [split1],8)
    test('missing-required-cpu', [split2],8)
    test('no-module-arguments', [],2)
    test('too-many-module-arguments', [legacy]*33,2)
    test('missing-file', [root/'absent.ko'],3)
    test('directory-input', [root],3)
    test('special-character-device-rejected-before-read', [Path('/dev/null')],3)
    fifo=root/'not-a-module-fifo';os.mkfifo(fifo)
    test('fifo-does-not-block', [fifo],3)
    link=root/'regular-symlink.ko';link.symlink_to(legacy)
    test('regular-module-symlink', [link],0,'legacy\n')
    test('short-file', [add('short',b'\x7fELF')],3)
    sparse=root/'oversize.ko'
    with sparse.open('wb') as f:f.truncate(64*1024*1024+1)
    test('bounded-file-size', [sparse],3)
    invalid=bytearray(base);invalid[:4]=b'NOPE'
    test('invalid-elf-magic', [add('badmagic',invalid)],4)
    invalid=bytearray(base);invalid[4]=1
    test('wrong-elf-class', [add('elf32',invalid)],4)
    invalid=bytearray(base);invalid[5]=2
    test('wrong-endianness', [add('bigendian',invalid)],4)
    test('wrong-machine', [add('x86',replace(base,18,'<H',62))],4)
    test('wrong-elf-type', [add('executable',replace(base,16,'<H',2))],4)
    test('wrong-elf-version', [add('badversion',replace(base,20,'<I',0))],4)
    test('bad-header-size', [add('bad-ehsize',replace(base,52,'<H',63))],4)
    test('bad-section-header-size', [add('bad-shentsize',replace(base,58,'<H',63))],4)
    test('section-table-overflow', [add('bad-shoff',replace(base,40,'<Q',0xfffffffffffffff0))],4)
    test('section-table-truncated', [add('truncated-table',base[:-1])],4)
    test('extended-count-not-guessed', [add('zero-shnum',replace(base,60,'<H',0))],4)
    test('bad-string-table-index', [add('bad-shstr',replace(base,62,'<H',65535))],4)
    shoff=struct.unpack_from('<Q',base,40)[0]
    test('bad-string-table-kind', [add('bad-str-kind',replace(base,shoff+64+4,'<I',1))],4)
    test('bad-string-table-span', [add('bad-str-size',replace(base,shoff+64+32,'<Q',0xffffffffffffffff))],4)
    test('bad-section-name-index', [add('bad-name-index',replace(base,shoff+128,'<I',0xffffffff))],4)
    invalid=bytearray(base);str_off,str_len=struct.unpack_from('<QQ',base,shoff+64+24);invalid[str_off+str_len-1]=ord('x')
    test('unterminated-section-name', [add('unterminated-section',invalid)],4)
    test('section-payload-overflow', [add('bad-data-span',replace(base,shoff+128+32,'<Q',0xffffffffffffffff))],4)
    test('missing-versions-section', [add('not-versions',elf(records(LEGACY),versions_name='versions_else'))],5)
    test('prefix-name-not-versions', [add('prefix-name',elf(records(LEGACY),versions_name='__versions_extra'))],5)
    test('duplicate-versions-section', [add('duplicate-version',elf(records(LEGACY),duplicate=True))],5)
    test('versions-not-progbits', [add('nobits-version',elf(records(LEGACY),versions_type=8))],5)
    test('bad-version-record-entsize', [add('entsize8',elf(records(LEGACY),versions_entsize=8))],5)
    test('short-version-record', [add('short-record',elf(records(LEGACY)[:-1]))],5)
    test('empty-versions', [add('empty',elf(b''))],5)
    test('overlong-versions', [add('too-many-records',elf(record('peer',1)*(1024*1024//64+1)))],5)
    test('record-name-without-nul', [add('nonul',elf(struct.pack('<Q',1)+b'X'*56))],5)
    test('empty-record-name', [add('empty-name',elf(struct.pack('<Q',1)+bytes(56)))],5)
    test('invalid-record-name', [add('bad-symbol',elf(record('bad symbol',1)))],5)
    test('crc-high-bits-nonzero', [add('wide-crc',elf(record('cpu_hwcaps',0x100000000+LEGACY['cpu_hwcaps'])))],5)
    long_peer=record('a'*55,1)
    test('maximum-valid-symbol-name', [add('long-peer',elf(records(LEGACY)+long_peer))],0,'legacy\n')
    test('trailing-invalid-input-does-not-print-success', [legacy,root/'absent.ko'],3)
    # Keep the previous 60 real-C file cases above unchanged. New cases below
    # cover the independently observed third combination and its boundaries.
    early=add('early-miui14-0-6',elf(records(EARLY)))
    test('early-miui14-0-6-real-four-anchors', [early],0,'early\n')
    test('early-three-required', [add('early-three',elf(records({k:v for k,v in EARLY.items() if k!='find_vma'})))],0,'early\n')
    test('early-shifted-sections', [add('early-shifted',elf(records(EARLY),data_offset=8195,extra_gap=271))],0,'early\n')
    early_cpu=add('early-cpu-only',elf(records({k:EARLY[k] for k in ['cpu_hwcaps','cpu_hwcap_keys']})))
    early_mm=add('early-mm-only',elf(records({k:EARLY[k] for k in ['remap_pfn_range','find_vma']})))
    test('early-anchors-across-files', [early_cpu,early_mm],0,'early\n')
    test('early-memory-first-across-files', [early_mm,early_cpu],0,'early\n')
    test('early-peer-does-not-select-family', [early,peer],0,'early\n')
    test('early-repeated-consistent-anchor', [early,early_cpu],0,'early\n')
    test('early-raw-decoy-records-ignored', [add('early-decoy',elf(records(EARLY),noise=records(T)))],0,'early\n')
    test('early-record-entsize64', [add('early-record-size',elf(records(EARLY),versions_entsize=64))],0,'early\n')
    unsupported={k:(T[k] if k in ['remap_pfn_range','find_vma'] else LEGACY[k]) for k in LEGACY}
    test('unobserved-old-cpu-new-mm-rejected', [add('unsupported-combination',elf(records(unsupported)))],7)
    test('unobserved-combination-without-optional-find-rejected', [add('unsupported-three',elf(records({k:v for k,v in unsupported.items() if k!='find_vma'})))],7)
    conflict=dict(EARLY);conflict['cpu_hwcaps']=LEGACY['cpu_hwcaps']
    test('early-cpu-pair-conflict', [add('early-bad-cpu-pair',elf(records(conflict)))],7)
    conflict=dict(EARLY);conflict['find_vma']=T['find_vma']
    test('early-mm-pair-conflict', [add('early-bad-mm-pair',elf(records(conflict)))],7)
    conflict=dict(EARLY);conflict['remap_pfn_range']=T['remap_pfn_range']
    test('t-remap-old-find-conflict', [add('early-bad-remap',elf(records(conflict)))],7)
    test('same-cpu-symbol-conflict-across-files', [early,add('legacy-one-cpu',elf(records({'cpu_hwcaps':LEGACY['cpu_hwcaps']})))],7)
    test('same-mm-symbol-conflict-across-files', [early,add('t-one-mm',elf(records({'remap_pfn_range':T['remap_pfn_range']})))],7)
    test('same-cpu-symbol-conflict-within-file', [add('cpu-duplicate-conflict',elf(records(EARLY)+record('cpu_hwcaps',LEGACY['cpu_hwcaps'])))],7)
    test('same-mm-symbol-conflict-within-file', [add('mm-duplicate-conflict',elf(records(EARLY)+record('remap_pfn_range',T['remap_pfn_range'])))],7)
    test('early-t-same-cpu-different-mm-rejected', [early,modern],7)
    test('early-legacy-same-mm-different-cpu-rejected', [early,legacy],7)
    test('early-missing-remap', [early_cpu],8)
    test('early-missing-cpu-pair', [early_mm],8)
    test('early-followed-by-malformed-still-rejected', [early,add('early-bad-elf',b'NOPE'+bytes(128))],4)
    test('early-followed-by-unknown-still-rejected', [early,add('early-unknown-mm',elf(records({'remap_pfn_range':0x12345678})))],6)
    test('early-followed-by-missing-file-no-success-output', [early,root/'absent.ko'],3)
    assert all(not path.is_block_device() for path in root.iterdir())
assert len(cases)==85,'Keep the original 60 cases plus the 25 third-family cases'
report={'status':'PASS_REAL_COMPILED_SELECTOR_SYNTHETIC_ELF_FILE_CASES_ONLY','cases':cases,'case_count':len(cases),'legacy_case_count':60,'third_family_case_count':25,'profiles':['legacy','early','t'],'supported_profiles':['legacy','early','t'],'early_anchor_source_commit':'9714227175010692d8374082ae98075abf18107c','generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).with_name('chopin_abi_select.c').read_bytes()).hexdigest(),'runner':a.runner,'real_vendor_binaries_used':False,'phone_or_block_device_read':False,'hardware_compatibility_verified':False}
a.report.parent.mkdir(parents=True,exist_ok=True)
a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'case_count':len(cases),'report':str(a.report),'runner':a.runner},ensure_ascii=False))
