"""Reconstruct small, source-hash-bound41100 parser/extension test fixture.

Reuse the actual successful b79 artifact, fixed builtin6397 and the original
0647 services source. No kernel compilation, target execution or device I/O.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,urllib.request,shutil

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--kernel-root',type=Path,required=True)
    p.add_argument('--legacy-tools',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--report',type=Path,default=Path('release41100-source-fixture.json'))
    a=p.parse_args();ref=a.reference.resolve();root=a.kernel_root.resolve();here=Path(__file__).resolve().parent;legacy=a.legacy_tools.resolve();sha=lambda b:hashlib.sha256(b).hexdigest()
    pin=json.loads((here/'susfs230/ci41100-source.json').read_text(encoding='utf-8'))
    assert not root.exists(), 'Use a new fixture directory, never overwrite an existing source tree'
    a.report.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(legacy/'prepare_extension_fixture.py'),'--reference',str(ref),'--kernel-root',str(root),'--pin',str(legacy/'susfs230/ci41098-source.json'),'--report',str(a.report.with_name('release41100-base41095-fixture.json'))],check=True)
    subprocess.run([sys.executable,str(legacy/'susfs230/update_ci41098.py'),str(root)],check=True)
    original_sha={'kernel/ksu_main.c':'34e49675903ec282f21350bba53312ff0353c9aad30ebacd065c305bbc969a2e','kernel/feature/selinux_hide.c':'6536bfe90b7e91b1363b403b8f94cf74c951f0c0a7c058555dda236b6dab92c8'}
    for name,expected in original_sha.items():
        url=f'https://raw.githubusercontent.com/SukiSU-Ultra/SukiSU-Ultra/{pin["builtin_commit"]}/{name}'
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(200000)
        assert sha(data)==expected and b'\r' not in data,name
        q=root/'KernelSU'/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
    patch=(ref/'release-evidence/SukiSU-changes.patch').resolve()
    subprocess.run(['git','-c','core.autocrlf=false','-c','core.eol=lf','-C',str(root/'KernelSU'),'apply','--whitespace=nowarn','--include=kernel/ksu_main.c','--include=kernel/feature/selinux_hide.c',str(patch)],check=True,capture_output=True)
    vendor=(ref/'release-evidence/vendor-changes.patch').read_text(encoding='utf-8')
    assert 'diff --git a/security/selinux/ss/services.c' not in vendor
    assert 'vendor=0647a49c9557faa92b90c4ae188587787226be9e' in (ref/'release-evidence/BUILD-STATUS.txt').read_text(encoding='utf-8')
    snapshot=ref/'release-evidence/chopin_selinux_query_snapshot.c'
    assert sha(snapshot.read_bytes())==pin['expected_before_sha256']['KernelSU/kernel/chopin_selinux_query_snapshot.c']
    shutil.copyfile(snapshot,root/'KernelSU/kernel/chopin_selinux_query_snapshot.c')
    native=here/'susfs230/upstream-ci41100/native414/services.c'
    assert sha(native.read_bytes())==pin['expected_before_sha256']['security/selinux/ss/services.c']
    q=root/'security/selinux/ss/services.c';q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(native,q)
    subprocess.run([sys.executable,str(here/'susfs230/update_ci41100.py'),str(root)],check=True)
    result={'status':'PASS_SOURCE_ONLY41100_FIXTURE_RECONSTRUCTION_NO_C_COMPILE','base_build_commit':'b79c0dec13c639c5f07754c399b345ae1ee256dd','base_build_run':40396562328,'upstream_release_commit':pin['main_commit'],'native_vendor_commit':'0647a49c9557faa92b90c4ae188587787226be9e','actual_build_patch_sha256':sha(patch.read_bytes()),'source_update_proof':json.loads((root/'chopin-release41100-port.json').read_text()),'kernel_compiled':False,'phone_accessed':False,'scope':'Small fixed-source test fixture only, not complete kernel source or runtime proof'}
    a.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
