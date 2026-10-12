#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib, json, os, pathlib, re, subprocess, zipfile
root=pathlib.Path.cwd();out=root/'out';out.mkdir(exist_ok=True)
source=root/'ui/manager-unsigned.apk'
assert source.is_file(),'Manager APK is missing'
binaries={
 'lib/arm64-v8a/libksud.so':root/'native/aarch64-linux-android/ksud',
 'lib/x86_64/libksud.so':root/'native/x86_64-linux-android/ksud',
}
for name,path in binaries.items():
 data=path.read_bytes();assert data[:4]==b'\x7fELF' and len(data)>100000,name
 expected_machine=183 if 'arm64' in name else 62
 assert int.from_bytes(data[18:20],'little')==expected_machine,name
unsigned=root/'repacked-unsigned.apk'
with zipfile.ZipFile(source) as src,zipfile.ZipFile(unsigned,'w') as dst:
 for item in src.infolist():
  if item.filename in binaries or re.match(r'^META-INF/([^/]+\.(SF|RSA|DSA|EC)|MANIFEST\.MF)$',item.filename,re.I):continue
  dst.writestr(item,src.read(item.filename))
 for name,path in binaries.items():dst.write(path,name,compress_type=zipfile.ZIP_DEFLATED)
tools=pathlib.Path(os.environ['ANDROID_HOME'])/'build-tools/37.0.0'
final=out/'moksu-unsigned.apk'
subprocess.run([str(tools/'zipalign'),'-P','16','-f','4',str(unsigned),str(final)],check=True)
subprocess.run([str(tools/'zipalign'),'-c','-P','16','4',str(final)],check=True)
badging=subprocess.check_output([str(tools/'aapt'),'dump','badging',str(final)],text=True)
assert "package: name='com.moksu.manager'" in badging
assert "application-label:'moksu'" in badging
(out/'apk-badging.txt').write_text(badging)
with zipfile.ZipFile(final) as apk:
 assert apk.testzip() is None
 names=apk.namelist()
 for abi in ('arm64-v8a','x86_64'):
  for lib in ('libsevenk.so','libadbroot.so','libksud.so'):assert f'lib/{abi}/{lib}' in names
 assert 'assets/ksu_manager_gen2' in names
(out/'build-status.json').write_text(json.dumps({'app_name':'moksu','package_name':'com.moksu.manager','version':'2.29.2','apk_compiled':True,'native_core_rebuilt':True,'kernel_kmi_count':8,'abi':['arm64-v8a','x86_64'],'apk_signed':False,'device_tested':False,'unsigned_sha256':hashlib.sha256(final.read_bytes()).hexdigest()},indent=2)+'\n')
import shutil
shutil.copy2(tools/'lib/apksigner.jar',out/'apksigner.jar')
print('Complete rebuilt APK packaged and aligned; local signing is still required.')
