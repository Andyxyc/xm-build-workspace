"""Independent R6 byte-bound CPU/ADB/SELinux/AVC and manager-key checks."""
from pathlib import Path
import argparse,hashlib,json,struct,re
p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
ev=a.candidate/'release-evidence';images=list((a.candidate/'kernel_workspace').rglob('Image'));assert len(images)==1
data=images[0].read_bytes();symbols={q[2]:int(q[0],16) for line in (ev/'System.map').read_text(encoding='utf-8').splitlines() if len(q:=line.split())==3}
base=symbols['_text'];ordered=sorted(set(symbols.values()))
all_rows=[q for line in (ev/'System.map').read_text(encoding='utf-8').splitlines() if len(q:=line.split())==3]
# Raw absolute pointers are zero until this ARM64 kernel applies RELATIVE
# relocations. Decode the actual RELA addends instead of treating zero as data.
log=(a.candidate/'build-logs/kpm-postprocess.log').read_text(encoding='utf-8')
ranges=re.findall(r'arm64 relocation table range: \[0x([0-9a-f]+), 0x([0-9a-f]+)\)',log);assert len(ranges)==1
rs,end=(int(x,16) for x in ranges[0]);assert 0<=rs<end<=len(data) and (end-rs)%24==0
needed={symbols['apk_sign_keys']+8,symbols['cpuinfo_op']+24};relocations={}
for address,kind,addend in struct.iter_unpack('<QQQ',data[rs:end]):
 if address in needed:
  assert kind==0x403 and address not in relocations
  assert struct.unpack_from('<Q',data,address-base)[0]==0
  relocations[address]=addend
assert set(relocations)==needed

def calls(caller,callee):
 # Kernel static names can repeat across translation units. Require exactly
 # one actual caller definition to reach the uniquely named feature helper.
 starts=sorted(set(int(q[0],16) for q in all_rows if q[2]==caller));hits=[]
 if caller=='c_show':
  expected=relocations[symbols['cpuinfo_op']+24]
  assert expected in starts
  starts=[expected]
 assert starts,caller
 for start in starts:
  end=next(x for x in ordered if x>start);found=[]
  assert 0<=start-base<end-base<=len(data),(caller,hex(start))
  for pc in range(start,end,4):
   op=struct.unpack_from('<I',data,pc-base)[0]
   if op&0x7c000000!=0x14000000:continue
   d=op&0x3ffffff
   if d&(1<<25):d-=1<<26
   if pc+4*d==symbols[callee]:found.append(hex(pc))
  if found:hits.append(found)
 assert len(hits)==1,(caller,callee,'expected exactly one linked caller',hits)
 return hits[0]

edges=[('c_show','ksu_cpu_identity_get'),('midr_el1_show','ksu_cpu_identity_midr'),
       ('emulate_mrs','ksu_cpu_identity_midr'),('sel_open_handle_status','chopin_selinux_query_state'),
       ('selinux_setprocattr','chopin_selinux_query_state'),('SyS_newuname','susfs_spoof_uname'),
       ('ksu_handle_faccessat','__ksu_is_allow_uid_for_current'),
       ('ksu_handle_stat','__ksu_is_allow_uid_for_current')]
records=[dict(caller=x,callee=y,sites=calls(x,y)) for x,y in edges]
avc=calls('slow_avc_audit','chopin_avc_audit_tsid');assert len(avc)>=2,'Both source and target must use audit rendering'
for name in ['ksu_adb_root_handle_execveat','ksu_adb_root_init','ksu_adb_root_handler']:
 assert name in symbols,name
assert 'CONFIG_KSU_FEATURE_ADBROOT=y' in (ev/'chopin-built.config').read_text(encoding='utf-8')
# Decode the actual compiled certificate entry, not a detached JSON declaration.
entry=symbols['apk_sign_keys']-base;size=struct.unpack_from('<I',data,entry)[0];pointer=relocations[symbols['apk_sign_keys']+8]-base
assert size==1149 and 0<=pointer<len(data)
certificate=data[pointer:pointer+64].decode('ascii')
assert certificate=='33a63461c5442d981bcab44b168cb4ab6d50462e21ce5a6ecb668305a9b422cc'
identity=json.loads((ev/'stock-identity.json').read_text(encoding='utf-8'))
assert (identity['banner']+'\n').encode() in data
record={'status':'PASS_LINKED_R6_REQUESTED_PATHS_AND_OWNER_CERT_ONLY','image_sha256':hashlib.sha256(data).hexdigest(),'edges':records,'avc_source_and_target_sites':avc,'adb_root_config':True,'manager_certificate_bytes':size,'manager_certificate_sha256':certificate,'original_banner_exact':True,'hardware_validated':False}
a.report.write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record,indent=2))
