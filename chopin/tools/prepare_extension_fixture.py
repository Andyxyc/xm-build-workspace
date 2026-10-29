"""Reconstruct only source files used by the extension host tests.

Input is the source patch/metadata from the actual successful b79 raw-build
artifact. It is applied to the fixed official builtin commit, never a guessed
code transcription. This creates ordinary files and a private local .git only;
it neither builds a kernel nor runs any device commands.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import urllib.request


BUILTIN = '6397fcb5d96e8f4953c71e02c73f8c6800541bff'
BUILD = 'b79c0dec13c639c5f07754c399b345ae1ee256dd'
PATCH_SHA = '68a7cd4125c4f5604a2ab517aa8ea3058332961ca301d8a41e05545c66e273d0'
PATHS = ['kernel/Makefile', 'kernel/extension/extension.c',
         'kernel/extension/extension.h', 'kernel/supercall/dispatch.c',
         'kernel/include/uapi/extension.h', 'kernel/extension/kpm/bridge.h']
ORIGINAL_SHA = {
    'kernel/Makefile': '8dd6c7d062afc86f4f9d29c4f460af82a2e55f67f99453bdebb2dccb75c02c44',
    'kernel/extension/extension.c': 'b5cc3138eae6b2eb6aaf2602eece79c16c802274422200cee5e9cdf70b9e895b',
    'kernel/extension/extension.h': 'fa2f9332c816c1a4e964dd762145673b4678766ba04c45da39dcf3453968d882',
    'kernel/supercall/dispatch.c': '6ce233a93902b36e03c0ea5432c116d90c3881573ee18e5d23516f6f2c6270cc',
    'kernel/include/uapi/extension.h': 'f94920768e3bb0e9993f76cc9d7dcace873d8e327866acb89047147861abd7f3',
    'kernel/extension/kpm/bridge.h': 'a95c61ba01cf6f738044abd624794a0b4e784d4d89310cd8272c6c6ecc2bf90f',
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True,
                   help='Extracted b79 raw-build artifact (run40396562328)')
    p.add_argument('--kernel-root', type=Path, required=True)
    p.add_argument('--pin', type=Path, required=True,
                   help='chopin/tools/susfs230/ci41098-source.json')
    p.add_argument('--report', type=Path, default=Path('extension-source-fixture.json'))
    a = p.parse_args()
    ref = a.reference.resolve()
    assert (ref / 'build-logs/root-build-complete.txt').read_text().strip() == BUILD
    patch = ref / 'release-evidence/SukiSU-changes.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == PATCH_SHA
    record = json.loads((ref / 'release-evidence/chopin-ci-port.json').read_text())
    assert record['version_code'] == 41095 and record['uapi_version'] == 6
    assert record['builtin_commit'] == BUILTIN
    pin = json.loads(a.pin.read_text())
    assert pin['base_ci'] == 41095 and pin['builtin_commit'] == BUILTIN
    root = a.kernel_root.resolve()
    assert not root.exists(), 'Use a new source fixture directory; do not overwrite a working source tree'
    ksu = root / 'KernelSU'
    ksu.mkdir(parents=True)
    original = {}
    for name in PATHS:
        url = f'https://raw.githubusercontent.com/SukiSU-Ultra/SukiSU-Ultra/{BUILTIN}/{name}'
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(200000)
        assert 0 < len(data) < 200000 and b'\r' not in data, name
        assert hashlib.sha256(data).hexdigest() == ORIGINAL_SHA[name], name
        path = ksu / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        original[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'url': url}
    subprocess.run(['git', '-C', str(ksu), 'init', '-q'], check=True, capture_output=True)
    includes = [f'--include={name}' for name in PATHS]
    command = ['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
               '-C', str(ksu), 'apply', '--whitespace=nowarn'] + includes
    subprocess.run(command + ['--check', str(patch)], check=True, capture_output=True)
    subprocess.run(command + [str(patch)], check=True, capture_output=True)
    patched = {}
    for name, expected in pin['expected_before_sha256'].items():
        data = (ksu / name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        assert actual == expected and b'\r' not in data, (name, actual, expected)
        patched[name] = actual
    assert 'KSU_VERSION := 41095' in (ksu / 'kernel/Makefile').read_text()
    assert '#define SUKISU_KPM_ABI_VERSION 1' in (ksu / 'kernel/extension/kpm/bridge.h').read_text()
    (root / 'chopin-ci-port.json').write_text(json.dumps(record, indent=2) + '\n',
                                             encoding='utf-8', newline='\n')
    report = {
        'status': 'PASS_FIXED_BUILTIN_PLUS_ACTUAL_B79_PATCH_SOURCE_RECONSTRUCTION',
        'base_build_commit': BUILD, 'base_build_run': 40396562328,
        'builtin_commit': BUILTIN, 'actual_build_patch_sha256': PATCH_SHA,
        'original_files': original, 'exact_before_update_ci41098': patched,
        'kernel_compiled': False, 'device_accessed': False,
        'scope': 'Six source files and source metadata only; not a complete kernel source tree',
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
