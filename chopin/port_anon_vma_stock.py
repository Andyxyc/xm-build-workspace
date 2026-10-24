"""Restore the real upstream rmap fix present in the supplied stock kernel."""
from pathlib import Path
import sys,hashlib,subprocess
if not __debug__:raise SystemExit('Normal Python mode is required')
root=Path(sys.argv[1]).resolve()
patch=Path(__file__).resolve().parent/'patches/anon-vma-double-reuse-stock.patch'
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='f6835f2526fd7692251833f4006b4cb1855fa3ec5120afb2f1a34530e52487a3'
protected=['include/linux/xattr.h','include/linux/mm_types.h','include/linux/sched.h','arch/arm64/configs/chopin_user_defconfig']
before={name:(root/name).read_bytes() for name in protected}
subprocess.run(['git','-C',str(root),'apply','--check','--whitespace=error',str(patch)],check=True)
subprocess.run(['git','-C',str(root),'apply','--whitespace=error',str(patch)],check=True)
h=(root/'include/linux/rmap.h').read_text();c=(root/'mm/rmap.c').read_text()
assert 'unsigned long num_children;' in h and 'unsigned long num_active_vmas;' in h
assert 'unsigned long private;' in h and '->degree' not in c
assert 'anon_vma->num_children = 0;' in c and 'anon_vma->num_active_vmas = 0;' in c
assert 'anon_vma->parent->num_children++;' in c and 'anon_vma->parent->num_children--;' in c
assert 'anon_vma->num_active_vmas == 0)' in c and 'vma->anon_vma->num_active_vmas--;' in c
assert all((root/name).read_bytes()==data for name,data in before.items())
print('Applied complete upstream 2555283 rmap lifecycle fix; no CRC overrides or hidden layout fields')
