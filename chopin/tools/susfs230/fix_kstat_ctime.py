"""Correct the native header's CTIME mask and compile both semantic controls."""
from pathlib import Path
import hashlib,json,re,subprocess,sys,tempfile
root=Path(sys.argv[1]);p=root/'include/linux/susfs.h';before=p.read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(before)=='3cf4f09b441ecec87c7ae875f18ebe83e80a31769da9e3b8883e99b00c7c906e'
old=b'#define KSTAT_SPOOF_CTIME_TV_SEC (1 < 8)';new=b'#define KSTAT_SPOOF_CTIME_TV_SEC (1 << 8)'
assert before.count(old)==1;after=before.replace(old,new,1)
names=['INO','DEV','NLINK','SIZE','ATIME_TV_SEC','ATIME_TV_NSEC','MTIME_TV_SEC','MTIME_TV_NSEC','CTIME_TV_SEC','CTIME_TV_NSEC','BLOCKS','BLKSIZE']
def compiled_check(header,stage):
 defs=dict(re.findall(rb'^#define (KSTAT_SPOOF_\w+) ([^\n]+)',header,re.M));expressions=[]
 for n in names:
  e=defs[('KSTAT_SPOOF_'+n).encode()];assert re.fullmatch(rb'[0-9()<> |&]+',e);expressions.append(e.decode())
 source='#include <stdio.h>\nint main(void){unsigned long f[]={'+','.join(expressions)+'};for(unsigned i=0;i<12;i++)if(f[i]!=(1UL<<i)){printf("bad_mask:%u:%lu\\n",i,f[i]);return 1;}return 0;}\n'
 with tempfile.TemporaryDirectory(prefix='chopin-kstat-flags-') as tmp:
  c=Path(tmp)/'flags.c';binary=Path(tmp)/'flags';c.write_text(source)
  subprocess.run(['cc','-std=c11','-O2',str(c),'-o',str(binary)],check=True)
  q=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
 return {'stage':stage,'exit':q.returncode,'output':q.stdout,'masks':12}
negative=compiled_check(before,'original_header_expected_failure');positive=compiled_check(after,'corrected_header')
assert negative['exit']==1 and 'bad_mask:8:1' in negative['output']
assert positive['exit']==0
p.write_bytes(after)
r={'status':'PASS_COMPILED_KSTAT_MASK_CORRECTION_WITH_NEGATIVE_CONTROL','before_sha256':sha(before),'after_sha256':sha(after),'change':'CTIME_TV_SEC uses shift1<<8 instead of comparison1<8; no ABI layout or stock identity change','controls':[negative,positive],'hardware_tested':False}
(root/'kstat-flags-source-fix.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
