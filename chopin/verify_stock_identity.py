from pathlib import Path
import json,sys
p=Path(__file__).parent/'stock-identity.json'
v=json.loads(p.read_text());b=Path(sys.argv[1]).read_bytes()
expected=(v['banner']+'\n').encode()
assert expected in b,'Compiled Linux banner differs from the original boot'
assert Path(sys.argv[2]).read_text().strip()=='#define UTS_RELEASE "'+v['release']+'"'
s=Path(sys.argv[3]).read_text()
for k,val in [('UTS_VERSION',v['version']),('LINUX_COMPILE_BY',v['compile_by']),('LINUX_COMPILE_HOST',v['compile_host']),('LINUX_COMPILER',v['compiler'])]:
 assert '#define '+k+' '+json.dumps(val) in s,k
print('PASS: compiled uname release, version, date, builder and complete Linux banner match original boot metadata')
