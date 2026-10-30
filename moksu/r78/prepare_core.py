#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproduce the delivered R7.7 source, then merge only the pinned upstream core.
No credentials, device access, or signing are performed by this script.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

OLD = '0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d'
NEW = 'ab05a0626e88d4ada1295ec561d5660f26547fdc'
PATCHES = [
 'r2/moksu-v3.3.1-R2.patch',
 'r3/r3-final-source.patch', 'r3/r3-security-supplement.patch', 'r3/r3-superuser-label.patch',
 'r4/moksu-v3.3.1-R4.patch', 'r5/moksu-v3.3.1-R5.patch', 'r5/r5-rust-utf8-fix.patch',
 'r6/moksu-v3.3.1-R6-20261014.patch', 'r6/r6-compose-state-hotfix.patch',
 'r7/moksu-v3.3.1-R7.patch', 'r7/presentation-recovery-hotfix.patch', 'r7/compose-setter-hotfix.patch',
 'r71/moksu-v3.3.2-R7.1-web-sync.patch', 'r71/android-compile-imports.patch',
 'r72/moksu-v3.3.1-R7.2-source.patch', 'r73/moksu-v3.3.2-R7.3-source.patch',
 'r74/moksu-v3.3.2-R7.4-single-apk.patch', 'r75/moksu-v3.3.2-R7.5-revert-identity-fix.patch',
 'r76/moksu-v3.3.2-R7.6-hidden-state-cache-fix.patch', 'r77/moksu-v3.3.2-R7.7-kernel-stealth-recovery.patch',
]
EXPECTED = {
 'manager': '8fff1707b219415f101a210bb9ab8382356926a9858050a4cb0910f4e95e3c76',
 'kernel': '3c6aeab452696b8165ec43f84e4700cec097bdd6a92e65a5eac3edcfe7f62389',
 'userspace': '65d094a4aea8da6c7a881eab596dd2ea96d3917efac93b19b81238d393b22502',
 'uapi': '9268fe59af5f8c0159df2e143f70c4359fae068f54f2622909219ef235cc882f',
}

def run(*args, cwd=None):
    subprocess.run([str(x) for x in args], cwd=cwd, check=True)

def digest(root, prefix):
    h = hashlib.sha256()
    for p in sorted((root / prefix).rglob('*')):
        if p.is_file() and not p.is_symlink():
            h.update(str(p.relative_to(root)).encode() + b'\0' + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def resolve_dispatch(text):
    pattern = re.compile(r'<<<<<<< [^\n]+\n(.*?)=======\n(.*?)>>>>>>> [^\n]+\n', re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 2:
        raise ValueError('Unexpected dispatch conflict shape')
    for i, m in reversed(list(enumerate(matches))):
        ours, theirs = m.group(1), m.group(2)
        if i == 0:
            assert 'do_moksu_stealth_set' in ours and 'do_lookup_symbols' in theirs
            replacement = ours + '}\n\n' + theirs
        else:
            assert 'KSU_IOCTL_STEALTH_SET' in ours and 'KSU_IOCTL_LOOKUP_SYMBOLS' in theirs
            replacement = ours + '    },\n    {\n' + theirs
        text = text[:m.start()] + replacement + text[m.end():]
    if any(x in text for x in ('<<<<<<<', '=======', '>>>>>>>')):
        raise ValueError('Unresolved dispatch conflict')
    assert hashlib.sha256(text.encode()).hexdigest() == '6c415cf2af05d8e730f4f447dbfa736dc8a9e2ca6b914e8b704d407490fa9eda'
    return text

def prepare(config, legacy, old, new, source, report_dir):
    config, legacy, old, new = [Path(p).resolve(strict=True) for p in (config, legacy, old, new)]
    source, report_dir = Path(source).resolve(), Path(report_dir).resolve()
    if source.exists():
        raise FileExistsError(source)
    report_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(old, source, symlinks=True)
    run(sys.executable, config/'moksu/ksu331/apply_release.py', source, source, config)
    for name in ('port_stealth.py', 'port_web.py', 'port_web_compat.py', 'port_android.py'):
        run(sys.executable, config/'moksu/features'/name, source, legacy)
    run(sys.executable, config/'moksu/redesign/apply_redesign.py', source, config/'moksu/redesign')
    shutil.copytree(config/'moksu', source/'moksu-build', symlinks=True)
    for patch in PATCHES:
        path = config/'moksu'/patch
        run('git', 'apply', '--check', path, cwd=source)
        run('git', 'apply', path, cwd=source)
    observed = {k: digest(source, k) for k in EXPECTED}
    (report_dir/'baseline-hashes.json').write_text(json.dumps(observed, indent=2)+'\n')
    if observed != EXPECTED:
        manifest = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for k in EXPECTED for p in (source/k).rglob('*') if p.is_file() and not p.is_symlink()}
        (report_dir/'baseline-file-hashes.json').write_text(json.dumps(manifest, indent=2)+'\n')
        raise ValueError('Replayed baseline differs from delivered R7.7; see baseline hashes')
    web_before = digest(source, 'userspace/ksud/assets/webadmin')
    stealth_before = (source/'kernel/manager/stealth.c').read_bytes()
    prefixes = ('kernel/', 'userspace/', 'uapi/', '.github/scripts/')
    paths = {str(p.relative_to(r)) for r in (old, new) for p in r.rglob('*') if p.is_file() and not p.is_symlink()}
    changed = []
    for rel in sorted(paths):
        if not (rel.startswith(prefixes) or rel in ('Cargo.toml','Cargo.lock')):
            continue
        op, np, target = old/rel, new/rel, source/rel
        ob = op.read_bytes() if op.is_file() else None
        nb = np.read_bytes() if np.is_file() else None
        ours = target.read_bytes() if target.is_file() else None
        if ob == nb:
            continue
        changed.append(rel)
        if ours == ob or ours == nb:
            if nb is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(nb)
        else:
            if any(x is None or b'\0' in x for x in (ob, nb, ours)):
                raise ValueError('Unexpected structural conflict: '+rel)
            result = subprocess.run(['git','merge-file','-p',str(target),str(op),str(np)], capture_output=True)
            content = result.stdout
            if result.returncode:
                if rel != 'kernel/supercall/dispatch.c' or result.returncode != 2:
                    raise ValueError('Unhandled conflict: '+rel)
                content = resolve_dispatch(content.decode()).encode()
            target.write_bytes(content)
    assert digest(source,'manager') == EXPECTED['manager']
    assert digest(source,'userspace/ksud/assets/webadmin') == web_before
    assert (source/'kernel/manager/stealth.c').read_bytes() == stealth_before
    uapi = (source/'uapi/supercall.h').read_text()
    assert 'KERNEL_SU_UAPI_VERSION = 6;' in uapi
    assert "_IOW('K', 22, struct ksu_lookup_symbols_cmd)" in uapi
    assert "_IOR('K', 25, struct ksu_stealth_cmd)" in uapi
    assert "_IOW('K', 26, struct ksu_stealth_cmd)" in uapi
    kbuild = (source/'kernel/Kbuild').read_text()
    assert 'KSU_PACKAGE_NAME ?= com.moksu.manager' in kbuild
    assert 'df131f3197ed55a19d7e0a86a2b04635a5c0e5ea4bf9b596fef5a8e1d5bbcbd8' in kbuild
    run('node','--check',source/'userspace/ksud/assets/webadmin/app.js')
    count = int(subprocess.check_output(['git','-C',str(new),'rev-list','--count','HEAD']).strip())
    assert subprocess.check_output(['git','-C',str(new),'rev-parse','HEAD']).decode().strip() == NEW
    assert 30000 + count == 32709
    report = {'baseline':'R7.7','upstream_commit':NEW,'upstream_ci_run':40993230053,
              'core_version':32709,'uapi_version':6,'changed_core_files':changed,
              'manager_tree_sha256':observed['manager'],'manager_tree_unchanged':True,
              'web_assets_unchanged':True,'stealth_logic_unchanged':True,'device_tested':False}
    (source/'MOKSU_R78_CORE_UPGRADE.json').write_text(json.dumps(report,indent=2)+'\n')
    (report_dir/'core-upgrade-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Verified baseline and merged',len(changed),'upstream core files; UI unchanged')

if __name__ == '__main__':
    if len(sys.argv) != 7:
        raise SystemExit('Usage: prepare_core.py CONFIG LEGACY OLD NEW SOURCE REPORT_DIR')
    prepare(*sys.argv[1:])
