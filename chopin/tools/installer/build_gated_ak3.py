"""Build a private TEST-CANDIDATE only after the byte-bound ABI gate passes.

Never accesses ADB/Fastboot or writes any device partition. The produced ZIP
remains a test candidate until independent real-device acceptance succeeds.
"""
from pathlib import Path
import argparse,hashlib,json,struct,gzip,shutil,subprocess,zipfile,re,sys
if not __debug__:raise SystemExit('Safety gates require normal Python mode; -O is forbidden')
p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--gate',type=Path,required=True);p.add_argument('--stock-boot',type=Path,required=True);p.add_argument('--ak3-source',type=Path,required=True);p.add_argument('--licenses',type=Path,required=True);p.add_argument('--installer-commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert re.fullmatch('[0-9a-f]{40}',a.installer_commit)
root=Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
g=json.loads(a.gate.read_text(encoding='utf-8'))
assert g['status']=='PASS_VENDOR_MODULE_ABI_ONLY' and not g['errors'],'ABI gate failed: no ZIP will be created'
assert len(g['modules'])==10 and g['imports_checked']==1299
images=list((a.candidate/'kernel_workspace').rglob('Image'));assert len(images)==1
image=images[0].read_bytes();assert digest(image)==g['image_sha256']
ev=a.candidate/'release-evidence'
sys.path.insert(0,str(root.parents[1]))
from verify_image_entry import inspect_kpm
from verify_kpm_resolver import verify as verify_resolver
entry=inspect_kpm(image,(ev/'Image.sukisu-susfs-before-kpm').read_bytes(),(ev/'kpimg.pinned').read_bytes())
resolver_log=a.candidate/'build-logs/kpm-reprocess.log'
if not resolver_log.is_file():resolver_log=a.candidate/'build-logs/kpm-postprocess.log'
entry['full_kallsyms_validation']=verify_resolver((ev/'Image.sukisu-susfs-before-kpm').read_bytes(),(ev/'System.map').read_text(),resolver_log.read_text())
assert entry['kpimg_sha256']=='396a20777668e85d674a23dd3945815f285332b5358be0bfc97297935e2d130b'
entry_receipt=json.loads((ev/'kpm-entry-gate.json').read_text())
assert entry_receipt['image_sha256']==digest(image) and entry_receipt['status']==entry['status']
assert digest((ev/'ported.Module.symvers').read_bytes())==g['symvers_sha256']
assert digest((ev/'System.map').read_bytes())==g['system_map_sha256']
assert subprocess.check_output(['git','-C',str(a.ak3_source),'rev-parse','HEAD'],text=True).strip()=='020dfeccf9d7e962a48400fc94d3e451df92eead'
core=subprocess.check_output(['git','-C',str(a.ak3_source),'show','HEAD:tools/ak3-core.sh'])
assert digest(core)=='f7a51cfe2e093016a34a76e16de6c9885c2d1992c3482fcabc668680e1f0f6bb'
stock=a.stock_boot.read_bytes();assert len(stock)==134217728 and digest(stock)=='ec7ef1343b410d04c35fb3567374418173d0dff104352711c2d24b41d467ad1a'
assert stock[:8]==b'ANDROID!';page=struct.unpack_from('<I',stock,36)[0];assert page==2048
ks=struct.unpack_from('<I',stock,8)[0];rs=struct.unpack_from('<I',stock,16)[0]
assert struct.unpack_from('<I',stock,40)[0]==2 and struct.unpack_from('<I',stock,24)[0]==0
assert struct.unpack_from('<I',stock,1632)[0]==0 and struct.unpack_from('<I',stock,1648)[0]==201848
align=lambda n:(n+page-1)//page*page
rd_off=page+align(ks);dtb_off=rd_off+align(rs)
rd=stock[rd_off:rd_off+rs];dtb=stock[dtb_off:dtb_off+201848]
assert digest(gzip.decompress(rd))=='58e70342f8d631f26c95546f787933b744f8fbb67412ca22be561c0a30b42095'
assert digest(dtb)=='d6aa88bad3591b62473a2b753ccd19dc371dbb30bd8e1efa487c651fdefd27fc'
header=bytearray(stock[:1660]);header[8:12]=bytes(4);header[16:20]=bytes(4);header[576:608]=bytes(32)
assert digest(header)=='597abf508e7e9fd153f952a352e04e09153945aab043113c07347a3c71674d40'
assert 'TEST-CANDIDATE' in a.output.name and a.output.suffix=='.zip' and not a.output.exists()
stage=a.output.parent/('ak3-stage-'+g['image_sha256'][:12]);stage.mkdir(parents=False,exist_ok=False)
# Read committed blobs, never a Windows checkout that may have CRLF conversion.
entries=subprocess.check_output(['git','-C',str(a.ak3_source),'ls-tree','-r','HEAD','--','META-INF','tools'],text=True)
for line in entries.splitlines():
    tree_record,name=line.split('\t',1);mode,kind,oid=tree_record.split()
    assert kind=='blob' and mode in ['100644','100755']
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(subprocess.check_output(['git','-C',str(a.ak3_source),'show','HEAD:'+name]))
# ADB shell stdout can be a socket which cannot be reopened via /proc/self/fd.
# Duplicate the existing updater descriptor instead; preserve the real exit code.
redirect=b'>> /proc/self/fd/$OUTFD'
assert core.count(redirect)==1
core=core.replace(redirect,b'>&$OUTFD')
updater=stage/'META-INF/com/google/android/update-binary'
updater_bytes=updater.read_bytes();assert updater_bytes.count(redirect)==2
updater.write_bytes(updater_bytes.replace(redirect,b'>&$OUTFD'))
# Insert a verified callback immediately before the sole active-boot write.
# All other official core behavior remains byte-for-byte unchanged.
start=core.index(b'flash_boot() {');end=core.index(b'\n# flash_generic ',start)
part=core[start:end];needle=b'  blockdev --setrw $BLOCK 2>/dev/null;'
assert part.count(needle)==1
part=part.replace(needle,b'  chopin_preflash_verify || abort "Chopin preflash validation failed";\n  chopin_record_attempt || abort "Cannot record the single write attempt";\n'+needle,1)
(stage/'tools/ak3-core.sh').write_bytes(core[:start]+part+core[end:])
(stage/'tools/chopin-preflight.sh').write_text((root/'ak3-preflight.sh').read_text(),encoding='utf-8',newline='\n')
(stage/'anykernel.sh').write_text((root/'chopin-anykernel-template.sh').read_text(),encoding='utf-8',newline='\n')
(stage/'Image').write_bytes(image);(stage/'stock-ramdisk.cpio.gz').write_bytes(rd);(stage/'stock-dtb.bin').write_bytes(dtb)
(stage/'expected').mkdir()
(stage/'expected/header.sha256').write_text(digest(header)+'\n',newline='\n')
(stage/'expected/kernel.sha256').write_text(digest(image)+'\n',newline='\n')
build_commit=(a.candidate/'build-logs/root-build-complete.txt').read_text().strip();assert re.fullmatch('[0-9a-f]{40}',build_commit)
(stage/'SOURCE.txt').write_text('TEST CANDIDATE - no real-device acceptance implied.\nSource and build scripts: https://github.com/Andyxyc/xm-build-workspace/tree/'+build_commit+'\nAnyKernel3: https://github.com/osm0sis/AnyKernel3/tree/020dfeccf9d7e962a48400fc94d3e451df92eead\nVendor source: https://github.com/ChopinKernels/android_kernel_chopin_android_T/tree/0647a49c9557faa92b90c4ae188587787226be9e\nSukiSU: https://github.com/SukiSU-Ultra/SukiSU-Ultra/tree/ce75122bec7423e0f1fa06e3e9a174085c5231ab\nSUSFS: https://github.com/Star-Seven/susfs4ksu/tree/d18028f2a8f3ba16a907bff0edc16376cf38e2bf\nKPM postprocessor source: https://github.com/bmax121/KernelPatch/tree/052c73f93dbb84861218086e60a9962c48ff3f7f (source-built kptools)\nPinned KPM runtime payload: https://github.com/ShirkNeko/SukiSU_patch/blob/7c6289c95bdc786119b03d150236853b7b4872ca/kpm/kpimg\n',newline='\n')
(stage/'AnyKernel3-LICENSE').write_bytes(subprocess.check_output(['git','-C',str(a.ak3_source),'show','HEAD:LICENSE']))
licenses={'Linux-COPYING':'af8067302947c01fd9eee72befa54c7e3ef8a48fecde7fd71277f2290b2bf0f7','SukiSU-LICENSE':'8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643','SUSFS-LICENSE':'3da27bc7c6a063f498b4278372d48e113453f93aecc709f44276e278fc0cac12','KernelPatch-LICENSE':'ce7f2f7bc1c5b68f592a04b763abaa9c180c5e44e30563153bee280763b54ae7'}
(stage/'LICENSES').mkdir()
for name,expected in licenses.items():
    blob=(a.licenses/name).read_bytes();assert digest(blob)==expected,(name,'License source changed')
    (stage/'LICENSES'/name).write_bytes(blob)
with (stage/'SOURCE.txt').open('a',newline='\n') as source:
    source.write('Installer source snapshot: https://github.com/Andyxyc/xm-build-workspace/tree/'+a.installer_commit+'/chopin/tools/installer\n')
    kpm_source=ev/'kpm-reprocess-source-commit.txt'
    kpm_commit=kpm_source.read_text().strip() if kpm_source.is_file() else build_commit
    assert re.fullmatch('[0-9a-f]{40}',kpm_commit)
    source.write('KPM processing source snapshot: https://github.com/Andyxyc/xm-build-workspace/tree/'+kpm_commit+'\n')
# The private module manifest remains local; only a minimal gate receipt ships.
(stage/'ABI-GATE.json').write_text(json.dumps(dict(status=g['status'],image_sha256=g['image_sha256'],imports_checked=g['imports_checked'],actual_image_export_crcs_checked=g['actual_image_export_crcs_checked'],hardware_validated=False),indent=2),newline='\n')
(stage/'ENTRY-GATE.json').write_text(json.dumps(entry,indent=2)+'\n',encoding='utf-8',newline='\n')
files=sorted(f for f in stage.rglob('*') if f.is_file())
(stage/'payload.sha256').write_text(''.join(digest(f.read_bytes())+'  '+f.relative_to(stage).as_posix()+'\n' for f in files),encoding='ascii',newline='\n')
with zipfile.ZipFile(a.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for f in sorted(stage.rglob('*')):
        if f.is_file():z.write(f,f.relative_to(stage).as_posix())
with zipfile.ZipFile(a.output) as z:assert z.testzip() is None
print(json.dumps(dict(status='TEST_CANDIDATE_PACKAGED_ONLY',zip=str(a.output),sha256=digest(a.output.read_bytes()),hardware_validated=False),indent=2))
