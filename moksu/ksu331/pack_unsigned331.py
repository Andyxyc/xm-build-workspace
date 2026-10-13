#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package verified KernelSU 3.3.1 native binaries in the modified manager APK.

No signing secret is handled in CI. A local owner-only release signing step must
follow, with APK v2 signing exclusively because kernel apk_sign.c rejects v3.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path.cwd()
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
MANAGER = ROOT / "ui" / "manager-staging.apk"
assert MANAGER.is_file(), "missing manager APK"
binaries = {
 "lib/arm64-v8a/libksud.so":ROOT / "native" / "aarch64-linux-android" / "ksud",
 "lib/x86_64/libksud.so":ROOT / "native" / "x86_64-linux-android" / "ksud",
}
for name,p in binaries.items():
 assert p.is_file(),f"missing native ksud: {p}"
 data=p.read_bytes()
 assert len(data) > 300000 and data[:4]==b"\x7fELF",f"bad ELF {name}"
 machine=int.from_bytes(data[18:20],"little")
 assert machine == (183 if "arm64" in name else 62),f"wrong ELF arch {name}"
result = ROOT / "repacked-unsigned.apk"
with zipfile.ZipFile(MANAGER) as src,zipfile.ZipFile(result,"w",allowZip64=False) as dst:
 for item in src.infolist():
  name=item.filename
  if name in binaries or re.match(r"^META-INF/([^/]+\.(SF|RSA|DSA|EC)|MANIFEST\.MF)$",name,re.I):
   continue
  if name.startswith("lib/riscv64/"):
   # v3.3.1 offers RISC-V but this release only compiled arm64 and x86-64.
   # It is safer to omit the unsupported ABI entirely.
   continue
  dst.writestr(item,src.read(name))
 for name,p in binaries.items():
  dst.write(p,name,compress_type=zipfile.ZIP_DEFLATED)
buildtools=Path(os.environ["ANDROID_HOME"])/"build-tools/37.0.0"
aligned=OUT/"moksu331-aligned-unsigned.apk"
subprocess.run([str(buildtools/"zipalign"),"-P","16","-f","4",str(result),str(aligned)],check=True)
subprocess.run([str(buildtools/"zipalign"),"-c","-P","16","4",str(aligned)],check=True)
with zipfile.ZipFile(aligned) as z:
 assert z.testzip() is None
 files=set(z.namelist())
 for abi in ("arm64-v8a","x86_64"):
  for name in ("libkernelsu.so","libadbroot.so","libksud.so"):
   assert f"lib/{abi}/{name}" in files,f"Missing {abi} {name}"
 assert any(x.startswith("classes") and x.endswith(".dex") for x in files)
 assert not any(x.startswith("lib/riscv64/") for x in files)
badging=subprocess.check_output([str(buildtools/"aapt"),"dump","badging",str(aligned)],text=True)
assert "package: name='com.moksu.manager'" in badging,badging[:400]
assert "application-label:'moksu'" in badging,badging[:600]
(OUT/"apk-badging.txt").write_text(badging,encoding="utf-8")
report={
 "app":"moksu",
 "author":"心中都是莫",
 "version":"3.3.1",
 "package_name":"com.moksu.manager",
 "source_upstream":"KernelSU v3.3.1",
 "build_stage":"COMPLETE_UNSIGNED",
 "kernel_KMI_count":8,
 "kernel_ABI_count":2,
 "userspace_binaries":["ksud","ksuinit"],
 "apk_ABIs":["arm64-v8a","x86_64"],
 "apk_signed":False,
 "device_tested":False,
 "apk_sha256":hashlib.sha256(aligned.read_bytes()).hexdigest(),
 "apk_size":aligned.stat().st_size,
 "direct_install_requires_existing_root":True,
 "partition_image_patch_available_in_KernelSU_manager":True,
 "old_7kimisu_custom_features_fully_merged":False
}
(OUT/"moksu331-build-status.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print("MOKSU331_COMPLETE_UNSIGNED",str(aligned),aligned.stat().st_size,report["apk_sha256"])
