"""One-byte official Android11 ROM range test; no full-ROM read or flashing."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,re,sys,urllib.request,urllib.error

url='https://bigota.d.miui.com/V12.5.7.0.RKPMIXM/miui_CHOPINGlobal_V12.5.7.0.RKPMIXM_c79b13bbdc_11.0.zip'
record={'utc':datetime.now(timezone.utc).isoformat(),'source_commit':os.environ.get('GITHUB_SHA'),
 'target':'chopin_global_V12.5.7.0_RKPMIXM_Android11',
 'catalog_source':'https://t.me/s/MIUIUpdatesTracker?after=15518','official_url':url,
 'catalog_MD5_reference_only':'c79b13bbdc7f6ba5e21aa869e69c8278',
 'full_ROM_downloaded':False,'ROM_hash_verified':False,'bytes_read':0,'hardware_tested':False}
status=2
try:
 request=urllib.request.Request(url,headers={'Range':'bytes=0-0','Accept-Encoding':'identity','User-Agent':'chopin-offline-abi-test/1.0'})
 with urllib.request.urlopen(request,timeout=20) as response:
  record['http_status']=response.status;record['content_range']=response.headers.get('Content-Range')
  if response.status==206:
   data=response.read(2);record['bytes_read']=len(data)
   assert len(data)==1 and re.fullmatch(r'bytes 0-0/\d+',record['content_range'] or '')
   record['status']='PASS_ONE_BYTE_RANGE_PREFLIGHT_ONLY';status=0
  else:record['status']='BLOCKED_RANGE_REFUSED_BODY_NOT_READ'
except urllib.error.HTTPError as error:
 record.update(status='BLOCKED_HTTP_ERROR_BODY_NOT_READ',http_status=error.code)
 error.close()
except Exception as error:
 record.update(status='BLOCKED_PREFLIGHT_ERROR',error=type(error).__name__+': '+str(error)[:300])
out=Path('a11-rom-preflight');out.mkdir(exist_ok=True)
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record));sys.exit(status)
