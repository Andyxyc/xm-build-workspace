from pathlib import Path
import os,subprocess,zipfile,json,hashlib
root=Path(__file__).resolve().parent;sdk=Path(os.environ['ANDROID_SDK_ROOT'])
tools=sorted(p for p in (sdk/'build-tools').iterdir() if (p/'aapt2').is_file() and (p/'d8').is_file())[-1]
platform=sorted((sdk/'platforms').glob('android-*/android.jar'))[-1]
out=Path('acceptance-evidence');out.mkdir();classes=out/'classes';classes.mkdir();dex=out/'dex';dex.mkdir()
def call(a):subprocess.run(list(map(str,a)),check=True)
call([tools/'aapt2','link','-I',platform,'--manifest',root/'AndroidManifest.xml','--min-sdk-version','29','--target-sdk-version','32','-o',out/'unsigned.apk'])
call(['javac','-source','8','-target','8','-cp',platform,'-d',classes,*root.glob('*.java')])
call([tools/'d8','--lib',platform,'--min-api','29','--output',dex,*classes.rglob('*.class')])
with zipfile.ZipFile(out/'unsigned.apk','a') as z:z.write(dex/'classes.dex','classes.dex')
call([tools/'zipalign','-p','4',out/'unsigned.apk',out/'aligned.apk'])
call(['keytool','-genkeypair','-keystore',out/'ephemeral-probe.jks','-storepass','android','-keypass','android','-alias','probe','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Chopin unprivileged acceptance probe'])
apk=out/'Chopin-Acceptance-Probe.apk'
call([tools/'apksigner','sign','--ks',out/'ephemeral-probe.jks','--ks-key-alias','probe','--ks-pass','pass:android','--out',apk,out/'aligned.apk'])
with (out/'signature.txt').open('w') as f:subprocess.run([str(tools/'apksigner'),'verify','--verbose','--print-certs',str(apk)],stdout=f,check=True)
with (out/'badging.txt').open('w') as f:subprocess.run([str(tools/'aapt2'),'dump','badging',str(apk)],stdout=f,check=True)
(out/'build-record.json').write_text(json.dumps({'source_commit':os.environ['GITHUB_SHA'],'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'permissions_requested':[],'root_request':False,'network_permission':False,'root_manager':False,'key_policy':'ephemeral validation key; not uploaded'},indent=2))
