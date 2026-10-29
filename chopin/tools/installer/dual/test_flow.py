"""Real ARM selector + real Shell/boot-I/O functions on synthetic ELF files.

Disposable Linux chroots only. This does not perform boot repacking, mount a
filesystem, create a device node, load a module or establish hardware support.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess,tempfile

PROFILES=['legacy','early','t']
sha=lambda b:hashlib.sha256(b).hexdigest()
here=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--selector-evidence',type=Path,required=True);p.add_argument('--qemu',type=Path,default=Path('/usr/bin/qemu-aarch64-static'));p.add_argument('--base-repo',type=Path,default=here.parents[3]);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
assert os.name=='posix' and os.geteuid()==0,'Disposable Linux chroot only; never run on a phone'
binary=(a.selector_evidence/'chopin-abi-select').resolve();qemu=a.qemu.resolve();assert binary.is_file() and qemu.is_file()
base=a.base_repo.resolve();minimal=base/'chopin/tools/installer/minimal'
generator=base/'chopin/tools/abi_selector/host-test.py';src=generator.read_text(encoding='utf-8');ns={}
assert '\np=argparse.ArgumentParser()' in src
exec(compile(src.split('\np=argparse.ArgumentParser()',1)[0],str(generator),'exec'),ns)
assert ns['EARLY']=={**ns['LEGACY'],**{key:ns['T'][key] for key in ['cpu_hwcaps','cpu_hwcap_keys']}}
source_hash=sha((base/'chopin/tools/abi_selector/chopin_abi_select.c').read_bytes());generator_hash=sha(generator.read_bytes());selector_reports={}
for name,executable in [('host-file-tests.json','chopin-abi-select-host'),('aarch64-file-tests.json','chopin-abi-select')]:
    path=a.selector_evidence/name;record=json.loads(path.read_text(encoding='utf-8'))
    assert record['status']=='PASS_REAL_COMPILED_SELECTOR_SYNTHETIC_ELF_FILE_CASES_ONLY'
    assert record['profiles']==PROFILES and record['supported_profiles']==PROFILES
    assert record['case_count']==len(record['cases']) and record['case_count']>=85 and record['legacy_case_count']==60 and record['third_family_case_count']>=25
    assert record['source_sha256']==source_hash and record['generator_sha256']==generator_hash
    assert record['binary_sha256']==sha((a.selector_evidence/executable).read_bytes())
    selector_reports[name]=sha(path.read_bytes())
make=lambda values:bytes(ns['elf'](ns['records'](values)))
legacy=make(ns['LEGACY']);early=make(ns['EARLY']);modern=make(ns['T']);unknown=dict(ns['LEGACY']);unknown['cpu_hwcaps']=0x12345678;unknown=make(unknown)
mixed=dict(ns['LEGACY']);mixed['cpu_hwcap_keys']=ns['T']['cpu_hwcap_keys'];mixed=make(mixed)
entry=(here/'anykernel.sh').read_text(encoding='utf-8')
assert 'supported.versions' not in entry and entry.count('chopin_select_kernel_abi;')==1
order=['split_boot 2>>','chopin_backup_boot;','chopin_select_kernel_abi;','chopin_clean_ramdisk ','flash_boot 2>>','chopin_postflash_verify;']
assert [entry.index(s) for s in order]==sorted(entry.index(s) for s in order)
assert 'SLOT_SELECT=active;' in entry and 'NO_VBMETA_PARTITION_PATCH=1;' in entry

cases=[{'name':'framework'+version+'-'+profile+'-vendor','sdk':sdk,'version':version,'profile':profile}
       for sdk,version in [(30,'11'),(31,'12'),(33,'13'),(34,'14'),(99,'99')] for profile in PROFILES]+[
 {'name':'t-keeps-root-image-without-copy','profile':'t'},
 {'name':'nested-vendor-dlkm-legacy','profile':'legacy','location':'vendor_dlkm/lib/modules/4.14 profile/conninfra.ko'},
 {'name':'odm-only-t','profile':'t','location':'odm/lib/modules/met.ko'},
 {'name':'unrelated-ko-is-not-scanned','profile':'legacy','decoy':True},
 {'name':'recovery-existing-vendor-legacy','profile':'legacy','bootmode':'false'},
 {'name':'recovery-ro-mount-vendor-legacy','profile':'legacy','bootmode':'false','mount':'vendor'},
 {'name':'recovery-ro-mount-odm-t','profile':'t','bootmode':'false','mount':'odm'},
 {'name':'recovery-ro-mount-vendor-early','profile':'early','bootmode':'false','mount':'vendor'},
 {'name':'unset-bootmode-android-t','profile':'t','bootmode':'unset','ps_zygote':True},
 {'name':'unset-bootmode-recovery-ro-mount','profile':'legacy','bootmode':'unset','ps_zygote':False,'mount':'vendor'},
 {'name':'unknown-crc','bad':'unknown','fail':True},
 {'name':'mixed-within-module','bad':'mixed','fail':True},
 {'name':'mixed-across-modules','bad':'mixed-files','fail':True},
 {'name':'early-t-conflict-across-modules','profile':'early','bad':'mixed-files','fail':True},
 {'name':'truncated-elf','bad':'truncated','fail':True},
 {'name':'android-missing-modules','bad':'missing','fail':True},
 {'name':'recovery-missing-modules','bad':'missing','bootmode':'false','fail':True},
 {'name':'missing-legacy-image','profile':'legacy','missing_image':'legacy','fail':True},
 {'name':'missing-early-image','profile':'early','missing_image':'early','fail':True},
 {'name':'empty-early-image','profile':'early','empty_early':True,'fail':True},
 {'name':'missing-t-root-image','profile':'t','missing_image':'t','fail':True},
 {'name':'empty-t-root-image','profile':'t','empty_t':True,'fail':True},
 {'name':'missing-selector','profile':'legacy','missing_selector':True,'fail':True},
 {'name':'recovery-mount-not-readonly','profile':'legacy','bootmode':'false','mount':'vendor','mount_rw':True,'fail':True},
 {'name':'recovery-unmount-failure','profile':'legacy','bootmode':'false','mount':'vendor','umount_fail':True,'fail':True},
 {'name':'t-same-image-readonly-no-write','profile':'t','same_image':True,'block_readonly':True},
 {'name':'early-same-image-readonly-no-write','profile':'early','same_image':True,'block_readonly':True},
 {'name':'read-write-error-is-not-success','profile':'legacy','block_readonly':True,'fail':True},
]
results=[];t_image=(b't-kernel-profile\0'+bytes(4096))[:4096];legacy_image=(b'legacy-kernel-profile\0'+bytes(4096))[:4096];early_image=(b'early-kernel-profile\0'+bytes(4096))[:4096]
images={'legacy':legacy_image,'early':early_image,'t':t_image};modules={'legacy':legacy,'early':early,'t':modern}
with tempfile.TemporaryDirectory(prefix='chopin-dual-shell-') as tmp:
 for c in cases:
    d=Path(tmp)/c['name']
    for n in ['bin','system/bin','stage/tools','stage/images/legacy','stage/images/early','proc','dev','data/adb/chopin-kernel-backups','vendor/lib/modules','vendor_dlkm/lib/modules','odm/lib/modules','odm_dlkm/lib/modules','fixtures']:(d/n).mkdir(parents=True,exist_ok=True)
    shutil.copyfile('/bin/busybox',d/'bin/busybox');(d/'bin/busybox').chmod(0o755)
    for n in ['sh','awk','cat','cp','dd','dirname','grep','head','mkdir','mktemp','mv','printf','readlink','sha256sum','sync','touch','wc']:(d/'bin'/n).symlink_to('/bin/busybox')
    (d/'system/bin/sh').symlink_to('/bin/busybox')
    shutil.copyfile(qemu,d/'bin/qemu-aarch64-static');(d/'bin/qemu-aarch64-static').chmod(0o755)
    shutil.copyfile(binary,d/'stage/tools/chopin-abi-select.real');(d/'stage/tools/chopin-abi-select.real').chmod(0o755)
    wrapper=d/'stage/tools/chopin-abi-select';wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> /selector-argv\nexec /bin/qemu-aarch64-static /stage/tools/chopin-abi-select.real "$@"\n');wrapper.chmod(0o755)
    (d/'stage/tools/chopin-select-kernel.sh').write_bytes((here/'select-kernel.sh').read_bytes())
    (d/'io.sh').write_bytes((minimal/'boot-io.sh').read_bytes())
    (d/'stage/Image').write_bytes(t_image);(d/'stage/images/legacy/Image').write_bytes(legacy_image);(d/'stage/images/early/Image').write_bytes(early_image)
    if c.get('missing_image')=='legacy':(d/'stage/images/legacy/Image').unlink()
    if c.get('missing_image')=='early':(d/'stage/images/early/Image').unlink()
    if c.get('missing_image')=='t':(d/'stage/Image').unlink()
    if c.get('empty_t'):(d/'stage/Image').write_bytes(b'')
    if c.get('empty_early'):(d/'stage/images/early/Image').write_bytes(b'')
    if c.get('missing_selector'):wrapper.unlink()
    profile=c.get('profile','legacy');current=images[profile]+bytes(4096) if c.get('same_image') else (b'old-boot-file'+bytes(8192))[:8192]
    (d/'target').write_bytes(current);(d/'stage/boot.img').write_bytes(current);(d/'stage/install-detail.log').write_text('ordinary-file selection fixture\n')
    (d/'stage/preserved.ramdisk').write_bytes(b'ROM-owned ramdisk sentinel');(d/'stage/preserved.dtb').write_bytes(b'ROM-owned DTB sentinel')
    (d/'dev/zero').write_bytes(bytes(16384));(d/'proc/cmdline').write_text('androidboot.slot_suffix=_a\n')
    mounts='rootfs / rootfs rw 0 0\n/dev/data /data f2fs rw 0 0\n'
    module=modules[profile]
    if c.get('bad')=='unknown':module=unknown
    if c.get('bad')=='mixed':module=mixed
    if c.get('bad')=='truncated':module=b'\x7fELF'
    if c.get('mount'):
        (d/'fixtures/mounted.ko').write_bytes(module)
    elif c.get('bad')!='missing':
        location=c.get('location','vendor/lib/modules/conninfra.ko');f=d/location;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(module)
        partition=location.split('/')[0];mounts+='/dev/'+partition+' /'+partition+' ext4 rw 0 0\n'
    if c.get('bad')=='mixed-files':(d/'odm/lib/modules/met.ko').write_bytes(modern);mounts+='/dev/odm /odm ext4 rw 0 0\n'
    if c.get('decoy'):(d/'vendor/lib/modules/unrelated.ko').write_bytes(modern)
    (d/'proc/mounts').write_text(mounts)
    old_journal=d/'data/adb/chopin-kernel-backups/attempt_old.txt';old_journal.write_text('phase=old_failure_must_be_retained\n');old_journal_data=old_journal.read_bytes()
    bootmode=c.get('bootmode','true');assignment='unset BOOTMODE;' if bootmode=='unset' else 'export BOOTMODE='+bootmode+';'
    sdk=str(c.get('sdk',33));version=c.get('version','13');mount_partition=c.get('mount','never-mounted');mount_flags='rw' if c.get('mount_rw') else 'ro';umount_rc='1' if c.get('umount_fail') else '0'
    script='export PATH=/bin AKHOME=/stage BOOTIMG=/stage/boot.img BLOCK=/target SLOT=_a\n'+assignment+'\n'
    script+='abort() { printf "%s\\n" "$*" >&2; exit 99; }\nui_print() { printf "%s\\n" "$*"; }\n'
    script+='getprop() { case "$1" in ro.boot.slot_suffix) echo _a;; ro.product.device) echo chopin;; ro.build.version.sdk) echo '+sdk+';; ro.build.version.release) echo '+version+';; esac; }\n'
    script+='ps() { '+('echo "1 root zygote64";' if c.get('ps_zygote',bootmode=='true') else ':;')+' }\n'
    script+='blockdev() { case "$1" in --getsize64) echo 8192;; --setrw) return '+('1' if c.get('block_readonly') else '0')+';; *) return 1;; esac; }\n'
    script+='cp() { printf "%s\\n" "$*" >> /payload-copy-calls; command cp "$@"; }\n'
    script+='dd() { printf "%s\\n" "$*" >> /target-write-calls; command dd "$@"; }\n'
    script+='mount() { printf "%s\\n" "$*" >> /mount-calls; for point in "$@"; do :; done; [ "$point" = /'+mount_partition+' ] || return 1; command mkdir -p "$point/lib/modules"; command cp /fixtures/mounted.ko "$point/lib/modules/conninfra.ko"; printf "/fixture %s ext4 '+mount_flags+' 0 0\\n" "$point" >> /proc/mounts; }\n'
    script+='umount() { printf "%s\\n" "$*" >> /umount-calls; [ '+umount_rc+' = 0 ] || return 1; awk -v point="$1" \'$2 != point\' /proc/mounts > /proc/new-mounts; mv /proc/new-mounts /proc/mounts; }\n'
    script+='. /io.sh\n. /stage/tools/chopin-select-kernel.sh\nchopin_backup_boot\nchopin_select_kernel_abi\ncat /stage/Image > /stage/boot-new.img\nchopin_preflash_verify\nchopin_record_attempt || abort journal\nchopin_write_boot || abort write\nchopin_postflash_verify\nprintf "%s\\n" "$CHOPIN_SELECTED_ABI" > /selected\n'
    (d/'run.sh').write_text(script)
    q=subprocess.run(['chroot',str(d),'/bin/sh','/run.sh'],capture_output=True,timeout=15)
    fail=c.get('fail',False);assert q.returncode==(99 if fail else 0),(c,q.returncode,q.stdout,q.stderr)
    writes=(d/'target-write-calls').read_text().splitlines() if (d/'target-write-calls').exists() else []
    copies=(d/'payload-copy-calls').read_text().splitlines() if (d/'payload-copy-calls').exists() else []
    mount_calls=(d/'mount-calls').read_text().splitlines() if (d/'mount-calls').exists() else []
    if fail:
        assert (d/'target').read_bytes()==current and not writes and not (d/'selected').exists(),(c,'Target changed on failure')
    else:
        assert (d/'selected').read_text().strip()==profile
        expected=images[profile]
        assert (d/'stage/Image').read_bytes()==expected and (d/'target').read_bytes()==expected+bytes(4096)
        assert len(copies)==(0 if profile=='t' else 1),('Self copy or wrong payload copy',c,copies)
        assert len(writes)==(0 if c.get('same_image') else 1)
        assert all('conv=fsync,notrunc' in line for line in writes)
    assert all('-o ro' in line and '-o rw' not in line for line in mount_calls)
    if bootmode=='true':assert not mount_calls
    if c.get('mount') and not c.get('umount_fail'):assert '/fixture ' not in (d/'proc/mounts').read_text()
    assert (d/'stage/preserved.ramdisk').read_bytes()==b'ROM-owned ramdisk sentinel' and (d/'stage/preserved.dtb').read_bytes()==b'ROM-owned DTB sentinel'
    assert old_journal.read_bytes()==old_journal_data
    assert all(not x.is_block_device() and not x.is_char_device() for x in d.rglob('*'))
    results.append({'case':c['name'],'sdk':int(sdk),'expected_profile':None if fail else profile,'exit':q.returncode,'ordinary_target_writes':len(writes),'payload_copy_calls':len(copies),'readonly_mount_attempts':len(mount_calls),'target_unchanged_on_failure':True if fail else None,'ramdisk_dtb_sentinels_unchanged':True})

assert len(results)==43
report={'status':'PASS_THREE_ABI_SHELL_REAL_SELECTOR_ORDINARY_FILE_FLOW_ONLY','profiles':PROFILES,'case_count':len(results),'cases':results,'source_sha256':{n:sha((here/n).read_bytes()) for n in ['anykernel.sh','select-kernel.sh','test_flow.py','build.py']},'minimal_boot_io_sha256':sha((minimal/'boot-io.sh').read_bytes()),'elf_generator_sha256':generator_hash,'selector_source_sha256':source_hash,'selector_binary_sha256':sha(binary.read_bytes()),'selector_test_reports_sha256':selector_reports,'selector_invoked_via_qemu_wrapper':True,'actual_selector_elf_files_not_mocked':True,'real_mounts_or_device_nodes_used':False,'boot_repacking_exercised':False,'phone_or_hardware_tested':False,'physical_recovery_flash_verified':False}
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':report['status'],'case_count':len(results),'report':str(a.report)},ensure_ascii=False))
