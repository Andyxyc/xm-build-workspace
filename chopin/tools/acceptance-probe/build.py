from pathlib import Path
import os,subprocess,zipfile,json,hashlib
root=Path(__file__).resolve().parent;sdk=Path(os.environ['ANDROID_SDK_ROOT'])
tools=sorted(p for p in (sdk/'build-tools').iterdir() if (p/'aapt2').is_file() and (p/'d8').is_file())[-1]
platform=next((sdk/'platforms'/('android-'+str(n))/'android.jar' for n in [35,34,33,36] if (sdk/'platforms'/('android-'+str(n))/'android.jar').is_file()),None)
assert platform is not None,'A preinstalled stable public Android SDK is required'
out=Path('acceptance-evidence');out.mkdir();classes=out/'classes';classes.mkdir();dex=out/'dex';dex.mkdir()
def call(a):subprocess.run(list(map(str,a)),check=True)
ndks=sorted(p for p in (sdk/'ndk').glob('*') if (p/'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang').is_file())
assert ndks,'Use the runner preinstalled NDK; no local virtualization or NDK download'
cc=ndks[-1]/'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang'
call([cc,'-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',root/'native_probe.c','-o',out/'libchopin_probe.so'])
call([cc,'-O2','-Wall','-Wextra','-Werror','-DCHOPIN_SOCKET_LISTENER',root/'native_probe.c','-o',out/'chopin_socket_listener'])
call([tools/'aapt2','link','-I',platform,'--manifest',root/'AndroidManifest.xml','--min-sdk-version','29','--target-sdk-version','32','-o',out/'unsigned.apk'])
call(['javac','-source','8','-target','8','-cp',platform,'-d',classes,*root.glob('*.java')])
call([tools/'d8','--lib',platform,'--min-api','29','--output',dex,*classes.rglob('*.class')])
with zipfile.ZipFile(out/'unsigned.apk','a') as z:
 z.write(dex/'classes.dex','classes.dex')
 z.write(out/'libchopin_probe.so','lib/arm64-v8a/libchopin_probe.so')
call([tools/'zipalign','-p','4',out/'unsigned.apk',out/'aligned.apk'])
call(['keytool','-genkeypair','-keystore',out/'ephemeral-probe.jks','-storepass','android','-keypass','android','-alias','probe','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Chopin unprivileged acceptance probe'])
apk=out/'Chopin-Acceptance-Probe.apk'
call([tools/'apksigner','sign','--ks',out/'ephemeral-probe.jks','--ks-key-alias','probe','--ks-pass','pass:android','--out',apk,out/'aligned.apk'])
with (out/'signature.txt').open('w') as f:subprocess.run([str(tools/'apksigner'),'verify','--verbose','--print-certs',str(apk)],stdout=f,check=True)
with (out/'badging.txt').open('w') as f:subprocess.run([str(tools/'aapt2'),'dump','badging',str(apk)],stdout=f,check=True)
(out/'build-record.json').write_text(json.dumps({'source_commit':os.environ['GITHUB_SHA'],'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'permissions_requested':[],'root_request':False,'network_permission':False,'root_manager':False,'key_policy':'ephemeral validation key; not uploaded'},indent=2))
