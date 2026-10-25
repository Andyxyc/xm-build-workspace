"""Read the actual binary manifest and V2 certificate without installing APK."""
from pathlib import Path
import argparse,hashlib,json,struct,zipfile
p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();blob=a.apk.read_bytes()
def u32(b,n):return struct.unpack_from('<I',b,n)[0]
def lp(b,n):
 length=u32(b,n);start=n+4;end=start+length;assert end<=len(b);return b[start:end],end
end=blob.rfind(b'PK\x05\x06',max(0,len(blob)-65557));assert end>=0
assert end+22+struct.unpack_from('<H',blob,end+20)[0]==len(blob)
cd=u32(blob,end+16);assert cd+u32(blob,end+12)==end
assert blob[cd-16:cd]==b'APK Sig Block 42'
size=struct.unpack_from('<Q',blob,cd-24)[0];start=cd-size-8;assert start>=0 and struct.unpack_from('<Q',blob,start)[0]==size
offset=start+8;v2=[]
while offset<cd-24:
 length=struct.unpack_from('<Q',blob,offset)[0];offset+=8;assert length>=4 and offset+length<=cd-24
 ident=u32(blob,offset)
 if ident==0x7109871a:v2.append(blob[offset+4:offset+length])
 offset+=length
assert offset==cd-24 and len(v2)==1
signers,_=lp(v2[0],0);signer,used=lp(signers,0);assert used==len(signers),'Expected one owner signer'
signed,_=lp(signer,0);_,next_field=lp(signed,0);certificates,_=lp(signed,next_field);certificate,used=lp(certificates,0);assert used==len(certificates)
assert len(certificate)==1149 and hashlib.sha256(certificate).hexdigest()=='33a63461c5442d981bcab44b168cb4ab6d50462e21ce5a6ecb668305a9b422cc'

with zipfile.ZipFile(a.apk) as z:
 assert z.testzip() is None
 xml=z.read('AndroidManifest.xml')
 strings=[];manifest={};pos=8
 while pos<len(xml):
  kind,header,length=struct.unpack_from('<HHI',xml,pos);assert length>=header>=8 and pos+length<=len(xml)
  if kind==1:
   count=u32(xml,pos+8);flags=u32(xml,pos+16);data_start=u32(xml,pos+20)
   for i in range(count):
    at=pos+data_start+u32(xml,pos+header+4*i)
    if flags&0x100:
     def length8(n):
      b=xml[n];return (((b&0x7f)<<8)|xml[n+1],n+2) if b&0x80 else (b,n+1)
     _,at=length8(at);n,at=length8(at);strings.append(xml[at:at+n].decode('utf-8'))
    else:
     n=struct.unpack_from('<H',xml,at)[0];at+=2
     if n&0x8000:n=((n&0x7fff)<<16)|struct.unpack_from('<H',xml,at)[0];at+=2
     strings.append(xml[at:at+2*n].decode('utf-16le'))
  elif kind==0x102 and strings[u32(xml,pos+20)]=='manifest':
   attr_start,attr_size,attr_count=struct.unpack_from('<HHH',xml,pos+24)
   assert attr_size==20
   for i in range(attr_count):
    at=pos+16+attr_start+i*attr_size;name=strings[u32(xml,at+4)];raw=u32(xml,at+8);value=u32(xml,at+16);typ=xml[at+15]
    manifest[name]=strings[raw] if raw!=0xffffffff else strings[value] if typ==3 else value
  pos+=length
 assert manifest['package']=='com.xiaomo.sukisu.chopin' and manifest['versionCode']==41078,manifest
 native=[n for n in z.namelist() if n.startswith('lib/') and not n.endswith('/')]
 assert native and all(n.startswith('lib/arm64-v8a/') for n in native)
 assert 'lib/arm64-v8a/libksud.so' in native and 'lib/arm64-v8a/libadbroot.so' in native
 daemon=z.read('lib/arm64-v8a/libksud.so');assert hashlib.sha256(daemon).hexdigest()=='abc3822f6b4b8521d57f9159aa5b7a56b51b4013eb13f9e38297339cbd79ddec'
report={'status':'PASS_BINARY_MANIFEST_V2_CERTIFICATE_NATIVE_PAYLOAD_ONLY','package':manifest['package'],'version_code':manifest['versionCode'],'version_name':manifest.get('versionName'),'certificate_bytes':len(certificate),'certificate_sha256':hashlib.sha256(certificate).hexdigest(),'apk_sha256':hashlib.sha256(blob).hexdigest(),'native_files':native,'installed':False,'ui_runtime_verified':False}
a.report.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
