#!/usr/bin/env python3
"""Port SUSFS v1.5.5 readdir path hiding to chopin's divergent 4.14 VFS.

The upstream 4.14 patch's readdir hunk #2 matches compat_filldir incorrectly
at a huge offset; #4/#5 reject. Never use fuzzy relocation here.
Remove only fs/readdir.c's hunks from the borrowed patch and integrate all
five directory callbacks by exact function-scoped anchors.
"""
from pathlib import Path
import hashlib
import sys

patchfile=Path(sys.argv[1]).resolve()
kernel=Path(sys.argv[2]).resolve()
original=patchfile.read_text()
start=original.index("diff --git a/fs/readdir.c b/fs/readdir.c")
end=original.index("diff --git a/fs/stat.c b/fs/stat.c",start)
readdir_hunks=original[start:end]
assert readdir_hunks.count("@@") == 10, "SUSFS readdir upstream hunk count changed"
patched=original[:start]+original[end:]
assert patched.count("diff --git a/fs/readdir.c") == 0
patchfile.write_text(patched)
print("Preserved original SUSFS readdir patch SHA256:",hashlib.sha256(readdir_hunks.encode()).hexdigest())
print("Kept all remaining SUSFS core patches, removed only obsolete readdir contexts.")

p=kernel/"fs/readdir.c"
text=p.read_text()
inc="#include <linux/uaccess.h>"
assert text.count(inc)==1,"4.14 readdir include anchor changed"
extra="""#ifdef CONFIG_KSU_SUSFS_SUS_PATH
#include <linux/susfs_def.h>
extern int susfs_sus_ino_for_filldir64(unsigned long ino);
#endif
"""
if "extern int susfs_sus_ino_for_filldir64" not in text:
    text=text.replace(inc,inc+"\n"+extra,1)

hook="""#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    if (likely(current->susfs_task_state & TASK_STRUCT_NON_ROOT_USER_APP_PROC) &&
        susfs_sus_ino_for_filldir64(ino))
        return 0;
#endif
"""
targets={
 "fillonedir":"\td_ino = ino;",
 "filldir":"\tbuf->error = -EINVAL;\t/* only used if we fail.. */",
 "filldir64":"\tbuf->error = -EINVAL;\t/* only used if we fail.. */",
 "compat_fillonedir":"\td_ino = ino;",
 "compat_filldir":"\td_ino = ino;",
}
for func,anchor in targets.items():
    marker=f"static int {func}("
    assert text.count(marker)==1,f"Missing or duplicated {func}"
    start=text.index(marker)
    finish=text.find("\n}\n",start)
    assert finish>start,f"Could not parse {func} body"
    sec=text[start:finish]
    assert sec.count(anchor)==1,f"{func} expected one injection anchor, got {sec.count(anchor)}"
    if "susfs_sus_ino_for_filldir64(ino)" not in sec:
        sec=sec.replace(anchor,hook+anchor,1)
        text=text[:start]+sec+text[finish:]
    print("port verified:",func)
p.write_text(text)
for func in targets:
    pos=text.index(f"static int {func}(")
    body=text[pos:text.index("\n}\n",pos)]
    assert body.count("susfs_sus_ino_for_filldir64(ino)")==1
print("All five readdir callbacks carry SUSFS checks; no mislocated hunks.")
