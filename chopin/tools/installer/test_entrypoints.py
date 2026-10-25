"""Linux chroot entry fixtures: mock backend only, no Image or device nodes.

Exercise the actual manager adapter's arguments, failure propagation and
guards, actual socket-based output functions, and one-attempt journal.
"""
from pathlib import Path
import hashlib,json,os,shutil,socket,subprocess,tempfile,zipfile,sys
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
from installer_transport import NEW_UI,NEW_PROGRESS
assert os.geteuid()==0,'Run only in the disposable CI runner chroot fixture'
busybox=Path('/bin/busybox');assert busybox.is_file()
results=[]
def prepare(root,rom='V14.0.8.0.TKPCNXM'):
 for name in ['bin','system/bin','tmp','data/adb/modules_update/xiaomo_chopin_ak3','data/adb/chopin-kernel-backups','stage/expected']:(root/name).mkdir(parents=True,exist_ok=True)
 shutil.copyfile(busybox,root/'bin/busybox');(root/'bin/busybox').chmod(0o755)
 for n in ['sh','cat','cut','mkdir','mktemp','unzip','sha256sum','touch','printf','sync']:(root/'bin'/n).symlink_to('/bin/busybox')
 (root/'system/bin/sh').symlink_to('/bin/busybox')
 getprop='#!/bin/sh\ncase "$1" in ro.product.device) echo chopin;; ro.build.version.incremental) echo '+rom+';; esac\n'
 (root/'bin/getprop').write_text(getprop);(root/'bin/getprop').chmod(0o755)
 for n in ['customize.sh','ak3-preflight.sh']:(root/n).write_bytes((here/n).read_bytes())
def run(root,script,fd=None):
 (root/'run.sh').write_text(script)
 command=['chroot',str(root),'/bin/sh','/run.sh']
 if fd is None:return subprocess.run(command,capture_output=True,timeout=15)
 return subprocess.run(command,stdout=fd,stderr=subprocess.PIPE,pass_fds=(fd,),timeout=15)
with tempfile.TemporaryDirectory(prefix='chopin-entry-fixtures-') as temp:
 parent=Path(temp)
 for name,rom,backend_code,expected in [('manager-success','V14.0.8.0.TKPCNXM',0,0),('manager-backend-failure','V14.0.8.0.TKPCNXM',23,99),('manager-wrong-rom','WRONG-ROM',0,99)]:
  root=parent/name;prepare(root,rom)
  backend='#!/bin/sh\nprintf "%s\\n" "$@" > /backend-args\nprintf "%s\\n" "$AKHOME" > /backend-home\nexit '+str(backend_code)+'\n'
  with zipfile.ZipFile(root/'input.zip','w') as z:
   z.writestr('tools/ak3-update-binary.sh',backend)
   z.writestr('expected/backend.sha256',hashlib.sha256(backend.encode()).hexdigest()+'\n')
   z.writestr('module.prop','id=xiaomo_chopin_ak3\nname=XiaoMo\n')
   assert not any(n in z.namelist() for n in ['Image','stock-ramdisk.cpio.gz'])
  script='export PATH=/bin BOOTMODE=true ZIPFILE=/input.zip TMPDIR=/tmp MODPATH=/data/adb/modules_update/xiaomo_chopin_ak3\nui_print() { printf "%s\\n" "$*"; }\nabort() { printf "%s\\n" "$*" >&2; exit 99; }\n. /customize.sh\n'
  p=run(root,script);assert p.returncode==expected,(name,p.stderr)
  if rom=='WRONG-ROM':assert not (root/'backend-args').exists()
  else:
   assert (root/'backend-args').read_text().splitlines()==['3','1','/input.zip']
   assert (root/'backend-home').read_text().startswith('/tmp/xiaomo-ak3.')
  if backend_code:assert b'Kernel installation and full partition readback completed' not in p.stdout
  assert not (root/'dev').exists()
  results.append({'case':name,'exit':p.returncode,'scope':'MOCK_BACKEND_NO_IMAGE_NO_DEVICE'})
 for mode in ['boot','recovery']:
  root=parent/('socket-'+mode);prepare(root)
  script='export CHOPIN_UI_STDOUT='+('1' if mode=='boot' else '0')+' OUTFD=1\n'+NEW_UI.decode()+'\n'+NEW_PROGRESS.decode()+'\nui_print "XiaoMo"\nshow_progress 1 2\n'
  left,right=socket.socketpair()
  try:
   p=run(root,script,right.fileno());right.close();left.settimeout(2);received=b''
   while True:
    chunk=left.recv(4096)
    if not chunk:break
    received+=chunk
   assert p.returncode==0,(mode,p.stderr)
   expected=b'XiaoMo\n' if mode=='boot' else b'ui_print XiaoMo\nui_print\nprogress 1 2\n'
   assert received==expected,(mode,received)
  finally:left.close();right.close()
  results.append({'case':'socket-'+mode,'exit':0,'scope':'REAL_OUTPUT_FUNCTION_SOCKET_NO_DEVICE'})
 root=parent/'single-attempt';prepare(root);(root/'stage/expected/kernel.sha256').write_text('b'*64+'\n')
 script='export PATH=/bin AKHOME=/stage\numask 077\nbackup_dir=/data/adb/chopin-kernel-backups\nBLOCK=/dev/block/by-name/boot_a\nSLOT=_a\nCHOPIN_NEW_IMAGE_SHA='+('a'*64)+'\nCHOPIN_BACKUP_SHA='+('c'*64)+'\nabort() { printf "%s\\n" "$*" >&2; exit 99; }\n. /ak3-preflight.sh\nchopin_record_attempt\nchopin_record_attempt\n'
 p=run(root,script);assert p.returncode==99
 markers=list((root/'data/adb/chopin-kernel-backups').glob('attempt*'));assert len(markers)==1
 assert markers[0].read_text().startswith('phase=prepared\n') and not (root/'dev').exists()
 results.append({'case':'duplicate-kernel-attempt-refused','exit':99,'scope':'REAL_JOURNAL_FUNCTION_NO_DEVICE'})
report={'status':'PASS_MANAGER_ADAPTER_SOCKET_OUTPUT_AND_DUPLICATE_ATTEMPT_FIXTURES','partition_writes':0,'real_device_test':False,'cases':results,'source_sha256':{n:hashlib.sha256((here/n).read_bytes()).hexdigest() for n in ['customize.sh','installer_transport.py','ak3-preflight.sh']}}
Path('installer-entry-fixtures.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
