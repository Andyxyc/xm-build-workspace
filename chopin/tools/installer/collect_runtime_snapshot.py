"""One bounded, read-only snapshot for comparable stock/candidate acceptance."""
from pathlib import Path
import argparse,json,subprocess,shlex,datetime,re
if not __debug__:raise SystemExit('Normal Python mode is required')
p=argparse.ArgumentParser();p.add_argument('--device-json',type=Path,required=True);p.add_argument('--phase',choices=['stock-before','stock-after','candidate-before','candidate-after'],required=True);p.add_argument('--expected-boot-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert re.fullmatch('[0-9a-f]{64}',a.expected_boot_sha256)
assert not a.output.exists(),'Keep earlier observations; choose a fresh output name'
m=json.loads(a.device_json.read_text(encoding='utf-8'));serial=m['serial'];assert re.fullmatch('[A-Za-z0-9_-]+',serial)
adb=r'C:\Windows\system32\adb.exe';rows=[]
def run(args,timeout=20):
    try:
        q=subprocess.run([adb,*args],capture_output=True,timeout=timeout)
        row=dict(args=args,code=q.returncode,stdout=q.stdout.decode('utf-8','replace')[:300000],stderr=q.stderr.decode('utf-8','replace')[:10000])
    except subprocess.TimeoutExpired:row=dict(args=args,code='TIMEOUT',stdout='',stderr='Bounded command timeout')
    rows.append(row);return row
def shell(command):return run(['-s',serial,'shell','su -c '+shlex.quote(command)])
report=dict(phase=a.phase,time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),records=rows,status='INCOMPLETE',partition_writes=0)
try:
    listed=run(['devices']);assert listed['code']==0
    assert [l.split() for l in listed['stdout'].splitlines()[1:] if l.strip()]==[[serial,'device']]
    assert shell('id -u')['stdout'].strip()=='0'
    assert shell('getprop ro.product.device')['stdout'].strip()=='chopin'
    assert shell('getprop ro.build.version.incremental')['stdout'].strip()=='V14.0.8.0.TKPCNXM'
    assert shell('getprop ro.boot.slot_suffix')['stdout'].strip()=='_'+m['slot']
    boot='/dev/block/by-name/'+m['target'];assert m['target']=='boot_a' and m['slot']=='a'
    assert shell('sha256sum '+boot)['stdout'].split()[0]==a.expected_boot_sha256
    commands={
      'identity':'uname -a; getprop ro.boot.bootreason; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime',
      'cpu':'cat /proc/stat; cat /proc/meminfo; for p in /sys/devices/system/cpu/cpufreq/policy*; do echo "$p"; for n in scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq stats/time_in_state; do if [ -r "$p/$n" ]; then echo "$n"; head -c 8192 "$p/$n"; else echo "UNAVAILABLE:$n"; fi; done; done',
      'battery':'for n in status capacity current_now voltage_now temp charge_counter cycle_count; do f=/sys/class/power_supply/battery/$n; echo "$n"; if [ -r "$f" ]; then cat "$f"; else echo UNAVAILABLE; fi; done',
      'thermal':'i=0; for p in /sys/class/thermal/thermal_zone*; do i=$((i+1)); [ "$i" -le 32 ] || break; echo "$p"; cat "$p/type" "$p/temp"; done',
      'wakeups':'if [ -r /sys/kernel/debug/wakeup_sources ]; then head -c 65536 /sys/kernel/debug/wakeup_sources; else echo UNAVAILABLE; fi',
      'modules':'cat /proc/modules',
      'camera_service':'dumpsys media.camera',
      'power_service':'dumpsys power',
      'kernel_log':'set -o pipefail; dmesg | tail -c 262144',
      'pstore':'for f in /sys/fs/pstore/console-ramoops /sys/fs/pstore/console-ramoops-0 /sys/fs/pstore/pmsg-ramoops-0; do if [ -r "$f" ]; then echo "$f"; tail -c 131072 "$f"; else echo "UNAVAILABLE:$f"; fi; done',
    }
    for label,command in commands.items():
        row=shell(command);row['label']=label
        if row['code']!=0:print(label,row['code'])
    assert shell('sha256sum '+boot)['stdout'].split()[0]==a.expected_boot_sha256
    report['status']='READ_ONLY_OBSERVATIONS_COLLECTED'
    report['limitations']='Charging/USB state, workload, screen state and elapsed time must match. A snapshot alone proves neither idle power nor camera quality. Missing readings and command failures remain explicit.'
finally:
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status=report['status'],phase=a.phase,records=len(rows),partition_writes=0)))
