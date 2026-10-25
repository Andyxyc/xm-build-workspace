"""Genuine original-policy selinuxfs queries using the vendor state API."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
ksu = root / 'KernelSU/kernel'


def edit(path, before, after):
    file = root / path
    text = file.read_text()
    assert text.count(before) == 1, (path, before, text.count(before))
    file.write_text(text.replace(before, after, 1))


guard = '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n'
edit('KernelSU/kernel/include/uapi/feature.h',
     guard + '    KSU_FEATURE_SELINUX_HIDE = 4,\n#endif',
     '    KSU_FEATURE_SELINUX_HIDE = 4,')
edit('KernelSU/kernel/policy/feature.c',
     guard + '    [KSU_FEATURE_SELINUX_HIDE] = "selinux_hide",\n#endif',
     '    [KSU_FEATURE_SELINUX_HIDE] = "selinux_hide",')
edit('KernelSU/kernel/ksu_main.c', '#include "chopin_avc_audit_display.c"',
     '#include "chopin_selinux_query_snapshot.c"\n#include "chopin_avc_audit_display.c"')
edit('KernelSU/kernel/ksu_main.c', '    chopin_avc_feature_init();',
     '    chopin_avc_feature_init();\n    chopin_selinux_hide_init();')
edit('KernelSU/kernel/selinux/rules.c',
     '    cpumask_t old_mask;\n    db = get_policydb();',
     '    cpumask_t old_mask;\n    chopin_selinux_capture_original();\n    db = get_policydb();')

path = root / 'security/selinux/selinuxfs.c'
text = path.read_text()
queries = ['sel_open_policy', 'sel_write_context', 'sel_write_validatetrans',
           'sel_write_access', 'sel_write_create', 'sel_write_relabel',
           'sel_write_user', 'sel_write_member']
for name in queries:
    # Exclude the forward declarations: search for the actual function body.
    import re
    found = list(re.finditer(r'static (?:int|ssize_t) ' + name +
                            r'\([^;]*?\)\n\{', text))
    assert len(found) == 1, (name, len(found))
    start = found[0].start()
    end = text.index('\n}\n', start) + 3
    body = text[start:end]
    old = '\tstruct selinux_state *state = fsi->state;'
    assert body.count(old) == 1, name
    body = body.replace(old, '\tstruct selinux_state *state = chopin_selinux_query_state(fsi->state);', 1)
    text = text[:start] + body + text[end:]
old = 'rc = security_read_policy(state, &plm->data, &plm->len);'
assert text.count(old) == 1
text = text.replace(old, 'rc = chopin_selinux_read_query_policy(state, &plm->data, &plm->len);', 1)
path.write_text(text)
edit('security/selinux/include/security.h', 'extern struct selinux_state selinux_state;',
     'extern struct selinux_state selinux_state;\n#ifdef CONFIG_KSU\n'
     'struct selinux_state *chopin_selinux_query_state(struct selinux_state *live);\n'
     'int chopin_selinux_read_query_policy(struct selinux_state *state, void **data, size_t *length);\n'
     '#else\n#define chopin_selinux_read_query_policy security_read_policy\n'
     'static inline struct selinux_state *chopin_selinux_query_state(struct selinux_state *live)\n'
     '{\n\treturn live;\n}\n#endif')
(ksu / 'chopin_selinux_query_snapshot.c').write_bytes(
    (Path(__file__).parent / 'selinux_query_snapshot.c').read_bytes())
print('Eight real selinuxfs queries use an independent original policy for app UIDs; live permission checks remain')
