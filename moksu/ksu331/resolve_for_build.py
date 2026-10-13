#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Produce an auditable first *build candidate* from the strict 3-way port.

Any conflicts in security-sensitive Rust/C/kernel/manager JNI choose official
3.3.1. UI extension conflicts choose 7kimisu to retain bespoke interface
features. It is NOT automatically fit for release: compilation and behavioral
tests are still required. All resolutions are logged.
"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from merge331 import apply, mapped, normalized

CORE_CONFLICT_PREFIXES = (
    "kernel/",
    "uapi/",
    "userspace/",
    "manager/app/src/main/cpp/",
    "manager/gradle/",
    "manager/app/src/main/java/me/weishu/kernelsu/data/model/",
    "manager/app/src/main/java/me/weishu/kernelsu/data/repository/SuperUserRepositoryImpl",
    "manager/app/src/main/java/me/weishu/kernelsu/Natives.kt",
)
RESOURCE_PREFIX = "manager/app/src/main/res/"

def norm_old_path(rel):
    npre = "manager/app/src/main/java/me/weishu/kernelsu/"
    opre = "manager/app/src/main/java/com/sevenk/core/"
    return opre + rel[len(npre):] if rel.startswith(npre) else rel

def merged_strings(old_data, new_data):
    try:
        old_root = ET.fromstring(old_data)
        new_root = ET.fromstring(new_data)
        if old_root.tag != "resources" or new_root.tag != "resources":
            return new_data, "official-unmergeable-xml"
        keys={(x.tag, x.attrib.get("name")) for x in new_root if x.attrib.get("name")}
        added=[]
        for node in old_root:
            key=(node.tag,node.attrib.get("name"))
            if node.attrib.get("name") and key not in keys:
                new_root.append(node)
                added.append(str(key))
                keys.add(key)
        if not added:return new_data,"official-resource"
        ET.indent(new_root,space="    ")
        return ('<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(new_root,encoding="unicode")+"\n").encode(),"xml-union+"+str(len(added))
    except Exception as e:
        return new_data,"official-resource-error:"+str(e)[:100]

def resolve(base, old, latest, out):
    root = Path(latest).resolve(strict=True)
    old = Path(old).resolve(strict=True)
    report_path = Path(out).resolve()
    report_path.parent.mkdir(parents=True,exist_ok=True)
    try:
        apply(base, old, root, report_path)
    except SystemExit as exc:
        if "unresolved conflicts" not in str(exc):
            raise
    initial=json.loads(report_path.read_text(encoding="utf-8"))
    choices=[]
    unresolved=[]
    # For safety: only conflicts found by the deterministic three-way audit.
    for label in initial["conflicts"]:
        rel=label.split(" => ",1)[0]
        dst=(root/rel).resolve()
        if not dst.is_relative_to(root):
            raise ValueError("unsafe target "+rel)
        old_path=old / norm_old_path(rel)
        if rel.startswith(CORE_CONFLICT_PREFIXES) or rel in ("Cargo.lock","Cargo.toml"):
            choice="official-3.3.1-core"
        elif rel.startswith(RESOURCE_PREFIX):
            if rel.endswith("strings.xml") and old_path.is_file() and dst.is_file():
                data,choice=merged_strings(old_path.read_bytes(),dst.read_bytes())
                dst.write_bytes(data)
            else:
                choice="official-3.3.1-resources"
        elif rel.startswith("manager/app/src/main/java/"):
            if not old_path.is_file():
                unresolved.append(rel)
                continue
            blob=normalized(norm_old_path(rel),old_path.read_bytes())
            # ABI mismatch: original fork native filename changed from sevenk.
            if rel.endswith("/KernelSUApplication.kt"):
                blob=blob.replace(b'loadLibrary("sevenk")',b'loadLibrary("kernelsu")')
            dst.write_bytes(blob)
            choice="7kimisu-custom-ui"
        else:
            choice="official-3.3.1-default"
        choices.append({"path":rel,"resolution":choice})
    initial["resolutions"]=choices
    initial["unresolved_after_automatic_choices"]=unresolved
    initial["status"]="candidate-not-release-tested"
    report_path.write_text(json.dumps(initial,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    counters={}
    for obj in choices:counters[obj["resolution"]]=counters.get(obj["resolution"],0)+1
    print("MOKSU331_RESOLVED",len(choices),"UNRESOLVED",len(unresolved))
    print("MOKSU331_POLICY",counters)
    if unresolved:
        raise SystemExit("unresolved mapped conflict paths: "+str(unresolved))
    # Guard: official release core needs to remain the basis.
    kbuild=(root/"kernel/Kbuild").read_text()
    assert "KSU_PACKAGE_NAME" in kbuild
    assert (root/"manager/app/src/main/java/me/weishu/kernelsu/ui/MainActivity.kt").is_file()
    assert (root/"userspace/ksud/Cargo.toml").is_file()

if __name__=="__main__":
    if len(sys.argv)!=5:raise SystemExit("Usage: resolve_for_build.py BASE FORK LATEST REPORT")
    resolve(*sys.argv[1:])
