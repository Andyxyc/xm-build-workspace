"""Compile genuine, isolated header-context probes; never emits a kernel Image.

Appending real headers tests genksyms visibility, without altering declarations,
symbol CRCs or module-loading policy. These are diagnostics, not kernel patches.
"""
from pathlib import Path
import os,subprocess,shlex,json,re,hashlib
root=Path(os.environ['WORKSPACE'])/'android-kernel'
out=Path(os.environ['GITHUB_WORKSPACE'])/'mm-diagnostics';out.mkdir(exist_ok=True)
env=os.environ.copy();env['PATH']=env['CLANG_PATH']+':'+env['PATH'];env.pop('DISABLE_LTO',None)
args=['make','-j2','O=out','ARCH=arm64','CC=clang']
for key in ['CUSTOM_CMDS','EXTRA_CMDS','GCC_64','GCC_32']:args+=shlex.split(env.get(key,''))
def run(target,label):
    with (out/(label+'.log')).open('w') as log:
        p=subprocess.run(args+[target],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    return p.returncode
assert run('chopin_user_defconfig','configure')==0
headers=['linux/netdevice.h','linux/fs_struct.h','linux/fdtable.h','linux/module.h',
         'linux/exportfs.h','linux/fscrypt.h','linux/pipe_fs_i.h','linux/binfmts.h',
         'linux/blk-mq.h','linux/device.h','linux/iommu.h','linux/key-type.h',
         'linux/posix_acl.h','linux/utsname.h','linux/futex.h','linux/aio.h',
         'linux/trace.h','linux/kernfs.h','linux/of.h','linux/pm_qos.h']
report=[]
for unit,symbol in [('mmap','find_vma'),('memory','remap_pfn_range')]:
    src=root/'mm'/(unit+'.c');original=src.read_bytes();digest=hashlib.sha256(original).hexdigest()
    try:
        for header in [None]+headers:
            label=unit+'-'+(header.replace('/','_').replace('.','_') if header else 'baseline')
            src.write_bytes(original+(b'\n#include <'+header.encode()+b'>\n' if header else b''))
            for suffix in ['o','symtypes']:(root/'out/mm'/(unit+'.'+suffix)).unlink(missing_ok=True)
            code=run('mm/'+unit+'.o',label)
            row=dict(unit=unit,header=header,exit_code=code,original_sha256=digest)
            if code==0:
                text=subprocess.check_output(['aarch64-linux-gnu-nm',str(root/'out/mm'/(unit+'.o'))],text=True)
                row['crc']={n:v for v,n in re.findall(r'^([0-9a-f]+)\s+[Aa]\s+__crc_(\w+)$',text,re.M)}
                assert symbol in row['crc'],row
                row['selected_crc']=row['crc'][symbol]
                (out/(label+'.symtypes')).write_bytes((root/'out/mm'/(unit+'.symtypes')).read_bytes())
            report.append(row);print(json.dumps(row),flush=True)
            (out/'context-results.json').write_text(json.dumps(report,indent=2))
    finally:
        src.write_bytes(original);assert hashlib.sha256(src.read_bytes()).hexdigest()==digest
(out/'status.txt').write_text('Diagnostic objects only. No Image, boot image or flash package built.\n')
