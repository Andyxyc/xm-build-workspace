"""Compile genuine, isolated header-context probes; never emits a kernel Image.

Including real headers before exports tests genksyms visibility, without altering declarations,
symbol CRCs or module-loading policy. These are diagnostics, not kernel patches.
"""
from pathlib import Path
import os,subprocess,shlex,json,re,hashlib
root=Path(os.environ['WORKSPACE'])/'android-kernel'
out=Path(os.environ['GITHUB_WORKSPACE'])/'mm-diagnostics';out.mkdir(exist_ok=True)
env=os.environ.copy();env['PATH']=env['CLANG_PATH']+':'+env['PATH'];env.pop('DISABLE_LTO',None)
args=['make','-j2','O=out','ARCH=arm64','CC=clang']
for key in ['CUSTOM_CMDS','EXTRA_CMDS','GCC_64','GCC_32']:args+=shlex.split(env.get(key,''))
def run(target,label,extra=None):
    with (out/(label+'.log')).open('w') as log:
        p=subprocess.run(args+(extra or [])+[target],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    return p.returncode
assert run('chopin_user_defconfig','configure')==0
if env.get('MM_DIAG_CONTROLS_ONLY')=='1':
    rows=[];failed=False
    controls=[('mm/backing-dev','bdi_register_va','5d89a086'),
              ('kernel/sched/core','wake_up_process','609fadad'),
              ('fs/inode','iget_locked','5eab1b42'),
              ('fs/file_table','alloc_file','dc878e5d'),
              ('drivers/base/core','device_add','74d18288')]
    for unit,symbol,expected in controls:
        label=unit.replace('/','_');extra=[]
        if unit.startswith('kernel/'):
            # A direct nested .o target skips kernel/Makefile's inherited paths.
            # Restore its actual source-defined flags rather than hiding errors.
            flags=re.findall(r'^subdir-ccflags-y\s*\+=\s*(.+)$',(root/'kernel/Makefile').read_text(),re.M)
            assert len(flags)==5,flags
            extra=['KCFLAGS='+' '.join(flags).replace('$(srctree)',str(root))]
        code=run(unit+'.o',label,extra)
        if code!=0:
            failed=True;rows.append(dict(unit=unit,exit_code=code,status='COMPILE_FAILED'))
            (out/'matching-controls.json').write_text(json.dumps(rows,indent=2));continue
        text=subprocess.check_output(['aarch64-linux-gnu-nm',str(root/'out'/(unit+'.o'))],text=True)
        values={n:v for v,n in re.findall(r'^([0-9a-f]+)\s+[Aa]\s+__crc_(\w+)$',text,re.M)}
        match=int(values[symbol],16)==int(expected,16)
        failed=failed or not match
        (out/(label+'.symtypes')).write_bytes((root/'out'/(unit+'.symtypes')).read_bytes())
        row=dict(unit=unit,symbol=symbol,actual_crc=values[symbol],stock_crc=expected,match=match);rows.append(row);print(json.dumps(row),flush=True)
        (out/'matching-controls.json').write_text(json.dumps(rows,indent=2))
    (out/'matching-controls.json').write_text(json.dumps(rows,indent=2))
    (out/'status.txt').write_text('Read-only ABI diagnosis: stock-matching controls. No Image built.\n')
    raise SystemExit(int(failed))
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
            marker=b'#include "internal.h"'
            assert original.count(marker)==1
            probe=original.replace(marker,b'#include <'+header.encode()+b'>\n'+marker,1) if header else original
            src.write_bytes(probe)
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
        baseline=next(x for x in report if x['unit']==unit and x['header'] is None)
        assert any(x.get('selected_crc')!=baseline['selected_crc'] for x in report if x['unit']==unit and x['exit_code']==0), 'Header probes did not affect export-time type visibility'
    finally:
        src.write_bytes(original);assert hashlib.sha256(src.read_bytes()).hexdigest()==digest
(out/'status.txt').write_text('Diagnostic objects only. No Image, boot image or flash package built.\n')
