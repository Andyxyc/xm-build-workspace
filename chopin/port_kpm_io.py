#!/usr/bin/env python3
"""Preserve KPM controls while enforcing the real 4.14 userspace-copy contract."""
from pathlib import Path
import sys
f=Path(sys.argv[1])/'KernelSU/kernel/extension/kpm/kpm.c'
s=f.read_text()
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
  '        int len = strnlen(s->buffer, sizeof(s->buffer));\n'
  '        if (!arg1 || !outlen || outlen > sizeof(s->buffer)) {\n            res = -EINVAL;\n            goto exit;\n        }\n'
  '        if (!len || len == sizeof(s->buffer)) {\n            res = -ENODEV;\n            goto exit;\n        }'),
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
