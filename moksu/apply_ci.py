#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply the reviewed R1 authentication overlay and moksu branding to a pinned CI clone."""
from pathlib import Path
import hashlib, json, re, shutil, sys
import xml.etree.ElementTree as ET

BASE = '0246ca0f16ea2e3a6af030643bb6f74262e0e26c'
APP = 'manager/app/src/main/'
JAVA = APP + 'java/com/sevenk/core/'
EXPECTED = {
 'manager/app/build.gradle.kts':'7dbae80d196de89703cd9f85feeab2fa1296b02b',
 APP+'AndroidManifest.xml':'7055553f26434e77ccba635b5a0580cfe2e5d68e',
 JAVA+'ui/UiMode.kt':'78c78bf3bc9f06fb5fde472711cdc75b96460fbb',
 JAVA+'ui/MainActivity.kt':'7d9f9e11f1030122af30023319e283c9305bfa43',
 JAVA+'data/repository/SettingsRepositoryImpl.kt':'8f43f5515991eb5f120fa5371e407ec54e30560a',
 JAVA+'ui/webui/WebUIActivity.kt':'4cfe0881059e8f2c24c2f1997aa9e2e64ff1e226',
 JAVA+'ui/screen/home/About7k.kt':'769a03207ef336ea9f0a53650bba455a534b13ff',
 JAVA+'ui/screen/about/AboutMaterial.kt':'2288a7fe8a7f658b7fe9480b7483f0ee64a90ed7',
 JAVA+'ui/util/StatusDecoration.kt':'f66cb4790d4dd2b0b97e7ed648bd5e9119ef789e',
}
A='http://schemas.android.com/apk/res/android'
ET.register_namespace('android', A)
ET.register_namespace('tools','http://schemas.android.com/tools')

def once(text,old,new):
 if text.count(old)!=1: raise ValueError('Source anchor mismatch: '+old[:100])
 return text.replace(old,new,1)

def xml(text):
 return ET.fromstring(text,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))

def serialize(root):
 ET.indent(root,space='    ')
 return '<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(root,encoding='unicode')+'\n'

def apply(root):
 root=root.resolve(strict=True)
 here=Path(__file__).resolve().parent
 changes={}
 def read(rel):
  p=root/rel
  if p.is_symlink() or not p.resolve().is_relative_to(root): raise ValueError('Unsafe input '+rel)
  return p.read_text(encoding='utf-8')
 def change(rel,old,new):
  changes[rel]=once(changes.get(rel,read(rel)),old,new)
 for rel,digest in EXPECTED.items():
  data=(root/rel).read_bytes()
  actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
  if actual!=digest: raise ValueError('Wrong upstream revision: '+rel)
 change('manager/app/build.gradle.kts','val defaultManagerName = if (isPrBuild) "KernelSU PR" else "7kimisu"','val defaultManagerName = if (isPrBuild) "moksu PR" else "moksu"')
 change('manager/app/build.gradle.kts','val defaultManagerPackageName = if (isPrBuild) "com.sevenk.core.pr" else "com.sevenk.core"','val defaultManagerPackageName = if (isPrBuild) "com.moksu.manager.pr" else "com.moksu.manager"')
 change(JAVA+'ui/UiMode.kt','val DEFAULT_VALUE = Miuix.value','val DEFAULT_VALUE = Material.value')
 change(JAVA+'ui/UiMode.kt','staticCompositionLocalOf { UiMode.Miuix }','staticCompositionLocalOf { UiMode.Material }')
 main=JAVA+'ui/MainActivity.kt'
 change(main,'        super.onCreate(savedInstanceState)\n','        super.onCreate(savedInstanceState)\n        runCatching { com.sevenk.core.mok.MokAppearance.applyOnce(this) }.onFailure {\n            android.util.Log.w("moksu", "Appearance initialization failed")\n        }\n        if (!com.sevenk.core.mok.MokAuthGate.ensureAccess(this)) return\n')
 change(main,'        super.onResume()\n','        super.onResume()\n        if (!com.sevenk.core.mok.MokAuthGate.ensureAccess(this)) return\n')
 change(main,'        super.onNewIntent(intent)\n','        super.onNewIntent(intent)\n        if (!com.sevenk.core.mok.MokAuthGate.ensureAccess(this, intent)) return\n')
 web=JAVA+'ui/webui/WebUIActivity.kt'
 change(web,'        super.onCreate(savedInstanceState)\n','        super.onCreate(savedInstanceState)\n        if (!com.sevenk.core.mok.MokAuthGate.ensureAccess(this)) return\n')
 change(web,'class WebUIActivity : ComponentActivity() {\n','class WebUIActivity : ComponentActivity() {\n    override fun onResume() {\n        super.onResume()\n        if (!com.sevenk.core.mok.MokAuthGate.ensureAccess(this)) return\n    }\n')
 settings=JAVA+'data/repository/SettingsRepositoryImpl.kt'
 for key in ('ui_translucent','snow_enabled','troll_rain_enabled','gravity_enabled','flat_home','nav_icon_circle'):
  change(settings,f'prefs.getBoolean("{key}", true)',f'prefs.getBoolean("{key}", false)')
 change(settings,'prefs.getBoolean("nav_icon_tint", false)','prefs.getBoolean("nav_icon_tint", true)')
 about=JAVA+'ui/screen/about/AboutMaterial.kt'
 anchor='''                    Text(
                        text = state.versionName,
                        fontSize = MaterialTheme.typography.bodyMedium.fontSize
                    )'''
 change(about,anchor,anchor+'''\n                    Text(
                        modifier = Modifier.padding(top = 8.dp),
                        text = "作者：闲鱼 心中都是莫",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        text = "基于 KernelSU / 7kimisu",
                        style = MaterialTheme.typography.bodySmall
                    )''')
 deco=JAVA+'ui/util/StatusDecoration.kt'
 change(deco,'const val CARD_HEIGHT_DP = 332f','const val CARD_HEIGHT_DP = 140f')
 change(deco,'return@runCatching loadBuiltin(context, targetWidthPx)','return@runCatching null')
 for name in ('HomeMaterial.kt','HomeMiuix.kt'):
  rel=JAVA+'ui/screen/home/'+name
  text=read(rel)
  if '"关于 7kimisu"' not in text: raise ValueError('About label missing')
  changes[rel]=text.replace('"关于 7kimisu"','"关于 moksu"')
 manifest=xml(read(APP+'AndroidManifest.xml'));app=manifest.find('application')
 if app is None:raise ValueError('Missing application')
 attrs={f'{{{A}}}'+k:v for k,v in {'name':'com.sevenk.core.mok.MokLoginActivity','exported':'false','directBootAware':'false','excludeFromRecents':'true','theme':'@style/Theme.KernelSU','windowSoftInputMode':'adjustResize'}.items()}
 app.insert(0,ET.Element('activity',attrs))
 changes[APP+'AndroidManifest.xml']=serialize(manifest)
 for rel in (APP+'res/xml/backup_rules.xml',APP+'res/xml/data_extraction_rules.xml'):
  doc=xml(read(rel));sections=[]
  if doc.tag=='full-backup-content':sections=[doc]
  elif doc.tag=='data-extraction-rules':
   for name in ('cloud-backup','device-transfer'):
    section=doc.find(name)
    if section is None:section=ET.SubElement(doc,name)
    sections.append(section)
  else:raise ValueError('Unexpected backup schema')
  for section in sections:
   ET.SubElement(section,'exclude',{'domain':'sharedpref','path':'mok_activation_v1.xml'})
  changes[rel]=serialize(doc)
 for p in (root/(APP+'res')).glob('values*/strings.xml'):
  rel=p.relative_to(root).as_posix();text=read(rel)
  new=re.sub(r'(<string\b[^>]*\bname="app_name"[^>]*>)[^<]*(</string>)',r'\g<1>moksu\2',text)
  if new!=text:changes[rel]=new
 colors=APP+'res/values/colors.xml';doc=xml(read(colors))
 for item in doc.findall('color'):
  if item.get('name')=='ic_launcher_background':item.text='#FFFFFFFF'
  elif item.get('name')=='ic_launcher_foreground':item.text='#FF1E110D'
 changes[colors]=serialize(doc)
 public=json.loads((here/'signing-public.json').read_text())
 change('kernel/Kbuild','KSU_EXPECTED_SIZE := 0x034d','KSU_EXPECTED_SIZE := '+public['certificate_size_hex'])
 change('kernel/Kbuild','KSU_EXPECTED_HASH := 490c6662b87ec51c8f43de6078bb42b8ab96854cc19f0f6b183995a7dde2320b','KSU_EXPECTED_HASH := '+public['certificate_sha256'])
 change('userspace/ksud/build.rs','cargo:rustc-env=KSU_PACKAGE_NAME=com.sevenk.core','cargo:rustc-env=KSU_PACKAGE_NAME=com.moksu.manager')
 for p in (here/'overlay').rglob('*'):
  if p.is_file():
   if p.is_symlink() or p.suffix not in ('.java','.kt','.xml'):raise ValueError('Unexpected overlay')
   changes[p.relative_to(here/'overlay').as_posix()]=p.read_text()
 for rel,text in changes.items():
  if rel.endswith('.xml'):xml(text)
 for rel,text in changes.items():
  p=root/rel
  if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('Unsafe output')
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n')
 for density in ('mdpi','hdpi','xhdpi','xxhdpi','xxxhdpi'):
  for stem in ('ic_launcher_foreground','ic_launcher_splash'):
   (root/(APP+f'res/drawable-{density}/{stem}.png')).unlink(missing_ok=True)
 report={'upstream_commit':BASE,'app_name':'moksu','application_id':'com.moksu.manager','changed_files':{k:hashlib.sha256((root/k).read_bytes()).hexdigest() for k in sorted(changes)},'apk_built':False,'device_tested':False}
 (root/'MOKSU_SOURCE_CHANGES.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('Applied moksu source changes:',len(changes))

if __name__=='__main__':
 if len(sys.argv)!=2:raise SystemExit('Usage: apply_ci.py PINNED_WORKING_COPY')
 apply(Path(sys.argv[1]))
