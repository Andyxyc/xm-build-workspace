"""Package three independently verified vendor ABIs with ordinary AK3 entries."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess,sys,tempfile,zipfile

if not __debug__:raise SystemExit('Normal Python mode required')
here=Path(__file__).resolve().parent
KPIMG_SHA='554aa43ff1594ea516eb9d74581565aea07e29665ffaf702a3c87d556a7a2425'
PROFILES=['legacy','early','t']
sha=lambda b:hashlib.sha256(b).hexdigest()

def json_file(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def selector_report(path,binary,source_hash,generator_hash):
    record=json_file(path)
    assert record['status']=='PASS_REAL_COMPILED_SELECTOR_SYNTHETIC_ELF_FILE_CASES_ONLY'
    assert record['profiles']==PROFILES and record['supported_profiles']==PROFILES
    assert record['case_count']==len(record['cases']) and record['case_count']>=85
    assert record['legacy_case_count']==60 and record['third_family_case_count']>=25
    assert record['source_sha256']==source_hash and record['generator_sha256']==generator_hash
    assert record['binary_sha256']==sha(binary.read_bytes())
    return {'case_count':record['case_count'],'report_sha256':sha(path.read_bytes()),'binary_sha256':record['binary_sha256']}

def manager_metadata(path,proof):
    record=json_file(path)
    version=record['version_code'];assert type(version) is int and version>0
    commit=record['manager_ci_commit'];assert re.fullmatch('[0-9a-f]{40}',commit)
    current=record['current_ci_source_verification']
    assert current['official_manager_ci']==version and current['main_commit']==commit
    for key in ['version_code','manager_version_code','official_manager_ci']:
        if key in proof:assert proof[key]==version,('Proof/manifest manager mismatch',key)
    for key in ['uapi_version','extension_api_version','kpm_bridge_abi']:
        assert type(record[key]) is int and record[key]>0
    return {'version_code':version,'manager_commit':commit,'release_tag':current.get('release_tag'),
            'version_name':current.get('version_name'),'uapi_version':record['uapi_version'],
            'extension_api_version':record['extension_api_version'],'kpm_bridge_abi':record['kpm_bridge_abi'],
            'manifest_sha256':sha(path.read_bytes())}

def main():
    parser=argparse.ArgumentParser()
    for name in ['t-candidate','legacy-candidate','early-candidate','t-proof','legacy-proof','early-proof',
                 'ak3','licenses','selector-evidence','fixtures','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--base-repo',type=Path,default=here.parents[3])
    parser.add_argument('--source-commit',required=True);parser.add_argument('--revision',default='r17')
    parser.add_argument('--early-proof-profile',default='early');parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}',args.source_commit) and re.fullmatch(r'r[1-9][0-9]*',args.revision)
    assert not args.output.exists() and re.fullmatch(r'chopin-[A-Za-z0-9._-]+\.zip',args.output.name)
    assert 'xiaomo' not in args.output.name.lower()
    report=args.report or args.output.with_suffix('.build.json');assert not report.exists()
    base=args.base_repo.resolve();minimal=base/'chopin/tools/installer/minimal'
    sys.path.insert(0,str(base/'chopin'))
    from verify_image_entry import inspect_kpm
    generator=base/'chopin/tools/abi_selector/host-test.py'
    generator_source=generator.read_text(encoding='utf-8');namespace={}
    assert '\np=argparse.ArgumentParser()' in generator_source
    exec(compile(generator_source.split('\np=argparse.ArgumentParser()',1)[0],str(generator),'exec'),namespace)
    anchor_sets={name:namespace[name.upper()] for name in PROFILES}
    assert anchor_sets['early']=={**anchor_sets['legacy'],
        **{key:anchor_sets['t'][key] for key in ['cpu_hwcaps','cpu_hwcap_keys']}}
    profiles={}
    inputs=[('t',args.t_candidate,args.t_proof,'A13'),
            ('legacy',args.legacy_candidate,args.legacy_proof,'A12'),
            ('early',args.early_candidate,args.early_proof,args.early_proof_profile)]
    for name,candidate,proof_path,expected_profile in inputs:
        image=(candidate/'kernel_workspace/android-kernel/out/arch/arm64/boot/Image').read_bytes()
        proof=json_file(proof_path);evidence=candidate/'release-evidence'
        assert proof['status']=='PASS_INDEPENDENT_NATIVE_IMAGE_CHECKS_ONLY' and proof['image_sha256']==sha(image)
        assert len(proof['checks'])==13 and all(row['exit']==0 for row in proof['checks']) and proof['native_current_uapi_checked']
        assert proof['profile'].casefold()==expected_profile.casefold(),(name,'Wrong proof profile')
        before=(evidence/'Image.sukisu-susfs-before-kpm').read_bytes();runtime=(evidence/'kpimg.pinned').read_bytes()
        entry=inspect_kpm(image,before,runtime)
        assert sha(runtime)==KPIMG_SHA and entry['kpimg_sha256']==KPIMG_SHA
        assert image[entry['kpimg_offset']+4096:entry['kpimg_offset']+entry['kpimg_bytes']]==runtime[4096:]
        rows={fields[1]:int(fields[0],16) for line in (evidence/'ported.Module.symvers').read_text(encoding='utf-8').splitlines()
              if len(fields:=line.split())>=3 and fields[2]=='vmlinux'}
        anchors=anchor_sets[name]
        assert all(rows.get(key)==value for key,value in anchors.items()),(name,'Selector anchors do not match packaged kernel')
        kernel_commit=(candidate/'build-logs/root-build-complete.txt').read_text(encoding='utf-8').strip()
        assert re.fullmatch('[0-9a-f]{40}',kernel_commit)
        manager=manager_metadata(evidence/'chopin-ci-port.json',proof)
        profiles[name]={'image':image,'image_sha256':sha(image),'bytes':len(image),'kernel_commit':kernel_commit,
            'proof_sha256':sha(proof_path.read_bytes()),'native_checks':13,
            'selector_anchor_crcs':{key:f'{value:08x}' for key,value in anchors.items()},
            'kpimg_sha256':sha(runtime),'manager':manager}
    assert len({info['image_sha256'] for info in profiles.values()})==3,'Three distinct ABI payloads are required'
    manager_versions={info['manager']['version_code'] for info in profiles.values()}
    manager_commits={info['manager']['manager_commit'] for info in profiles.values()}
    assert len(manager_versions)==len(manager_commits)==1,'All kernels must match the same official manager build'
    for key in ['uapi_version','extension_api_version','kpm_bridge_abi']:
        assert len({info['manager'][key] for info in profiles.values()})==1,('Inconsistent kernel API',key)
    build_version=manager_versions.pop()

    tool_path=args.selector_evidence/'chopin-abi-select';tool=tool_path.read_bytes();tool_hash=sha(tool)
    assert tool[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',tool,18)[0]==183
    offset=struct.unpack_from('<Q',tool,32)[0];size,count=struct.unpack_from('<HH',tool,54)
    assert size==56 and 0<count<64 and offset+size*count<=len(tool)
    assert all(struct.unpack_from('<I',tool,offset+index*size)[0]!=3 for index in range(count)), 'Selector must be static (no PT_INTERP)'
    source_hash=sha((base/'chopin/tools/abi_selector/chopin_abi_select.c').read_bytes())
    generator_hash=sha(generator.read_bytes())
    selector_tests={name:selector_report(args.selector_evidence/name,args.selector_evidence/binary,source_hash,generator_hash)
        for name,binary in [('host-file-tests.json','chopin-abi-select-host'),('aarch64-file-tests.json','chopin-abi-select')]}
    for folder in [args.selector_evidence,args.fixtures]:
        assert (folder/'source-commit.txt').read_text(encoding='utf-8').strip()==args.source_commit,'CI commit does not match installer source commit'
    minimal_cases=0
    for name in ['minimal-installer-fixtures.json','minimal-entry-tools-fixtures.json']:
        result=json_file(args.fixtures/name);assert result['status'].startswith('PASS_')
        for filename,digest in result['source_sha256'].items():
            assert digest==sha((minimal/filename).read_bytes()),('Stale minimal fixture',filename)
        minimal_cases+=len(result['cases'])
    assert minimal_cases==38,'The existing 38 minimal installer cases must run against these exact common sources'
    flow_path=args.fixtures/'dual-flow-fixtures.json';flow=json_file(flow_path)
    assert flow['status']=='PASS_THREE_ABI_SHELL_REAL_SELECTOR_ORDINARY_FILE_FLOW_ONLY'
    assert flow['profiles']==PROFILES and flow['case_count']>=43 and len(flow['cases'])==flow['case_count']
    assert flow['selector_binary_sha256']==tool_hash and flow['selector_source_sha256']==source_hash
    assert flow['minimal_boot_io_sha256']==sha((minimal/'boot-io.sh').read_bytes())
    for filename,digest in flow['source_sha256'].items():
        assert digest==sha((here/filename).read_bytes()),('Stale installer fixture',filename)
    assert flow['elf_generator_sha256']==generator_hash
    assert flow['selector_test_reports_sha256']=={name:info['report_sha256'] for name,info in selector_tests.items()}

    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chopin-three-abi-build-',dir=args.output.parent) as temporary:
        assert Path(temporary).resolve().parent==args.output.parent.resolve()
        temporary_zip=Path(temporary)/'chopin-t-verified.zip'
        command=[sys.executable,str(minimal/'build.py'),'--candidate',str(args.t_candidate),'--proof',str(args.t_proof),
            '--ak3',str(args.ak3),'--licenses',str(args.licenses),'--output',str(temporary_zip),
            '--source-commit',args.source_commit,'--revision',args.revision]
        completed=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        if completed.returncode:
            raise RuntimeError('Common AK3 package preparation failed:\n'+completed.stdout+completed.stderr)
        with zipfile.ZipFile(temporary_zip) as archive:
            assert archive.testzip() is None;files={name:archive.read(name) for name in archive.namelist()}
        assert files['Image']==profiles['t']['image']
        for name in ['legacy','early']:files['images/'+name+'/Image']=profiles[name]['image']
        files['tools/chopin-abi-select']=tool
        files['tools/chopin-select-kernel.sh']=(here/'select-kernel.sh').read_bytes()
        files['anykernel.sh']=(here/'anykernel.sh').read_bytes()
        assert b'supported.versions=' not in files['anykernel.sh']
        assert files['customize.sh']==(minimal/'customize.sh').read_bytes()
        assert files['tools/chopin-preflight.sh']==(minimal/'boot-io.sh').read_bytes()
        module=files['module.prop'].decode()
        module=re.sub(r'(?m)^version=.*$',f'version={args.revision}-CI{build_version}',module)
        module=re.sub(r'(?m)^versionCode=.*$',f'versionCode={build_version}',module)
        files['module.prop']=module.encode()
        manifest={'format':2,'profiles':PROFILES,'buildVersion':build_version,
            'selection':'Real vendor ELF __versions anchors; never Android SDK',
            'payloads':{name:{key:value for key,value in info.items() if key!='image'} for name,info in profiles.items()},
            'root_Image_profile':'t','other_Image_paths':['images/legacy/Image','images/early/Image'],
            'selector_sha256':tool_hash,'selector_source_sha256':source_hash,'installer_commit':args.source_commit,
            'minimal_common_fixture_cases':minimal_cases,'installer_shell_fixture_cases':flow['case_count'],
            'selector_tests':selector_tests,'unknown_or_conflicting_abi_default':None,'device_scope':'chopin',
            'phone_or_recovery_test_verified_by_this_builder':False}
        files['DUAL-ABI.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
        source_note='Three ABI installer: https://github.com/Andyxyc/xm-build-workspace/tree/'+args.source_commit+'/chopin/tools/installer/dual\n'
        source_note+='Official manager build (from all three kernel manifests): '+str(build_version)+'\n'
        for name in ['legacy','early']:
            source_note+=name+' ABI kernel: https://github.com/Andyxyc/xm-build-workspace/tree/'+profiles[name]['kernel_commit']+'\n'
        source_note+='Selection uses vendor ABI, not a fixed Android/MIUI version.\n'
        files['SOURCE.txt']+=source_note.encode()
        expected_images=['Image','images/early/Image','images/legacy/Image']
        assert sorted(name for name in files if name=='Image' or name.endswith('/Image'))==expected_images
        assert not any(name.lower().endswith('.apk') or name.startswith(('expected/','stock-')) for name in files)
        with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for name,data in sorted(files.items()):
                assert not Path(name).is_absolute() and '..' not in Path(name).parts
                item=zipfile.ZipInfo(name,(2026,10,29,0,0,0));item.create_system=3
                item.external_attr=(0o100755 if name.startswith('tools/') or name.endswith('.sh') or name.endswith('update-binary') else 0o100644)<<16
                archive.writestr(item,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        for name,path in [('t','Image'),('legacy','images/legacy/Image'),('early','images/early/Image')]:
            assert archive.read(path)==profiles[name]['image']
    result={'status':'PASS_THREE_ABI_PACKAGE_STATIC_PROOFS_AND_BOUND_FILE_FIXTURES_ONLY',
        'path':str(args.output),'bytes':args.output.stat().st_size,'sha256':sha(args.output.read_bytes()),
        'files':len(files),'image_payload_count':3,'embedded_apks':0,'buildVersion':build_version,
        'profiles':manifest['payloads'],'selector_sha256':tool_hash,'minimal_common_fixture_cases':minimal_cases,
        'installer_shell_fixture_cases':flow['case_count'],'file_sha256':{name:sha(data) for name,data in files.items()},
        'physical_flash_or_boot_proved_by_packaging':False}
    with report.open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ['profiles','file_sha256']},ensure_ascii=False))

if __name__=='__main__':main()
