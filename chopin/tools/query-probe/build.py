"""Compile a permission-free ordinary-app observer using the existing runner SDK."""
from pathlib import Path
import os,subprocess,tempfile,zipfile,hashlib,json
root=Path(__file__).resolve().parent
sdk=Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','/usr/local/lib/android/sdk')))
platform=sdk/'platforms/android-35/android.jar';assert platform.is_file()
tools=sorted(p for p in (sdk/'build-tools').iterdir() if (p/'aapt2').is_file() and (p/'d8').is_file())[-1]
out=Path('query-probe-out');out.mkdir(exist_ok=False)
with tempfile.TemporaryDirectory(prefix='chopin-query-') as temp:
 w=Path(temp);classes=w/'classes';classes.mkdir();dex=w/'dex';dex.mkdir()
 subprocess.run(['javac','-source','8','-target','8','-bootclasspath',str(platform),'-d',str(classes),str(root/'QueryActivity.java')],check=True)
 subprocess.run([str(tools/'d8'),'--lib',str(platform),'--min-api','26','--output',str(dex),*[str(p) for p in classes.rglob('*.class')]],check=True)
 unsigned=w/'unsigned.apk';aligned=w/'aligned.apk'
 subprocess.run([str(tools/'aapt2'),'link','-I',str(platform),'--manifest',str(root/'AndroidManifest.xml'),'--min-sdk-version','26','--target-sdk-version','32','-o',str(unsigned)],check=True)
 with zipfile.ZipFile(unsigned,'a',compression=zipfile.ZIP_DEFLATED) as z:z.write(dex/'classes.dex','classes.dex')
 subprocess.run([str(tools/'zipalign'),'-p','-f','4',str(unsigned),str(aligned)],check=True)
 key=w/'fixture.jks'
 subprocess.run(['keytool','-genkeypair','-keystore',str(key),'-storepass','android','-keypass','android','-alias','probe','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Unprivileged Query Test Fixture'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 apk=out/'XiaoMo-Query-Probe-r6.apk'
 subprocess.run([str(tools/'apksigner'),'sign','--ks',str(key),'--ks-key-alias','probe','--ks-pass','pass:android','--out',str(apk),str(aligned)],check=True)
 verify=subprocess.check_output([str(tools/'apksigner'),'verify','--verbose','--print-certs',str(apk)],text=True)
 badging=subprocess.check_output([str(tools/'aapt2'),'dump','badging',str(apk)],text=True)
 permissions=subprocess.check_output([str(tools/'aapt2'),'dump','permissions',str(apk)],text=True)
 assert "package: name='cn.chopin.queryprobe'" in badging and 'uses-permission:' not in permissions
 assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in verify
 (out/'signature.txt').write_text(verify);(out/'badging.txt').write_text(badging);(out/'permissions.txt').write_text(permissions)
 report=dict(status='PASS_BUILD_SIGNATURE_AND_PERMISSION_FREE_MANIFEST_ONLY',apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),bytes=apk.stat().st_size,package='cn.chopin.queryprobe',root_requested=False,network_permission=False,hardware_validation=False,private_fixture_key_uploaded=False)
 (out/'build-record.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
