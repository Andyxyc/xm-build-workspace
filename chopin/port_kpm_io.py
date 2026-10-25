#!/usr/bin/env python3
"""Preserve KPM controls while enforcing the real 4.14 userspace-copy contract."""
from pathlib import Path
import sys
f=Path(sys.argv[1])/'KernelSU/kernel/extension/kpm/kpm.c'
s=f.read_text()
if (f.parent/'bridge.h').is_file():
    assert 'access_ok(VERIFY_WRITE, u64_to_user_ptr(cmd.result_code), sizeof(result))' in s
    for contract in ['len >= size', 'SUKISU_KPM_OUTPUT_MAX', '-ENAMETOOLONG', 'copy_to_user', 'result_code']:
        assert contract in s, contract
    # No user syscall in 4.14 has the required pt_regs prototype. This endpoint
    # is resolved by the paired runtime; until it is hooked it returns an error.
    endpoint='noinline __nocfi long ksu_kpm_bridge_trampoline(const struct pt_regs *regs)\n{\n    (void)regs;\n    /* Complete inline-hook window; the unhooked endpoint reports no support. */\n    __asm__ volatile("nop; nop; nop; nop" ::: "memory");\n    return -EOPNOTSUPP;\n}\nEXPORT_SYMBOL(ksu_kpm_bridge_trampoline);\n\n'
    needle='long __nocfi sukisu_kpm_bridge('
    assert s.count(needle)==1
    s=s.replace(needle,endpoint+needle,1)
    s=s.replace('long __nocfi sukisu_kpm_bridge(', 'noinline long __nocfi sukisu_kpm_bridge(',1)
    needle='        fn = (handler_t)find_kernel_symbol_exact("__arm64_sys_truncate");'
    replacement='        fn = (handler_t)find_kernel_symbol_exact("ksu_kpm_bridge_trampoline");\n        if (!fn) fn = (handler_t)find_kernel_symbol_exact("__arm64_sys_truncate");'
    assert s.count(needle)==1;s=s.replace(needle,replacement,1)
    s=s.replace('#include "bridge.h"','#include "bridge.h"\n#include <linux/export.h>',1)
    # Prefix private unity-build helpers to avoid colliding with other includes.
    for name in ['copy_string','copy_output','handle_kpm']:
        import re
        s=re.sub(r'\b'+name+r'\b','chopin_kpm_'+name,s)
    f.write_text(s,encoding='utf-8',newline='\n')
    print('Current KPM copy contract and real kernel-only endpoint retained')
    raise SystemExit(0)
def edit(old,new):
    global s
    assert s.count(old)==1,(old,s.count(old))
    s=s.replace(old,new,1)

for old,new in [
 ('        int size;','        int size = -EOPNOTSUPP;'),
 ('        if (!access_ok(VERIFY_WRITE, (void __user *)arg2, size))',
  '        if (size < 0) {\n            res = size;\n            goto exit;\n        }\n'
  '        if (size > sizeof(s->buf)) {\n            res = -EOVERFLOW;\n            goto exit;\n        }\n'
  '        if (!access_ok(VERIFY_WRITE, (void __user *)arg2, size))'),
 ('        res = copy_to_user(arg2, s->buf, size);',
  '        res = copy_to_user((void __user *)arg2, s->buf, size) ? -EFAULT : 0;'),
 ('        if (res > len) {','        if (res < 0)\n            goto exit;\n        if (res > len || res > sizeof(s->buf)) {'),
 ('        if (copy_to_user(arg1, s->buf, len) != 0)\n            pr_info("kpm: Copy to user failed.");',
  '        if (copy_to_user((void __user *)arg1, s->buf, res))\n            res = -EFAULT;'),
 ('        int len = strlen(s->buffer);',
  '        size_t len = strnlen(s->buffer, sizeof(s->buffer));\n'
  '        if (!arg1 || !outlen) {\n            res = -EINVAL;\n            goto exit;\n        }\n'
  '        if (!len || len == sizeof(s->buffer)) {\n            res = -ENODEV;\n            goto exit;\n        }'),
 ('        if (len >= outlen)\n            len = outlen - 1;',
  '        if (len >= outlen) {\n            len = outlen - 1;\n            s->buffer[len] = 0;\n        }'),
 ('        res = copy_to_user(arg1, s->buffer, len + 1);',
  '        res = copy_to_user((void __user *)arg1, s->buffer, len + 1) ? -EFAULT : 0;'),
 ('    if (copy_to_user(result_code, &res, sizeof(res)) != 0)\n        pr_info("kpm: Copy to user failed.");',
  '    if (copy_to_user((void __user *)result_code, &res, sizeof(res)))\n        return -EFAULT;'),
]: edit(old,new)

# Reject every failed or truncated string before invoking the patch backend.
copies=[
 ('strncpy_from_user(s->kernel_load_path, (const char __user *)arg1,\n                          255);','s->kernel_load_path','arg1'),
 ('strncpy_from_user(s->kernel_args_buffer,\n                              (const char __user *)arg2, 255);','s->kernel_args_buffer','arg2'),
]
for old,buf,arg in copies:
    edit(old,'do {\n            long copied = strncpy_from_user('+buf+', (const char __user *)'+arg+', sizeof('+buf+'));\n'
         '            if (copied < 0 || copied >= sizeof('+buf+')) {\n'
         '                res = copied < 0 ? copied : -ENAMETOOLONG;\n                goto exit;\n            }\n        } while (0);')
old='''        strncpy_from_user(s->kernel_name_buffer,
                          (const char __user *)arg1,
                          sizeof(s->kernel_name_buffer));'''
assert s.count(old)==2
new='''        {
            long copied = strncpy_from_user(s->kernel_name_buffer,
                (const char __user *)arg1, sizeof(s->kernel_name_buffer));
            if (copied <= 0 || copied >= sizeof(s->kernel_name_buffer)) {
                res = copied < 0 ? copied : -EINVAL;
                goto exit;
            }
        }'''
s=s.replace(old,new)
edit('        if (name_len <= 0) {','        if (name_len <= 0 || name_len >= sizeof(s->kpm_name)) {')
edit('        sukisu_kpm_control(s->kpm_name, s->kpm_args, arg_len, &res);',
     '        if (arg_len < 0 || arg_len >= sizeof(s->kpm_args)) {\n'
     '            res = arg_len < 0 ? arg_len : -ENAMETOOLONG;\n            goto exit;\n        }\n'
     '        sukisu_kpm_control(s->kpm_name, s->kpm_args, arg_len, &res);')
f.write_text(s)
print('KPM error, length and userspace-copy contracts preserved without disabling backend')
