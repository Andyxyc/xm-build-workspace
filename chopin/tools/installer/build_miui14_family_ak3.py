"""Broaden ROM/slot selection without altering the independently verified kernel."""
from pathlib import Path
import argparse,hashlib,json,struct,zipfile,re
if not __debug__:raise SystemExit('Normal Python safety gates are required')
p=argparse.ArgumentParser();p.add_argument('--base-zip',type=Path,required=True);p.add_argument('--base-report',type=Path,required=True);p.add_argument('--abi-report',type=Path,required=True);p.add_argument('--stock-boot',type=Path,required=True);p.add_argument('--source-commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert re.fullmatch('[0-9a-f]{40}',a.source_commit)
sha=lambda b:hashlib.sha256(b).hexdigest();report=json.loads(a.base_report.read_text(encoding='utf-8'));abi=json.loads(a.abi_report.read_text(encoding='utf-8'))
assert report['status']=='PASS_OFFLINE_ENTRY_FULL_KPM_ABI_AND_PACKAGE_ONLY' and report['slim_package']
assert sha(a.base_zip.read_bytes())==report['zip_sha256'] and report['image_sha256']==abi['image_sha256']
assert abi['status']=='PASS_VENDOR_MODULE_ABI_ONLY' and not abi['errors'] and len(abi['modules'])==10
source=Path(__file__).resolve().parent/'miui14-family'
with zipfile.ZipFile(a.base_zip) as z:
 assert z.testzip() is None
 files={n:z.read(n) for n in z.namelist()}
 manifest={n:h for h,n in (l.split('  ',1) for l in files['payload.sha256'].decode().splitlines())}
 assert set(manifest)==set(files)-{'payload.sha256'}
 for n,h in manifest.items():assert sha(files[n])==h
assert sha(files['Image'])==abi['image_sha256'] and report['kallsyms_link_time_symbols']==129832
for n in ['payload.sha256','stock-dtb.bin','tools/stock-ramdisk-source.sh','expected/header.sha256']:del files[n]
for n,s in [('anykernel.sh','anykernel.sh'),('customize.sh','customize.sh'),('tools/chopin-preflight.sh','preflight.sh'),('tools/miui14-compat.sh','compat.sh')]:files[n]=(source/s).read_bytes();assert b'\r' not in files[n]
modules=abi['modules'];assert all(v['vermagic']=='4.14.186-gaa24d707761c SMP preempt mod_unload modversions aarch64' for v in modules.values())
files['expected/vendor-modules.sha256']=''.join(v['sha256']+'  '+n+'\n' for n,v in sorted(modules.items())).encode()
b=a.stock_boot.read_bytes();assert len(b)==134217728 and sha(b)=='ec7ef1343b410d04c35fb3567374418173d0dff104352711c2d24b41d467ad1a'
h=bytearray(b[:1660])
for start,size in [(8,4),(16,4),(44,4),(576,32),(1648,4)]:h[start:start+size]=bytes(size)
files['expected/family-header.sha256']=(sha(h)+'\n').encode()
policy=dict(model='chopin',equivalent='Redmi Note 10 Pro 5G / POCO X3 GT',android_sdk=33,miui='14',rom_incremental_binding=None,account_binding=False,serial_binding=False,device_uuid_binding=False,uid_binding=False,active_slots=['a','b'],driver_policy='All ten independently audited modules must match; reject additional or changed drivers',ramdisk_policy='Preserve current clean ramdisk; restore its own embedded Magisk backup if present; reject incomplete backup',dtb_policy='Preserve current DTB and verify identical bytes after repack',boot_header_policy='Preserve current boot header; family layout allows different OS patch stamp and DTB length',kernel_sha256=abi['image_sha256'],source_commit=a.source_commit,hardware_validated=False)
files['COMPATIBILITY.json']=(json.dumps(policy,indent=2)+'\n').encode()
files['module.prop']=b'id=xiaomo_chopin_ak3\n'+('name=小墨 XiaoMo\nversion=r6 MIUI14 FAMILY TEST CANDIDATE\nversionCode=6\nauthor=XiaoMo\ndescription=Chopin MIUI14 Android13 compatible driver family. Guarded AnyKernel3 installer receipt.\n').encode()
files['SOURCE.txt']+=('MIUI14 family installer: https://github.com/Andyxyc/xm-build-workspace/tree/'+a.source_commit+'/chopin/tools/installer\nNo device identity or account binding. Hardware acceptance on each firmware remains separate.\n').encode()
assert len(files)==30
files['payload.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
assert not a.output.exists() and 'TEST-CANDIDATE' in a.output.name
with zipfile.ZipFile(a.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,b in sorted(files.items()):
  i=zipfile.ZipInfo(n,(2026,10,26,0,0,0));i.create_system=3;i.external_attr=(0o100755 if n.startswith('tools/') or n.endswith('.sh') or n.endswith('update-binary') else 0o100644)<<16;i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,b)
print(json.dumps(dict(status='FAMILY_TEST_CANDIDATE_PACKAGED_ONLY',path=str(a.output),bytes=a.output.stat().st_size,sha256=sha(a.output.read_bytes()),hardware_validated=False),indent=2))
