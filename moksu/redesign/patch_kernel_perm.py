#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grant trusted root ksud the same profile IOCTL permission as manager.
Narrow change: only GET_APP_PROFILE and SET_APP_PROFILE. All other private
ioctls keep their native 3.3.1 security policy.
"""
from pathlib import Path
import sys
def patch(root):
    f=Path(root)/"kernel/supercall/dispatch.c"
    code=f.read_text()
    for name,handler in (("GET_APP_PROFILE","do_get_app_profile"),("SET_APP_PROFILE","do_set_app_profile")):
        exact='''        .cmd = KSU_IOCTL_'''+name+''',
        .name = "'''+name+'''",
        .handler = '''+handler+''',
        .perm_check = only_manager'''
        if code.count(exact)!=1:raise ValueError(f"Unexpected KernelSU source mismatch in {name}")
        code=code.replace(exact,exact.replace("only_manager","manager_or_root"),1)
    f.write_text(code)
    print("MOKSU_ROOT_PERMISSION_MATCHED: 2 IOCTL handlers only")
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_kernel_perm.py source")
    patch(sys.argv[1])
