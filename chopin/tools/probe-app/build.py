"""Build a small unprivileged Android probe using the runner's existing SDK."""
from pathlib import Path
import os,subprocess,tempfile,zipfile,hashlib,json
root=Path(__file__).resolve().parent
sdk=Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','/usr/local/lib/android/sdk')))
platform=sdk/'platforms/android-35/android.jar'
assert platform.is_file(),'Runner Android 35 SDK is required; do not download another SDK blindly'
tools=sorted(p for p in (sdk/'build-tools').iterdir() if (p/'aapt2').is_file() and (p/'d8').is_file())[-1]
out=Path('probe-app-out');out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='chopin-probe-') as tmp:
    work=Path(tmp);classes=work/'classes';classes.mkdir();dex=work/'dex';dex.mkdir()
    subprocess.run(['javac','-source','8','-target','8','-bootclasspath',str(platform),'-d',str(classes),str(root/'ProbeActivity.java')],check=True)
    subprocess.run([str(tools/'d8'),'--lib',str(platform),'--min-api','26','--output',str(dex),*[str(p) for p in classes.rglob('*.class')]],check=True)
    unsigned=work/'unsigned.apk'
    subprocess.run([str(tools/'aapt2'),'link','-I',str(platform),'--manifest',str(root/'AndroidManifest.xml'),'--min-sdk-version','26','--target-sdk-version','32','-o',str(unsigned)],check=True)
    with zipfile.ZipFile(unsigned,'a',compression=zipfile.ZIP_DEFLATED) as z:z.write(dex/'classes.dex','classes.dex')
    # This ephemeral key signs only this unprivileged test fixture. Never upload it.
    store=work/'fixture.jks'
    subprocess.run(['keytool','-genkeypair','-keystore',str(store),'-storepass','android','-keypass','android','-alias','probe','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Chopin Unprivileged Test Fixture'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    apk=out/'Chopin-Unprivileged-Probe.apk'
    subprocess.run([str(tools/'apksigner'),'sign','--ks',str(store),'--ks-key-alias','probe','--ks-pass','pass:android','--key-pass','pass:android','--out',str(apk),str(unsigned)],check=True)
    verify=subprocess.check_output([str(tools/'apksigner'),'verify','--verbose','--print-certs',str(apk)],text=True)
    (out/'apk-signature-verification.txt').write_text(verify)
    dump=subprocess.check_output([str(tools/'aapt2'),'dump','badging',str(apk)],text=True)
    assert "package: name='cn.chopin.kernelprobe'" in dump and 'android.permission.INTERNET' not in dump
    (out/'apk-badging.txt').write_text(dump)
    (out/'build-record.json').write_text(json.dumps(dict(sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),bytes=apk.stat().st_size,package='cn.chopin.kernelprobe',root_requested=False,network_permission=False,hardware_validation=False,build_tools=tools.name),indent=2))
    print((out/'build-record.json').read_text())
