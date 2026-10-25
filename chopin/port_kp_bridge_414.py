"""Use a dedicated kernel-only pt_regs endpoint on kernels without syscall wrappers."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);p=root/'kernel/patch/sukisu/sukisu.c'
s=p.read_text(encoding='utf-8')
old='''    if (!has_syscall_wrapper) return -EOPNOTSUPP;
    /* Hook the handler itself: a kernel direct call never enters invoke_syscall
     * or the global EL0 dispatcher. Prefer inline over the syscall table. */
    addr = kallsyms_lookup_name("__arm64_sys_truncate");
    if (!addr) addr = kallsyms_lookup_name("__arm64_sys_truncate.cfi_jt");
    if (!addr) addr = kallsyms_lookup_name("__arm64_sys_truncate.cfi");'''
new='''    /* The chopin 4.14 syscall table has sys_truncate(path,len), not a
     * pt_regs wrapper. Do not call or hook it with the wrong C prototype.
     * The paired SukiSU build provides a kernel-only pt_regs endpoint. */
    addr = kallsyms_lookup_name("ksu_kpm_bridge_trampoline");
    if (!addr) {
        if (!has_syscall_wrapper) return -EOPNOTSUPP;
        addr = kallsyms_lookup_name("__arm64_sys_truncate");
        if (!addr) addr = kallsyms_lookup_name("__arm64_sys_truncate.cfi_jt");
        if (!addr) addr = kallsyms_lookup_name("__arm64_sys_truncate.cfi");
    }'''
assert s.count(old)==1
p.write_text(s.replace(old,new,1),encoding='utf-8',newline='\n')
# A Linux-distribution cross compiler injects libc stack guards and outlined
# atomic helpers by default. This freestanding runtime supplies neither libc
# nor libgcc; match the original bare-metal compiler model explicitly.
p=root/'kernel/Makefile';s=p.read_text(encoding='utf-8')
anchor='CFLAGS += -g'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\nCFLAGS += -fno-stack-protector -fno-pie -mno-outline-atomics',1)
p.write_text(s,encoding='utf-8',newline='\n')
print('Paired KPM endpoint ported; EL0 passthrough and all framing checks retained')
