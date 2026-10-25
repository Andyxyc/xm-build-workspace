"""Compile genuine ARM64 interface objects; no Image and no device operations."""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess

root = Path(os.environ['WORKSPACE']) / 'android-kernel'
out = Path(os.environ['GITHUB_WORKSPACE']) / 'feature-object-diagnostics'
out.mkdir(exist_ok=False)
env = os.environ.copy()
env['PATH'] = env['CLANG_PATH'] + ':' + env['PATH']
env.pop('DISABLE_LTO', None)
args = ['make', '-j2', 'O=out', 'ARCH=arm64', 'CC=clang']
for key in ['CUSTOM_CMDS', 'EXTRA_CMDS', 'GCC_64', 'GCC_32']:
    args += shlex.split(env.get(key, ''))
flags = re.findall(r'^subdir-ccflags-y\s*\+=\s*(.+)$',
                   (root / 'kernel/Makefile').read_text(), re.M)
assert len(flags) == 5
kernel_flags = 'KCFLAGS=' + ' '.join(flags).replace('$(srctree)', str(root))
rows = []
targets = ['chopin_user_defconfig', 'init/version.o', 'drivers/kernelsu/ksu_main.o',
           'fs/susfs.o', 'fs/proc_namespace.o', 'fs/namei.o', 'kernel/reboot.o',
           'security/selinux/avc.o', 'security/selinux/selinuxfs.o']
for target in targets:
    command = args + ([kernel_flags] if target.startswith('kernel/') else []) + [target]
    log = out / (target.replace('/', '_') + '.log')
    with log.open('w') as output:
        code = subprocess.run(command, cwd=root, env=env, stdout=output,
                              stderr=subprocess.STDOUT).returncode
    row = {'target': target, 'command': command, 'exit_code': code}
    rows.append(row)
    print(json.dumps({'target': target, 'exit_code': code}), flush=True)
    (out / 'commands.json').write_text(json.dumps(rows, indent=2))
    if target == 'chopin_user_defconfig' and code:
        raise SystemExit(code)
    obj = root / 'out' / target
    if target.endswith('.o') and obj.is_file():
        shutil.copyfile(obj, out / target.replace('/', '_'))

files = ['out/.config', 'out/include/generated/autoconf.h',
         'out/include/generated/utsrelease.h', 'fs/susfs.c',
         'fs/chopin_susfs_typed_core.inc', 'fs/namei.c', 'fs/proc_namespace.c',
         'kernel/reboot.c', 'include/linux/susfs.h',
         'include/linux/chopin_susfs_state.h',
         'KernelSU/kernel/chopin_susfs_typed_reboot.c',
         'KernelSU/kernel/chopin_susfs_typed_abi.h',
         'KernelSU/kernel/chopin_avc_audit_display.c',
         'KernelSU/kernel/chopin_selinux_query_snapshot.c',
         'security/selinux/avc.c', 'security/selinux/selinuxfs.c',
         'KernelSU/kernel/extension/kpm/kpm.c']
manifest = []
for name in files:
    src = root / name
    if not src.is_file():
        manifest.append({'source': name, 'status': 'MISSING'})
        continue
    shutil.copyfile(src, out / name.replace('/', '_'))
    manifest.append({'source': name, 'bytes': src.stat().st_size,
                     'sha256': hashlib.sha256(src.read_bytes()).hexdigest()})
(out / 'manifest.json').write_text(json.dumps({'files': manifest,
    'status': 'DIAGNOSTIC_OBJECTS_ONLY', 'hardware_validated': False}, indent=2))
raise SystemExit(int(any(row['exit_code'] for row in rows)))
