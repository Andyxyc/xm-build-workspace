"""Synthetic fixtures only; never reads OEM modules/vendor or extracts an archive."""
from pathlib import Path
import io,tarfile,lzma,struct,json,hashlib
import bounded_kheaders as k

ROOT=Path(__file__).resolve().parent

def make_tar(entries,fmt=tarfile.GNU_FORMAT):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=fmt) as archive:
        for spec in entries:
            info=tarfile.TarInfo(spec['name']);info.uid=info.gid=0;info.mtime=0;info.mode=0o644
            info.type=spec.get('type',tarfile.REGTYPE);info.linkname=spec.get('link','');info.pax_headers=spec.get('pax',{})
            payload=spec.get('data',b'');info.size=len(payload)
            archive.addfile(info,io.BytesIO(payload) if payload else None)
    return stream.getvalue()

BASE=[{'name':'./','type':tarfile.DIRTYPE},
 {'name':'./include/generated/autoconf.h','data':b'#define CONFIG_ARM64 1\n#define CONFIG_SMP 1\n#define CONFIG_PRIVATE_FIXTURE "must-not-emit"\n'},
 {'name':'./include/generated/utsrelease.h','data':b'#define UTS_RELEASE "4.14.186-SYNTHETIC-ONLY"\n'},
 {'name':'./include/generated/compile.h','data':b'#define LINUX_COMPILE_BY "not-public-header-output"\n'},
 {'name':'./include/generated/uapi/linux/version.h','data':b'#define LINUX_VERSION_CODE 265914\n'},
 {'name':'./include/linux/not-selected.h','data':b'DO-NOT-EXPORT-COMPLETE-HEADER\n'}]

def elf(archive,prefix=b'FAKE-XZ-PREFIX',suffix=b'NO-TRAILING-TAR-EXPORT',extra_pad=0):
    shnames=b'\0.shstrtab\0.rodata\0.strtab\0.symtab\0'
    strings=b'\0kernel_headers_data\0kernel_headers_data_end\0'
    section_names=[0]+[shnames.index(x) for x in [b'.shstrtab',b'.rodata',b'.strtab',b'.symtab']]
    ro=prefix+archive+suffix
    symbols=bytes(24)+struct.pack('<IBBHQQ',1,0x10,0,2,len(prefix),0)+struct.pack('<IBBHQQ',strings.index(b'kernel_headers_data_end'),0x10,0,2,len(prefix)+len(archive),0)
    body=bytearray(bytes(64)+bytes(extra_pad));offsets=[]
    for payload in [shnames,ro,strings,symbols]:
        body.extend(bytes((-len(body))%8));offsets.append(len(body));body.extend(payload)
    body.extend(bytes((-len(body))%8));shoff=len(body)
    sections=[bytes(64)]
    sections.append(struct.pack('<IIQQQQIIQQ',section_names[1],3,0,0,offsets[0],len(shnames),0,0,1,0))
    sections.append(struct.pack('<IIQQQQIIQQ',section_names[2],1,2,0,offsets[1],len(ro),0,0,8,0))
    sections.append(struct.pack('<IIQQQQIIQQ',section_names[3],3,0,0,offsets[2],len(strings),0,0,1,0))
    sections.append(struct.pack('<IIQQQQIIQQ',section_names[4],2,0,0,offsets[3],len(symbols),3,1,8,24))
    body.extend(b''.join(sections));ident=b'\x7fELF\x02\x01\x01'+bytes(9)
    body[:64]=struct.pack('<16sHHIQQQIHHHHHH',ident,1,183,1,0,0,shoff,0,64,0,0,64,5,1)
    return bytes(body),{'symoff':offsets[3],'shoff':shoff,'ro_size':len(ro),'strtaboff':offsets[2]}

def module(entries=BASE,raw=None,xz=None,**kw):
    raw=make_tar(entries) if raw is None else raw
    archive=lzma.compress(raw,format=lzma.FORMAT_XZ) if xz is None else xz
    return elf(archive,**kw)

def mutate(blob,at,value,fmt=None):
    result=bytearray(blob)
    if fmt:struct.pack_into(fmt,result,at,value)
    else:result[at]=value
    return bytes(result)

cases=[]
def run(name,blob,expected=True,overrides=None,macros=('CONFIG_ARM64','CONFIG_MISSING'),contains=None):
    try:
        result=k.inspect_kheaders_module('kheaders.ko',blob,macros,overrides)
        passed=expected
        if expected:
            text=json.dumps(result)
            passed=passed and 'must-not-emit' not in text and 'not-public-header-output' not in text and 'DO-NOT-EXPORT' not in text
            if contains:passed=passed and contains in text
        cases.append({'name':name,'expected_accept':expected,'accepted':True,'pass':passed})
        return result
    except k.KheadersError as e:
        cases.append({'name':name,'expected_accept':expected,'accepted':False,'reason':str(e),'pass':not expected})
        return None

valid,meta=module()
reference=run('valid_generated_headers_only',valid,contains='4.14.186-SYNTHETIC-ONLY')
assert reference and reference['selected_headers']['include/generated/autoconf.h']['requested_macros']['CONFIG_MISSING']['state']=='not_defined_in_this_header'
run('different_ELF_offsets',module(extra_pad=312)[0])
run('misleading_XZ_magic_outside_anchors',module(prefix=b'\xfd7zXZ\x00BADPREFIX',suffix=b'\xfd7zXZ\x00BADSUFFIX')[0])
run('wrong_machine',mutate(valid,18,62,'<H'),False)
run('wrong_class',mutate(valid,4,1),False)
run('wrong_endian',mutate(valid,5,2),False)
run('wrong_ELF_type',mutate(valid,16,2,'<H'),False)
run('truncated_module',valid[:-20],False)
run('section_past_EOF',mutate(valid,meta['shoff']+2*64+24,len(valid)+1,'<Q'),False)
run('missing_end_anchor',mutate(valid,meta['strtaboff']+21,ord('X')),False)
run('end_anchor_other_section',mutate(valid,meta['symoff']+48+6,3,'<H'),False)
run('end_anchor_out_of_range',mutate(valid,meta['symoff']+48+8,meta['ro_size']+1,'<Q'),False)
run('non_global_anchor',mutate(valid,meta['symoff']+24+4,0),False)
run('symbol_count_limit',valid,False,{'symbols':2})
run('section_count_limit',valid,False,{'sections':2})
run('module_size_limit',valid,False,{'module':100})
run('compressed_size_limit',valid,False,{'xz':10})
run('XZ_memory_limit',valid,False,{'xz_memory':1024})
raw=make_tar(BASE);compressed=lzma.compress(raw)
run('truncated_XZ',module(xz=compressed[:-5])[0],False)
run('XZ_trailing_data',module(xz=compressed+b'X')[0],False)
run('concatenated_XZ_streams',module(xz=compressed+compressed)[0],False)
run('XZ_checksum_failure',module(xz=compressed[:-15]+bytes([compressed[-15]^1])+compressed[-14:])[0],False)
run('XZ_output_bomb_limit',module(raw=b'A'*100000)[0],False,{'raw_tar':2048})
run('tar_member_limit',valid,False,{'members':2})
for name in ['../escape.h','/absolute.h','include\\escape.h','./include/../escape.h']:
    run('unsafe_member_'+repr(name),module(BASE+[{'name':name,'data':b'X'}])[0],False)
run('duplicate_normalized_member',module(BASE+[{'name':'include/generated/autoconf.h','data':b'X'}])[0],False)
run('oversized_member',module(BASE+[{'name':'include/oversized.h','data':b'X'*(2*1024*1024+1)}])[0],False)
run('selected_autoconf_symlink',module([x for x in BASE if 'autoconf.h' not in x['name']]+[{'name':'include/generated/autoconf.h','type':tarfile.SYMTYPE,'link':'utsrelease.h'}])[0],False)
run('selected_autoconf_hardlink',module([x for x in BASE if 'autoconf.h' not in x['name']]+[{'name':'include/generated/autoconf.h','type':tarfile.LNKTYPE,'link':'./include/generated/utsrelease.h'}])[0],False)
run('safe_nonselected_symlink_not_followed',module(BASE+[{'name':'include/linux/safe-link.h','type':tarfile.SYMTYPE,'link':'../generated/autoconf.h'}])[0])
run('escaping_symlink_rejected',module(BASE+[{'name':'include/linux/unsafe-link.h','type':tarfile.SYMTYPE,'link':'../../../outside.h'}])[0],False)
run('missing_link_target_rejected',module(BASE+[{'name':'include/linux/unknown.h','type':tarfile.SYMTYPE,'link':'missing.h'}])[0],False)
run('link_count_limit',module(BASE+[{'name':'include/linux/l1.h','type':tarfile.SYMTYPE,'link':'not-selected.h'},{'name':'include/linux/l2.h','type':tarfile.SYMTYPE,'link':'not-selected.h'}])[0],False,{'links':1})
run('character_device_rejected',module(BASE+[{'name':'include/dev.h','type':tarfile.CHRTYPE}])[0],False)
run('FIFO_rejected',module(BASE+[{'name':'include/fifo.h','type':tarfile.FIFOTYPE}])[0],False)
run('PAX_metadata_rejected',module(BASE+[{'name':'include/pax.h','data':b'X','pax':{'comment':'unsupported'}}],raw=make_tar(BASE+[{'name':'include/pax.h','data':b'X','pax':{'comment':'unsupported'}}],tarfile.PAX_FORMAT))[0],False)
long_name='include/'+('x'*145)+'/long.h'
run('GNU_long_name_bounded',module(BASE+[{'name':long_name,'data':b'not-exported'}])[0])
run('GNU_long_link_bounded_not_followed',module(BASE+[{'name':long_name,'data':b'not-exported'},{'name':'link.h','type':tarfile.SYMTYPE,'link':long_name}])[0])
run('path_limit',module(BASE+[{'name':'include/'+('x'*180)+'.h','data':b'X'}])[0],False,{'path':120})
run('tar_checksum_error',module(raw=mutate(raw,100,ord('7')))[0],False)
run('tar_nonzero_after_terminator',module(raw=raw+b'X'+bytes(511))[0],False)
run('tar_no_terminator',module(raw=raw[:512])[0],False)
run('requested_macro_duplicate',module([x if 'autoconf.h' not in x['name'] else dict(x,data=b'#define CONFIG_ARM64 1\n#define CONFIG_ARM64 0\n') for x in BASE])[0],False)
run('requested_macro_value_limit',module([x if 'autoconf.h' not in x['name'] else dict(x,data=b'#define CONFIG_ARM64 '+b'X'*257+b'\n') for x in BASE])[0],False)
run('macro_allowlist_invalid',valid,False,macros=('LINUX_COMPILE_BY',))
run('limit_may_not_be_increased',valid,False,{'raw_tar':k.HARD_LIMITS['raw_tar']+1})
missing=run('no_autoconf_is_partial_not_config_acceptance',module([x for x in BASE if 'autoconf.h' not in x['name']])[0])
assert missing and missing['status']=='BOUNDED_ARCHIVE_WITHOUT_AUTOCONF_EVIDENCE'
failed=[c['name'] for c in cases if not c['pass']]
report={'status':'PASS_SYNTHETIC_FIXTURES' if not failed else 'FAIL_SYNTHETIC_FIXTURES','fixture_cases':len(cases),'failed':failed,'cases':cases,'positive_synthetic_example':reference,'OEM_module_read':False,'OEM_module_sha256':None,'synthetic_fixture_only':True,'helper_sha256':hashlib.sha256((ROOT/'bounded_kheaders.py').read_bytes()).hexdigest(),'fixture_generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(ROOT/'fixture-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'cases':len(cases),'failed':failed,'OEM_module_read':False},ensure_ascii=False))
raise SystemExit(1 if failed else 0)
