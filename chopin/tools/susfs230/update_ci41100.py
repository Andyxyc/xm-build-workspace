"""Apply the actual v4.3.0 parser fix after audited CI41098 compatibility.

The upstream dual-policy parser is source-backported, not enabled on 4.14.
The active 4.14 original-policy snapshot and native state-based parser remain
byte-identical. Keep this distinction in the build manifest and release notes.
"""
from pathlib import Path
import hashlib,json,re,sys
root=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
pin=json.loads((here/'ci41100-source.json').read_text(encoding='utf-8'))
up=here/'upstream-ci41100';ksu=root/'KernelSU/kernel'
sha=lambda b:hashlib.sha256(b).hexdigest()
def function(source,name):
    matches=list(re.finditer(r'^static int '+re.escape(name)+r'\([^;]*?\)\n\{',source,re.M))
    assert len(matches)==1,(name,'exactly one definition required')
    start=matches[0].start();end=source.index('\n}',start)+3
    return source[start:end]
for name,expected in pin['upstream_files'].items():
    assert sha((up/name).read_bytes())==expected,('Upstream source changed',name)
for name,expected in pin['expected_before_sha256'].items():
    assert sha((root/name).read_bytes())==expected,('Changed base source; review instead of guessing',name)
record_file=root/'chopin-ci-port.json';record=json.loads(record_file.read_text(encoding='utf-8'))
assert record['version_code']==41098 and record['uapi_version']==6 and record['extension_api_version']==2
assert record['kpm_bridge_abi']==1 and record['kpm_event_aware_load_supported'] is False
assert '#define SUKISU_KPM_ABI_VERSION 1' in (ksu/'extension/kpm/bridge.h').read_text(encoding='utf-8')
guard='#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n#include "feature/selinux_hide.c"\n#endif'
main=(ksu/'ksu_main.c').read_text(encoding='utf-8');assert main.count(guard)==1
assert '#include "chopin_selinux_query_snapshot.c"' in main
native=(root/'security/selinux/ss/services.c').read_text(encoding='utf-8')
assert 'struct selinux_state *state' in function(native,'security_context_to_sid_core')
assert 'struct policydb *orig_pol' not in function(native,'string_to_context_struct')
snapshot=ksu/'chopin_selinux_query_snapshot.c';snapshot_before=snapshot.read_bytes()
before=(ksu/'feature/selinux_hide.c').read_text(encoding='utf-8')
old_reference=(up/'builtin6397/kernel/feature/selinux_hide.c').read_text(encoding='utf-8')
new_reference=(up/'kernel/feature/selinux_hide.c').read_text(encoding='utf-8')
after=before
for name,expected in pin['old_parser_function_sha256'].items():
    old=function(old_reference,name);new=function(new_reference,name)
    assert sha(old.encode())==expected and sha(new.encode())==pin['new_parser_function_sha256'][name]
    assert after.count(old)==1,(name,'fixed builtin parser no longer exact')
    after=after.replace(old,new,1)
assert sha(after.encode())==pin['patched_builtin_selinux_hide_sha256']
(ksu/'feature/selinux_hide.c').write_text(after,encoding='utf-8',newline='\n')
makefile=ksu/'Makefile';make=makefile.read_text(encoding='utf-8')
for old,new in [('KSU_VERSION := 41098','KSU_VERSION := 41100'),
                ('VERSION_TAG     := $(or $(KSU_GITHUB_VER),$(git_latest_tag),4.2.1)',
                 'VERSION_TAG     := $(or $(KSU_GITHUB_VER),$(git_latest_tag),4.3.0)'),
                ('KSU_VERSION_FULL := v4.2.1-r2-6397fcb5@builtin+29f8b18d',
                 'KSU_VERSION_FULL := v4.3.0-6397fcb5@builtin+e67b14e6')]:
    assert make.count(old)==1,old
    make=make.replace(old,new,1)
makefile.write_text(make,encoding='utf-8',newline='\n')
assert snapshot.read_bytes()==snapshot_before
assert sha((root/'security/selinux/ss/services.c').read_bytes())==pin['expected_before_sha256']['security/selinux/ss/services.c']
record.update(manager_ci_commit=pin['main_commit'],version_code=41100,version_name='v4.3.0',
              official_release_tag='v4.3.0',current_ci_source_verification=pin,
              extension_api_version=2,extension_caps_kernel_reported=True,extension_enumeration_supported=True,
              kpm_bridge_abi=1,kpm_event_aware_load_supported=False,version_spoof_default_mask=0,
              selinux_parser_upstream_fix='e67b14e6/tiann-KernelSU-3936',
              selinux_dual_parser_fix_source_backported=True,
              selinux_dual_parser_compiled_on_414=False,
              selinux_414_active_backend='original_policy_query_snapshot_plus_vendor_state_based_services_parser',
              selinux_414_query_snapshot_unchanged=True)
record_file.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
proof={'status':'SOURCE_BACKPORT_ONLY_COMPILE_AND_RUNTIME_PENDING','main_commit':pin['main_commit'],
       'builtin_retained':pin['builtin_commit'],'version_code':41100,'version_name':'v4.3.0',
       'parser_before_sha256':sha(before.encode()),'parser_after_sha256':sha(after.encode()),
       'upstream_dual_policy_parser_replaced_exactly':True,'guarded_out_on_414':True,
       'active_native_parser_unchanged':True,'query_snapshot_unchanged':True,
       'uapi':6,'extension_api':2,'kpm_bridge_abi':1,'event_aware_load_supported':False,
       'full_latest_builtin_replaced':False}
(root/'chopin-release41100-port.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8',newline='\n')
print('v4.3.0/41100 actual source backport: e67 dual-parser fix retained behind >=5.10 guard; active4.14 QuerySnapshot/native parser unchanged; UAPI6 extensionABI2 KPMbridgeABI1. Compile/runtime still required.')
