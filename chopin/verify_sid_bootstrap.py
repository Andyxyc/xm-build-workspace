#!/usr/bin/env python3
"""Check the real policy function's preprocessed legacy/modern SID setup paths.

This is a source regression check, not proof of manager detection on a device.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def check(path, cpp):
    source = path.read_text()
    start = source.index('void apply_kernelsu_rules(void)\n{')
    end = source.index('\n}\n', start) + 3
    function = source[start:end]
    reports = []
    for version in [(4, 14, 186), (5, 10, 0), (6, 1, 0)]:
        for susfs in (False, True):
            header = '#define KERNEL_VERSION(a,b,c) (((a)<<16)+((b)<<8)+(c))\n'
            header += '#define LINUX_VERSION_CODE KERNEL_VERSION(%d,%d,%d)\n' % version
            if susfs:
                header += '#define CONFIG_KSU_SUSFS 1\n'
            result = subprocess.run([cpp, '-E', '-P', '-x', 'c', '-'],
                                    input=header + function, text=True,
                                    capture_output=True, check=True)
            text = result.stdout
            calls = list(re.finditer(r'\bsusfs_set_batch_sid\s*\(', text))
            assert len(calls) == int(susfs), (version, susfs, len(calls))
            assert text.count('reset_avc_cache();') == 1, (version, susfs)
            if susfs:
                sid = calls[0].start()
                assert text.index('reset_avc_cache();') < sid
                if version < (5, 10, 0):
                    # Both the rwlock and stop_machine routes must reach it.
                    assert text.index('write_unlock(lock);') < text.index('goto out_flush;')
                    assert text.index('set_cpus_allowed_ptr(current, &old_mask);') < text.index('goto out_flush;')
                    assert text.index('stop_machine(apply_kernelsu_rules_fn, (void *)db, NULL);') < text.index('out_flush:') < sid
                else:
                    assert 'stop_machine(' not in text
                    assert text.index('rcu_assign_pointer(selinux_state.policy, pol);') < sid
            reports.append({'version': list(version), 'susfs': susfs,
                            'sid_initializations': len(calls),
                            'preprocessed_sha256': hashlib.sha256(text.encode()).hexdigest()})
    return {'status': 'PASS_SOURCE_ONLY', 'rules_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'cases': reports, 'hardware_manager_detection': 'NOT_TESTED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rules', type=Path)
    parser.add_argument('--cpp', default='gcc')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = check(args.rules, args.cpp)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: actual preprocessed policy function: legacy/modern x SUSFS on/off (source only)')


if __name__ == '__main__':
    main()
