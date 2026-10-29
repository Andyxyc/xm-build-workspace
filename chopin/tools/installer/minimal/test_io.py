"""Run the real simplified functions on ordinary files in a disposable chroot."""
from pathlib import Path
import gzip,hashlib,json,os,shutil,subprocess,tempfile
assert os.geteuid()==0,'Disposable CI chroot only; never run on a phone'
here=Path(__file__).resolve().parent;results=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cases=[('firmware-1408-slot-a',0),('firmware-1409-slot-a',0),('firmware-1408-slot-b',0),('firmware-1409-slot-b',0),('old-failure-and-repeat-install',0),('same-image-readonly-target',0),('changed-target',99),('changed-slot',99),('oversize-image',99),('short-image',99),('corrupt-backup',99),('flush-error',99),('readback-error',99),('readonly-target',99),('recovery-cmdline-slot-a',0),('recovery-property-slot-b',0),('recovery-normalized-slot-values',0),('recovery-conflicting-slot-sources',99),('recovery-missing-slot',99),('recovery-invalid-slot',99),('recovery-zip-backup-unmounted-data',0),('recovery-zip-backup-readonly-data',0),('recovery-zip-backup-unavailable-data-directory',0),('recovery-no-persistent-backup',99),('recovery-tmpfs-zip-rejected',99)]
original_case_count=len(cases)
cache_cases=[
    ('recovery-cache-zip-parent',0),
    ('recovery-cache-tmp-zip',0),
    ('recovery-cache-existing-gzip',0),
    ('recovery-cache-corrupt-gzip',99),
    ('recovery-cache-truncated-gzip',99),
    ('recovery-cache-wrong-content-gzip',99),
    ('recovery-cache-gzip-output-failure',99),
    ('recovery-cache-gzip-decompress-status',99),
    ('recovery-cache-no-space',99),
    ('recovery-cache-readonly',99),
    ('recovery-cache-tmpfs',99),
    ('recovery-cache-unmounted',99),
    ('recovery-cache-symlink',99),
    ('recovery-cache-backup-directory-symlink',99),
    ('recovery-cache-gzip-symlink',99),
    ('recovery-cache-df-error',99),
    ('recovery-cache-publication-collision',99),
    ('recovery-cache-existing-raw',0),
    ('recovery-cache-corrupt-raw',99),
    ('android-cache-fallback-rejected',99),
    ('android-cache-zip-rejected',99),
    ('recovery-cache-no-export-bootmode',0),
    ('android-cache-zygote-rejected',99),
    ('unknown-cache-context-rejected',99),
    ('recovery-cache-process-list-failure',99),
    ('recovery-cache-backup-sync-failure',99),
]
cases+=cache_cases
with tempfile.TemporaryDirectory(prefix='chopin-minimal-io-') as tmp:
    for name,want in cases:
        root=Path(tmp)/name
        for n in ['bin','stage','dev','proc','data/adb/chopin-kernel-backups','vendor/lib/modules','external_sd','tmp','cache/chopin-kernel-backups']:(root/n).mkdir(parents=True,exist_ok=True)
        shutil.copyfile('/bin/busybox',root/'bin/busybox');(root/'bin/busybox').chmod(0o755)
        for n in ['sh','cat','mkdir','mktemp','sha256sum','printf','sync','dd','wc','head','awk','readlink','dirname','gzip','df','ln','rm','grep']:(root/'bin'/n).symlink_to('/bin/busybox')
        (root/'io.sh').write_bytes((here/'boot-io.sh').read_bytes())
        old=(b'old-current-boot'+bytes(8192))[:8192];new=(b'new-kernel-fixture'+bytes(4096))[:4096]
        (root/'target').write_bytes(old);(root/'stage/boot.img').write_bytes(old);(root/'stage/boot-new.img').write_bytes(new);(root/'stage/install-detail.log').write_text('ordinary-file fixture\n')
        (root/'dev/zero').write_bytes(bytes(16384))
        marker=root/'data/adb/chopin-kernel-backups/attempt_old_failed.txt';marker.write_text('phase=write_or_flush_failed\n');marker_before=marker.read_bytes()
        # Both ROM versions and arbitrary changed vendor bytes are accepted.
        rom='V14.0.9.0' if '1409' in name else 'V14.0.8.0'
        (root/'vendor/lib/modules/fixture.ko').write_bytes(rom.encode())
        slot='_b' if name.endswith('slot-b') or name in ['recovery-property-slot-b','recovery-normalized-slot-values'] else '_a'
        suffix='_b' if name=='changed-slot' else slot;property_slot='';cmdline='';zipfile='/external_sd/kernel.zip';backup_folder='data/adb/chopin-kernel-backups'
        mounts='rootfs / rootfs rw 0 0\n/dev/data /data f2fs rw 0 0\n/dev/sd /external_sd vfat rw 0 0\ntmpfs /tmp tmpfs rw 0 0\n'
        if name=='recovery-cmdline-slot-a':suffix='';cmdline='console=tty0 androidboot.slot_suffix=_a buildvariant=user'
        if name=='recovery-property-slot-b':suffix='';property_slot='b'
        if name=='recovery-normalized-slot-values':property_slot='b';cmdline='androidboot.slot_suffix=_b androidboot.slot=b'
        if name=='recovery-conflicting-slot-sources':cmdline='androidboot.slot_suffix=_b'
        if name=='recovery-missing-slot':suffix=''
        if name=='recovery-invalid-slot':suffix='normal'
        if name=='recovery-zip-backup-unmounted-data':
            mounts=mounts.replace('/dev/data /data f2fs rw 0 0\n','');backup_folder='external_sd/chopin-kernel-backups'
        if name=='recovery-zip-backup-readonly-data':
            mounts=mounts.replace('/data f2fs rw','/data f2fs ro');backup_folder='external_sd/chopin-kernel-backups'
        if name=='recovery-zip-backup-unavailable-data-directory':
            marker=root/'legacy-attempt.txt';marker.write_bytes(marker_before)
            shutil.rmtree(root/'data/adb');(root/'data/adb').write_text('unavailable encrypted directory fixture')
            backup_folder='external_sd/chopin-kernel-backups'
        if name=='recovery-no-persistent-backup':
            mounts='rootfs / rootfs rw 0 0\ntmpfs /tmp tmpfs rw 0 0\n';zipfile='/tmp/input.zip'
        if name=='recovery-tmpfs-zip-rejected':
            mounts='rootfs / rootfs rw 0 0\ntmpfs /data tmpfs rw 0 0\ntmpfs /external_sd tmpfs rw 0 0\n'
        is_cache_case=name in dict(cache_cases)
        bootmode='false'
        twrp_boot='';twrp_version='';processes='PID NAME\n1 init';ps_status=0
        if is_cache_case:
            mounts=mounts.replace('/dev/data /data f2fs rw 0 0\n','')+'/dev/cache /cache ext4 rw 0 0\n'
            zipfile='/tmp/kernel.zip';backup_folder='cache/chopin-kernel-backups'
            if name in ['recovery-cache-zip-parent','android-cache-zip-rejected']:zipfile='/cache/kernel.zip'
            if name=='recovery-cache-readonly':mounts=mounts.replace('/cache ext4 rw','/cache ext4 ro')
            if name=='recovery-cache-tmpfs':mounts=mounts.replace('/dev/cache /cache ext4','tmpfs /cache tmpfs')
            if name=='recovery-cache-unmounted':mounts=mounts.replace('/dev/cache /cache ext4 rw 0 0\n','')
            if name=='recovery-cache-symlink':
                shutil.rmtree(root/'cache');(root/'cache').symlink_to('/external_sd')
            if name=='recovery-cache-backup-directory-symlink':
                (root/backup_folder).rmdir();(root/backup_folder).symlink_to('/external_sd')
            if name.startswith('android-cache-'):bootmode='true'
            if name in ['recovery-cache-no-export-bootmode','android-cache-zygote-rejected','unknown-cache-context-rejected','recovery-cache-process-list-failure']:
                bootmode=None
                if name!='unknown-cache-context-rejected':twrp_boot='1';twrp_version='fixture'
                if name=='android-cache-zygote-rejected':processes+='\n234 zygote64'
                if name=='recovery-cache-process-list-failure':ps_status=1
            compressed=root/(backup_folder+'/boot'+slot+'-'+sha(root/'target')+'.img.gz')
            if name in ['recovery-cache-existing-gzip','recovery-cache-gzip-decompress-status']:
                compressed.write_bytes(gzip.compress(old,mtime=0))
            if name=='recovery-cache-corrupt-gzip':compressed.write_bytes(b'not gzip')
            if name=='recovery-cache-truncated-gzip':compressed.write_bytes(gzip.compress(old,mtime=0)[:-5])
            if name=='recovery-cache-wrong-content-gzip':compressed.write_bytes(gzip.compress(b'wrong'+bytes(8187),mtime=0))
            if name=='recovery-cache-gzip-symlink':
                (root/'preserved-backup').write_bytes(b'preserve this existing file')
                compressed.symlink_to('/preserved-backup')
            if name in ['recovery-cache-existing-raw','recovery-cache-corrupt-raw']:
                (root/(backup_folder+'/boot'+slot+'-'+sha(root/'target')+'.img')).write_bytes(old if name.endswith('existing-raw') else b'corrupt old raw backup')
        (root/'proc/mounts').write_text(mounts);(root/'proc/cmdline').write_text(cmdline+'\n')
        if name=='oversize-image':(root/'stage/boot-new.img').write_bytes(bytes(8193))
        if name=='short-image':(root/'stage/boot-new.img').write_bytes(b'short')
        if name=='same-image-readonly-target':(root/'stage/boot-new.img').write_bytes(old)
        if name=='corrupt-backup':(root/('data/adb/chopin-kernel-backups/boot'+slot+'-'+sha(root/'target')+'.img')).write_bytes(b'corrupt')
        script='export PATH=/bin AKHOME=/stage BOOTIMG=/stage/boot.img BLOCK=/target ZIPFILE='+zipfile+'\nSLOT='+slot+'\n'
        if bootmode is not None:script+='export BOOTMODE='+bootmode+'\n'
        script+='abort() { printf "%s\\n" "$*" >&2; exit 99; }\n'
        # These are ordinary files. Do not flush the cloud runner's whole host.
        script+='sync() { return '+('1' if name=='recovery-cache-backup-sync-failure' else '0')+'; }\n'
        script+='getprop() { case "$1" in ro.boot.slot_suffix) printf "%s\\n" "'+suffix+'";; ro.boot.slot) printf "%s\\n" "'+property_slot+'";; ro.build.version.incremental) echo '+rom+';; ro.twrp.boot) echo "'+twrp_boot+'";; ro.twrp.version) echo "'+twrp_version+'";; esac; }\n'
        script+='ps() { printf "%s\\n" "'+processes+'"; return '+str(ps_status)+'; }\n'
        script+='df() { printf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/cache 8192 4096 '+('0' if name=='recovery-cache-no-space' else '4096')+' 50%% /cache\\n"; return '+('1' if name=='recovery-cache-df-error' else '0')+'; }\n'
        if name=='recovery-cache-gzip-output-failure':
            script+='gzip() { if [ "$1" = -c ]; then calls=$(cat /gzip-calls 2>/dev/null); calls=$((calls + 1)); echo "$calls" > /gzip-calls; if [ "$calls" -eq 2 ]; then printf "partial"; echo "No space left on device (injected)" >&2; return 1; fi; fi; command gzip "$@"; }\n'
        if name=='recovery-cache-gzip-decompress-status':
            script+='gzip() { command gzip "$@"; return 1; }\n'
        if name=='recovery-cache-existing-raw':
            script+='gzip() { echo "gzip must not be called for an existing raw backup" >&2; return 1; }\n'
        if name=='recovery-cache-publication-collision':
            script+='ln() { printf "existing backup from another writer" > "$2"; return 1; }\n'
        script+='blockdev() { case "$1" in --getsize64) echo 8192;; --setrw) return '+('1' if name in ['readonly-target','same-image-readonly-target'] else '0')+';; *) return 1;; esac; }\n'
        script+='dd() { printf "%s\\n" "$*" >> /write-calls; command dd "$@"; rc=$?; '+('return 1;' if name=='flush-error' else 'return "$rc";')+' }\n. /io.sh\nchopin_backup_boot\n'
        if name=='changed-target':script+='printf CHANGED >> /target\n'
        script+='chopin_preflash_verify\nchopin_record_attempt || abort journal\nchopin_write_boot || abort write\n'
        if name=='readback-error':script+='printf DAMAGED >> /target\n'
        script+='chopin_postflash_verify\n'
        if name=='old-failure-and-repeat-install':script+='cat /target > /stage/boot.img\nchopin_backup_boot\nchopin_preflash_verify\nchopin_record_attempt || abort journal\nchopin_write_boot || abort write\nchopin_postflash_verify\n'
        (root/'run.sh').write_text(script)
        q=subprocess.run(['chroot',str(root),'/bin/sh','/run.sh'],capture_output=True,timeout=15,env={'PATH':os.environ['PATH']})
        assert q.returncode==want,(name,q.returncode,q.stdout,q.stderr)
        assert marker.read_bytes()==marker_before,'Historical failure evidence changed'
        writes=(root/'write-calls').read_text().splitlines() if (root/'write-calls').exists() else []
        if want==0:
            assert (root/'target').read_bytes()==(old if name=='same-image-readonly-target' else new+bytes(4096))
            assert len(writes)==(0 if name=='same-image-readonly-target' else 1)
            backups=list((root/backup_folder).glob('boot*.img'))
            compressed_backups=list((root/backup_folder).glob('boot*.img.gz'))
            assert any(p.read_bytes()==old for p in backups) or any(gzip.decompress(p.read_bytes())==old for p in compressed_backups),(name,'Persistent backup missing')
            if is_cache_case:
                logs=''.join(f.read_text() for f in (root/backup_folder).glob('install*.log.*'))
                assert 'backup_format='+('raw' if name=='recovery-cache-existing-raw' else 'gzip')+'\n' in logs
                assert 'backup_raw_sha256='+hashlib.sha256(old).hexdigest()+'\n' in logs
                assert 'backup_raw_bytes=8192\n' in logs and 'phase=boot_backup_verified\n' in logs
                if name!='recovery-cache-existing-raw':assert not backups,'Cache created a full raw backup'
                assert not list((root/'data').rglob('boot*.img')),'Recovery used unavailable /data'
                assert not list((root/'tmp').rglob('boot*.img*')),'Recovery put a persistent backup in RAM'
                assert not list((root/backup_folder).glob('*.partial.*')),'Successful publication left its temporary file'
            if backup_folder.startswith('external_sd/'):
                assert not list((root/'data').rglob('boot*.img')),'Recovery used unavailable /data'
            if name in ['same-image-readonly-target','old-failure-and-repeat-install']:
                logs=''.join(f.read_text() for f in (root/backup_folder).glob('install*.log.*'))
                assert 'phase=already_installed_no_partition_write' in logs
        elif name in ['flush-error','readback-error']:assert len(writes)==1
        else:assert not writes
        if is_cache_case and want!=0:
            assert (root/'target').read_bytes()==old,'A rejected backup changed the target'
        if name=='recovery-cache-publication-collision':assert compressed.read_bytes()==b'existing backup from another writer'
        if name=='recovery-cache-gzip-symlink':assert (root/'preserved-backup').read_bytes()==b'preserve this existing file'
        if name=='recovery-cache-gzip-output-failure':
            partials=list((root/backup_folder).glob('*.partial.*'))
            assert len(partials)==1 and partials[0].read_bytes()==b'partial'
            assert not compressed.exists(),'An incomplete gzip was published as a backup'
        if name=='recovery-cache-backup-sync-failure':
            assert compressed.is_file() and gzip.decompress(compressed.read_bytes())==old,'A flush failure discarded the verified backup'
        assert all('conv=fsync,notrunc' in w and 'if=/dev/zero' not in w for w in writes)
        assert all(not p.is_block_device() and not p.is_char_device() for p in root.rglob('*'))
        results.append({'case':name,'exit':q.returncode,'ordinary_file_writes':len(writes),'old_journal_preserved':True,'backup_folder':backup_folder if want==0 else None})
report={'status':'PASS_MINIMAL_INSTALLER_ORDINARY_FILE_CASES','cases':results,'original_case_count':original_case_count,'compressed_cache_case_count':len(cache_cases),'generator_sha256':sha(here/'test_io.py'),'source_sha256':{n:sha(here/n) for n in ['boot-io.sh','anykernel.sh','customize.sh']},'host_sync_mocked':True,'physical_filesystem_flush_verified':False,'real_device_or_kernel_image_used':False,'hardware_boot_verified':False,'actual_recovery_device_tested':False}
Path('minimal-installer-fixtures.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
