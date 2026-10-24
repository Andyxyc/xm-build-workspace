#!/usr/bin/env python3
from pathlib import Path
import subprocess,sys

src=Path(sys.argv[1]); out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
s=(src/'ksu_susfs/jni/main.c').read_text()
s=s.replace('#include <android/log.h>', '#include <limits.h>')
assert s.count('bool                    is_statically;')==1
s=s.replace('bool                    is_statically;', 'int                     is_statically;',1)
for field,replacement in [('st_atime_nsec','st_atim.tv_nsec'),('st_mtime_nsec','st_mtim.tv_nsec'),('st_ctime_nsec','st_ctim.tv_nsec'),('st_atimensec','st_atim.tv_nsec'),('st_mtimensec','st_mtim.tv_nsec'),('st_ctimensec','st_ctim.tv_nsec')]:
    s=s.replace(field,replacement)
target=out/'ksu_susfs_155.c';target.write_text(s)
subprocess.run(['aarch64-linux-gnu-gcc','-O2','-static','-Wall',str(target),'-o',str(out/'ksu_susfs_155')],check=True)
