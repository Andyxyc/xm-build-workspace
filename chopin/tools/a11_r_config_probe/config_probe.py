"""Cloud-only two-object config experiment, never a flashable kernel build."""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def run(args, log, env):
    with log.open('w',encoding='utf-8') as f:
        p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env)
        for line in p.stdout:
            f.write(line); print(line,end='',flush=True)
        if p.wait(): raise subprocess.CalledProcessError(p.returncode,args)


def config(path):
    return dict(line.split('=',1) for line in path.read_text().splitlines() if line.startswith('CONFIG_') and '=' in line)


def main():
    assert os.name=='posix' and os.environ.get('GITHUB_ACTIONS')=='true'
    here=Path(__file__).resolve().parent
    workspace=Path(os.environ['WORKSPACE']); kernel=workspace/'android-kernel'
    output=Path(os.environ['GITHUB_WORKSPACE'])/'r-config-object-evidence'
    output.mkdir(exist_ok=True)
    report={'status':'IN_PROGRESS','source_commit':os.environ['GITHUB_SHA'],
        'kernel_source':'2af31af37e12a338fddca780044f8b182c23ed9a',
        'stock_config_source_run':41237793221,
        'targets':['kernel/module.o'],'full_Image_built':False,'flashed':False,
        'crc_overrides_used':False,'module_validation_disabled':False,'variants':[]}
    env=os.environ.copy()
    env['PATH']=':'.join(str(workspace/x/'bin') for x in ['clang','gcc-64','gcc-32'])+':'+env['PATH']
    env['LD_LIBRARY_PATH']=str(workspace/'clang/lib64')+':'+env.get('LD_LIBRARY_PATH','')
    assert subprocess.check_output(['git','-C',str(kernel),'rev-parse','HEAD'],text=True).strip()==report['kernel_source']
    assert not subprocess.check_output(['git','-C',str(kernel),'status','--porcelain'])
    assert subprocess.check_output(['git','-C',str(workspace/'clang'),'rev-parse','HEAD'],text=True).strip()=='b62936c20dfd8fabd680b8879e2aa0a3cc1b024a'
    assert sha(kernel/'arch/arm64/configs/chopin_user_defconfig')=='414f9454e7a177f22d9531987ff980bff2eea68c6b0858dabdf132ca0453d06d'
    delta_path=here/'stock-config-delta.json'
    delta=json.loads(delta_path.read_text())
    assert len(delta['deltas'])==14
    report['delta_sha256']=sha(delta_path)
    try:
        for name, changes in [('native',[]),('stock14',delta['deltas'])]:
            out=kernel/('out-config-'+name)
            base=['make','-C',str(kernel),'O='+str(out),'ARCH=arm64',
                'CC=ccache '+str(workspace/'clang/bin/clang'),'LD=ld.lld','AR=llvm-ar','NM=llvm-nm',
                'STRIP=llvm-strip','OBJCOPY=llvm-objcopy','OBJDUMP=llvm-objdump','CLANG_TRIPLE=aarch64-linux-gnu-',
                'CROSS_COMPILE='+str(workspace/'gcc-64/bin/aarch64-linux-android-'),
                'CROSS_COMPILE_ARM32='+str(workspace/'gcc-32/bin/arm-linux-androideabi-'),'KBUILD_SYMTYPES=1']
            row={'name':name,'requested_stock_changes':changes}
            report['variants'].append(row)
            run(base+['chopin_user_defconfig'],output/(name+'-defconfig.log'),env)
            if name=='native':
                assert sha(out/'.config')=='a588493bffac0acdf0e573603482c0598403e8f0a4096802213071ef04e89863'
            for change in changes:
                key,value=change['key'],change['stock']
                assert re.fullmatch('CONFIG_[A-Z0-9_]+',key)
                opt={'y':['-e'],'m':['-m'],'n':['-d']}.get(value,['--set-val'])
                args=[str(kernel/'scripts/config'),'--file',str(out/'.config')]+opt+[key[7:]]
                if opt==['--set-val']: args.append(value)
                subprocess.run(args,check=True,cwd=kernel,env=env)
            if changes: run(base+['olddefconfig'],output/(name+'-olddefconfig.log'),env)
            values=config(out/'.config')
            row['unretained_stock_options']=[dict(c,actual=values.get(c['key'],'n')) for c in changes if values.get(c['key'],'n')!=c['stock']]
            row['config_sha256']=sha(out/'.config')
            shutil.copyfile(out/'.config',output/(name+'.config'))
            run(base+['-j2','kernel/module.o'],output/(name+'-module-object.log'),env)
            text=subprocess.check_output([str(workspace/'clang/bin/llvm-nm'),'--defined-only',str(out/'kernel/module.o')],text=True,env=env)
            (output/(name+'-nm.txt')).write_text(text,encoding='utf-8')
            crcs={m[3]:m[1][-8:].lower() for line in text.splitlines() if (m:=re.fullmatch(r'([0-9a-fA-F]+)\s+([Aa])\s+__crc_(\w+)',line))}
            assert 'module_layout' in crcs
            row['object_crc_exports']=crcs
            row['module_layout']=crcs['module_layout']
            row['stock_module_layout']='2d3d4373'
            row['stock_module_layout_match']=row['module_layout']=='2d3d4373'
            if name=='native': assert row['module_layout']=='41891213'
            shutil.copyfile(out/'kernel/module.symtypes',output/(name+'-module.symtypes'))
            row['module_symtypes_sha256']=sha(out/'kernel/module.symtypes')
        report['status']='PASS_TWO_OBJECT_CONFIG_EXPERIMENT_NOT_FIRMWARE_COMPATIBILITY'
    except Exception as e:
        report['status']='FAIL_DIAGNOSTIC_NO_COMPATIBILITY_CLAIM'
        report['error']=type(e).__name__+': '+str(e)
        raise
    finally:
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
