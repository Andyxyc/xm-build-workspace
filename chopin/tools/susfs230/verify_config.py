"""All common stock/root gates plus the real native SUSFS2.3 features.
The removed legacy TRY_UMOUNT option is superseded by the native KernelSU
unmount path, which is separately checked in linked ARM64 code.
"""
from pathlib import Path
import sys
values={}
for line in Path(sys.argv[1]).read_text().splitlines():
 if line.startswith('CONFIG_') and '=' in line:
  k,v=line.split('=',1);values[k]=v
 elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
  values[line[2:].split(' is not set')[0]]='n'
required={'CONFIG_KSU': 'y', 'CONFIG_KSU_FEATURE_ADBROOT': 'y', 'CONFIG_KPM': 'y', 'CONFIG_KALLSYMS': 'y', 'CONFIG_KALLSYMS_ALL': 'y', 'CONFIG_KSU_SUSFS': 'y', 'CONFIG_KSU_SUSFS_SUS_PATH': 'y', 'CONFIG_KSU_SUSFS_SUS_MOUNT': 'y', 'CONFIG_KSU_SUSFS_SUS_KSTAT': 'y', 'CONFIG_MACH_MT6893': 'y', 'CONFIG_MTK_CAMERA_ISP': 'y', 'CONFIG_MTK_CAMERA_ISP_RSC_SUPPORT': 'y', 'CONFIG_MTK_CAMERA_ISP_DPE_SUPPORT': 'y', 'CONFIG_MTK_CAMERA_ISP_TSF_SUPPORT': 'y', 'CONFIG_MTK_CAMERA_ISP_FD_SUPPORT': 'y', 'CONFIG_MTK_CAMERA_ISP_WPE_SUPPORT': 'y', 'CONFIG_MTK_CAMERA_ISP_OWE_SUPPORT': 'y', 'CONFIG_MTK_CAMERA_ISP_MFB_SUPPORT': 'y', 'CONFIG_MTK_IMGSENSOR': 'y', 'CONFIG_MTK_GPU_VERSION': '"mali valhall r32p1"', 'CONFIG_MTK_VOW_SUPPORT': 'y', 'CONFIG_MODULE_FORCE_LOAD': 'n', 'CONFIG_ARM64_ERRATUM_1188873': 'y', 'CONFIG_MITIGATE_SPECTRE_BRANCH_HISTORY': 'y', 'CONFIG_MTK_SENSOR_SUPPORT': 'y', 'CONFIG_MTK_IOMMU_V2': 'y', 'CONFIG_MTK_SMI': 'y', 'CONFIG_MTK_THERMAL_PA_VIA_ATCMD': 'y', 'CONFIG_CPU_FREQ_GOV_SCHEDUTIL': 'y', 'CONFIG_EXT4_FS': 'y', 'CONFIG_VIDEO_V4L2': 'y', 'CONFIG_MEDIA_SUPPORT': 'y', 'CONFIG_THREAD_INFO_IN_TASK': 'y', 'CONFIG_KSU_SUSFS_SUS_MAP': 'y', 'CONFIG_KSU_SUSFS_SPOOF_UNAME': 'y', 'CONFIG_KSU_SUSFS_OPEN_REDIRECT': 'y', 'CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG': 'y'}
profile=sys.argv[2] if len(sys.argv)>2 else 'miui14-a13'
assert profile in ('miui14-a13','miui13-a12','miui14-early'),profile
if profile=='miui13-a12':
 for key in ('CONFIG_ARM64_ERRATUM_1188873','CONFIG_MITIGATE_SPECTRE_BRANCH_HISTORY'):
  required.pop(key)
  assert values.get(key) not in ('y','m'),('Unexpected A13 CPU mitigation profile',key)
fail={k:(v,values.get(k)) for k,v in required.items() if values.get(k)!=v}
assert not fail,fail
print('PASS_NATIVE2.3_CONFIG_AND_ALL_COMMON_STOCK_CAMERA_THERMAL_ROOT_GATES',len(required))
