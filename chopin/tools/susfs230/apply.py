"""Stage native SUSFS 2.3 filesystem objects on the exact chopin vendor source.

This experiment does not build an Image, invoke ADB, or create a flash package.
"""
from pathlib import Path
import hashlib,json,subprocess,sys,urllib.request
kernel=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
cfg=json.loads((here/'manifest.json').read_text(encoding='utf-8'))
for row in cfg['patches']:
    assert sha((kernel/row['file']).read_bytes())==row['stock_sha256'],row['file']
    assert sha((here/'patches'/row['patch']).read_bytes())==row['patch_sha256']
patch=b''.join((here/'patches'/r['patch']).read_bytes() for r in cfg['patches'])
subprocess.run(['git','apply','--check','--whitespace=nowarn','-'],input=patch,cwd=kernel,check=True)
subprocess.run(['git','apply','--whitespace=nowarn','-'],input=patch,cwd=kernel,check=True)
for row in cfg['patches']:
    assert sha((kernel/row['file']).read_bytes())==row['patched_sha256']
for row in cfg['remote_sources']:
    with urllib.request.urlopen(row['url'],timeout=40) as r:data=r.read(200000)
    assert sha(data)==row['sha256'],row['file']
    (kernel/row['file']).write_bytes(data)
# Exact source sync to upstream 5419f4ee (priority UID filter and its real backend).
for row in json.loads((here/'upstream-sync.json').read_text(encoding='utf-8')):
    p=kernel/row['file'];text=p.read_text(encoding='utf-8')
    assert text.count(row['old'])==1,(row['file'],'upstream sync context')
    p.write_text(text.replace(row['old'],row['new'],1),encoding='utf-8',newline='\n')
p=kernel/'include/linux/susfs_def.h';data=p.read_bytes()
assert data.count(b'#include <linux/bits.h>')==1
p.write_bytes(data.replace(b'#include <linux/bits.h>',b'#include <linux/bitops.h>',1))
config=kernel/'arch/arm64/configs/chopin_user_defconfig'
with config.open('a') as f:
    f.write('\nCONFIG_KSU=y\nCONFIG_KSU_SUSFS=y\nCONFIG_KSU_SUSFS_SUS_PATH=y\nCONFIG_KSU_SUSFS_SUS_MOUNT=y\nCONFIG_KSU_SUSFS_SUS_KSTAT=y\nCONFIG_KSU_SUSFS_SUS_MAP=y\nCONFIG_KSU_SUSFS_SPOOF_UNAME=y\nCONFIG_KSU_SUSFS_OPEN_REDIRECT=y\n')
print('Native SUSFS2.3 filesystem stage complete; no KSU runtime/link/ABI acceptance implied')
