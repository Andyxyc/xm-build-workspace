#!/usr/bin/env python3
"""Rebuild reviewed R7.7, then transplant the pinned upstream core.
No signing keys, device access, boot-image writes or UI changes are involved.
"""
from pathlib import Path
import hashlib, json, re, shutil, subprocess, sys, tempfile

BASE = '0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d'
CI = 'ab05a0626e88d4ada1295ec561d5660f26547fdc'
CERT = 'df131f3197ed55a19d7e0a86a2b04635a5c0e5ea4bf9b596fef5a8e1d5bbcbd8'
BASELINE = {
 'manager': 'c48f67e1dc97de73217bee907b32acda16669f4f3b991b748a44b376213059cb',
 'kernel': '2335b724dc4e76a7b5351f0b22628220ac010d3e5a2c2a4e776b877549fea002',
 'userspace': '2e6067f71ef10d61974a2581aa00aea2a86b8b13652fa453348ac9e62f4739ff',
 'uapi': '9531fad269950e438a0cfede6fef83f424dcde01e31d5446a752e51a3eb30a39',
}
PATCHES = [
 'r2/moksu-v3.3.1-R2.patch',
 'r3/r3-final-source.patch', 'r3/r3-security-supplement.patch', 'r3/r3-superuser-label.patch',
 'r4/moksu-v3.3.1-R4.patch',
 'r5/moksu-v3.3.1-R5.patch', 'r5/r5-rust-utf8-fix.patch',
 'r6/moksu-v3.3.1-R6-20261014.patch', 'r6/r6-compose-state-hotfix.patch',
 'r7/moksu-v3.3.1-R7.patch', 'r7/compose-setter-hotfix.patch', 'r7/presentation-recovery-hotfix.patch',
 'r71/moksu-v3.3.2-R7.1-web-sync.patch', 'r71/android-compile-imports.patch',
 'r72/moksu-v3.3.1-R7.2-source.patch',
 'r73/moksu-v3.3.2-R7.3-source.patch',
 'r74/moksu-v3.3.2-R7.4-single-apk.patch',
 'r75/moksu-v3.3.2-R7.5-revert-identity-fix.patch',
 'r76/moksu-v3.3.2-R7.6-hidden-state-cache-fix.patch',
 'r77/moksu-v3.3.2-R7.7-kernel-stealth-recovery.patch',
]

def run(args, cwd=None):
    print('+', ' '.join(map(str,args)), flush=True)
    subprocess.run(list(map(str,args)),cwd=cwd,check=True)

def tree_hash(root):
    h=hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':
            continue
        h.update(p.relative_to(root).as_posix().encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def reconstruct(src, cfg, old):
    run([sys.executable,cfg/'moksu/ksu331/apply_release.py',src,src,cfg])
    for name in ('port_stealth','port_web','port_web_compat','port_android'):
        run([sys.executable,cfg/f'moksu/features/{name}.py',src,old])
    run([sys.executable,cfg/'moksu/redesign/apply_redesign.py',src,cfg/'moksu/redesign'])
    shutil.copytree(cfg/'moksu',src/'moksu-build',dirs_exist_ok=True)
    for relative in PATCHES:
        patch=cfg/'moksu'/relative
        if not patch.is_file():
            raise FileNotFoundError(patch)
        run(['git','apply','--check',patch],cwd=src)
        run(['git','apply',patch],cwd=src)
    got={name:tree_hash(src/name) for name in BASELINE}
    (src/'R78-baseline-check.json').write_text(json.dumps({'expected':BASELINE,'actual':got},indent=2)+'\n')
    if got != BASELINE:
        raise RuntimeError('Reconstructed R7.7 differs from verified delivery: '+json.dumps(got))

def merge_dispatch(text):
    pattern=re.compile(r'^<<<<<<< R7\.7\n(.*?)^=======\n(.*?)^>>>>>>> CI32709\n',re.M|re.S)
    hits=[]
    def replace(m):
        ours,theirs=m.groups()
        if 'static int do_moksu_stealth_get' in ours and 'static int do_lookup_symbols' in theirs:
            hits.append('functions')
            return ours+'}\n\n'+theirs
        if '.cmd = KSU_IOCTL_STEALTH_GET' in ours and '.cmd = KSU_IOCTL_LOOKUP_SYMBOLS' in theirs:
            hits.append('handlers')
            return ours+'    },\n    {\n'+theirs
        raise RuntimeError('Unexpected dispatch conflict; manual review required')
    result=pattern.sub(replace,text)
    if sorted(hits)!=['functions','handlers']:
        raise RuntimeError('Dispatch conflict shape changed: '+repr(hits))
    if any(x in result for x in ('<<<<<<<','>>>>>>>')):
        raise RuntimeError('Unresolved dispatch conflict')
    return result

def upgrade(src):
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=src)
    def blob(ref,path):
        r=subprocess.run(['git','show',f'{ref}:{path}'],cwd=src,capture_output=True)
        if r.returncode: return None
        return r.stdout
    scopes=['kernel','uapi','userspace','Cargo.toml','Cargo.lock','.github/scripts']
    paths=git('diff','--name-only',BASE,CI,'--',*scopes).decode().splitlines()
    protected={p:tree_hash(src/p) for p in ('manager','userspace/ksud/assets')}
    stealth_before=(src/'kernel/manager/stealth.c').read_bytes()
    applied=[]
    for relative in paths:
        target=src/relative
        b=blob(BASE,relative); n=blob(CI,relative)
        o=target.read_bytes() if target.is_file() else None
        if o==b or o==n:
            merged=n
        elif b is not None and n is not None and o is not None:
            with tempfile.TemporaryDirectory() as td:
                t=Path(td)
                for name,data in [('ours',o),('base',b),('new',n)]: (t/name).write_bytes(data)
                m=subprocess.run(['git','merge-file','-p','-L','R7.7','-L','base','-L','CI32709',str(t/'ours'),str(t/'base'),str(t/'new')],capture_output=True)
                if m.returncode==0: merged=m.stdout
                elif 0<m.returncode<128 and relative=='kernel/supercall/dispatch.c':
                    merged=merge_dispatch(m.stdout.decode()).encode()
                else: raise RuntimeError(f'Unreviewed merge conflict: {relative}, exit {m.returncode}')
        else:
            raise RuntimeError('Unreviewed add/delete conflict: '+relative)
        if merged is None: target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(merged)
        applied.append(relative)
    for folder,value in protected.items():
        if tree_hash(src/folder)!=value: raise RuntimeError('Protected UI changed: '+folder)
    assert (src/'kernel/manager/stealth.c').read_bytes()==stealth_before
    kb=(src/'kernel/Kbuild').read_text()
    assert 'KSU_PACKAGE_NAME ?= com.moksu.manager' in kb and CERT in kb
    assert 'KSU_PACKAGE_NAME=com.moksu.manager' in (src/'userspace/ksud/build.rs').read_text()
    dispatch=(src/'kernel/supercall/dispatch.c').read_text()
    for name in ('do_moksu_stealth_get','do_moksu_stealth_set','do_lookup_symbols'):
        assert dispatch.count('static int '+name+'(')==1, name
    assert 'lastVerifiedInProcess' in (src/'manager/app/src/main/java/me/weishu/kernelsu/mok/MokDisplayState.kt').read_text()
    assert tree_hash(src/'manager')==BASELINE['manager']
    assert int(git('rev-list','--count',CI).strip())+30000==32709
    report={'upstream':CI,'upstream_ci':40993230053,'core_version':32709,'baseline':'R7.7',
            'core_files_updated':applied,'preserved_tree_hashes':protected,
            'signer_sha256':CERT,'package':'com.moksu.manager','device_tested':False,
            'resolved_conflict':'kernel/supercall/dispatch.c: retain both upstream symbol lookup and original stealth handlers'}
    (src/'R78-core-upgrade.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R78_CORE_SOURCE_VERIFIED',len(applied),flush=True)

if __name__=='__main__':
    if len(sys.argv)!=4: raise SystemExit('usage: prepare_r78.py SOURCE CONFIG OLD_FORK')
    src,cfg,old=[Path(x).resolve(strict=True) for x in sys.argv[1:]]
    reconstruct(src,cfg,old)
    upgrade(src)
