"""Backport the real AVC display feature without changing access decisions."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
ksu = root / 'KernelSU/kernel'


def edit(name, old, new, count=1):
    path = root / name
    source = path.read_text()
    assert source.count(old) == count, (name, old, source.count(old))
    path.write_text(source.replace(old, new))


edit('KernelSU/kernel/include/uapi/feature.h', '    KSU_FEATURE_MAX',
     '    KSU_FEATURE_AVC_SPOOF = 10003,\n\n    KSU_FEATURE_MAX')
edit('KernelSU/kernel/policy/feature.c',
     '    [KSU_FEATURE_MOUNT_HIDE] = "mount_hide",',
     '    [KSU_FEATURE_MOUNT_HIDE] = "mount_hide",\n'
     '    [KSU_FEATURE_AVC_SPOOF] = "avc_spoof",')
# The builtin tree uses a unity translation unit. Tentative bitmap definitions
# shared a name while both fit in one word, but are independent subsystems.
# The real official AVC ID extends only the feature bitmap to 10004 entries.
import re
feature_source = ksu / 'policy/feature.c'
text = feature_source.read_text()
for old in ['forced_mask', 'forced_pending']:
    text, count = re.subn(r'\b' + old + r'\b', 'feature_' + old, text)
    assert count == 4, (old, count)
feature_source.write_text(text)

edit('KernelSU/kernel/ksu_main.c', '#include "chopin_susfs_typed_reboot.c"',
     '#include "chopin_avc_audit_display.c"\n#include "chopin_susfs_typed_reboot.c"')
edit('KernelSU/kernel/ksu_main.c', '    ksu_feature_init();',
     '    ksu_feature_init();\n    chopin_avc_feature_init();')
edit('KernelSU/kernel/runtime/ksud.c', '    pr_info("on_post_fs_data!\\n");',
     '    pr_info("on_post_fs_data!\\n");\n    chopin_avc_resolve_sids();')

path = root / 'security/selinux/avc.c'
source = path.read_text()
start = source.index('noinline int slow_avc_audit(struct selinux_state *state,')
end = source.index('\n}\n', start) + 3
body = source[start:end]
assert body.count('\tsad.tsid = tsid;') == 1
body = body.replace('\tsad.tsid = tsid;',
    '#ifdef CONFIG_KSU\n\tsad.tsid = chopin_avc_audit_tsid(tsid);\n'
    '#else\n\tsad.tsid = tsid;\n#endif')
declaration = '#ifdef CONFIG_KSU\nextern u32 chopin_avc_audit_tsid(u32 tsid);\n#endif\n'
path.write_text(source[:start] + declaration + body + source[end:])
(ksu / 'chopin_avc_audit_display.c').write_bytes(
    (Path(__file__).parent / 'avc_audit_display.c').read_bytes())
print('AVC target audit rendering hooked; decision fields and return value unchanged')
