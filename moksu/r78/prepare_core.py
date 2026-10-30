#!/usr/bin/env python3
"""Reproduce the released R7.7 sources, then merge only the pinned upstream core.
SPDX-License-Identifier: GPL-3.0-or-later
No signing keys are used by this script. Any conflict or baseline mismatch stops CI.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

BASE = '0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d'
UPSTREAM = 'ab05a0626e88d4ada1295ec561d5660f26547fdc'
EXPECTED = {
    'manager': '2802dbe1a34e93eefc2e85e518710000cf9fffb8515ca4e44bcdacad952708d9',
    'kernel': '908c3d1bb3ee2db5170eb20cdc0a075fbea4b2c9812437ea570907bfe4d30ac5',
    'userspace': 'ab94365381440f98f4808f076c1104e8ee58cfacf4d96c12b034838ae447bf69',
    'uapi': '7faca3fdb28c58f2e042974f2c0ccf1d4f65ec2fed4afd7b642244d4f4e2e762',
}
PATCHES = [
    'r2/moksu-v3.3.1-R2.patch',
    'r3/r3-final-source.patch',
    'r3/r3-security-supplement.patch',
    'r3/r3-superuser-label.patch',
    'r4/moksu-v3.3.1-R4.patch',
    'r5/moksu-v3.3.1-R5.patch',
    'r5/r5-rust-utf8-fix.patch',
    'r6/moksu-v3.3.1-R6-20261014.patch',
    'r6/r6-compose-state-hotfix.patch',
    'r7/moksu-v3.3.1-R7.patch',
    'r7/presentation-recovery-hotfix.patch',
    'r7/compose-setter-hotfix.patch',
    'r71/moksu-v3.3.2-R7.1-web-sync.patch',
    'r71/android-compile-imports.patch',
    'r72/moksu-v3.3.1-R7.2-source.patch',
    'r73/moksu-v3.3.2-R7.3-source.patch',
    'r74/moksu-v3.3.2-R7.4-single-apk.patch',
    'r75/moksu-v3.3.2-R7.5-revert-identity-fix.patch',
    'r76/moksu-v3.3.2-R7.6-hidden-state-cache-fix.patch',
    'r77/moksu-v3.3.2-R7.7-kernel-stealth-recovery.patch',
]

def run(*args: str, cwd: Path | None = None) -> str:
    p = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    print(p.stdout, end='', flush=True)
    if p.returncode:
        raise RuntimeError(f'command failed ({p.returncode}): {args[0:4]}')
    return p.stdout

def manifest(root: Path, prefixes: tuple[str, ...]) -> dict[str, str]:
    result = {}
    for prefix in prefixes:
        directory = root / prefix
        paths = [directory] if directory.is_file() else directory.rglob('*')
        for p in paths:
            if p.is_file():
                if p.is_symlink():
                    raise ValueError(f'unexpected source symlink: {p}')
                result[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def digest(items: dict[str, str]) -> str:
    value = ''.join(f'{k}\0{items[k]}\n' for k in sorted(items)).encode()
    return hashlib.sha256(value).hexdigest()

def reconstruct(source: Path, old: Path, config: Path, out: Path) -> None:
    def py(script: str, *args: Path) -> None:
        run(sys.executable, str(config / 'moksu' / script), *(str(a) for a in args))
    py('ksu331/apply_release.py', source, source, config)
    for name in ('port_stealth.py', 'port_web.py', 'port_web_compat.py', 'port_android.py'):
        py('features/' + name, source, old)
    py('redesign/apply_redesign.py', source, config / 'moksu/redesign')
    shutil.copytree(config / 'moksu', source / 'moksu-build', dirs_exist_ok=True)
    for name in PATCHES:
        patch = config / 'moksu' / name
        if not patch.is_file():
            raise FileNotFoundError(patch)
        print('Applying', name, flush=True)
        run('git', 'apply', '--check', str(patch), cwd=source)
        run('git', 'apply', str(patch), cwd=source)
    checks = {}
    for prefix, expected in EXPECTED.items():
        data = manifest(source, (prefix,))
        checks[prefix] = {'files': len(data), 'expected': expected, 'actual': digest(data)}
        (out / f'baseline-{prefix}-manifest.json').write_text(json.dumps(data, indent=2) + '\n')
    (out / 'baseline-checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    bad = [name for name, value in checks.items() if value['actual'] != value['expected']]
    if bad:
        raise RuntimeError('R7.7 baseline does not match released source: ' + ', '.join(bad))

def merge_core(source: Path, base: Path, upstream: Path, out: Path) -> None:
    protected = manifest(source, ('manager', 'userspace/ksud/assets/webadmin'))
    prefixes = ('kernel', 'userspace', 'uapi', 'Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml')
    before = manifest(base, prefixes)
    after = manifest(upstream, prefixes)
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    conflicts = []
    audit = []
    for relative in changed:
        dst = source / relative
        a = base / relative
        b = upstream / relative
        old = a.read_bytes() if a.is_file() else None
        new = b.read_bytes() if b.is_file() else None
        local = dst.read_bytes() if dst.is_file() else None
        if local == new:
            audit.append({'path': relative, 'mode': 'already-current'})
            continue
        if local == old:
            if new is None:
                dst.unlink()
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(b, dst)
            audit.append({'path': relative, 'mode': 'upstream'})
            continue
        if any(v is None or b'\0' in v for v in (old, new, local)):
            conflicts.append(relative)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            ours = Path(tmp) / 'ours'
            ours.write_bytes(local)
            p = subprocess.run(['git', 'merge-file', '-p', str(ours), str(a), str(b)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            problem = out / 'conflicts' / relative
            problem.parent.mkdir(parents=True, exist_ok=True)
            problem.write_bytes(p.stdout)
            conflicts.append(relative)
        else:
            dst.write_bytes(p.stdout)
            audit.append({'path': relative, 'mode': 'three-way-preserve-custom'})
    (out / 'core-merge.json').write_text(json.dumps({'base': BASE, 'target': UPSTREAM,
        'changed': audit, 'conflicts': conflicts}, indent=2) + '\n')
    if conflicts:
        raise RuntimeError('Unresolved core merge: ' + ', '.join(conflicts))
    if protected != manifest(source, ('manager', 'userspace/ksud/assets/webadmin')):
        raise RuntimeError('Protected R7.7 manager/UI/web resources changed')
    kbuild = (source / 'kernel/Kbuild').read_text()
    for exact in ('KSU_PACKAGE_NAME ?= com.moksu.manager',
                  'KSU_EXPECTED_HASH ?= df131f3197ed55a19d7e0a86a2b04635a5c0e5ea4bf9b596fef5a8e1d5bbcbd8'):
        if exact not in kbuild:
            raise RuntimeError('Manager trust configuration changed')
    for relative in ('kernel/manager/stealth.c', 'userspace/ksud/src/webadmin.rs',
                     'manager/app/src/main/java/me/weishu/kernelsu/mok/MokStealthRecovery.kt'):
        if not (source / relative).is_file():
            raise RuntimeError('Lost custom feature: ' + relative)
    run('node', '--check', str(source / 'userspace/ksud/assets/webadmin/app.js'))
    run('git', 'fetch', str(upstream), UPSTREAM, cwd=source)
    run('git', 'reset', '--soft', UPSTREAM, cwd=source)
    count = int(run('git', 'rev-list', '--count', 'HEAD', cwd=source).strip())
    if count + 30000 != 32709:
        raise RuntimeError('Unexpected KSU version count')
    (out / 'upgrade-lock.json').write_text(json.dumps({
        'baseline': 'R7.7', 'upstream': UPSTREAM, 'upstream_ci': 40993230053,
        'ksu_version': 32709, 'package': 'com.moksu.manager',
        'protected_files': len(protected), 'protected_tree_sha256': digest(protected),
        'ui_changed': False, 'signed': False, 'device_tested': False,
    }, indent=2) + '\n')

if __name__ == '__main__':
    if len(sys.argv) != 7:
        raise SystemExit('usage: prepare_core.py SOURCE OLD_FORK CONFIG BASE UPSTREAM OUT')
    source, old, config, base, upstream, out = [Path(p).resolve() for p in sys.argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    if run('git', 'rev-parse', 'HEAD', cwd=source).strip() != BASE:
        raise SystemExit('Wrong baseline checkout')
    if run('git', 'rev-parse', 'HEAD', cwd=upstream).strip() != UPSTREAM:
        raise SystemExit('Wrong upstream checkout')
    reconstruct(source, old, config, out)
    merge_core(source, base, upstream, out)
    print('R7.8 source verified; original UI, identity and custom features preserved.')
