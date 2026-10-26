"""Bounded official-ROM boot/export comparison. Never a flash or hardware claim."""
from pathlib import Path
import collections,gzip,hashlib,io,json,re,struct,urllib.request,zipfile
class RemoteZip(io.RawIOBase):
 def __init__(self,url):
  self.url=url;self.pos=0;self.total=None;self.downloaded=0;self.cache_start=0;self.cache=b''
  with self.request(0,0) as r:
   cr=r.headers.get('Content-Range','');m=re.fullmatch(r'bytes 0-0/(\d+)',cr);assert r.status==206 and m,'CDN does not provide byte ranges'
   self.total=int(m[1]);assert len(r.read(2))==1
 def request(self,start,end):
  r=urllib.request.urlopen(urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','User-Agent':'chopin-offline-abi-test/1.0'}),timeout=35)
  if r.status!=206:r.close();raise RuntimeError('Range refused; full ROM download prohibited')
  return r
 def seekable(self):return True
 def readable(self):return True
 def tell(self):return self.pos
 def seek(self,offset,whence=0):
  self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.total+offset
  assert 0<=self.pos<=self.total;return self.pos
 def read(self,n=-1):
  if n<0:n=self.total-self.pos
  n=min(n,self.total-self.pos);assert n<=96*1024*1024,'Whole ROM reads are prohibited'
  result=[]
  while n:
   offset=self.pos-self.cache_start
   if not 0<=offset<len(self.cache):
    amount=min(max(n,1024*1024),8*1024*1024,self.total-self.pos);assert self.downloaded+amount<=96*1024*1024,'Per-ROM byte budget reached'
    with self.request(self.pos,self.pos+amount-1) as r:
     assert r.headers.get('Content-Range')==f'bytes {self.pos}-{self.pos+amount-1}/{self.total}'
     data=r.read(amount+1);assert len(data)==amount
    self.cache_start=self.pos;self.cache=data;self.downloaded+=len(data);offset=0
   amount=min(n,len(self.cache)-offset);result.append(self.cache[offset:offset+amount]);self.pos+=amount;n-=amount
  return b''.join(result)
def exported(image,expected):
 from vmlinux_to_elf.core.kallsyms import KallsymsFinder
 found=KallsymsFinder(image,64);symbols={s.name:s for s in found.symbols};text=symbols['_text'];base=text.virtual_address-text.file_offset;data=found.kernel_img
 seed_name=b'remap_pfn_range\0';names=[m.start() for m in re.finditer(re.escape(seed_name),data)]
 seeds=[]
 for off in names:
  needle=struct.pack('<QQ',symbols['remap_pfn_range'].virtual_address,base+off)
  seeds.extend(m.start() for m in re.finditer(re.escape(needle),data))
 assert len(seeds)==1,('export table seed count',len(seeds))
 def entry(pos):
  if pos<0 or pos+16>len(data):return None
  addr,name=struct.unpack_from('<QQ',data,pos);off=name-base
  if not base<=addr<base+128*1024*1024 or not 0<=off<len(data):return None
  name=data[off:off+256].split(b'\0',1)[0]
  return name.decode() if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_.$]*',name) else None
 start=seeds[0]
 while entry(start-16):start-=16
 rows=[];pos=start
 while name:=entry(pos):rows.append(name);pos+=16
 assert len(rows)>1000
 groups=[]
 for name in rows:
  if not groups or name<=groups[-1][-1]:groups.append([])
  groups[-1].append(name)
 wanted=set(expected.values())-{0,0xffffffff};positions=collections.defaultdict(list)
 for i,(value,) in enumerate(struct.iter_unpack('<I',data[:len(data)//4*4])):
  if value in wanted:positions[value].append(i*4)
 exports={};proof=[]
 for group in groups:
  votes=collections.Counter()
  for i,name in enumerate(group):
   if name in expected and expected[name] in wanted:
    for pos in positions[expected[name]]:votes[pos-4*i]+=1
  assert votes,'No independent export CRC location votes'
  begin,count=votes.most_common(1)[0];assert count>=10 and 0<=begin and begin+4*len(group)<=len(data)
  for i,name in enumerate(group):exports[name]=struct.unpack_from('<I',data,begin+4*i)[0]
  proof.append({'first':group[0],'last':group[-1],'exports':len(group),'independent_crc_votes':count})
 common=set(expected)&set(exports);differences=[{'name':n,'candidate':f'{expected[n]:08x}','firmware':f'{exports[n]:08x}'} for n in sorted(common) if expected[n]!=exports[n]]
 return {'symbols_recovered':len(symbols),'exports_recovered':len(exports),'shared_exports_compared':len(common),'different_export_crcs':differences,'candidate_exports_missing_from_firmware':sorted(set(expected)-set(exports)),'table_location_proof':proof}
reference=Path('current-reference');symvers=reference/'release-evidence/ported.Module.symvers'
assert (reference/'build-logs/root-build-complete.txt').read_text().strip()=='b79c0dec13c639c5f07754c399b345ae1ee256dd'
expected={q[1]:int(q[0],16) for s in symvers.read_text().splitlines() if len(q:=s.split())>=3 and q[2]=='vmlinux'}
assert len(expected)>10000
out=Path('rom-analysis');out.mkdir(exist_ok=True);results=[]
for item in json.loads(Path('chopin/tools/rom_abi_targets.json').read_text()):
 row={'firmware':item,'status':'IN_PROGRESS','hardware_tested':False,'flashed':False,'full_zip_md5_verified':False,'max_network_bytes':96*1024*1024};results.append(row)
 try:
  remote=RemoteZip(item['link']);row['full_rom_bytes']=remote.total
  with zipfile.ZipFile(remote) as z:
   names=z.namelist();matches=[n for n in names if n=='boot.img' or n.endswith('/boot.img')];row['image_container_names']=[n for n in names if any(x in n.lower() for x in ['boot.img','payload.bin','vendor.new.dat','super.img'])][:20]
   assert len(matches)==1,'A direct boot member is unavailable; payload/full-ROM extraction not attempted'
   info=z.getinfo(matches[0]);assert info.file_size==134217728
   boot=z.read(matches[0]);row['boot_zip_member_crc_verified']=True;row['boot_sha256']=hashlib.sha256(boot).hexdigest();assert boot[:8]==b'ANDROID!'
   size=struct.unpack_from('<I',boot,8)[0];page=struct.unpack_from('<I',boot,36)[0];assert page in [2048,4096]
   image=gzip.decompress(boot[page:page+size]);assert image[56:60]==b'ARMd';row['image_sha256']=hashlib.sha256(image).hexdigest()
   banner=re.search(rb'Linux version [^\0\n]{1,400}',image);assert banner;row['kernel_banner']=banner[0].decode(errors='replace')
   row['export_comparison']=exported(image,expected);row['status']='PASS_BOUNDED_BOOT_CRC_AND_EXPORT_COMPARISON_ONLY'
  row['actual_network_bytes']=remote.downloaded
 except Exception as error:row['status']='BLOCKED_OR_DIFFERENT_LAYOUT_NO_COMPATIBILITY_CLAIM';row['error']=repr(error)
 (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in row.items() if k not in ['export_comparison','firmware']},ensure_ascii=False),flush=True)
summary={'scope':'Offline public firmware only; CRC differences are evidence, not proof of hardware compatibility. No raw OEM boot images are published.','candidate_kernel_source':'b79c0dec13c639c5f07754c399b345ae1ee256dd','parser_commit':'29eac31a38db48b51c0dc6aae3be0162237601eb','reference_symvers_sha256':hashlib.sha256(symvers.read_bytes()).hexdigest(),'results':results}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
