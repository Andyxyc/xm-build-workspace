"""Retain the actual pinned module-loader source, preprocessing and object.

No validation is bypassed, no Image is built, and no device is accessed.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

root = Path(os.environ['WORKSPACE']) / 'android-kernel'
out = Path(os.environ['GITHUB_WORKSPACE']) / 'module-loader-diagnostics'
out.mkdir(exist_ok=False)
env = os.environ.copy()
env['PATH'] = env['CLANG_PATH'] + ':' + env['PATH']
env.pop('DISABLE_LTO', None)
args = ['make', '-j2', 'O=out', 'ARCH=arm64', 'CC=clang']
for key in ['CUSTOM_CMDS', 'EXTRA_CMDS', 'GCC_64', 'GCC_32']:
    args += shlex.split(env.get(key, ''))
flags = re.findall(r'^subdir-ccflags-y\s*\+=\s*(.+)$',
                   (root / 'kernel/Makefile').read_text(), re.M)
assert len(flags) == 5, flags
inherited = 'KCFLAGS=' + ' '.join(flags).replace('$(srctree)', str(root))
rows = []
for target in ['chopin_user_defconfig', 'kernel/module.i', 'kernel/module.o']:
    command = args + ([inherited] if target.startswith('kernel/') else []) + [target]
    with (out / (target.replace('/', '_') + '.log')).open('w') as log:
        code = subprocess.run(command, cwd=root, env=env, stdout=log,
                              stderr=subprocess.STDOUT).returncode
    rows.append({'target': target, 'command': command, 'exit_code': code})
    (out / 'commands.json').write_text(json.dumps(rows, indent=2))
    assert code == 0, (target, code)

files = ['kernel/module.c', 'kernel/Makefile', 'include/linux/vermagic.h',
         'out/.config', 'out/include/generated/autoconf.h',
         'out/include/generated/utsrelease.h', 'out/kernel/module.i',
         'out/kernel/module.o', 'out/kernel/.module.o.cmd']
manifest = []
for name in files:
    src = root / name
    dest = out / name.replace('/', '_')
    shutil.copyfile(src, dest)
    manifest.append({'source': name, 'bytes': src.stat().st_size,
                     'sha256': hashlib.sha256(src.read_bytes()).hexdigest()})
for name, command in [
    ('module-disassembly.txt', ['aarch64-linux-gnu-objdump', '-dr', str(root / 'out/kernel/module.o')]),
    ('compiler.txt', ['clang', '--version']),
    ('vendor-index-and-worktree.patch', ['git', '-C', str(root), 'diff', 'HEAD', '--binary'])
]:
    result = subprocess.run(command, env=env, capture_output=True, check=True)
    (out / name).write_bytes(result.stdout)
(out / 'manifest.json').write_text(json.dumps({'files': manifest,
    'vendor_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
    'status': 'DIAGNOSTICS_ONLY_NO_IMAGE_NO_DEVICE'}, indent=2))
print('Retained pinned loader C, preprocessed code, compiler command and ARM64 object')
