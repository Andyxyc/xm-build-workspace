"""Run the real simplified functions on ordinary files in a disposable chroot."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile
assert os.geteuid()==0,'Disposable CI chroot only; never run on a phone'
here=Path(__file__).resolve().parent;results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cases=[('firmware-1408-slot-a',0),('firmware-1409-slot-a',0),('firmware-1408-slot-b',0),('firmware-1409-slot-b',0),('old-failure-and-repeat-install',0),('changed-target',99),('changed-slot',99),('oversize-image',99),('short-image',99),('corrupt-backup',99),('flush-error',99),('readback-error',99),('readonly-target',99)]
with tempfile.TemporaryDirectory(prefix='chopin-minimal-io-') as tmp:
    for name,want in cases:
        root=Path(tmp)/name
        for n in ['bin','stage','dev','data/adb/chopin-kernel-backups','vendor/lib/modules']:(root/n).mkdir(parents=True,exist_ok=True)
        shutil.copyfile('/bin/busybox',root/'bin/busybox');(root/'bin/busybox').chmod(0o755)
        for n in ['sh','cat','mkdir','mktemp','sha256sum','printf','sync','dd','wc','head']:(root/'bin'/n).symlink_to('/bin/busybox')
        (root/'io.sh').write_bytes((here/'boot-io.sh').read_bytes())
        old=(b'old-current-boot'+bytes(8192))[:8192];new=(b'new-kernel-fixture'+bytes(4096))[:4096]
        (root/'target').write_bytes(old);(root/'stage/boot.img').write_bytes(old);(root/'stage/boot-new.img').write_bytes(new);(root/'stage/install-detail.log').write_text('ordinary-file fixture\n')
        (root/'dev/zero').write_bytes(bytes(16384))
        marker=root/'data/adb/chopin-kernel-backups/attempt_old_failed.txt';marker.write_text('phase=write_or_flush_failed\n');marker_before=marker.read_bytes()
        # Both ROM versions and arbitrary changed vendor bytes are accepted.
        rom='V14.0.9.0' if '1409' in name else 'V14.0.8.0'
        (root/'vendor/lib/modules/fixture.ko').write_bytes(rom.encode())
        slot='_b' if name.endswith('slot-b') else '_a'
        if name=='oversize-image':(root/'stage/boot-new.img').write_bytes(bytes(8193))
        if name=='short-image':(root/'stage/boot-new.img').write_bytes(b'short')
        if name=='corrupt-backup':(root/('data/adb/chopin-kernel-backups/boot'+slot+'-'+sha(root/'target')+'.img')).write_bytes(b'corrupt')
        script='export PATH=/bin AKHOME=/stage BOOTIMG=/stage/boot.img BLOCK=/target\nSLOT='+slot+'\n'
        script+='abort() { printf "%s\\n" "$*" >&2; exit 99; }\n'
        script+='getprop() { case "$1" in ro.boot.slot_suffix) echo '+('_b' if name=='changed-slot' else slot)+';; ro.build.version.incremental) echo '+rom+';; esac; }\n'
        script+='blockdev() { case "$1" in --getsize64) echo 8192;; --setrw) return '+('1' if name=='readonly-target' else '0')+';; *) return 1;; esac; }\n'
        script+='dd() { printf "%s\\n" "$*" >> /write-calls; command dd "$@"; rc=$?; '+('return 1;' if name=='flush-error' else 'return "$rc";')+' }\n. /io.sh\nchopin_backup_boot\n'
        if name=='changed-target':script+='printf CHANGED >> /target\n'
        script+='chopin_preflash_verify\nchopin_record_attempt || abort journal\nchopin_write_boot || abort write\n'
        if name=='readback-error':script+='printf DAMAGED >> /target\n'
        script+='chopin_postflash_verify\n'
        if name=='old-failure-and-repeat-install':script+='cat /target > /stage/boot.img\nchopin_backup_boot\nchopin_preflash_verify\nchopin_record_attempt || abort journal\nchopin_write_boot || abort write\nchopin_postflash_verify\n'
        (root/'run.sh').write_text(script)
        q=subprocess.run(['chroot',str(root),'/bin/sh','/run.sh'],capture_output=True,timeout=15)
        assert q.returncode==want,(name,q.returncode,q.stdout,q.stderr)
        assert marker.read_bytes()==marker_before,'Historical failure evidence changed'
        writes=(root/'write-calls').read_text().splitlines() if (root/'write-calls').exists() else []
        if want==0:
            assert (root/'target').read_bytes()==new+bytes(4096)
            assert len(writes)==(2 if name=='old-failure-and-repeat-install' else 1)
        elif name in ['flush-error','readback-error']:assert len(writes)==1
        else:assert not writes
        assert all('conv=fsync,notrunc' in w and 'if=/dev/zero' not in w for w in writes)
        assert all(not p.is_block_device() and not p.is_char_device() for p in root.rglob('*'))
        results.append({'case':name,'exit':q.returncode,'ordinary_file_writes':len(writes),'old_journal_preserved':True})
report={'status':'PASS_MINIMAL_INSTALLER_ORDINARY_FILE_CASES','cases':results,'source_sha256':{n:sha(here/n) for n in ['boot-io.sh','anykernel.sh','customize.sh']},'real_device_or_kernel_image_used':False,'hardware_boot_verified':False}
Path('minimal-installer-fixtures.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
