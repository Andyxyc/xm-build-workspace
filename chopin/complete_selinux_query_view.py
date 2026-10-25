"""Complete r5's original-policy view for the state-based vendor SELinux.

Keep permission enforcement live. Select the same original state for raw
selinuxfs access/context queries, the status mmap and context validity probes.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]);ksu=root/'KernelSU/kernel'
def edit(path,old,new):
 p=root/path;s=p.read_text();assert s.count(old)==1,(path,old[:90],s.count(old));p.write_text(s.replace(old,new,1))

p=ksu/'chopin_selinux_query_snapshot.c';s=p.read_text()
old='    snapshot->state.ss = &snapshot->server;'
new=old+'''
    /* Match the clean policy's status baseline; never map the modified live
     * server's reload counters beside an original-policy access vector. */
    {
        struct page *live_status = selinux_kernel_status_page(&selinux_state);
        if (!live_status) { error = -ENOMEM; goto fail; }
        snapshot->server.status_page = alloc_page(GFP_KERNEL | __GFP_ZERO);
        if (!snapshot->server.status_page) { error = -ENOMEM; goto fail; }
        mutex_lock(&selinux_state.ss->status_lock);
        memcpy(page_address(snapshot->server.status_page),
               page_address(live_status), PAGE_SIZE);
        mutex_unlock(&selinux_state.ss->status_lock);
    }'''
assert s.count(old)==1;s=s.replace(old,new,1)
old='        kfree(snapshot->server.map.mapping);'
assert s.count(old)==1;s=s.replace(old,'        if (snapshot->server.status_page)\n            __free_page(snapshot->server.status_page);\n'+old,1)
s=s.replace('    if (!READ_ONCE(chopin_selinux_hide_enabled) ||',
            '    if (!enforcing_enabled(live) || !READ_ONCE(chopin_selinux_hide_enabled) ||',1)
p.write_text(s)
edit('security/selinux/selinuxfs.c',
     'struct page    *status = selinux_kernel_status_page(fsi->state);',
     'struct page    *status = selinux_kernel_status_page(chopin_selinux_query_state(fsi->state));')
# Reject contexts absent from the selected original view before converting
# them with the live SID table. Real transition permission checks stay live.
edit('security/selinux/hooks.c',
     '\t\terror = security_context_to_sid(&selinux_state, value, size,\n\t\t\t\t\t\t&sid, GFP_KERNEL);',
     '''#ifdef CONFIG_KSU
        if (!strcmp(name, "current")) {
            struct selinux_state *query = chopin_selinux_query_state(&selinux_state);
            if (query != &selinux_state) {
                u32 query_sid;
                error = security_context_to_sid(query, value, size,
                                                &query_sid, GFP_KERNEL);
                if (error)
                    return error;
            }
        }
#endif
\t\terror = security_context_to_sid(&selinux_state, value, size,
\t\t\t\t\t\t&sid, GFP_KERNEL);''')
# The AVC feature must render both ends of a root-domain denial consistently.
edit('security/selinux/avc.c','\tsad.ssid = ssid;',
     '#ifdef CONFIG_KSU\n\tsad.ssid = chopin_avc_audit_tsid(ssid);\n#else\n\tsad.ssid = ssid;\n#endif')
print('Completed original-policy status mmap/context validity view and both AVC audit context endpoints')
