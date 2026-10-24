#!/usr/bin/env python3
"""Restore real ARM64 BHB/1188873 implementation matching the stock capability ABI.

Common CPU code only, from MiCode/Xiaomi_Kernel_OpenSource GPL-2.0 source
f4e416aea06c81f1e661d0524c0554f0538d11cb (camellian-t-oss).
No device trees, camera, platform, clock/DVFS or thermal drivers are imported.
The unrelated camera/HWCONF Kconfig and Makefile differences are excluded.
"""
from pathlib import Path
import hashlib,re,subprocess,sys
root=Path(sys.argv[1]).resolve()
patch=Path(__file__).resolve().parent/'patches/arm64-stock-bhb-1188873.patch'
assert hashlib.sha256(patch.read_bytes()).hexdigest()=='5ee770ee97e9269825eb72a3573f5b3afd59a119ae5881c868084261c14cd045'
names=re.findall(r'^\+\+\+ b/(.+)$',patch.read_text(),flags=re.M)
assert len(names)==20
assert all(p.startswith('arch/arm64/') or p in ['drivers/clocksource/arm_arch_timer.c','include/linux/arm-smccc.h'] for p in names)
assert not any('/dts/' in p or '/configs/' in p or '..' in Path(p).parts for p in names)
kconfig=(root/'arch/arm64/Kconfig').read_text()
camera=kconfig[kconfig.index('config BUILD_XIAOMI_CAMERA_IMAGE_NAMES'):]
hwconf=(root/'arch/arm64/kernel/Makefile').read_bytes()
subprocess.run(['git','-C',str(root),'apply','--check','--whitespace=error',str(patch)],check=True)
subprocess.run(['git','-C',str(root),'apply','--whitespace=error',str(patch)],check=True)
after=(root/'arch/arm64/Kconfig').read_text()
assert after[after.index('config BUILD_XIAOMI_CAMERA_IMAGE_NAMES'):]==camera
assert (root/'arch/arm64/kernel/Makefile').read_bytes()==hwconf
assert re.search(r'^#define ARM64_NCAPS\s+30$',(root/'arch/arm64/include/asm/cpucaps.h').read_text(),re.M)
for name in ['ARM64_ERRATUM_1188873','MITIGATE_SPECTRE_BRANCH_HISTORY']:
    assert 'config '+name+'\n' in after
print('Applied real ARM64 CPU mitigation implementation; original chopin camera/HWCONF definitions retained')
