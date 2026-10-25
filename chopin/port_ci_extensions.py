"""Apply the pinned manager CI additions to the current builtin 4.14 port."""
from pathlib import Path
import sys,re,json,hashlib
root=Path(sys.argv[1]);here=Path(__file__).resolve().parent;ksu=root/'KernelSU/kernel';up=here/'upstream-ci'
def edit(path,old,new):
 p=ksu/path;s=p.read_text(encoding='utf-8');assert s.count(old)==1,(path,old[:100],s.count(old));p.write_text(s.replace(old,new,1),encoding='utf-8',newline='\n')
for n in ['version_spoof.c','version_spoof.h']:(ksu/'extension'/n).write_bytes((up/'kernel/extension'/n).read_bytes())
p=ksu/'extension/version_spoof.c';v=p.read_text(encoding='utf-8');v=v.replace('void ksu_version_spoof_apply_', 'noinline void ksu_version_spoof_apply_');p.write_text(v,encoding='utf-8',newline='\n')
(ksu/'include/uapi/extension.h').write_bytes((up/'uapi/extension.h').read_bytes())
edit('ksu_main.c','#include "extension/extension.h"','#include "extension/version_spoof.h"\n#include "extension/extension.h"')
edit('ksu_main.c','#include "extension/extension.c"','#include "extension/extension.c"\n#include "extension/version_spoof.c"')
edit('extension/extension.c','    [KSU_EXTENSION_SUSFS] = "susfs",','    [KSU_EXTENSION_SUSFS] = "susfs",\n    [KSU_EXTENSION_VERSION_SPOOF] = "version_spoof",')
p=ksu/'extension/extension.c';s=p.read_text(encoding='utf-8');at=s.index('    if (ksu_register_extension_handler(&kpm_handler))')
handler='''    static const struct ksu_extension_handler version_spoof_handler = {
        .extension_id = KSU_EXTENSION_VERSION_SPOOF,
        .name = "version_spoof",
        .ops = NULL,
        .io_handler = ksu_extension_version_spoof_io,
        .wipe = ksu_extension_version_spoof_wipe,
    };

'''
s=s[:at]+handler+s[at:];needle='    /* Publish: any future ksu_extension_apply_forced() is now safe.'
assert s.count(needle)==1;s=s.replace(needle,'    if (ksu_register_extension_handler(&version_spoof_handler))\n        pr_err("extension: failed to register version_spoof\\n");\n\n'+needle,1);p.write_text(s,encoding='utf-8',newline='\n')
p=ksu/'supercall/dispatch.c';s=p.read_text(encoding='utf-8');s='#include "extension/version_spoof.h"\n'+s
for name,call in [('do_get_info','ksu_version_spoof_apply_info(&cmd);'),('do_get_info_legacy','ksu_version_spoof_apply_info_legacy(&cmd);'),('do_get_full_version','ksu_version_spoof_apply_full_version(cmd.version_full, sizeof(cmd.version_full));')]:
 start=s.index('static int '+name+'(');end=s.index('\n}',start)+2;body=s[start:end];needle='    if (copy_to_user(arg, &cmd, sizeof(cmd)))';assert body.count(needle)==1,name
 body=body.replace(needle,'    '+call+'\n\n'+needle,1);s=s[:start]+body+s[end:]
p.write_text(s,encoding='utf-8',newline='\n')
# The SUSFS 1.5.5 branch has no priority-filter backend. Do not call an absent
# function or claim its support. Its original working configuration is retained.
edit('manager/pkg_observer.c','    susfs_parse_priority_app_strings();','#ifdef CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER\n    susfs_parse_priority_app_strings();\n#endif')
# Preserve the builtin file's 4.14 compatibility helpers, taking only the RCU
# lifetime correction from the current CI implementation.
p=ksu/'policy/allowlist.c';s=p.read_text(encoding='utf-8');new=(up/'kernel/policy/allowlist.c').read_text(encoding='utf-8')
start=new.index('bool ksu_uid_should_umount(uid_t uid)');end=new.index('\nvoid ksu_put_app_profile',start);body=new[start:end]
at=s.index('bool ksu_uid_should_umount(uid_t uid)');finish=s.index('\nvoid ksu_put_app_profile',at);s=s[:at]+body+s[finish:];p.write_text(s,encoding='utf-8',newline='\n')
# Pin the version to the published CI revision rather than a network-dependent
# mutable main-branch commit count during an incremental build.
p=ksu/'Makefile';s=p.read_text(encoding='utf-8');s,n=re.subn(r'(?m)^KSU_VERSION\s*:=.*$','KSU_VERSION := 41084',s);assert n==1
s,n=re.subn(r'(?m)^KSU_VERSION_FULL\s*:=.*$','KSU_VERSION_FULL := v4.2.1-r2-6397fcb5@builtin+3b58d46f',s);assert n==1;p.write_text(s,encoding='utf-8',newline='\n')
record=dict(builtin_commit='6397fcb5d96e8f4953c71e02c73f8c6800541bff',manager_ci_commit='3b58d46f7e109e49d4133d6c04636f724bd65983',version_code=41084,uapi_version=6,version_spoof_default_mask=0,priority_uid_filter_supported=False,upstream_files={str(p.relative_to(up)):hashlib.sha256(p.read_bytes()).hexdigest() for p in up.rglob('*') if p.is_file()})
(root/'chopin-ci-port.json').write_text(json.dumps(record,indent=2))
print('Applied CI version extension and RCU profile lookup; UAPI remains 6')
