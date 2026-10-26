"""Compile the actual experimental ARM64 files; never link an Image."""
from pathlib import Path
import hashlib,json,os,shlex,shutil,subprocess
kernel=Path(os.environ['WORKSPACE'])/'android-kernel'
out=Path(os.environ['GITHUB_WORKSPACE'])/'susfs230-object-diagnostics';out.mkdir()
env=os.environ.copy();env['PATH']=env['CLANG_PATH']+':'+env['PATH'];env.pop('DISABLE_LTO',None)
args=['make','-j2','O=out','ARCH=arm64','CC=clang']
for k in ['CUSTOM_CMDS','EXTRA_CMDS','GCC_64','GCC_32']:args+=shlex.split(env.get(k,''))
here=Path(__file__).resolve().parent;manifest=json.loads((here/'manifest.json').read_text())
targets=['chopin_user_defconfig','init/version.o','security/selinux/flask.h','fs/susfs.o']+[r['file'][:-2]+'.o' for r in manifest['patches'] if r['file'].endswith('.c')]
targets+=['kernel/reboot.o','security/selinux/selinuxfs.o','security/selinux/hooks.o','arch/arm64/kernel/cpuinfo.o','drivers/kernelsu/ksu_main.o']
rows=[]
for target in targets:
    path=out/(target.replace('/','_')+'.log')
    with path.open('w') as log:
        rc=subprocess.run(args+[target],cwd=kernel,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    rows.append({'target':target,'exit':rc});print(json.dumps(rows[-1]),flush=True)
    if target=='chopin_user_defconfig' and rc: raise SystemExit(rc)
    if target=='chopin_user_defconfig':
        subprocess.run(['bash','scripts/config','--file','out/.config','-e','KSU_SUSFS_SUS_MAP'],cwd=kernel,check=True)
        with path.open('a') as log:
            subprocess.run(args+['olddefconfig'],cwd=kernel,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        assert 'CONFIG_KSU_SUSFS_SUS_MAP=y' in (kernel/'out/.config').read_text()

    obj=kernel/'out'/target
    if not rc and obj.is_file():shutil.copyfile(obj,out/target.replace('/','_'))
    (out/'commands.json').write_text(json.dumps(rows,indent=2))
if (kernel/'out/.config').is_file():shutil.copyfile(kernel/'out/.config',out/'built.config')
shutil.copyfile(here/'manifest.json',out/'source-manifest.json')
(out/'status.json').write_text(json.dumps({'status':'OBJECTS_PASS' if all(r['exit']==0 for r in rows) else 'OBJECTS_FAILED','image_built':False,'kpm_or_root_runtime_tested':False,'hardware_tested':False},indent=2))
raise SystemExit(any(r['exit'] for r in rows))
