#!/usr/bin/env python3
"""Accurate availability gating for optional SukiSU CPU spoof on ARM64 Linux 4.14.

On this platform the vDSO CPU spoof implementation assumes a modern
vdso/datapage.h and clocksource layout. Never compile it against mismatched
headers or provide a fake positive capability. All demanded SukiSU, SUSFS,
and KPM paths remain enabled.
"""
from pathlib import Path
import sys

kernel=Path(sys.argv[1]).resolve()
makefile=(kernel/"Makefile").read_text()
assert "VERSION = 4" in makefile and "PATCHLEVEL = 14" in makefile, "Only apply to kernel 4.14"

def replace(path, before, after):
    target=kernel/path
    content=target.read_text()
    if after in content:
        print("already guarded:",path)
        return
    if content.count(before)!=1:
        raise SystemExit(f"Unexpected optional extension anchor in {path}: {content.count(before)}")
    target.write_text(content.replace(before,after,1))
    print("guarded:",path)

replace("KernelSU/kernel/ksu_main.c",
        '#include "extension/cpu_spoof.c"',
        '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n#include "extension/cpu_spoof.c"\n#endif')

s=(kernel/"KernelSU/kernel/extension/extension.c").read_text()
start=s.index('    static const struct ksu_extension_handler cpu_spoof_handler = {')
end=s.index('    static const struct ksu_extension_handler umount_paths_handler = {',start)
original=s[start:end]
assert original.count("cpu_spoof_handler")==1
guard='#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n'+original+'#endif\n'
replace("KernelSU/kernel/extension/extension.c",original,guard)

replace("KernelSU/kernel/extension/extension.c",
        '    if (ksu_register_extension_handler(&cpu_spoof_handler))\n        pr_err("extension: failed to register cpu_spoof\\n");',
        '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n'
        '    if (ksu_register_extension_handler(&cpu_spoof_handler))\n'
        '        pr_err("extension: failed to register cpu_spoof\\n");\n#endif')
print("CPU spoof not advertised on 4.14; KPM, SUSFS and root handlers remain intact.")
