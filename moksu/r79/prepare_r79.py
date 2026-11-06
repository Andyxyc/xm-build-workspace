#!/usr/bin/env python3
"""Reproduce R7.8, then merge the verified 2026-11-06 upstream core only."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile

PREVIOUS = 'ab05a0626e88d4ada1295ec561d5660f26547fdc'
LATEST = '019a3c0103a8f8d56675546016c4073d0fd18352'
VERSION = 32717
OFFICIAL_RUN = 42154926106
CERT = 'df131f3197ed55a19d7e0a86a2b04635a5c0e5ea4bf9b596fef5a8e1d5bbcbd8'
BASELINE = {
    'manager': 'c48f67e1dc97de73217bee907b32acda16669f4f3b991b748a44b376213059cb',
    'kernel': '44ec9725b87d5b5c8b4c30fc427a7768aed2fe56aa22fa092e61f00345bdc0d6',
    'userspace': '32238c0bdecbcd79a613a7ced58249a121abe8968d1cab08e5f9217325d0cf23',
    'uapi': '5abcc6b0b85e7110a668bf0f4e9735ae1a2711e0c06a575802fdeff6c5c1f82b',
}
EXPECTED_CHANGES = {
    'kernel/Kbuild', 'kernel/core/init.c', 'kernel/feature/selinux_hide.c',
    'kernel/hook/arm64/patch_memory.c', 'kernel/hook/setuid_hook.c',
    'kernel/hook/syscall_event_bridge.c', 'kernel/hook/tp_marker.c',
    'kernel/hook/x86_64/patch_memory.c', 'kernel/infra/btf_parser.c',
    'kernel/infra/btf_parser.h', 'kernel/infra/file_wrapper.c',
    'kernel/policy/allowlist.c', 'kernel/policy/allowlist.h',
    'kernel/runtime/ksud_integration.c', 'kernel/selinux/inode.c',
    'kernel/selinux/rules.c', 'kernel/selinux/selinux.h',
    'kernel/selinux/sepolicy.c', 'kernel/selinux/sepolicy.h',
    'kernel/supercall/dispatch.c',
}


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            h.update(p.relative_to(root).as_posix().encode() + b'\0' + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def merge_bytes(ours, base, new, path: str):
    if ours == base or ours == new:
        return new
    if base == new:
        return ours
    if ours is None or base is None or new is None or any(b'\0' in b for b in (ours, base, new)):
        raise RuntimeError('Unreviewed binary/add/delete conflict: ' + path)
    with tempfile.TemporaryDirectory(prefix='moksu-merge-') as td:
        d = Path(td)
        for label, value in [('ours', ours), ('base', base), ('new', new)]:
            (d / label).write_bytes(value)
        r = subprocess.run(['git', 'merge-file', '-p', '-L', 'R7.8', '-L', 'upstream32709',
                            '-L', 'upstream32717', str(d/'ours'), str(d/'base'), str(d/'new')], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError('Unreviewed merge conflict: ' + path + '\n' + r.stdout.decode(errors='replace'))
        return r.stdout


def self_test():
    assert merge_bytes(b'a\n', b'a\n', b'b\n', 'same') == b'b\n'
    assert merge_bytes(b'custom\n', b'a\n', b'a\n', 'unchanged') == b'custom\n'
    assert merge_bytes(None, None, b'new\n', 'add') == b'new\n'
    assert merge_bytes(b'old\n', b'old\n', None, 'delete') is None
    assert merge_bytes(b'new\n', b'old\n', b'new\n', 'idempotent') == b'new\n'
    for values in [(b'custom\n', b'old\n', b'upstream\n'), (b'\0x', b'\0y', b'\0z'), (b'custom', None, b'upstream')]:
        try:
            merge_bytes(*values, 'must-fail')
        except RuntimeError:
            pass
        else:
            raise AssertionError('Conflict accepted')
    print('MERGE_SELF_TESTS_OK 8', flush=True)


def main(src: Path, cfg: Path, old: Path):
    self_test()
    spec = importlib.util.spec_from_file_location('r78', cfg/'moksu/r78/prepare_r78.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('Missing R7.8 reconstruction module')
    r78 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r78)
    r78.reconstruct(src, cfg, old)
    r78.upgrade(src)
    got = {name: tree_hash(src/name) for name in BASELINE}
    if got != BASELINE:
        raise RuntimeError('R7.8 baseline differs from original delivery: ' + json.dumps(got))
    (src/'R79-baseline-check.json').write_text(json.dumps({'expected': BASELINE, 'actual': got}, indent=2)+'\n')

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=src)

    def blob(ref, path):
        r = subprocess.run(['git', 'show', f'{ref}:{path}'], cwd=src, capture_output=True)
        return None if r.returncode else r.stdout

    if int(git('rev-list', '--count', LATEST).strip()) + 30000 != VERSION:
        raise RuntimeError('Version count does not match official CI artifact')
    if git('merge-base', PREVIOUS, LATEST).decode().strip() != PREVIOUS:
        raise RuntimeError('Unexpected upstream ancestry')
    paths = git('diff', '--name-only', PREVIOUS, LATEST, '--', 'kernel', 'uapi', 'userspace',
                'Cargo.toml', 'Cargo.lock', '.github/scripts').decode().splitlines()
    if set(paths) != EXPECTED_CHANGES:
        raise RuntimeError('Upstream core diff changed: ' + repr(paths))
    preserved = {name: tree_hash(src/name) for name in ('manager', 'userspace', 'uapi')}
    stealth = (src/'kernel/manager/stealth.c').read_bytes()
    records = []
    for relative in paths:
        p = src/relative
        ours = p.read_bytes() if p.is_file() else None
        base, new = blob(PREVIOUS, relative), blob(LATEST, relative)
        merged = merge_bytes(ours, base, new, relative)
        if merged is None:
            p.unlink(missing_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(merged)
        records.append({'path': relative, 'sha256': hashlib.sha256(merged).hexdigest() if merged is not None else None})
    for name, before in preserved.items():
        if tree_hash(src/name) != before:
            raise RuntimeError('Protected source changed: ' + name)
    assert (src/'kernel/manager/stealth.c').read_bytes() == stealth
    kb = (src/'kernel/Kbuild').read_text()
    assert 'KSU_PACKAGE_NAME ?= com.moksu.manager' in kb and CERT in kb
    assert 'KSU_PACKAGE_NAME=com.moksu.manager' in (src/'userspace/ksud/build.rs').read_text()
    dispatch = (src/'kernel/supercall/dispatch.c').read_text()
    for handler in ('do_moksu_stealth_get', 'do_moksu_stealth_set', 'do_lookup_symbols'):
        assert dispatch.count('static int '+handler+'(') == 1, handler
    report = {
        'baseline': 'R7.8 / CI32709', 'upstream': LATEST, 'previous_upstream': PREVIOUS,
        'official_ci_run': OFFICIAL_RUN, 'official_ci_date': '2026-11-06',
        'upstream_version': git('describe', '--tags', '--always', LATEST).decode().strip(),
        'core_version': VERSION, 'updated_core_files': records,
        'manager_files': sum(p.is_file() for p in (src/'manager').rglob('*')),
        'preserved_tree_hashes': preserved, 'package': 'com.moksu.manager',
        'signer_sha256': CERT, 'device_tested': False,
    }
    (src/'R79-core-upgrade.json').write_text(json.dumps(report, indent=2)+'\n')
    print('R79_SOURCE_VERIFIED', VERSION, len(records), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    elif len(sys.argv) == 4:
        main(*(Path(p).resolve(strict=True) for p in sys.argv[1:]))
    else:
        raise SystemExit('usage: prepare_r79.py SOURCE CONFIG OLD_FORK | --self-test')
