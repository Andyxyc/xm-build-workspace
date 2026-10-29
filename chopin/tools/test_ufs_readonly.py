"""Run the real probe main with a mock read-only transport, never a device."""
from pathlib import Path
import argparse,hashlib,json,os,struct,subprocess

parser=argparse.ArgumentParser();parser.add_argument('--binary',type=Path,required=True)
parser.add_argument('--harness',type=Path,required=True);parser.add_argument('--runner',action='append',default=[])
parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
assert os.name=='posix','Disposable cloud Linux only; no local compiler or device'
here=Path(__file__).resolve().parent;sha=lambda data:hashlib.sha256(data).hexdigest()
binary=args.binary.read_bytes();assert binary[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',binary,18)[0]==183
offset=struct.unpack_from('<Q',binary,32)[0];size,count=struct.unpack_from('<HH',binary,54)
assert size==56 and offset+size*count<=len(binary)
assert all(struct.unpack_from('<I',binary,offset+i*size)[0]!=3 for i in range(count))
cases=[('wp-clear',0,'lun_mode_write_protect=0 '),('wp-set',0,'lun_mode_write_protect=1 '),
 ('mode6-offset-decoy',0,'lun_mode_write_protect=0 '),('allocation-limited-pages',0,'lun_mode_write_protect=0 ')]
for case in ['short-transfer','negative-residual','oversized-residual','oversized-dxfer','short-declared-header',
             'mode-ioctl-error','host-error','driver-error','masked-status-error','info-error','oversized-sense',
             'fixed-sense','descriptor-sense','sense-with-good-status']:
    cases.append((case,2,'lun_mode_write_protect=unknown'))
cases += [('boot-query-error',2,'boot_lun=unknown'),('unit-query-error',2,'unit_write_protect=unknown'),
          ('unit-malformed',2,'unit_write_protect=unknown'),('wrong-path',64,''),
          ('open-error',1,''),('not-a-block-device',65,'')]
results=[]
for case,exit_code,expected in cases:
    run=subprocess.run([*args.runner,str(args.harness.resolve()),case],capture_output=True,text=True,timeout=10)
    assert run.returncode==exit_code,(case,run.returncode,run.stdout,run.stderr)
    assert expected in run.stdout,(case,run.stdout)
    if expected.startswith('lun_mode_write_protect=unknown'):
        assert 'lun_mode_write_protect=0 ' not in run.stdout and 'query_summary=incomplete' in run.stdout
    if case in ['fixed-sense','descriptor-sense','sense-with-good-status']:
        assert 'sense_key=0x07 asc=0x27 ascq=0x01' in run.stdout and 'sense_raw=' in run.stdout
    results.append({'case':case,'exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr})
report={'status':'PASS_REAL_PROBE_MAIN_MOCK_READ_ONLY_TRANSPORT_ONLY','case_count':len(results),'cases':results,
 'source_sha256':{name:sha((here/name).read_bytes()) for name in ['ufs_readonly.c','ufs_readonly_fixture.c','test_ufs_readonly.py']},
 'production_binary_sha256':sha(binary),'harness_sha256':sha(args.harness.read_bytes()),'runner':args.runner,
 'production_binary_aarch64_static':True,'mode_sense_command_bytes':'5a 00 3f 00 00 00 00 00 40 00',
 'mode10_header_wp_byte':3,'new_set_clear_write_or_partition_io_operations':False,
 'actual_ioctls_or_phone_or_block_devices_used':False,'hardware_mode_sense_or_protection_state_verified':False}
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'case_count':len(results),'report':str(args.report)},ensure_ascii=False))
