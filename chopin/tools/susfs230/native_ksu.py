"""Connect the real native SUSFS2.3 backend to the pinned 4.14 SukiSU driver.

Run after the pinned builder's path_umount and general 4.14 compatibility
functions. No legacy SUSFS dispatcher, old task fields or personal signer.
"""
from pathlib import Path
import json,runpy,subprocess,sys
root=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
ports=here.parents[1];ksu=root/'KernelSU/kernel'
subprocess.run([sys.executable,str(here/'fix_kstat_ctime.py'),str(root)],check=True)
def edit(path,old,new):
    p=root/path;s=p.read_text();assert s.count(old)==1,(path,old[:80],s.count(old))
    p.write_text(s.replace(old,new,1))
def run(name):
    try:
        runpy.run_path(str(ports/name),run_name='__main__')
    except SystemExit as result:
        # Some standalone port scripts explicitly exit(0) after a successful
        # version branch. Only that success ends the child script, not this
        # multi-step port. Every nonzero error must still abort the build.
        if result.code not in (None,0):raise

def prefix(name,delimiter,changes=()):
    p=ports/name;s=p.read_text().split(delimiter)[0]
    for old,new in changes:s=s.replace(old,new)
    exec(compile(s,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})

run('stock_module_layout.py');run('port_vendor_refcnt.py')
# Only exec and init.rc read interception; stat/access already use the native
# filename-based SUSFS2.3 hooks, with the original permission checks retained.
prefix('port_hooks.py','# SukiSU builtin with SUSFS expects struct filename')
prefix('port_414_compat.py','# Linux 4.14 SUSFS v1.5.5')
run('port_414_optional.py')
saved=sys.argv[:]
try:
    sys.argv=[saved[0],str(root),str(root)]
    prefix('port_susfs155.py','patch=(susfs/',[("SUSFS_VERSION \"v1.5.5\"","SUSFS_VERSION \"v2.3.0\"")])
finally:sys.argv=saved

# Return only for the two private transport magics. Normal Android reboot
# continues through the untouched vendor capability and command validation.
edit('kernel/reboot.c','\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);',
     '\tif ((u32)magic1 == 0xDEADBEEFu &&\n'
     '\t    ((u32)magic2 == 0xCAFEBABEu || (u32)magic2 == 0xFAFAFAFAu))\n'
     '\t\treturn ksu_handle_sys_reboot(magic1, magic2, cmd, &arg);')
# The native SUSFS branch exposes ksu_handle_setresuid(), not the other
# branch's private ksu_task_fix_setuid(). Use the real 4.14 LSM credential
# boundary and pass the validated new UIDs while current still has old creds.
edit('KernelSU/kernel/hook/lsm_hook.c',
     'static struct security_hook_list ksu_hooks[] = {',
     '''#ifdef CONFIG_KSU_SUSFS
static noinline int chopin_native_task_fix_setuid(struct cred *new,
                                        const struct cred *old, int flags)
{
    if (!new || !old || old->uid.val != 0)
        return 0;
    return ksu_handle_setresuid(new->uid.val, new->euid.val, new->suid.val);
}
#endif
static struct security_hook_list ksu_hooks[] = {''')
edit('KernelSU/kernel/hook/lsm_hook.c',
     '#ifndef CONFIG_KSU_SUSFS\n    LSM_HOOK_INIT(task_fix_setuid, ksu_task_fix_setuid),\n#endif',
     '#ifdef CONFIG_KSU_SUSFS\n    LSM_HOOK_INIT(task_fix_setuid, chopin_native_task_fix_setuid),\n#else\n    LSM_HOOK_INIT(task_fix_setuid, ksu_task_fix_setuid),\n#endif')
edit('KernelSU/kernel/hook/lsm_hook.c','int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid)', 'noinline int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid)')
guard='#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n'
edit('KernelSU/kernel/policy/feature.c',
     '    [KSU_FEATURE_SELINUX_HIDE] = "selinux_hide",',
     guard+'    [KSU_FEATURE_SELINUX_HIDE] = "selinux_hide",\n#endif')
run('port_kpm_io.py')
# Reuse the actual original-policy and audit implementation, replacing only
# the former legacy-dispatch include anchor with the native dispatch anchor.
p=ports/'port_avc_audit_display.py';s=p.read_text().replace(
    'chopin_susfs_typed_reboot.c','supercall/dispatch.c')
exec(compile(s,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
run('port_selinux_query_snapshot.py');run('complete_selinux_query_view.py')
run('port_requested_features.py');run('port_ci_extensions.py')

# The native SUSFS ioctl and the SukiSU feature toggle share one real key.
p=ksu/'chopin_avc_audit_display.c';s=p.read_text()
s=s.replace('static bool chopin_avc_enabled = true;',
            'extern struct static_key_false susfs_is_avc_log_spoofing_enabled;')
s=s.replace('READ_ONCE(chopin_avc_enabled)',
            'static_branch_unlikely(&susfs_is_avc_log_spoofing_enabled)')
s=s.replace('    WRITE_ONCE(chopin_avc_enabled, value != 0);',
            '    if (value)\n        static_branch_enable(&susfs_is_avc_log_spoofing_enabled);\n'
            '    else\n        static_branch_disable(&susfs_is_avc_log_spoofing_enabled);')
needle='    int error = ksu_register_feature_handler(&chopin_avc_feature);'
assert s.count(needle)==1;s=s.replace(needle,needle+'\n    if (!error)\n        static_branch_enable(&susfs_is_avc_log_spoofing_enabled);',1)
p.write_text(s)

# Latest upstream priority filter: preserve PRIO_USER error semantics, and
# apply only to requests for another app UID, exactly as its upstream hook.
p=root/'kernel/sys.c';s=p.read_text();anchor='SYSCALL_DEFINE3(setpriority,'
assert s.count(anchor)==1;s=s.replace(anchor,
    '#ifdef CONFIG_KSU_SUSFS\nextern bool susfs_is_priority_uid_filtered(uid_t uid);\n#endif\n'+anchor,1)
for start_name in ['SYSCALL_DEFINE3(setpriority,','SYSCALL_DEFINE2(getpriority,']:
    a=s.index(start_name);b=s.index('\n}\n',a)+3;body=s[a:b]
    needle='\t\telse if (!uid_eq(uid, cred->uid)) {';assert body.count(needle)==1
    body=body.replace(needle,needle+'\n#ifdef CONFIG_KSU_SUSFS\n'
        '\t\t\tif (cred->uid.val >= 10000 && susfs_is_priority_uid_filtered(uid.val))\n'
        '\t\t\t\tgoto out_unlock;\n#endif',1);s=s[:a]+body+s[b:]
p.write_text(s)
edit('KernelSU/kernel/manager/pkg_observer.c',
     '#ifdef CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER\n    susfs_parse_priority_app_strings();\n#endif',
     '    susfs_parse_priority_app_strings();')
p=root/'chopin-ci-port.json';r=json.loads(p.read_text());r.update(
    susfs_version='2.3.0',priority_uid_filter_supported=True,
    susfs_core_upstream='5419f4ee97cc8bf7ca67a9ff207f39653d7784f4',
    personal_manager_signature_added=False);p.write_text(json.dumps(r,indent=2))
assert '33a63461c5442d981bcab44b168cb4ab6d50462e21ce5a6ecb668305a9b422cc' not in (ksu/'manager/apk_sign.c').read_text()
print('Native2.3 syscall/LSM/driver, current KPM, original-policy/audit/CPU/ADB paths staged; object/link/device acceptance still required')
