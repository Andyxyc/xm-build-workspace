"""Backport official eb95 priority-filter fixes to the exact native 4.14 port.

Run AFTER native_ksu.py and update_ci41100.py. No network access is used.
This is not a replacement of the whole official GKI filesystem source.
"""
from pathlib import Path
import argparse
import hashlib
import json

SHA = lambda data: hashlib.sha256(data).hexdigest()
RCU_OLD = '\tmutex_unlock(&susfs_mutex_lock_priority_uid_filter);\n\n\tkfree_rcu(old_bitmap, rcu);'
RCU_NEW = '\tmutex_unlock(&susfs_mutex_lock_priority_uid_filter);\n\tsynchronize_rcu();\n\tif (old_bitmap)\n\t\tkfree_rcu(old_bitmap, rcu);'
QUEUE_OLD = '    // Renew the getpriority uid bitmap filter\n    susfs_parse_priority_app_strings();\n\n'
CALLBACK_OLD = '    if (current->flags & PF_EXITING)\n        return;\n    track_throne(false);\n}'
CALLBACK_NEW = CALLBACK_OLD[:-1] + '    // Renew the getpriority uid bitmap filter\n    susfs_parse_priority_app_strings();\n}'

def store_if_changed(path, data):
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)

def encoded(record):
    return (json.dumps(record, indent=2) + '\n').encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel_root', type=Path)
    args = parser.parse_args()
    root = args.kernel_root.resolve()
    here = Path(__file__).resolve().parent
    pin = json.loads((here / 'susfs-eb95-source.json').read_text(encoding='utf-8'))
    upstream = here / 'upstream-eb95'
    for name, expected in pin['upstream_source_sha256'].items():
        assert SHA((upstream / name).read_bytes()) == expected, ('Official source changed', name)
    commit = json.loads((upstream / 'commit.json').read_text(encoding='utf-8'))
    diff = json.loads((upstream / 'diff.json').read_text(encoding='utf-8'))
    assert commit['id'] == pin['official_commit'] and commit['parent_ids'] == [pin['official_parent']]
    assert {row['new_path'] for row in diff} == {
        'kernel_patches/fs/susfs.c', 'kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch'}
    assert sum(row['diff'].count('+\tsynchronize_rcu();') for row in diff) == 2
    official_ksu = (upstream / '10_enable_susfs_for_ksu.patch').read_text(encoding='utf-8')
    assert 'static void ksu_track_throne_tw_func(struct callback_head *cb)' in official_ksu
    # The current native 4.14 source really uses this old callback name.
    assert pin['existing_deferred_callback'] == 'ksu_track_throne_tw_func'
    # 4.14's macro is not NULL-safe. Bind the exact source before adding guards.
    for path, expected in pin['vendor_rcu_evidence_sha256'].items():
        assert SHA((root / path).read_bytes()) == expected, ('Native RCU implementation changed', path)

    metadata_path = root / 'chopin-ci-port.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    for key, value in pin['expected_runtime_metadata'].items():
        assert metadata.get(key) == value, ('Run after official41100 update', key, metadata.get(key))
    assert metadata['susfs_version'] == '2.3.0'
    assert metadata['builtin_commit'] == pin['builtin_commit']
    assert metadata['susfs_core_upstream'] in (pin['official_parent'], pin['official_commit'])
    planned = {}
    for path, expected_before in pin['before_sha256'].items():
        data = (root / path).read_bytes()
        digest = SHA(data)
        expected_after = pin['after_sha256'][path]
        assert digest in (expected_before, expected_after), ('Unexpected native source', path, digest)
        if digest == expected_after:
            planned[path] = data
            continue
        text = data.decode('utf-8')
        if path == 'fs/susfs.c':
            assert text.count(RCU_OLD) == 2
            assert text.index(RCU_OLD) > text.index('void susfs_set_priority_uid_filter(')
            assert text.rindex(RCU_OLD) > text.index('static int susfs_priority_app_strings_worker(')
            text = text.replace(RCU_OLD, RCU_NEW)
        else:
            assert text.count(QUEUE_OLD) == 1 and text.count(CALLBACK_OLD) == 1
            assert text.index(QUEUE_OLD) > text.index('static void ksu_defer_track_throne(void)')
            text = text.replace(QUEUE_OLD, '', 1).replace(CALLBACK_OLD, CALLBACK_NEW, 1)
        planned[path] = text.encode()
        assert SHA(planned[path]) == expected_after, ('Unexpected patch result', path)

    # Preflight completed for all files before any target writes.
    metadata.update(susfs_core_base_upstream=pin['official_parent'],
                    susfs_core_upstream=pin['official_commit'],
                    susfs_priority_uid_filter_fix=pin['official_commit'],
                    susfs_priority_uid_filter_native414_null_guard=True,
                    susfs_priority_uid_filter_callback='ksu_track_throne_tw_func')
    proof = {
        'status': 'APPLIED_SOURCE_ONLY_CLOUD_AND_RUNTIME_VALIDATION_REQUIRED',
        'official_commit': pin['official_commit'], 'official_parent': pin['official_parent'],
        'upstream_version': '2.3.0', 'before_sha256': pin['before_sha256'],
        'after_sha256': pin['after_sha256'],
        'official_rcu_grace_periods_added': 2, 'native414_null_guards_added': 2,
        'priority_refresh_after_existing_task_work_track_throne': True,
        'defer_entry_no_longer_starts_priority_worker': True,
        'PF_EXITING_guard_and_inline_fallback_unchanged': True,
        'manager_41100_uapi6_extension2_kpm1_unchanged': True,
        'vendor_rcu_evidence_commit': pin['vendor_rcu_evidence_commit'],
        'vendor_rcu_evidence_sha256': pin['vendor_rcu_evidence_sha256'],
        'upstream_source_sha256': pin['upstream_source_sha256'],
        'UAF_or_NULL_crash_reproduced_on_phone': False,
        'scope': pin['scope']}
    for path, data in planned.items():
        store_if_changed(root / path, data)
    store_if_changed(metadata_path, encoded(metadata))
    store_if_changed(root / 'susfs-priority-filter-eb95.json', encoded(proof))
    print('Native SUSFS2.3 eb95 priority-filter source fix staged; cloud build and runtime validation required')

if __name__ == '__main__':
    main()
