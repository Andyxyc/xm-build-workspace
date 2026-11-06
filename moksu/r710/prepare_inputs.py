#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import hashlib
import json
import re
import sys

s=Path(sys.argv[1]).resolve(strict=True)
c=Path(sys.argv[2]).resolve(strict=True)
j=s/'manager/app/src/main/java/me/weishu/kernelsu'

def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts}

def tree_digest(root):
    h=hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            h.update(p.relative_to(root).as_posix().encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

assert tree_digest(s/'manager')=='c48f67e1dc97de73217bee907b32acda16669f4f3b991b748a44b376213059cb', 'Not the verified R7.9 manager'
before=inventory(s)

def replace(path,a,b,count=1):
    p=s/path
    text=p.read_text()
    assert text.count(a)==count,(path,a,text.count(a),count)
    p.write_text(text.replace(a,b))

base='manager/app/src/main/java/me/weishu/kernelsu/'
helper=base+'mok/MokInputPresentation.kt'
test='manager/app/src/test/java/me/weishu/kernelsu/mok/MokInputPresentationTest.kt'
assert not (s/helper).exists() and not (s/test).exists()
(s/helper).write_bytes((c/'MokInputPresentation.kt').read_bytes())
(s/test).parent.mkdir(parents=True,exist_ok=True)
(s/test).write_bytes((c/'MokInputPresentationTest.kt').read_bytes())

p=base+'mok/MokLoginActivity.kt'
replace(p,'window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)','window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)')
replace(p,'dismissOnClickOutside = false\n','dismissOnClickOutside = false,\n                            securePolicy = androidx.compose.ui.window.SecureFlagPolicy.SecureOff\n')
replace(p,'OutlinedTextField(','MokCredentialTextField(')
replace(p,'                                    visualTransformation = PasswordVisualTransformation(),\n','')
replace(p,'''                                    keyboardOptions = KeyboardOptions(
                                        capitalization = KeyboardCapitalization.Characters,
                                        keyboardType = KeyboardType.Ascii,
                                        imeAction = ImeAction.Done
                                    ),''','''                                    keyboardOptions = MokInputPresentation.cardOptions,''')

p=base+'mok/MoksuExtrasActivity.kt'
replace(p,'''        // Regular extension-page content is recordable. Password setup and
        // explicitly revealed web tokens remain protected below.''','''        window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)''')
replace(p,'''                if (showPinSetup || revealAccessToken) {
                    window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                } else {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                }''','''                window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)''')
replace(p,'DialogProperties(securePolicy = SecureFlagPolicy.SecureOn)','MokInputPresentation.dialogProperties')
replace(p,'OutlinedTextField(','MokCredentialTextField(',2)
replace(p,'                            visualTransformation=PasswordVisualTransformation(),\n','',2)
replace(p,'KeyboardOptions(keyboardType=KeyboardType.NumberPassword)','MokInputPresentation.digitOptions',2)

for rel in ['mok/MokCalendarV7.kt','mok/MokDisguise.kt']:
    p=base+rel
    replace(p,'if(showPin) AlertDialog(onDismissRequest=','if(showPin) AlertDialog(properties=MokInputPresentation.dialogProperties,onDismissRequest=')
    a='text={OutlinedTextField(value=pin,' if 'CalendarV7' in rel else 'text={OutlinedTextField(pinEntry,'
    b=a.replace('OutlinedTextField','MokCredentialTextField')
    replace(p,a,b)
    replace(p,'''keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),
            visualTransformation=androidx.compose.ui.text.input.PasswordVisualTransformation())''','''keyboardOptions=MokInputPresentation.digitOptions)''')

p=base+'ui/screen/install/InstallScreen.kt'
replace(p,'AlertDialog(onDismissRequest={passwordStage=0;passwordInput=""},','AlertDialog(properties=MokInputPresentation.dialogProperties,onDismissRequest={passwordStage=0;passwordInput=""},')
replace(p,'OutlinedTextField(value=passwordInput,','MokCredentialTextField(value=passwordInput,')
replace(p,'                    visualTransformation=PasswordVisualTransformation(),\n','')
replace(p,'KeyboardOptions(keyboardType=KeyboardType.Password)','MokInputPresentation.textOptions')
replace(p,'import me.weishu.kernelsu.mok.MokFlashPermit\n','import me.weishu.kernelsu.mok.MokFlashPermit\nimport me.weishu.kernelsu.mok.MokCredentialTextField\nimport me.weishu.kernelsu.mok.MokInputPresentation\n')

modified=['mok/MokLoginActivity.kt','mok/MoksuExtrasActivity.kt','mok/MokCalendarV7.kt','mok/MokDisguise.kt','ui/screen/install/InstallScreen.kt']
for rel in modified:
    p=j/rel
    text=p.read_text()
    for line in text.splitlines(keepends=True):
        if not line.startswith('import '):continue
        name=line.strip().rsplit('.',1)[-1]
        if name in ['OutlinedTextField','KeyboardOptions','KeyboardCapitalization','KeyboardType','ImeAction','PasswordVisualTransformation','DialogProperties','SecureFlagPolicy']:
            body='\n'.join(x for x in text.splitlines() if not x.startswith('import '))
            if name not in body:text=text.replace(line,'')
    p.write_text(text)

web='userspace/ksud/assets/webadmin/app.js'
replace(web,'  field.type="password";','''  field.type="text";
  field.inputMode="text";
  field.autocapitalize="none";
  field.setAttribute("autocorrect","off");
  field.style.webkitTextSecurity="disc";''')
replace(web,'    field.type="text";toast("已安全生成新密钥，点击保存才会生效");','    field.style.webkitTextSecurity="none";toast("已安全生成新密钥，点击保存才会生效");')

after=inventory(s)
changed={p for p in set(before)|set(after) if before.get(p)!=after.get(p)}
allowed={base+p for p in modified}|{helper,test,web}
assert changed==allowed,sorted(changed^allowed)
assert before['manager/app/src/main/AndroidManifest.xml']==after['manager/app/src/main/AndroidManifest.xml']
production='\n'.join(p.read_text() for p in j.rglob('*.kt'))
for forbidden in ['SecureFlagPolicy.SecureOn','KeyboardType.Password','KeyboardType.NumberPassword','PasswordVisualTransformation','BasicSecureTextField','BiometricPrompt']:
    assert forbidden not in production,forbidden
for line in production.splitlines():
    if 'FLAG_SECURE' in line:assert 'clearFlags' in line,line
assert sum((j/p).read_text().count('MokCredentialTextField(') for p in modified)==6
assert sum((j/p).read_text().count('MokInputPresentation.dialogProperties') for p in modified)==4
assert 'securePolicy = androidx.compose.ui.window.SecureFlagPolicy.SecureOff' in (j/'mok/MokLoginActivity.kt').read_text()
assert 'field.type="password"' not in (s/web).read_text()
assert 'field.style.webkitTextSecurity="disc"' in (s/web).read_text()
report={'release':'R7.10','base':'R7.9','core_version':32717,'app_version_code':32718,
        'changed_files':sorted(changed),'native_input_fields':6,'credential_dialogs':5,
        'core_sources_unchanged':True,'manifest_permissions_unchanged':True,
        'authorization_implementation_unchanged':True,'default_modes_unchanged':True,
        'file_hashes':{p:{'before':before.get(p),'after':after[p]} for p in sorted(changed)},
        'not_tested':['OEM secure keyboard','physical device casting','physical device remote control']}
(s/'R710-input-checks.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report,ensure_ascii=False))
