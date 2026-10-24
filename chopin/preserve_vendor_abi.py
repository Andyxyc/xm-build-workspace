#!/usr/bin/env python3
"""Keep public task/vfsmount layouts unchanged while retaining real SUSFS state.

This ARM64 4.14 port stores state in trailing storage of the kernel-owned
task/mount slab objects. It follows their existing allocation/free lifetimes,
inherits state during fork, and uses neither a side hash table nor CRC overrides.
"""
from pathlib import Path
import re,subprocess,sys
root=Path(sys.argv[1]).resolve()

def edit(file,old,new):
    text=file.read_text()
    assert text.count(old)==1,(str(file),old,text.count(old))
    file.write_text(text.replace(old,new,1))

edit(root/'include/linux/sched.h',
     '#ifdef CONFIG_KSU_SUSFS\n\tu64 susfs_task_state;\n\tu64 susfs_last_fake_mnt_id;\n#endif\n','')
edit(root/'include/linux/mount.h',
     '#ifdef CONFIG_KSU_SUSFS\n\tu64 susfs_mnt_id_backup;\n#endif\n','')

header='''/* SPDX-License-Identifier: GPL-2.0 */
#ifndef CHOPIN_SUSFS_STATE_H
#define CHOPIN_SUSFS_STATE_H
#include <linux/types.h>
struct task_struct;
struct chopin_susfs_task_state {
    u64 task_state;
    u64 last_fake_mnt_id;
};
struct chopin_susfs_task_state *chopin_susfs_task_state(struct task_struct *task);
#endif
'''
(root/'include/linux/chopin_susfs_state.h').write_text(header)
edit(root/'include/linux/susfs_def.h','#define KSU_SUSFS_DEF_H',
     '#define KSU_SUSFS_DEF_H\n#include <linux/chopin_susfs_state.h>')

f=root/'kernel/fork.c';text=f.read_text()
anchor='#ifndef CONFIG_ARCH_TASK_STRUCT_ALLOCATOR\nstatic struct kmem_cache *task_struct_cachep;'
assert text.count(anchor)==1
metadata='''#ifdef CONFIG_KSU_SUSFS
#include <linux/chopin_susfs_state.h>
#if !defined(CONFIG_ARM64) || defined(CONFIG_ARCH_TASK_STRUCT_ALLOCATOR) || defined(CONFIG_ARCH_WANTS_DYNAMIC_TASK_STRUCT)
#error "The chopin SUSFS tail-storage port requires the audited fixed ARM64 task allocator"
#endif
static struct chopin_susfs_task_state chopin_init_susfs_state;
struct chopin_susfs_task_state *chopin_susfs_task_state(struct task_struct *task)
{
    if (task == &init_task)
        return &chopin_init_susfs_state;
    return (void *)((char *)task + sizeof(struct task_struct));
}
#define CHOPIN_SUSFS_TASK_BYTES sizeof(struct chopin_susfs_task_state)
#else
#define CHOPIN_SUSFS_TASK_BYTES 0
#endif

'''
text=text.replace(anchor,metadata+anchor,1)
anchor='\t\t\tarch_task_struct_size, align,'
assert text.count(anchor)==1
text=text.replace(anchor,'\t\t\tarch_task_struct_size + CHOPIN_SUSFS_TASK_BYTES, align,',1)
anchor='\terr = arch_dup_task_struct(tsk, orig);'
assert text.count(anchor)==1
text=text.replace(anchor,anchor+'''
#ifdef CONFIG_KSU_SUSFS
    if (!err)
        *chopin_susfs_task_state(tsk) = *chopin_susfs_task_state(orig);
#endif
''',1)
f.write_text(text)

# The original mount slab is zero-allocated and freed by one cache throughout
# the tree. Reserve one u64 after the original private struct, leaving every
# original vfsmount and mount member at its stock offset.
f=root/'fs/namespace.c';text=f.read_text()
anchor='static inline struct hlist_head *m_hash(struct vfsmount *mnt, struct dentry *dentry)'
assert text.count(anchor)==1
helpers='''#ifdef CONFIG_KSU_SUSFS
static inline u64 *chopin_susfs_mount_backup(struct mount *mnt)
{
    return (void *)((char *)mnt + sizeof(struct mount));
}
#define CHOPIN_SUSFS_MOUNT_BYTES sizeof(u64)
#else
#define CHOPIN_SUSFS_MOUNT_BYTES 0
#endif

'''
text=text.replace(anchor,helpers+anchor,1)
anchor='kmem_cache_create("mnt_cache", sizeof(struct mount),'
assert text.count(anchor)==1
text=text.replace(anchor,'kmem_cache_create("mnt_cache", sizeof(struct mount) + CHOPIN_SUSFS_MOUNT_BYTES,',1)
text,n=re.subn(r'(\b\w+)->mnt\.susfs_mnt_id_backup',r'(*chopin_susfs_mount_backup(\1))',text)
assert n>=5,n
f.write_text(text)

files=list((root/'fs').rglob('*.c'))+[root/'KernelSU/kernel/hook/lsm_hook.c']
count=0
for f in files:
    raw=f.read_bytes()
    if b'->susfs_task_state' not in raw and b'->susfs_last_fake_mnt_id' not in raw:
        continue
    text=raw.decode('utf-8')
    new,n1=re.subn(r'(\b\w+)->susfs_task_state',r'chopin_susfs_task_state(\1)->task_state',text)
    new,n2=re.subn(r'(\b\w+)->susfs_last_fake_mnt_id',r'chopin_susfs_task_state(\1)->last_fake_mnt_id',new)
    if new!=text:
        f.write_text(new)
    count+=n1+n2
assert count>=20,count
if (root/'.git').exists():
    for name in ['include/linux/sched.h','include/linux/mount.h','fs/mount.h']:
        original=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+name]).decode()
        assert (root/name).read_text()==original,'Public/internal original layout changed: '+name
print('Real SUSFS state retained in slab tail storage; original task/vfsmount/mount declarations preserved')
