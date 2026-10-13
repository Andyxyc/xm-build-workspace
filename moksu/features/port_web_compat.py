#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapt 7kimisu v2.29 webadmin backend to official KernelSU v3.3.1 APIs.

Safely retain modern kernel syscall implementation and official CLI while
transplanting only missing helper functions from pinned GPL source.
No insecure root-web bind; original 256-bit token + loopback stays mandatory.
"""
from pathlib import Path
import re
import sys

def definition(src, prefix):
    lines=src.splitlines(keepends=True)
    starts=[i for i,line in enumerate(lines) if line.startswith(prefix)]
    if len(starts)!=1:
        raise ValueError(f"expected one {prefix!r} definition, got {len(starts)}")
    start=starts[0]
    # Function/struct closes with unindented '}' (all code is Rustfmt-formatted).
    end=next((i for i in range(start+1,len(lines)) if lines[i].strip()=='}' and not lines[i].startswith((' ','\t'))),None)
    if end is None:raise ValueError("definition did not close: "+prefix)
    return ''.join(lines[start:end+1])

def add_compat(new_root,old_root):
    new=Path(new_root).resolve(strict=True)
    old=Path(old_root).resolve(strict=True)
    older=(old/"userspace/ksud/src/ksucalls.rs").read_text()
    newer=new/"userspace/ksud/src/ksucalls.rs"
    current=newer.read_text()
    helpers=(
       "pub fn allow_list_uids",
       "pub fn deny_list_uids",
       "fn list_uids",
       "pub fn manager_appid",
       "fn ioctl_as_manager",
       "const fn struct_bytes",
       "fn struct_from_bytes",
       "pub fn write_cstr",
       "pub fn get_app_profile",
       "pub fn set_app_profile",
       "pub fn read_cstr",
    )
    addition=[]
    for name in helpers:
        if name.startswith("const fn"):frag=definition(older,name)
        else:frag=definition(older,name)
        if name=="fn ioctl_as_manager":
            addition.append("const MANAGER_IOCTL_MAX: usize = 4096;\n")
        addition.append(frag)
    current += "\n// 7kimisu compatibility bridge for local-token-authenticated webadmin.\n" + "\n".join(addition)
    newer.write_text(current)
    oldmod=(old/"userspace/ksud/src/module.rs").read_text()
    modernpath=new/"userspace/ksud/src/module.rs"
    modern=modernpath.read_text()
    fragments=[
       "#[derive(Default)]\n" + definition(oldmod,"pub struct ExecOptions"),
       definition(oldmod,"pub fn parse_exec_options"),
       definition(oldmod,"fn run_busybox_capture"),
       definition(oldmod,"pub fn list_package_names"),
       definition(oldmod,"pub fn packages_info"),
       definition(oldmod,"pub fn run_action_capture"),
       definition(oldmod,"pub fn exec_in_module"),
       definition(oldmod,"pub fn list_modules_json"),
    ]
    # Official 3.3.1 deliberately removed original label reader:
    # use package name, never silently attribute incorrect app metadata.
    fragments=[x.replace("crate::res_label::label_from_apk(p)","None::<String>") for x in fragments]
    modern+="\n// 7SU webadmin helpers adapted to modern core; bounded script execution.\n"+"\n\n".join(fragments)
    modernpath.write_text(modern)
    backend=new/"userspace/ksud/src/webadmin_ksud.rs"
    src=backend.read_text()
    # v3.3.1 moved enum to feature_id.rs and made feature:: import private
    src=src.replace("crate::feature::FeatureId::", "crate::feature_id::FeatureId::")
    old_expression='''        let (enabled, supported) = ksucalls::get_feature(crate::feature_id::FeatureId::Sulog as u32)
            .unwrap_or((0, false));'''
    new_expression='''        let feature = ksucalls::get_feature(crate::feature_id::FeatureId::Sulog as u32)
            .unwrap_or_default();
        let (enabled, supported) = (feature.value, feature.supported);'''
    if src.count(old_expression)!=1:raise ValueError("sulog feature API anchor")
    src=src.replace(old_expression,new_expression)
    backend.write_text(src)
    print("MOKSU_WEB_BACKEND_API_ADAPTED",
          "ksucalls helpers:",len(helpers),
          "module helpers:",len(fragments),
          "old core unaffected")

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: port_web_compat.py KSU331_SOURCE OLD_7KIMISU_SOURCE")
    add_compat(sys.argv[1],sys.argv[2])
