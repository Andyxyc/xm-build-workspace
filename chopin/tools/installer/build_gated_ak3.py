"""Build a private TEST-CANDIDATE only after the byte-bound ABI gate passes.

Never accesses ADB/Fastboot or writes any device partition. The produced ZIP
remains a test candidate until independent real-device acceptance succeeds.
"""
from pathlib import Path
import argparse,hashlib,json,struct,gzip,shutil,subprocess,zipfile,re
if not __debug__:raise SystemExit('Safety gates require normal Python mode; -O is forbidden')
p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--gate',type=Path,required=True);p.add_argument('--stock-boot',type=Path,required=True);p.add_argument('--ak3-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
g=json.loads(a.gate.read_text(encoding='utf-8'))
assert g['status']=='PASS_VENDOR_MODULE_ABI_ONLY' and not g['errors'],'ABI gate failed: no ZIP will be created'
assert len(g['modules'])==10 and g['imports_checked']==1299
images=list((a.candidate/'kernel_workspace').rglob('Image'));assert len(images)==1
image=images[0].read_bytes();assert digest(image)==g['image_sha256']
ev=a.candidate/'release-evidence'
assert digest((ev/'ported.Module.symvers').read_bytes())==g['symvers_sha256']
assert digest((ev/'System.map').read_bytes())==g['system_map_sha256']
assert subprocess.check_output(['git','-C',str(a.ak3_source),'rev-parse','HEAD'],text=True).strip()=='020dfeccf9d7e962a48400fc94d3e451df92eead'
core=(a.ak3_source/'tools/ak3-core.sh').read_bytes()
assert digest(core)=='fd7fe76586e23a75d2f98261a68757f1f4a86e4dc73597da455d1a7039037bce'
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
for folder in ['META-INF','tools']:
    shutil.copytree(a.ak3_source/folder,stage/folder)
# Insert a verified callback immediately before the sole active-boot write.
# All other official core behavior remains byte-for-byte unchanged.
start=core.index(b'flash_boot() {');end=core.index(b'\n# flash_generic ',start)
part=core[start:end];needle=b'  blockdev --setrw $BLOCK 2>/dev/null;'
assert part.count(needle)==1
part=part.replace(needle,b'  chopin_preflash_verify || abort "Chopin preflash validation failed";\n  chopin_record_attempt || abort "Cannot record the single write attempt";\n'+needle,1)
(stage/'tools/ak3-core.sh').write_bytes(core[:start]+part+core[end:])
shutil.copyfile(root/'ak3-preflight.sh',stage/'tools/chopin-preflight.sh')
(stage/'anykernel.sh').write_text((root/'chopin-anykernel-template.sh').read_text(),encoding='utf-8',newline='\n')
(stage/'Image').write_bytes(image);(stage/'stock-ramdisk.cpio.gz').write_bytes(rd);(stage/'stock-dtb.bin').write_bytes(dtb)
(stage/'expected').mkdir()
(stage/'expected/header.sha256').write_text(digest(header)+'\n')
(stage/'expected/kernel.sha256').write_text(digest(image)+'\n')
build_commit=(a.candidate/'build-logs/root-build-complete.txt').read_text().strip();assert re.fullmatch('[0-9a-f]{40}',build_commit)
(stage/'SOURCE.txt').write_text('TEST CANDIDATE - no real-device acceptance implied.\nSource and build scripts: https://github.com/Andyxyc/xm-build-workspace/tree/'+build_commit+'\nAnyKernel3: https://github.com/osm0sis/AnyKernel3/tree/020dfeccf9d7e962a48400fc94d3e451df92eead\nVendor source: https://github.com/ChopinKernels/android_kernel_chopin_android_T/tree/0647a49c9557faa92b90c4ae188587787226be9e\nSukiSU: https://github.com/SukiSU-Ultra/SukiSU-Ultra/tree/ce75122bec7423e0f1fa06e3e9a174085c5231ab\nSUSFS: https://github.com/Star-Seven/susfs4ksu/tree/d18028f2a8f3ba16a907bff0edc16376cf38e2bf\nKPM patch tool: https://github.com/ShirkNeko/SukiSU_patch/tree/7c6289c95bdc786119b03d150236853b7b4872ca\n')
shutil.copyfile(a.ak3_source/'LICENSE',stage/'AnyKernel3-LICENSE')
# The private module manifest remains local; only a minimal gate receipt ships.
(stage/'ABI-GATE.json').write_text(json.dumps(dict(status=g['status'],image_sha256=g['image_sha256'],imports_checked=g['imports_checked'],actual_image_export_crcs_checked=g['actual_image_export_crcs_checked'],hardware_validated=False),indent=2))
files=sorted(f for f in stage.rglob('*') if f.is_file())
(stage/'payload.sha256').write_text(''.join(digest(f.read_bytes())+'  '+f.relative_to(stage).as_posix()+'\n' for f in files),encoding='ascii')
with zipfile.ZipFile(a.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for f in sorted(stage.rglob('*')):
        if f.is_file():z.write(f,f.relative_to(stage).as_posix())
with zipfile.ZipFile(a.output) as z:assert z.testzip() is None
print(json.dumps(dict(status='TEST_CANDIDATE_PACKAGED_ONLY',zip=str(a.output),sha256=digest(a.output.read_bytes()),hardware_validated=False),indent=2))
