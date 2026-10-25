"""Independent whitelist comparison against the byte-verified base AK3."""
from pathlib import Path
import argparse,hashlib,json,zipfile,subprocess,struct
if not __debug__:raise SystemExit('Normal Python safety gates are required')
p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,required=True);p.add_argument('--base-zip',type=Path,required=True);p.add_argument('--base-report',type=Path,required=True);p.add_argument('--abi-report',type=Path,required=True);p.add_argument('--stock-boot',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
assert not a.report.exists();sha=lambda b:hashlib.sha256(b).hexdigest()
base=json.loads(a.base_report.read_text(encoding='utf-8'));abi=json.loads(a.abi_report.read_text(encoding='utf-8'))
assert base['status']=='PASS_OFFLINE_ENTRY_FULL_KPM_ABI_AND_PACKAGE_ONLY' and sha(a.base_zip.read_bytes())==base['zip_sha256']
with zipfile.ZipFile(a.base_zip) as z:old={n:z.read(n) for n in z.namelist()}
with zipfile.ZipFile(a.zip) as z:
 assert z.testzip() is None and len(z.namelist())==31 and len(set(z.namelist()))==31
 files={n:z.read(n) for n in z.namelist()}
manifest={n:h for h,n in (line.split('  ',1) for line in files['payload.sha256'].decode().splitlines())}
assert set(manifest)==set(files)-{'payload.sha256'}
for n,h in manifest.items():assert sha(files[n])==h
removed={'stock-dtb.bin','tools/stock-ramdisk-source.sh','expected/header.sha256'}
added={'tools/miui14-compat.sh','expected/family-header.sha256','expected/vendor-modules.sha256','COMPATIBILITY.json'}
changed={'anykernel.sh','customize.sh','tools/chopin-preflight.sh','module.prop','SOURCE.txt','payload.sha256'}
assert set(old)-set(files)==removed and set(files)-set(old)==added
for n,b in old.items():
 if n not in removed|changed:assert files[n]==b,('Unexpected change',n)
assert sha(files['Image'])==abi['image_sha256']==base['image_sha256']
family=Path(__file__).resolve().parent/'miui14-family'
for name,source in [('anykernel.sh','anykernel.sh'),('customize.sh','customize.sh'),('tools/chopin-preflight.sh','preflight.sh'),('tools/miui14-compat.sh','compat.sh')]:assert files[name]==(family/source).read_bytes()
modules={n:h for h,n in (l.split('  ',1) for l in files['expected/vendor-modules.sha256'].decode().splitlines())}
assert modules=={n:v['sha256'] for n,v in abi['modules'].items()} and len(modules)==10
b=a.stock_boot.read_bytes();assert sha(b)=='ec7ef1343b410d04c35fb3567374418173d0dff104352711c2d24b41d467ad1a'
h=bytearray(b[:1660])
for off,size in [(8,4),(16,4),(44,4),(576,32),(1648,4)]:h[off:off+size]=bytes(size)
assert files['expected/family-header.sha256'].decode().strip()==sha(h)
policy=json.loads(files['COMPATIBILITY.json']);assert policy['model']=='chopin' and policy['android_sdk']==33 and policy['active_slots']==['a','b'] and policy['rom_incremental_binding'] is None
assert all(policy[x] is False for x in ['account_binding','serial_binding','device_uuid_binding','uid_binding','hardware_validated'])
script=files['anykernel.sh'];pre=files['tools/chopin-preflight.sh']
assert b'V14.0.8.0' not in script and b'[ "$SLOT" = _a ]' not in script
assert b'cp "$AKHOME/stock-dtb.bin"' not in script and b'chopin_family_ramdisk' in script and b'chopin_family_dtb' in script
assert b'full_partition_readback_verified' in pre and b'set -C;' in pre and b'Boot changed since backup' in pre and b'Active slot changed before write' in pre
assert b'$CHOPIN_EXPECTED_RAMDISK_SHA' in pre and b'$CHOPIN_EXPECTED_DTB_SHA' in pre and b'$CHOPIN_EXPECTED_HEADER_SHA' in pre
assert not any(n.endswith('.apk') for n in files)
check=a.report.parent/(a.report.stem+'-shell');check.mkdir()
for n in ['anykernel.sh','customize.sh','tools/chopin-preflight.sh','tools/miui14-compat.sh']:
 p=check/n.replace('/','_');p.write_bytes(files[n]);r=subprocess.run([r'C:\Program Files\Git\bin\bash.exe','--noprofile','--norc','-n',str(p.resolve())],capture_output=True);assert r.returncode==0,r.stderr
record=dict(status='PASS_FAMILY_PACKAGE_WHITELIST_AND_PRESERVED_KERNEL_GATES_ONLY',path=str(a.zip),bytes=a.zip.stat().st_size,sha256=sha(a.zip.read_bytes()),kernel_sha256=abi['image_sha256'],kernel_source_commit=base['kernel_build_commit'],installer_source_commit=policy['source_commit'],driver_modules=10,imports_checked=base['imports_checked'],kallsyms_checked=base['kallsyms_link_time_symbols'],embedded_apks=0,personal_identity_binding=False,rom_incremental_binding=False,active_slots=['a','b'],real_install_verified=False,multiple_firmwares_verified=False,hardware_validated=False)
a.report.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False,indent=2))
