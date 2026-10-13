#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply moksu identity and offline activation gate to pinned KernelSU 3.3.1.

This core smoke-test build does NOT claim 7kimisu-only features have been ported.
Full feature migration is tracked separately by merge331.py.
"""
from pathlib import Path
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET

EXPECTED_TAG = "0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d"
APP = "manager/app/src/main/"
JAVA = APP + "java/me/weishu/kernelsu/"
A = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", A)
ET.register_namespace("tools", "http://schemas.android.com/tools")

def replace_once(src, old, new):
    if src.count(old) != 1:
        raise ValueError(f"expected one occurrence, found {src.count(old)} of {old[:80]!r}")
    return src.replace(old, new, 1)

def parse_xml(src):
    return ET.fromstring(src, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))

def xmlstr(root):
    ET.indent(root, space="    ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root,encoding="unicode") + "\n"

def apply(worktree, config):
    worktree = Path(worktree).resolve(strict=True)
    config = Path(config).resolve(strict=True)
    changes = {}
    def read(rel):
        p = (worktree / rel).resolve(strict=True)
        if not p.is_relative_to(worktree) or p.is_symlink():
            raise ValueError(f"unsafe source path: {rel}")
        return p.read_text(encoding="utf-8")
    def put(rel, text):
        changes[rel] = text
    def change(rel, old, new):
        put(rel, replace_once(changes.get(rel,read(rel)),old,new))
    build = "manager/app/build.gradle.kts"
    change(build, 'val defaultManagerPackageName = if (isPrBuild) "me.weishu.kernelsu.pr" else "me.weishu.kernelsu"',
          'val defaultManagerPackageName = if (isPrBuild) "com.moksu.manager.pr" else "com.moksu.manager"')
    change(build, 'val defaultManagerName = if (isPrBuild) "KernelSU PR" else "KernelSU"',
          'val defaultManagerName = if (isPrBuild) "moksu PR" else "moksu"')

    ui = JAVA + "ui/UiMode.kt"
    change(ui, "val DEFAULT_VALUE = Miuix.value", "val DEFAULT_VALUE = Material.value")
    change(ui, "staticCompositionLocalOf { UiMode.Miuix }", "staticCompositionLocalOf { UiMode.Material }")
    main = JAVA + "ui/MainActivity.kt"
    change(main, "        super.onCreate(savedInstanceState)\n",
           '        super.onCreate(savedInstanceState)\n'
           '        runCatching { me.weishu.kernelsu.mok.MokAppearance.applyOnce(this) }\n'
           '        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n')
    change(main, "        super.onNewIntent(intent)\n",
           '        super.onNewIntent(intent)\n'
           '        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this, intent)) return\n')
    mainText=changes[main]
    classpos='class MainActivity : ComponentActivity() {\n'
    if classpos not in mainText:raise ValueError("MainActivity class declaration not found")
    mainText=replace_once(mainText,classpos,classpos+
          '    override fun onResume() {\n'
          '        super.onResume()\n'
          '        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n'
          '    }\n')
    put(main,mainText)
    web = JAVA + "ui/webui/WebUIActivity.kt"
    change(web, "        super.onCreate(savedInstanceState)\n",
          '        super.onCreate(savedInstanceState)\n'
          '        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n')
    wc='class WebUIActivity : ComponentActivity() {\n'
    if wc not in changes[web]:raise ValueError("WebUI class not found")
    put(web,replace_once(changes[web],wc,wc+
      '    override fun onResume() {\n'
      '        super.onResume()\n'
      '        if (!me.weishu.kernelsu.mok.MokAuthGate.ensureAccess(this)) return\n'
      '    }\n'))
    about=JAVA+"ui/screen/about/AboutMaterial.kt"
    anchor='''                    Text(
                        text = state.versionName,
                        fontSize = MaterialTheme.typography.bodyMedium.fontSize
                    )'''
    change(about,anchor,anchor+'''
                    Text(
                        modifier = Modifier.padding(top = 8.dp),
                        text = "作者：闲鱼 心中都是莫",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        text = "基于 KernelSU 与 7kimisu 开源项目",
                        style = MaterialTheme.typography.bodySmall
                    )''')
    manifest=APP+"AndroidManifest.xml"
    m=parse_xml(read(manifest))
    application=m.find("application")
    if application is None:raise ValueError("application missing")
    activity = ET.Element("activity",{
        f"{{{A}}}name":"me.weishu.kernelsu.mok.MokLoginActivity",
        f"{{{A}}}exported":"false",
        f"{{{A}}}directBootAware":"false",
        f"{{{A}}}excludeFromRecents":"true",
        f"{{{A}}}theme":"@style/Theme.KernelSU",
        f"{{{A}}}windowSoftInputMode":"adjustResize"
    })
    application.insert(0,activity)
    put(manifest,xmlstr(m))
    for rel in (APP+"res/xml/backup_rules.xml",APP+"res/xml/data_extraction_rules.xml"):
        doc=parse_xml(read(rel))
        sections=[]
        if doc.tag=="full-backup-content":sections=[doc]
        elif doc.tag=="data-extraction-rules":
            for sn in ("cloud-backup","device-transfer"):
                sec=doc.find(sn)
                if sec is None:sec=ET.SubElement(doc,sn)
                sections.append(sec)
        else:raise ValueError("unsupported backup rules XML")
        for sec in sections:
            if not any(x.attrib.get("path")=="mok_activation_v1.xml" for x in sec.findall("exclude")):
                ET.SubElement(sec,"exclude",{"domain":"sharedpref","path":"mok_activation_v1.xml"})
        put(rel,xmlstr(doc))
    for p in (worktree/(APP+"res")).glob("values*/strings.xml"):
        rel=p.relative_to(worktree).as_posix()
        before=read(rel)
        after=re.sub(r'(<string\b[^>]*\bname="app_name"[^>]*>)[^<]*(</string>)',
                     r'\g<1>moksu\2',before)
        if before != after:put(rel,after)

    original_overlay=config/"moksu/overlay/manager/app/src/main/java/com/sevenk/core/mok"
    if not original_overlay.is_dir():raise ValueError("missing existing R1 card code")
    for p in original_overlay.glob("*"):
        if p.suffix not in (".kt",".java"):raise ValueError("unexpected overlay extension")
        rel=JAVA+"mok/"+p.name
        src=p.read_text(encoding="utf-8")
        src=src.replace("com.sevenk.core","me.weishu.kernelsu")
        if p.name=="MokLoginActivity.kt":
            src=src.replace('title = { Text("M-O-KSU") }','title = { Text("moksu") }')
        put(rel,src)
    # Only the original official icon is retained; no third party graphic.
    # Manifest, auth state and data extraction are updated with no boot writes.
    for rel,text in changes.items():
        if rel.endswith(".xml"):parse_xml(text)
        target=worktree/rel
        if target.is_symlink() or not target.resolve().is_relative_to(worktree):
            raise ValueError("unsafe target path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text,encoding="utf-8",newline="\n")
    report={
       "source":"tiann/KernelSU",
       "official_tag":"v3.3.1",
       "official_commit":EXPECTED_TAG,
       "package":"com.moksu.manager",
       "label":"moksu",
       "source_changes":sorted(changes),
       "card_literals_in_public_repository":False,
       "original_7kimisu_custom_features_migrated":False,
       "apk_signed":False,
       "device_tested":False
    }
    (worktree/"MOKSU331_CORE_PREVIEW.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("Applied official 3.3.1 moksu core preview, changed:",len(changes))

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: apply_core.py SOURCE_ROOT CONFIG_ROOT")
    apply(sys.argv[1],sys.argv[2])
