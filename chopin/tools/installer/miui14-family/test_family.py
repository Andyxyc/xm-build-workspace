"""Ordinary-file compatibility fixtures; actual pinned ARM magiskboot via QEMU.

No real boot image, device node, root grant, module loading or partition write.
"""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,sys,shutil,re
source=Path(__file__).resolve().parent
tool=Path(sys.argv[1]).resolve();assert tool.is_file();tool.chmod(0o755)
results=[];sha=lambda b:hashlib.sha256(b).hexdigest()
def newc(entries):
 b=bytearray();ino=1
 for name,data in [*sorted(entries.items()),('TRAILER!!!',b'')]:
  n=name.encode()+b'\0';fields=[ino,0o100750 if name=='init' else 0o100644,0,0,1,0,len(data),0,0,0,0,len(n),0]
  b+=b'070701'+''.join(f'{x:08x}' for x in fields).encode()+n;b+=bytes((-len(b))%4);b+=data;b+=bytes((-len(b))%4);ino+=1
 return bytes(b)
def mb(*args):return subprocess.run(['qemu-arm',str(tool),*map(str,args)],capture_output=True,timeout=15)
with tempfile.TemporaryDirectory(prefix='chopin-family-files-') as temp:
 root=Path(temp);(root/'expected').mkdir();mods=root/'modules';mods.mkdir()
 # Exercise the actual packaged ARM BusyBox, including the phone failure case.
 busybox=tool.with_name('busybox');assert sha(busybox.read_bytes())=='66436dc1e97d22886ed2d35bd69a9cb82bb0fdba4e4267c5184cee1d39a2f5f4';busybox.chmod(0o755)
 template=re.search(r'CHOPIN_DETAIL_LOG=\$\(mktemp "\$backup_dir/([^"\n]+)"\)',(source/'anykernel.sh').read_text()).group(1).replace('${SLOT}','_a')
 def bmk(template):return subprocess.run(['qemu-arm',str(busybox),'mktemp',str(root/template)],capture_output=True,timeout=15)
 bad=bmk('install_a-XXXXXXXX.log');assert bad.returncode!=0
 results.append(dict(case='actual-busybox-old-log-template-rejected',exit=bad.returncode,scope='ACTUAL_ARM_BUSYBOX_ORDINARY_FILE_ONLY'))
 first=bmk(template);second=bmk(template);assert first.returncode==second.returncode==0
 f1=Path(first.stdout.decode().strip());f2=Path(second.stdout.decode().strip());assert f1.is_file() and f2.is_file() and f1!=f2 and f1.parent==f2.parent==root
 results.append(dict(case='actual-busybox-source-log-template-unique',exit=0,scope='ACTUAL_ARM_BUSYBOX_ORDINARY_FILE_ONLY'))
 manifest=''
 for i in range(10):
  n=f'driver{i}.ko';b=f'file-only fixture {i}\n'.encode();(mods/n).write_bytes(b);manifest+=sha(b)+'  '+n+'\n'
 (root/'modules.sha256').write_text(manifest)
 common='AKHOME='+str(root)+'\n. '+str(source/'compat.sh')+'\nabort() { echo "$*" >&2; exit 99; }\nmagiskboot() { qemu-arm '+str(tool)+' "$@"; }\n'
 def run(name,body,want=0):
  r=subprocess.run(['bash','--noprofile','--norc','-c',common+body],capture_output=True,timeout=30)
  assert r.returncode==want,(name,r.returncode,r.stdout,r.stderr)
  results.append(dict(case=name,exit=r.returncode,scope='ORDINARY_FILES_ONLY_NO_DEVICE'))
  return r
 for name,device,sdk,miui,want in [('base-rom','chopin','33','V14',0),('miui-real-V140','chopin','33','V140',0),('miui-numeric-140','chopin','33','140',0),('different-miui14-incremental','chopin','33','14',0),('wrong-model','other','33','V14',99),('wrong-android','chopin','34','V14',99),('wrong-miui','chopin','33','V12',99)]:
  prop='getprop() { case "$1" in ro.product.device) echo '+device+';; ro.build.version.sdk) echo '+sdk+';; ro.miui.ui.version.name) echo '+miui+';; *) echo DIFFERENT-ROM-INCREMENTAL;; esac; }\n'
  run(name,prop+'chopin_family_rom',want)
 run('matching-driver-family',f'chopin_family_modules {mods} {root}/modules.sha256')
 original=(mods/'driver0.ko').read_bytes();(mods/'driver0.ko').write_bytes(b'changed')
 run('changed-driver-rejected',f'chopin_family_modules {mods} {root}/modules.sha256',99);(mods/'driver0.ko').write_bytes(original)
 (mods/'extra.ko').write_bytes(b'extra');run('extra-driver-rejected',f'chopin_family_modules {mods} {root}/modules.sha256',99);(mods/'extra.ko').unlink()
 header=bytearray(1660);header[:8]=b'ANDROID!';header[44:48]=(402653563).to_bytes(4,'little');header[1648:1652]=(201848).to_bytes(4,'little')
 normalized=bytearray(header)
 for off,size in [(8,4),(16,4),(44,4),(576,32),(1648,4)]:normalized[off:off+size]=bytes(size)
 (root/'expected/family-header.sha256').write_text(sha(normalized)+'\n')
 for name,offset,value,want in [('original-header',44,402653563,0),('other-os-patch-header',44,402653564,0),('other-dtb-size-header',1648,210000,0),('wrong-boot-layout',36,4096,99)]:
  h=bytearray(header);h[offset:offset+4]=value.to_bytes(4,'little');f=root/(name+'.img');f.write_bytes(h)
  run(name,f'chopin_family_header {f} {root}/{name}.header',want)
 clean=root/'clean.cpio';clean.write_bytes(newc({'init':b'original init fixture\n','keep.txt':b'per-ROM content\n'}))
 run('clean-current-ramdisk',f'chopin_family_ramdisk {clean}\n[ "$CHOPIN_EXPECTED_RAMDISK_SHA" = "{sha(clean.read_bytes())}" ]')
 patched=root/'patched.cpio';patched.write_bytes(newc({'init':b'modified init\n','keep.txt':b'per-ROM content\n','init.magisk.rc':b'fixture\n'}))
 r=mb('cpio',patched,'backup '+str(clean));assert r.returncode==0,r.stderr
 run('restore-own-magisk-backup',f'chopin_family_ramdisk {patched}')
 restored=root/'restored-init';assert mb('cpio',patched,'extract init '+str(restored)).returncode==0
 assert restored.read_bytes()==b'original init fixture\n' and mb('cpio',patched,'exists init.magisk.rc').returncode!=0
 missing=root/'missing-backup.cpio';missing.write_bytes(newc({'init':b'modified init\n','init.magisk.rc':b'fixture'}))
 run('missing-magisk-backup-rejected',f'chopin_family_ramdisk {missing}',99)
 unsupported=root/'unsupported.cpio';unsupported.write_bytes(newc({'init':b'fixture','sbin/su':b'old-root'}))
 run('unsupported-root-ramdisk-rejected',f'chopin_family_ramdisk {unsupported}',99)
 for name,magic,want in [('current-dtb',b'\xd7\xb7\xab\x1e',0),('current-fdt',b'\xd0\x0d\xfe\xed',0),('invalid-dtb',b'bad!',99)]:
  f=root/name;f.write_bytes(magic+bytes(60));run(name,f'chopin_family_dtb {f}',want)
 assert not (root/'dev').exists()
report=dict(status='PASS_FAMILY_ROM_MODULE_HEADER_AND_ACTUAL_RAMDISK_FIXTURES',cases=results,partition_writes=0,real_device_test=False,actual_tool_sha256=sha(tool.read_bytes()),source_sha256={n:sha((source/n).read_bytes()) for n in ['compat.sh','preflight.sh','anykernel.sh','customize.sh']})
Path('miui14-family-fixtures.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
