"""Insert the exact current CI daemon before local signing.

Keep every other uncompressed entry byte-identical and align stored entries.
This script never reads a signing key and never connects to a device.
"""
from pathlib import Path
import argparse,copy,hashlib,json,struct,zipfile
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--daemon',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
daemon=a.daemon.read_bytes();expected='8e07e8e85945558426ddff31a6e107d16400a2a1c5354ab9f8dcce130357c66d';assert hashlib.sha256(daemon).hexdigest()==expected
assert not a.output.exists()
name='lib/arm64-v8a/libksud.so'
with zipfile.ZipFile(a.input) as source, zipfile.ZipFile(a.output,'x') as dest:
 assert source.testzip() is None
 entries=source.infolist()
 if name not in source.namelist():
  item=zipfile.ZipInfo(name,(2026,10,26,0,0,0));item.compress_type=zipfile.ZIP_STORED;item.external_attr=0o100755<<16;entries.append(item)
 for original in entries:
  info=copy.copy(original);data=daemon if info.filename==name else source.read(info.filename)
  if info.compress_type==zipfile.ZIP_STORED:
   alignment=16384 if info.filename.startswith('lib/') and info.filename.endswith('.so') else 4
   offset=dest.fp.tell()+30+len(info.filename.encode('utf-8'))+len(info.extra)
   if offset%alignment:
    padding=(-(offset+4))%alignment
    info.extra+=struct.pack('<HH',0xffff,padding)+bytes(padding)
  dest.writestr(info,data,compresslevel=9)
with zipfile.ZipFile(a.input) as old,zipfile.ZipFile(a.output) as new:
 assert new.testzip() is None and set(new.namelist())==set(old.namelist())|{name} and len(new.namelist())==len(set(new.namelist()))
 assert all(old.read(n)==new.read(n) for n in old.namelist() if n!=name)
 assert hashlib.sha256(new.read(name)).hexdigest()==expected
raw=a.output.read_bytes()
with zipfile.ZipFile(a.output) as z:
 for info in z.infolist():
  if info.compress_type==zipfile.ZIP_STORED:
   at=info.header_offset;filename,extra=struct.unpack_from('<HH',raw,at+26)
   alignment=16384 if info.filename.startswith('lib/') and info.filename.endswith('.so') else 4
   assert (at+30+filename+extra)%alignment==0,info.filename
print(json.dumps({'status':'PASS_EXACT_DAEMON_REPACK_AND_STORED_ENTRY_ALIGNMENT','daemon_sha256':expected,'output':str(a.output),'bytes':a.output.stat().st_size}))
