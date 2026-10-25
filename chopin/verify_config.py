#!/usr/bin/env python3
"""Fail the chopin build if kernel options required for SukiSU/SUSFS/KPM
or known stock camera / thermal / filesystem drivers are lost."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"Missing generated .config: {path}")
values = {}
for ln in path.read_text().splitlines():
    if ln.startswith("CONFIG_") and "=" in ln:
        k,v=ln.split("=",1)
        values[k]=v
    elif ln.startswith("# CONFIG_") and ln.endswith(" is not set"):
        values[ln[2:].split(" is not set")[0]]="n"

required = {
 "CONFIG_KSU":"y",
 "CONFIG_KSU_FEATURE_ADBROOT":"y",
 "CONFIG_KPM":"y",
 "CONFIG_KALLSYMS":"y",
 "CONFIG_KALLSYMS_ALL":"y",
 "CONFIG_KSU_SUSFS":"y",
 "CONFIG_KSU_SUSFS_SUS_PATH":"y",
 "CONFIG_KSU_SUSFS_SUS_MOUNT":"y",
 "CONFIG_KSU_SUSFS_SUS_KSTAT":"y",
 "CONFIG_KSU_SUSFS_TRY_UMOUNT":"y",
 "CONFIG_MACH_MT6893":"y",
 "CONFIG_MTK_CAMERA_ISP":"y",
 "CONFIG_MTK_CAMERA_ISP_RSC_SUPPORT":"y",
 "CONFIG_MTK_CAMERA_ISP_DPE_SUPPORT":"y",
 "CONFIG_MTK_CAMERA_ISP_TSF_SUPPORT":"y",
 "CONFIG_MTK_CAMERA_ISP_FD_SUPPORT":"y",
 "CONFIG_MTK_CAMERA_ISP_WPE_SUPPORT":"y",
 "CONFIG_MTK_CAMERA_ISP_OWE_SUPPORT":"y",
 "CONFIG_MTK_CAMERA_ISP_MFB_SUPPORT":"y",
 "CONFIG_MTK_IMGSENSOR":"y",
 "CONFIG_MTK_GPU_VERSION":'"mali valhall r32p1"',
 "CONFIG_MTK_VOW_SUPPORT":"y",
 "CONFIG_MODULE_FORCE_LOAD":"n",
 "CONFIG_ARM64_ERRATUM_1188873":"y",
 "CONFIG_MITIGATE_SPECTRE_BRANCH_HISTORY":"y",
 "CONFIG_MTK_SENSOR_SUPPORT":"y",
 "CONFIG_MTK_IOMMU_V2":"y",
 "CONFIG_MTK_SMI":"y",
 "CONFIG_MTK_THERMAL_PA_VIA_ATCMD":"y",
 "CONFIG_CPU_FREQ_GOV_SCHEDUTIL":"y",
 "CONFIG_EXT4_FS":"y",
 "CONFIG_VIDEO_V4L2":"y",
 "CONFIG_MEDIA_SUPPORT":"y",
 "CONFIG_THREAD_INFO_IN_TASK":"y",
}
failure = []
for key,want in required.items():
    got=values.get(key,"absent")
    if got!=want:
        failure.append(f"{key}: expected {want}, got {got}")
if values.get("CONFIG_KSU_SUSFS_SUS_MAP")=="y":
    failure.append("Kernel-4.14 SUSFS v1.5.5 has no SUS_MAP; incompatible option enabled")
if failure:
    print("REJECTED SOURCE CONFIG:")
    for line in failure: print(" - "+line)
    raise SystemExit(2)
print(f"PASS: {len(required)} KSU, SUSFS, KPM, vendor camera, thermal and filesystem config checks")
