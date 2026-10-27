"""Exercise the shipped entry adapter, socket output and real ARM file tools."""
from pathlib import Path
import hashlib,json,os,shutil,socket,subprocess,sys,tempfile,zipfile
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent))
from installer_transport import NEW_UI,NEW_PROGRESS
assert os.geteuid()==0,'Disposable cloud chroot only'
tool=Path(sys.argv[1]).resolve();busy=tool.with_name('busybox');tool.chmod(0o755);busy.chmod(0o755)
sha=lambda b:hashlib.sha256(b).hexdigest();results=[]
assert sha(busy.read_bytes())=='66436dc1e97d22886ed2d35bd69a9cb82bb0fdba4e4267c5184cee1d39a2f5f4'
def newc(entries):
 b=bytearray()
 for ino,(n,data) in enumerate([*sorted(entries.items()),('TRAILER!!!',b'')],1):
  n=n.encode()+b'\0';fields=[ino,0o100750,0,0,1,0,len(data),0,0,0,0,len(n),0]
  b+=b'070701'+''.join(f'{x:08x}' for x in fields).encode()+n;b+=bytes((-len(b))%4);b+=data;b+=bytes((-len(b))%4)
 return bytes(b)
with tempfile.TemporaryDirectory(prefix='chopin-minimal-entry-') as tmp:
 root=Path(tmp)
 for name,boot,code,want in [('magisk-success','true',0,0),('sukisu-backend-failure','true',23,99),('recovery-use-direct-zip','false',0,99)]:
  d=root/name
  for n in ['bin','system/bin','tmp','receipt']:(d/n).mkdir(parents=True,exist_ok=True)
  shutil.copyfile('/bin/busybox',d/'bin/busybox');(d/'bin/busybox').chmod(0o755)
  for n in ['sh','mkdir','mktemp','unzip','touch','printf']:(d/'bin'/n).symlink_to('/bin/busybox')
  (d/'system/bin/sh').symlink_to('/bin/busybox')
  (d/'customize.sh').write_bytes((here/'customize.sh').read_bytes())
  with zipfile.ZipFile(d/'input.zip','w') as z:
   z.writestr('tools/ak3-update-binary.sh','#!/bin/sh\nprintf "%s\\n" "$@" > /args\nprintf "%s\\n" "$AKHOME" > /home\nexit '+str(code)+'\n')
   z.writestr('module.prop','id=chopin_ak3\nname=fixture\n')
  (d/'run.sh').write_text('export PATH=/bin BOOTMODE='+boot+' ZIPFILE=/input.zip TMPDIR=/tmp MODPATH=/receipt\nui_print() { printf "%s\\n" "$*"; }\nabort() { printf "%s\\n" "$*" >&2; exit 99; }\n. /customize.sh\n')
  q=subprocess.run(['chroot',str(d),'/bin/sh','/run.sh'],capture_output=True,timeout=10)
  assert q.returncode==want,(name,q.stdout,q.stderr)
  if boot=='true':
   assert (d/'args').read_text().splitlines()==['3','1','/input.zip'] and (d/'home').read_text().startswith('/tmp/chopin-ak3.')
   assert (d/'receipt/skip_mount').exists() and not (d/'receipt/service.sh').exists()
  else:assert not (d/'args').exists()
  if code:assert b'Kernel installed.' not in q.stdout
  assert not (d/'dev').exists();results.append({'case':name,'exit':q.returncode})
 for mode in ['boot','recovery','sukisu','kernelflasher']:
  d=root/('socket-'+mode);(d/'bin').mkdir(parents=True)
  shutil.copyfile('/bin/busybox',d/'bin/busybox');(d/'bin/busybox').chmod(0o755);(d/'bin/sh').symlink_to('/bin/busybox')
  (d/'run.sh').write_text('export CHOPIN_UI_STDOUT='+('0' if mode in ['recovery','kernelflasher'] else '1')+' OUTFD=1 POSTINSTALL='+('/fixture-sukisu' if mode=='sukisu' else '""')+'\n'+NEW_UI.decode()+'\n'+NEW_PROGRESS.decode()+'\nui_print "installer"\nshow_progress 1 2\n')
  left,right=socket.socketpair()
  try:
   q=subprocess.run(['chroot',str(d),'/bin/sh','/run.sh'],stdout=right.fileno(),stderr=subprocess.PIPE,pass_fds=(right.fileno(),),timeout=10)
   right.close();left.settimeout(2);out=b''
   while chunk:=left.recv(4096):out+=chunk
   expected=b'installer\n' if mode=='boot' else b'ui_print installer\n      ui_print\n' if mode=='sukisu' else b'ui_print installer\n      ui_print\nprogress 1 2\n'
   assert q.returncode==0 and out==expected,(mode,q.stderr,out)
   if mode=='kernelflasher':
    filtered=[line[len('ui_print')+1:] for line in out.decode().splitlines() if line.startswith('ui_print')]
    assert filtered==['installer'] and all(len(line)>len('ui_print') for line in out.decode().splitlines() if line.startswith('ui_print'))
  finally:left.close();right.close()
  results.append({'case':'socket-'+mode,'exit':0})
 common='. '+str(here/'boot-io.sh')+'\nabort() { echo "$*" >&2; exit 99; }\nmagiskboot() { qemu-arm '+str(tool)+' "$@"; }\n'
 clean=root/'clean.cpio';clean.write_bytes(newc({'init':b'original init','keep':b'firmware-specific file'}))
 patched=root/'patched.cpio';patched.write_bytes(newc({'init':b'patched init','keep':b'firmware-specific file','init.magisk.rc':b'fixture'}))
 q=subprocess.run(['qemu-arm',str(tool),'cpio',str(patched),'backup '+str(clean)],capture_output=True,timeout=10);assert q.returncode==0,q.stderr
 incomplete=root/'incomplete.cpio';incomplete.write_bytes(newc({'init':b'patched init','init.magisk.rc':b'fixture'}))
 unsupported=root/'unsupported.cpio';unsupported.write_bytes(newc({'init':b'fixture','sbin/su':b'old-root'}))
 for name,file,want in [('clean-ramdisk',clean,0),('restore-own-backup',patched,0),('incomplete-backup',incomplete,99),('unsupported-old-ramdisk',unsupported,99)]:
  q=subprocess.run(['bash','--noprofile','--norc','-c',common+'chopin_clean_ramdisk '+str(file)],capture_output=True,timeout=15)
  assert q.returncode==want,(name,q.stdout,q.stderr);results.append({'case':name,'exit':q.returncode})
 out=root/'restored-init';q=subprocess.run(['qemu-arm',str(tool),'cpio',str(patched),'extract init '+str(out)],capture_output=True,timeout=10)
 assert q.returncode==0 and out.read_bytes()==b'original init'
 for n in range(2):
  q=subprocess.run(['qemu-arm',str(busy),'mktemp',str(root/'install_a.log.XXXXXXXX')],capture_output=True,timeout=10)
  assert q.returncode==0 and Path(q.stdout.decode().strip()).is_file(),q.stderr
 results.append({'case':'actual-arm-busybox-log-template','exit':0})
 data=root/'file-input';out=root/'file-output';data.write_bytes(b'ordinary file flush fixture')
 q=subprocess.run(['qemu-arm',str(busy),'dd','if='+str(data),'of='+str(out),'conv=fsync,notrunc'],capture_output=True,timeout=10)
 assert q.returncode==0 and out.read_bytes()==data.read_bytes();results.append({'case':'actual-arm-busybox-fsync','exit':0})
 assert all(not p.is_block_device() and not p.is_char_device() for p in root.rglob('*'))
report={'status':'PASS_MINIMAL_ENTRY_SOCKET_AND_ACTUAL_ARM_FILE_TOOLS_ONLY','cases':results,'source_sha256':{n:sha((here/n).read_bytes()) for n in ['customize.sh','boot-io.sh','anykernel.sh']},'actual_tools_sha256':{'magiskboot':sha(tool.read_bytes()),'busybox':sha(busy.read_bytes())},'transport_source_sha256':sha((here.parent/'installer_transport.py').read_bytes()),'device_or_real_boot_image_used':False,'hardware_verified':False}
Path('minimal-entry-tools-fixtures.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
