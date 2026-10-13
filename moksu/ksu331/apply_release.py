#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Patch the merged 3.3.1 candidate for the moksu app, gated UI and matching LKM.

Public certificate digest is read from the repository. Private key must remain
local to the owner (no signing happens in GitHub Actions).
"""
from pathlib import Path
import json, re, shutil, sys, xml.etree.ElementTree as ET

A="http://schemas.android.com/apk/res/android"
ET.register_namespace("android",A)
ET.register_namespace("tools","http://schemas.android.com/tools")
APP="manager/app/src/main/"
PKG=APP+"java/me/weishu/kernelsu/"
BRAND="心中都是莫"

def one(t, old, new):
    if t.count(old)!=1: raise ValueError(f"anchored replacement expected once ({t.count(old)}): {old[:90]}")
    return t.replace(old,new,1)

def xdoc(src):
    return ET.fromstring(src,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))

def xstr(doc):
    ET.indent(doc,space="    ")
    return '<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(doc,encoding="unicode")+"\n"

def patch(repo,official,config):
    repo=Path(repo).resolve(strict=True)
    official=Path(official).resolve(strict=True)
    config=Path(config).resolve(strict=True)
    pub=json.loads((config/"moksu/signing-public.json").read_text())
    assert pub["package_name"]=="com.moksu.manager"
    assert len(pub["certificate_sha256"])==64
    assert int(pub["certificate_size_hex"],16)==pub["certificate_size"]
    out={}
    def read(rel):
        p=(repo/rel).resolve(strict=True)
        if not p.is_relative_to(repo) or p.is_symlink(): raise ValueError("unsafe input "+rel)
        return p.read_text(encoding="utf-8")
    def put(rel,txt):out[rel]=txt
    def change(rel,old,new):put(rel,one(out.get(rel,read(rel)),old,new))
    def source(rel):return out.get(rel,read(rel))
    build="manager/app/build.gradle.kts"
    orig=read(build)
    matched=0
    for pattern,repl in [
      (r'val defaultManagerName = if \(isPrBuild\) "[^"\n]+" else "[^"\n]+"',
       'val defaultManagerName = if (isPrBuild) "moksu PR" else "moksu"'),
      (r'val defaultManagerPackageName = if \(isPrBuild\) "[^"\n]+" else "[^"\n]+"',
       'val defaultManagerPackageName = if (isPrBuild) "com.moksu.manager.pr" else "com.moksu.manager"')
    ]:
      orig,c=re.subn(pattern,repl,orig)
      if c!=1:raise ValueError("Gradle default pattern missing:"+pattern)
      matched+=c
    put(build,orig)
    mode=PKG+"ui/UiMode.kt"
    change(mode,"val DEFAULT_VALUE = Miuix.value","val DEFAULT_VALUE = Material.value")
    change(mode,"staticCompositionLocalOf { UiMode.Miuix }","staticCompositionLocalOf { UiMode.Material }")
    main=PKG+"ui/MainActivity.kt"
    src=read(main)
    if "MokAuthGate.ensureAccess" in src:raise ValueError("duplicate login gate")
    src=one(src,"        super.onCreate(savedInstanceState)\n",
       "        super.onCreate(savedInstanceState)\n"
       "        runCatching { me.weishu.kernelsu.mok.MokAppearance.applyOnce(this) }\n"
       "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n")
    if "override fun onResume()" in src:
        src=one(src,"        super.onResume()\n",
          "        super.onResume()\n"
          "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n")
    else:
        src=one(src,"class MainActivity : ComponentActivity() {\n",
          "class MainActivity : ComponentActivity() {\n"
          "    override fun onResume() {\n"
          "        super.onResume()\n"
          "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n"
          "    }\n")
    src=one(src,"        super.onNewIntent(intent)\n",
          "        super.onNewIntent(intent)\n"
          "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this, intent)) return\n")
    put(main,src)
    web=PKG+"ui/webui/WebUIActivity.kt"
    src=read(web)
    src=one(src,"        super.onCreate(savedInstanceState)\n",
          "        super.onCreate(savedInstanceState)\n"
          "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n")
    if "override fun onResume()" in src:
        src=one(src,"        super.onResume()\n",
            "        super.onResume()\n"
            "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n")
    else:
        src=one(src,"class WebUIActivity : ComponentActivity() {\n",
            "class WebUIActivity : ComponentActivity() {\n"
            "    override fun onResume() {\n"
            "        super.onResume()\n"
            "        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n"
            "    }\n")
    put(web,src)
    about=PKG+"ui/screen/about/AboutMaterial.kt"
    src=read(about)
    anchor='''                    Text(
                        text = state.versionName,
                        fontSize = MaterialTheme.typography.bodyMedium.fontSize
                    )'''
    src=one(src,anchor,anchor+
           '\n                    Text(\n'
           '                        modifier = Modifier.padding(top = 8.dp),\n'
           '                        text = "作者：'+BRAND+'",\n'
           '                        style = MaterialTheme.typography.bodyMedium\n'
           '                    )\n'
           '                    Text(\n'
           '                        text = "基于 KernelSU 3.3.1 / 7kimisu 开源项目",\n'
           '                        style = MaterialTheme.typography.bodySmall\n'
           '                    )')
    put(about,src)
    manifest=APP+"AndroidManifest.xml"
    doc=xdoc(read(manifest));application=doc.find("application")
    if application is None:raise ValueError("missing application")
    application.insert(0,ET.Element("activity",{
        "{"+A+"}name":"me.weishu.kernelsu.mok.MokLoginActivity",
        "{"+A+"}exported":"false",
        "{"+A+"}directBootAware":"false",
        "{"+A+"}excludeFromRecents":"true",
        "{"+A+"}theme":"@style/Theme.KernelSU",
        "{"+A+"}windowSoftInputMode":"adjustResize"
    }))
    put(manifest,xstr(doc))
    for rel in (APP+"res/xml/backup_rules.xml",APP+"res/xml/data_extraction_rules.xml"):
        doc=xdoc(read(rel));sections=[]
        if doc.tag=="full-backup-content":sections=[doc]
        elif doc.tag=="data-extraction-rules":
            for name in ("cloud-backup","device-transfer"):
                sec=doc.find(name)
                if sec is None:sec=ET.SubElement(doc,name)
                sections.append(sec)
        else:raise ValueError("unexpected xml "+rel)
        for sec in sections:
            if not any(n.attrib.get("path")=="mok_activation_v1.xml" for n in sec.findall("exclude")):
                ET.SubElement(sec,"exclude",{"domain":"sharedpref","path":"mok_activation_v1.xml"})
        put(rel,xstr(doc))
    for p in (repo/(APP+"res")).glob("values*/strings.xml"):
        rel=p.relative_to(repo).as_posix()
        before=read(rel)
        after=re.sub(r'(<string\b[^>]*\bname="app_name"[^>]*>)[^<]*(</string>)',
                     r'\g<1>moksu\2',before)
        if before!=after:put(rel,after)
    kbuild="kernel/Kbuild"
    src=read(kbuild)
    # Preserve the official 3.3.1 apk_sign.c behavior, pinned-package scheme.
    src=one(src,'KSU_PACKAGE_NAME ?= me.weishu.kernelsu',
                 'KSU_PACKAGE_NAME ?= com.moksu.manager')
    src=one(src,'KSU_EXPECTED_SIZE ?= 0x033b',
                 'KSU_EXPECTED_SIZE ?= '+pub["certificate_size_hex"])
    src=one(src,'KSU_EXPECTED_HASH ?= c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6',
                 'KSU_EXPECTED_HASH ?= '+pub["certificate_sha256"])
    put(kbuild,src)
    buildrs="userspace/ksud/build.rs"
    change(buildrs,"cargo:rustc-env=KSU_PACKAGE_NAME=me.weishu.kernelsu",
                   "cargo:rustc-env=KSU_PACKAGE_NAME=com.moksu.manager")

    originals=config/"moksu/overlay/manager/app/src/main/java/com/sevenk/core/mok"
    assert originals.is_dir()
    for p in originals.glob("*"):
        if p.suffix not in (".kt",".java"):raise ValueError("overlay type")
        rel=PKG+"mok/"+p.name
        src=p.read_text(encoding="utf-8").replace("com.sevenk.core","me.weishu.kernelsu")
        src=src.replace("闲鱼 心中都是莫",BRAND)
        put(rel,src)
    # Preserve the real upstream KernelSU launcher icon, not 7kimisu's icon.
    for folder in ("drawable","mipmap-anydpi-v26"):
        srcdir=official/(APP+"res/"+folder)
        if not srcdir.is_dir():continue
        for p in srcdir.glob("ic_launcher*"):
            target=repo/(APP+"res/"+folder)/p.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,target)
    for rel,t in out.items():
        if rel.endswith(".xml"):xdoc(t)
        target=repo/rel
        if target.is_symlink() or not target.resolve().is_relative_to(repo):
            raise ValueError("unsafe target:"+rel)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(t,encoding="utf-8",newline="\n")
    (repo/"MOKSU331_RELEASE_CANDIDATE.json").write_text(json.dumps({
       "upstream":"tiann/KernelSU v3.3.1",
       "commit":"0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d",
       "package_name":"com.moksu.manager",
       "app_name":"moksu",
       "author":BRAND,
       "public_cert_size":pub["certificate_size"],
       "public_cert_sha256":pub["certificate_sha256"],
       "edited_files":sorted(out),
       "signed":False,
       "device_tested":False,
       "install_ui_kept":True,
       "custom_feature_semantics_verified":False,
     },ensure_ascii=False,indent=2)+"\n")
    print("MOKSU331_APP_PATCHED",len(out))

if __name__=="__main__":
    if len(sys.argv)!=4:
        raise SystemExit("Usage: apply_release.py MERGED_ROOT OFFICIAL_ROOT CONFIG_ROOT")
    patch(*sys.argv[1:])
