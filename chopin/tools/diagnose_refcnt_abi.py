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
source=(root/'chopin/vendor_refcnt_trace.c').read_text()
variants={'refcnt-original':source,'refcnt-without-size-typedef':re.sub(r'typedef char chopin_refcnt_record_must_be_536_bytes\[.*?\];','',source,flags=re.S)}
for name,text in variants.items():
    # This fixture uses only C builtins plus EXPORT_SYMBOL, a genksyms keyword.
    # Its include is unnecessary for direct genksyms parsing, not a kernel patch.
    text=re.sub(r'^#include[^\n]*\n','',text,flags=re.M)
    (out/(name+'.c')).write_text(text)
    with (out/(name+'.ver')).open('w') as dst,(out/(name+'.definitions')).open('w') as err:
        subprocess.run([str(out/'genksyms-host'),'-D','-T',str(out/(name+'.symtypes'))],input=text,text=True,stdout=dst,stderr=err,check=True)
    print(name,(out/(name+'.ver')).read_text())
