"""Backport actual CI41098 extension ABI/caps/ENUM after update_ci41095.py.

Keep the boot-tested 4.14 builtin, actual KPM bridge ABI1 and Arm GNU payload.
This is an audited compatibility backport, not a whole-main integration claim.
"""
from pathlib import Path
import hashlib,json,re,sys
root=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
pin=json.loads((here/'ci41098-source.json').read_text(encoding='utf-8'))
up=here/'upstream-ci41098';ksu=root/'KernelSU/kernel'
sha=lambda data:hashlib.sha256(data).hexdigest()
for name,h in pin['upstream_files'].items():
 assert sha((up/name).read_bytes())==h,name
for name,h in pin['expected_before_sha256'].items():
 assert sha((root/'KernelSU'/name).read_bytes())==h,('Changed base source; review instead of guessing',name)
makefile=ksu/'Makefile';make=makefile.read_text(encoding='utf-8')
assert make.count('KSU_VERSION := 41095')==1 and make.count('6397fcb5@builtin+96ceb4a4')==1
record_file=root/'chopin-ci-port.json';record=json.loads(record_file.read_text(encoding='utf-8'))
assert record['version_code']==41095 and record['uapi_version']==6
assert '#define SUKISU_KPM_ABI_VERSION 1' in (ksu/'extension/kpm/bridge.h').read_text(encoding='utf-8')

# This 4.14 driver is a unity translation unit. The unprefixed static
# forced_values in upstream collides with policy/feature.c in that model.
extension=(up/'kernel/extension/extension.c').read_text(encoding='utf-8')
extension=re.sub(r'\bforced_values\b','extension_forced_values',extension)
include_block='''#include "extension.h"
#include "kpm.h"
#include "cpu_spoof.h"
#include "umount_paths.h"
#include "dynamic_manager.h"
#include "susfs_extension.h"
#include "version_spoof.h"
#include "klog.h" // IWYU pragma: keep

'''
assert extension.count(include_block)==1
extension=extension.replace(include_block,'',1)

# Port only the real extension dispatcher. Other 4.14, SELinux and reboot
# adaptations remain byte-identical to the already compiled driver.
dispatch_file=ksu/'supercall/dispatch.c';dispatch=dispatch_file.read_text(encoding='utf-8')
old_start=dispatch.index('/*\n * Single entry point',dispatch.index('static int do_get_hook_type('))
old_end=dispatch.index('\n// IOCTL handlers mapping table',old_start)
new=(up/'kernel/supercall/dispatch.c').read_text(encoding='utf-8')
new_start=new.index('/* Capability bits for a reply:')
new_end=new.index('\n// IOCTL handlers mapping table',new_start)
replacement=new[new_start:new_end]
assert replacement.count('static int do_extension(')==1 and 'KSU_EXTENSION_ENUM' in replacement
dispatch=dispatch[:old_start]+replacement+dispatch[old_end:]

(ksu/'extension/extension.c').write_text(extension,encoding='utf-8',newline='\n')
(ksu/'extension/extension.h').write_bytes((up/'kernel/extension/extension.h').read_bytes())
(ksu/'include/uapi/extension.h').write_bytes((up/'uapi/extension.h').read_bytes())
dispatch_file.write_text(dispatch,encoding='utf-8',newline='\n')
make=make.replace('KSU_VERSION := 41095','KSU_VERSION := 41098',1).replace('6397fcb5@builtin+96ceb4a4','6397fcb5@builtin+29f8b18d',1)
makefile.write_text(make,encoding='utf-8',newline='\n')
record.update(manager_ci_commit=pin['main_commit'],version_code=41098,current_ci_source_verification=pin,extension_api_version=2,extension_caps_kernel_reported=True,extension_enumeration_supported=True,kpm_bridge_abi=1,kpm_event_aware_load_supported=False,version_spoof_default_mask=0)
record_file.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Actual CI41098 caps/ABI/ENUM backport; UAPI6; extensionABI2; tested KPM bridgeABI1 retained. Compile/link/device checks remain required.')
