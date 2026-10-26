"""Check real linked ARM64 transport/query/audit calls in the unpatched Image."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

p = argparse.ArgumentParser()
p.add_argument('--image', type=Path, required=True)
p.add_argument('--system-map', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
data = a.image.read_bytes()
symbols = {parts[2]: int(parts[0], 16) for line in a.system_map.read_text().splitlines()
           if len(parts := line.split()) == 3}
base = symbols['_text']
addresses = sorted(set(symbols.values()))


def calls(caller, callee):
    start, dest = symbols[caller], symbols[callee]
    end = next(x for x in addresses if x > start)
    assert 0 <= start-base < end-base <= len(data), caller
    found = []
    for pc in range(start, end, 4):
        op, = struct.unpack_from('<I', data, pc-base)
        if op & 0x7c000000 != 0x14000000:
            continue
        offset = op & 0x03ffffff
        if offset & 0x02000000:
            offset -= 0x04000000
        if pc + 4*offset == dest:
            found.append(hex(pc))
    assert found, (caller, callee, 'missing real B/BL')
    return found


edges = [('SyS_reboot', 'ksu_handle_sys_reboot'),
         ('slow_avc_audit', 'chopin_avc_audit_tsid'),
         ('on_post_fs_data', 'chopin_avc_resolve_sids'),
         ('apply_kernelsu_rules', 'chopin_selinux_capture_original')]
queries = ['sel_open_policy', 'sel_write_context', 'sel_write_validatetrans',
           'sel_write_access', 'sel_write_create', 'sel_write_relabel',
           'sel_write_user', 'sel_write_member']
edges += [(q, 'chopin_selinux_query_state') for q in queries]
records = [{'caller': x, 'callee': y, 'sites': calls(x, y)} for x, y in edges]
native_edges=[('chopin_native_task_fix_setuid','ksu_handle_setresuid'),
 ('SyS_getpriority','susfs_is_priority_uid_filtered'),
 ('SyS_setpriority','susfs_is_priority_uid_filtered'),
 ('ksu_handle_sys_reboot','susfs_add_sus_path_loop'),
 ('ksu_handle_sys_reboot','susfs_add_sus_map'),
 ('ksu_handle_sys_reboot','susfs_set_priority_uid_filter')]
records += [{'caller':x,'callee':y,'sites':calls(x,y)} for x,y in native_edges]
for name in ['susfs_add_sus_path_loop','susfs_add_sus_map','susfs_set_priority_uid_filter',
 'ksu_handle_umount','path_umount','chopin_native_task_fix_setuid',
 'chopin_avc_feature_set','chopin_selinux_hide_set']:
 assert name in symbols,name
for name in ['forced_mask', 'forced_pending']:
    assert symbols['feature_' + name] != symbols[name], ('shared feature/extension bitmap', name)

result = {'status': 'PASS_REAL_LINKED_FEATURE_PATHS_ONLY',
          'image_sha256': hashlib.sha256(data).hexdigest(), 'edges': records,
          'hardware_validated': False, 'runtime_feature_validation': 'PENDING'}
a.report.write_text(json.dumps(result, indent=2))
print(result['status'])
