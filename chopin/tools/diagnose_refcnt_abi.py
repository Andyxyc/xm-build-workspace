#!/usr/bin/env python3
"""Build the exact vendor genksyms and inspect a public, task-owned C fixture."""
from pathlib import Path
import subprocess,urllib.request,re,shutil
root=Path.cwd();out=root/'tools-out';work=root/'abi-fixture';work.mkdir(exist_ok=True)
base='https://raw.githubusercontent.com/ChopinKernels/android_kernel_chopin_android_T/0647a49c9557faa92b90c4ae188587787226be9e/'
sources=['genksyms.c','genksyms.h','keywords.c','lex.lex.c_shipped','parse.tab.c_shipped','parse.tab.h_shipped']
for name in sources:
    with urllib.request.urlopen(base+'scripts/genksyms/'+name,timeout=30) as response:
        data=response.read()
    dest=work/name.removesuffix('_shipped');dest.write_bytes(data)
for cc,name in [('gcc','genksyms-host'),('aarch64-linux-gnu-gcc','genksyms-aarch64')]:
    subprocess.run([cc,'-O2','-static','-I'+str(work),str(work/'genksyms.c'),str(work/'lex.lex.c'),str(work/'parse.tab.c'),'-o',str(out/name)],check=True)
(work/'linux').mkdir(exist_ok=True)
with urllib.request.urlopen(base+'include/linux/export.h',timeout=30) as response:
    (work/'linux/export.h').write_bytes(response.read())
# C comments must be removed by the preprocessor and real header line markers
# must be kept. genksyms intentionally treats .c-local compound types as opaque.
shutil.copyfile(root/'chopin/vendor_refcnt_trace.h',work/'chopin_vendor_refcnt_trace.h')
source=(root/'chopin/vendor_refcnt_trace.c').read_text()
fixture=work/'refcnt-public-header.c';fixture.write_text(source)
text=subprocess.check_output(['gcc','-E','-D__GENKSYMS__','-D__KERNEL__','-DCONFIG_MODULES','-I'+str(work),str(fixture)],text=True)
name='refcnt-public-header'
(out/(name+'.i')).write_text(text)
with (out/(name+'.ver')).open('w') as dst,(out/(name+'.definitions')).open('w') as err:
    subprocess.run([str(out/'genksyms-host'),'-D','-T',str(out/(name+'.symtypes'))],input=text,text=True,stdout=dst,stderr=err,check=True)
versions=(out/(name+'.ver')).read_text()
assert re.search(r'__crc_trace_idx\s*=\s*0x18d43e99',versions),versions
assert re.search(r'__crc_trace_array\s*=\s*0xe476cdfb',versions),versions
print(name,versions)
