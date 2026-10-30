#!/usr/bin/env python3
"""Verify shared native UAPI and unchanged manager files. SPDX-License-Identifier: GPL-3.0-or-later"""
import json,re,subprocess,sys,tempfile
from pathlib import Path
from prepare_core import manifest,digest
LEGACY={
'KSU_IOCTL_GRANT_ROOT':19201,'KSU_IOCTL_GET_INFO':2148551426,'KSU_IOCTL_GET_INFO_LEGACY':2147502850,
'KSU_IOCTL_REPORT_EVENT':1073761027,'KSU_IOCTL_SET_SEPOLICY':3221244676,'KSU_IOCTL_CHECK_SAFEMODE':2147502853,
'KSU_IOCTL_GET_ALLOW_LIST':3221244678,'KSU_IOCTL_GET_DENY_LIST':3221244679,'KSU_IOCTL_NEW_GET_ALLOW_LIST':3221506822,
'KSU_IOCTL_NEW_GET_DENY_LIST':3221506823,'KSU_IOCTL_UID_GRANTED_ROOT':3221244680,'KSU_IOCTL_UID_SHOULD_UMOUNT':3221244681,
'KSU_IOCTL_GET_MANAGER_APPID':2147502858,'KSU_IOCTL_GET_APP_PROFILE':3221244683,'KSU_IOCTL_SET_APP_PROFILE':1073761036,
'KSU_IOCTL_GET_FEATURE':3221244685,'KSU_IOCTL_SET_FEATURE':1073761038,'KSU_IOCTL_GET_WRAPPER_FD':1073761039,
'KSU_IOCTL_MANAGE_MARK':3221244688,'KSU_IOCTL_NUKE_EXT4_SYSFS':1073761041,'KSU_IOCTL_ADD_TRY_UMOUNT':1073761042,
'KSU_IOCTL_SET_INIT_PGRP':19219,'KSU_IOCTL_GET_SULOG_FD':1074023188,'KSU_IOCTL_DISABLE_ESCAPE_TO_ROOT':19221,
'KSU_IOCTL_STEALTH_GET':2147568409,'KSU_IOCTL_STEALTH_SET':1073826586}

def validate(source: Path,out: Path) -> None:
    link=source/'manager/app/src/main/cpp/uapi'
    if not link.is_symlink() or link.resolve()!=source/'uapi':
        raise RuntimeError('Manager JNI must use the same verified root UAPI headers')
    header=(source/'uapi/supercall.h').read_text()
    names=re.findall(r'^static const __u32 (KSU_IOCTL_[A-Z0-9_]+)\s*=',header,re.M)
    if len(names)!=27 or len(set(names))!=27: raise RuntimeError('Unexpected IOCTL set')
    with tempfile.TemporaryDirectory() as temp:
        code=Path(temp)/'abi.c';exe=Path(temp)/'abi'
        code.write_text('#include <stdbool.h>\n#include <stdio.h>\n#include "uapi/supercall.h"\nint main(void){\n'+''.join(f'printf("{n}=%u\\n",(unsigned int){n});\n' for n in names+['KERNEL_SU_UAPI_VERSION'])+'return 0;}\n')
        subprocess.run(['cc','-std=c11','-I'+str(source),str(code),'-o',str(exe)],check=True)
        data=subprocess.check_output([str(exe)],text=True)
    values={k:int(v) for k,v in (line.split('=',1) for line in data.splitlines())}
    if any(values.get(k)!=v for k,v in LEGACY.items()): raise RuntimeError('Existing IOCTL value changed')
    if values['KERNEL_SU_UAPI_VERSION']!=6: raise RuntimeError('Expected native UAPI6')
    baseline=json.loads((out/'baseline-manager-manifest.json').read_text())
    actual=manifest(source,('manager',))
    if baseline!=actual: raise RuntimeError('Manager sources, UI or configuration changed')
    lock=json.loads((out/'upgrade-lock.json').read_text())
    lock.update({'manager_uapi_symlink_verified':True,'uapi_version':6,
        'existing_ioctl_values_preserved':len(LEGACY),'new_ioctl_count':1,
        'manager_files_unchanged':len(actual),'manager_tree_sha256':digest(actual)})
    (out/'upgrade-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    (out/'final-manager-manifest.json').write_text(json.dumps(actual,indent=2)+'\n')
    (out/'abi-values.json').write_text(json.dumps(values,indent=2)+'\n')
    print('PASS: shared UAPI6, 26 legacy IOCTLs unchanged, all manager files unchanged.')

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('usage: finalize_source.py SOURCE OUT')
    validate(*(Path(p).resolve() for p in sys.argv[1:]))
