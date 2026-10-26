"""Package the verified Arm GNU candidate with the ordinary AK3 installer."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys,zipfile
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent));sys.path.insert(0,str(here.parents[2]))
from installer_transport import output_adapter
from installer_write import guarded_writer
from verify_image_entry import inspect_kpm
if not __debug__:raise SystemExit('Normal Python mode required')
p=argparse.ArgumentParser()
for name in ['candidate','proof','ak3','licenses','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--source-commit',required=True);a=p.parse_args()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert re.fullmatch('[0-9a-f]{40}',a.source_commit)
proof=json.loads(a.proof.read_text(encoding='utf-8'));e=a.candidate/'release-evidence'
image=(a.candidate/'kernel_workspace/android-kernel/out/arch/arm64/boot/Image').read_bytes()
assert proof['status']=='PASS_INDEPENDENT_NATIVE_IMAGE_CHECKS_ONLY' and proof['image_sha256']==sha(image)
assert len(proof['checks'])==13 and all(x['exit']==0 for x in proof['checks']) and proof['native_current_uapi_checked']
entry=inspect_kpm(image,(e/'Image.sukisu-susfs-before-kpm').read_bytes(),(e/'kpimg.pinned').read_bytes())
assert entry['kpimg_sha256']=='554aa43ff1594ea516eb9d74581565aea07e29665ffaf702a3c87d556a7a2425'
assert sha(image)!='f280e96ef79a1de925f8be4dcc17ff418a32f065300bd02acf727808585c0ef6'
assert image[entry['kpimg_offset']+4096:entry['kpimg_offset']+entry['kpimg_bytes']]==(e/'kpimg.pinned').read_bytes()[4096:]
assert subprocess.check_output(['git','-C',str(a.ak3),'rev-parse','HEAD'],text=True).strip()=='020dfeccf9d7e962a48400fc94d3e451df92eead'
def blob(n):return subprocess.check_output(['git','-C',str(a.ak3),'show','HEAD:'+n])
files={}
for line in subprocess.check_output(['git','-C',str(a.ak3),'ls-tree','-r','HEAD','--','META-INF','tools'],text=True).splitlines():
 record,n=line.split('\t',1);assert record.split()[1]=='blob';files[n]=blob(n)
core=files['tools/ak3-core.sh'];assert sha(core)=='f7a51cfe2e093016a34a76e16de6c9885c2d1992c3482fcabc668680e1f0f6bb'
up='META-INF/com/google/android/update-binary';core,backend=output_adapter(core,files[up])
start=core.index(b'flash_boot() {');end=core.index(b'\n# flash_generic ',start)
part=core[start:end];needle=b'  blockdev --setrw $BLOCK 2>/dev/null;';assert part.count(needle)==1
part=part.replace(needle,b'  chopin_preflash_verify || abort "Boot preparation failed";\n  chopin_record_attempt || abort "Cannot save installation log";\n'+needle,1)
files['tools/ak3-core.sh']=guarded_writer(core[:start]+part+core[end:])
files[up]=files['tools/ak3-update-binary.sh']=backend
files['META-INF/com/google/android/updater-script']=b'#MAGISK\n'+files['META-INF/com/google/android/updater-script']
files['anykernel.sh']=(here/'anykernel.sh').read_bytes()
files['customize.sh']=(here/'customize.sh').read_bytes()
files['tools/chopin-preflight.sh']=(here/'boot-io.sh').read_bytes()
files['module.prop']='id=chopin_ak3\nname=小莫\nversion=r11\nversionCode=11\nauthor=小莫\ndescription=AnyKernel3 kernel installer.\n'.encode()
files['Image']=image
files['AnyKernel3-LICENSE']=blob('LICENSE')
for name,expected in {'Linux-COPYING':'af8067302947c01fd9eee72befa54c7e3ef8a48fecde7fd71277f2290b2bf0f7','SukiSU-LICENSE':'8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643','SUSFS-LICENSE':'3da27bc7c6a063f498b4278372d48e113453f93aecc709f44276e278fc0cac12','KernelPatch-LICENSE':'ce7f2f7bc1c5b68f592a04b763abaa9c180c5e44e30563153bee280763b54ae7'}.items():
 b=(a.licenses/name).read_bytes();assert sha(b)==expected;files['LICENSES/'+name]=b
files['SOURCE.txt']=('Test candidate; hardware acceptance remains pending.\nKernel build: https://github.com/Andyxyc/xm-build-workspace/tree/d57256cbd03b83326c3005d6a7ae806807983e25\nKPM processing: https://github.com/Andyxyc/xm-build-workspace/tree/eecc28814edcf0d6269c00d34d6ed84b61cfef08\nInstaller: https://github.com/Andyxyc/xm-build-workspace/tree/'+a.source_commit+'/chopin/tools/installer/minimal\nVendor kernel: https://github.com/ChopinKernels/android_kernel_chopin_android_T/tree/0647a49c9557faa92b90c4ae188587787226be9e\nSukiSU builtin: https://github.com/SukiSU-Ultra/SukiSU-Ultra/tree/6397fcb5d96e8f4953c71e02c73f8c6800541bff\nSUSFS: https://gitlab.com/simonpunk/susfs4ksu/-/tree/5419f4ee97cc8bf7ca67a9ff207f39653d7784f4\n4.14 filesystem reference: https://github.com/souta-lab/agate-bakasu-susfs/tree/9f3ab3fbd2b0cef34aeb441f2216d8e83e09776e\nKernelPatch: https://github.com/SukiSU-Ultra/SukiSU_KernelPatch_patch/tree/a3965c6e137e46b2c94a69eeb5a7e4696a3abbb0\nArm GNU KPM build: https://github.com/Andyxyc/xm-build-workspace/tree/4bdf8eaed26aac9ee60f1d96c58327891cdb719d\nAnyKernel3: https://github.com/osm0sis/AnyKernel3/tree/020dfeccf9d7e962a48400fc94d3e451df92eead\n').encode()
assert not any(n.endswith('.apk') or n.startswith('expected/') for n in files)
assert not a.output.exists() and re.fullmatch(r'chopin-[A-Za-z0-9._-]+\.zip',a.output.name)
a.output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(a.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,b in sorted(files.items()):
  assert not Path(n).is_absolute() and '..' not in Path(n).parts
  i=zipfile.ZipInfo(n,(2026,10,26,0,0,0));i.create_system=3;i.external_attr=(0o100755 if n.startswith('tools/') or n.endswith('.sh') or n.endswith('update-binary') else 0o100644)<<16
  z.writestr(i,b,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
print(json.dumps({'status':'TEST_CANDIDATE_ONLY','path':str(a.output),'sha256':sha(a.output.read_bytes()),'bytes':a.output.stat().st_size,'image_sha256':sha(image),'hardware_boot_verified':False},indent=2))
