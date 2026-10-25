"""Independent ZIP/entry/component/source checks; never uses ADB or Fastboot."""
from pathlib import Path
import argparse,zipfile,json,hashlib,re,struct,gzip,subprocess
from installer_transport import OLD_UI,NEW_UI,BOOT_ANCHOR,BOOT_ADAPTER,OLD_PROGRESS,NEW_PROGRESS,OLD_UNZIP,NEW_UNZIP
from installer_write import ORIGINAL_WRITE,GUARDED_WRITE_CALL
if not __debug__:raise SystemExit('Normal Python mode is required')
p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--gate',type=Path,required=True);p.add_argument('--ak3',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
assert not a.report.exists(),'Preserve earlier report'
sha=lambda b:hashlib.sha256(b).hexdigest();g=json.loads(a.gate.read_text(encoding="utf-8"));ev=a.candidate/'release-evidence'
assert g['status']=='PASS_VENDOR_MODULE_ABI_ONLY' and not g['errors'] and g['imports_checked']==1299
with zipfile.ZipFile(a.zip) as z:
    assert z.testzip() is None
    names=z.namelist();assert len(names)==len(set(names))
    slim='stock-ramdisk.cpio.gz' not in names
    assert len(names)==(30 if slim else 31),len(names)
    assert not any(n.lower().endswith('.apk') for n in names)
    assert all(not n.startswith('/') and '..' not in Path(n).parts and '\\' not in n for n in names)
    manifest={n:h for h,n in (line.split('  ',1) for line in z.read('payload.sha256').decode().splitlines())}
    assert set(manifest)==set(names)-{'payload.sha256'}
    for n,h in manifest.items():assert sha(z.read(n))==h,('Payload mismatch',n)
    image=z.read('Image');assert sha(image)==g['image_sha256']
    assert image[56:60]==b'ARMd';off=4 if image[:2]==b'MZ' else 0
    insn=struct.unpack_from('<I',image,off)[0];assert insn&0xfc000000==0x14000000
    displacement=insn&0x3ffffff
    if displacement&(1<<25):displacement-=1<<26
    target=off+4*displacement;assert 64<=target and target+64<=len(image),'Entry must have actual backed code'
    before=(ev/'Image.sukisu-susfs-before-kpm').read_bytes();kp=(ev/'kpimg.pinned').read_bytes()
    assert len(kp)==294144 and sha(kp)=='1d9a0d6772b14197313b4184e290ea7f627a340349430f58efe7600609cde7a4'
    start=(len(before)+4095)//4096*4096
    assert image[start:start+64]==kp[:64] and target==start+4096
    assert len(image)>=start+len(kp) and image[target:target+64]==kp[4096:4160] and any(image[target:target+64])
    assert image[start+4096:start+len(kp)]==kp[4096:],'All pinned executable payload bytes must remain identical'
    entry=json.loads(z.read('ENTRY-GATE.json'));assert isinstance(entry,dict),'Entry proof must be a structured record';assert entry['image_sha256']==sha(image) and entry['before_sha256']==sha(before) and entry['kpimg_sha256']==sha(kp)
    if not slim: assert sha(gzip.decompress(z.read('stock-ramdisk.cpio.gz')))=='58e70342f8d631f26c95546f787933b744f8fbb67412ca22be561c0a30b42095'
    stock_source=z.read('tools/stock-ramdisk-source.sh')
    assert b'58e70342f8d631f26c95546f787933b744f8fbb67412ca22be561c0a30b42095' in stock_source
    assert b'use the full XiaoMo AK3 fallback ZIP' in stock_source
    assert sha(z.read('stock-dtb.bin'))=='d6aa88bad3591b62473a2b753ccd19dc371dbb30bd8e1efa487c651fdefd27fc'
    assert z.read('expected/header.sha256').decode().strip()=='597abf508e7e9fd153f952a352e04e09153945aab043113c07347a3c71674d40'
    core=z.read('tools/ak3-core.sh');original=subprocess.check_output(['git','-C',str(a.ak3),'show','HEAD:tools/ak3-core.sh'])
    hook=b'  chopin_preflash_verify || abort "Chopin preflash validation failed";\n  chopin_record_attempt || abort "Cannot record the single write attempt";\n'
    assert core.count(hook)==1 and core.count(NEW_UI)==1
    assert core.count(GUARDED_WRITE_CALL)==1
    assert core.replace(hook,b'',1).replace(NEW_UI,OLD_UI,1).replace(GUARDED_WRITE_CALL,ORIGINAL_WRITE,1)==original
    up='META-INF/com/google/android/update-binary';original_up=subprocess.check_output(['git','-C',str(a.ak3),'show','HEAD:'+up])
    backend=z.read(up)
    assert backend==z.read('tools/ak3-update-binary.sh')
    assert sha(backend)==z.read('expected/backend.sha256').decode().strip()
    assert backend.replace(NEW_UI,OLD_UI,1).replace(BOOT_ADAPTER+BOOT_ANCHOR,BOOT_ANCHOR,1).replace(NEW_PROGRESS,OLD_PROGRESS,1).replace(NEW_UNZIP,OLD_UNZIP,1)==original_up
    bridge=z.read('customize.sh')
    assert bridge.startswith(b'SKIPUNZIP=1\n') and b'tools/ak3-update-binary.sh' in bridge
    assert b'3 1 "$ZIPFILE"' in bridge and b'AnyKernel3 installation failed' in bridge
    assert z.read('META-INF/com/google/android/updater-script').startswith(b'#MAGISK\n')
    assert z.read('module.prop').decode().splitlines()[1]=='name=小莫 XiaoMo'

    script=z.read('anykernel.sh').decode();assert '[ "$SLOT" = _a ]' in script and 'NO_MAGISK_CHECK=1' in script
    assert 'do.modules=0' in script and 'NO_VBMETA_PARTITION_PATCH=1' in script and script.rstrip().endswith('flash_boot;\nchopin_postflash_verify;')
    pre=z.read('tools/chopin-preflight.sh').decode();assert 'set -C;' in pre and 'phase=full_partition_readback_verified' in pre
    texts=['customize.sh','tools/stock-ramdisk-source.sh','tools/ak3-update-binary.sh','module.prop','anykernel.sh','tools/ak3-core.sh','tools/chopin-preflight.sh',up,'payload.sha256','SOURCE.txt','expected/kernel.sha256','expected/header.sha256']
    assert all(b'\r' not in z.read(n) for n in texts)
    check=a.report.parent/(a.report.stem+'-shell');check.mkdir(exist_ok=False)
    for n in ['anykernel.sh','tools/ak3-core.sh','tools/chopin-preflight.sh','customize.sh','tools/stock-ramdisk-source.sh','tools/ak3-update-binary.sh',up]:
        f=check/n.replace('/','_');f.write_bytes(z.read(n));q=subprocess.run([r'C:\Program Files\Git\bin\bash.exe','--noprofile','--norc','-n',str(f.resolve())],capture_output=True);assert q.returncode==0,q.stderr
    build=(a.candidate/'build-logs/root-build-complete.txt').read_text(encoding="utf-8").strip();assert re.fullmatch('[0-9a-f]{40}',build)
    report=dict(status='PASS_OFFLINE_ENTRY_FULL_KPM_ABI_AND_PACKAGE_ONLY',zip=str(a.zip),zip_sha256=sha(a.zip.read_bytes()),zip_bytes=a.zip.stat().st_size,image_sha256=sha(image),image_bytes=len(image),entry_target=hex(target),kpimg_bytes=len(kp),imports_checked=1299,kpm_payload_body_matches=True,kallsyms_link_time_symbols=entry['full_kallsyms_validation']['symbols_checked'],actual_image_export_crcs_checked=g['actual_image_export_crcs_checked'],kernel_build_commit=build,slim_package=slim,embedded_apk_count=0,manager_install_bridge=True,partition_writes=0,boot_hardware=False,camera_hardware=False,power_hardware=False,sukisu_runtime=False,susfs_runtime=False,kpm_runtime=False,distribution='Private test candidate containing original stock ROM components; do not publish')
a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
