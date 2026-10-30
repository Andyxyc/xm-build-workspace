"""Cloud-only generated ext4 -> synthetic payload -> fixed-module integration."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import test_vendor_reader as fixture
from vendor_reader import module_manifests, reviewed_definitions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS")!="true" or not shutil.which("mke2fs"):
        raise RuntimeError("This generated ordinary-file fixture needs the cloud runner's existing mke2fs")
    if args.report.exists():raise ValueError("Preserve the prior fixture report")
    fixture.HELPER=reviewed_definitions(args.helper)
    with tempfile.TemporaryDirectory(prefix="chopin-synthetic-ext4-") as directory:
        work=Path(directory);tree=work/"tree";modules=tree/"lib/modules";modules.mkdir(parents=True)
        expected={}
        for name in ("conninfra.ko","met.ko"):
            data=fixture.module_bytes();(modules/name).write_bytes(data)
            expected[name]=hashlib.sha256(data).hexdigest()
        image=work/"fixture.img"
        with image.open("xb")as stream:stream.truncate(32*1024*1024)
        if image.is_block_device()or image.is_symlink():raise ValueError("Fixture target must be an ordinary temporary file")
        command=["mke2fs","-q","-t","ext4","-F","-b","4096","-d",str(tree),str(image)]
        result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=30)
        data=image.read_bytes();rows=[]
        for offset in range(0,len(data),1024*1024):
            raw=data[offset:offset+1024*1024]
            kind=6 if not any(raw)else 1 if len(rows)%2 else 8
            rows.append((kind,raw,[(offset//4096,len(raw)//4096)]))
        payload=fixture.payload_zip(rows,len(data))
        reader=fixture.partition_from(payload)
        parsed,filesystem=module_manifests(reader,["conninfra.ko","met.ko"])
        assert {row["file"]:row["sha256"]for row in parsed}==expected
        assert all(row["imports"]=={"module_layout":"2d3d4373"}for row in parsed)
        assert 0<len(reader.proof)<len(rows),"Fixture unexpectedly read the whole generated partition"
        checked=len(reader.proof)
        # A symlink is not followed to another path, even inside this generated image.
        (modules/"met.ko").unlink();(modules/"met.ko").symlink_to("conninfra.ko")
        other=work/"symlink.img"
        with other.open("xb")as stream:stream.truncate(32*1024*1024)
        subprocess.run(command[:-1]+[str(other)],check=True,capture_output=True,timeout=30)
        raw=other.read_bytes();symlink_rows=[]
        for offset in range(0,len(raw),1024*1024):
            block=raw[offset:offset+1024*1024]
            symlink_rows.append((6 if not any(block)else 1,block,[(offset//4096,len(block)//4096)]))
        symlink_reader=fixture.partition_from(fixture.payload_zip(symlink_rows,len(raw)))
        rejected=False
        try:module_manifests(symlink_reader,["met.ko"])
        except ValueError:rejected=True
        assert rejected,"Module symlink was followed"
        report={"status":"PASS_GENERATED_EXT4_AND_SYNTHETIC_PAYLOAD_ONLY","regular_file_fixture_bytes":len(data),
                "requested_modules":parsed,"filesystem":filesystem,"payload_operations_total":len(rows),
                "payload_operations_read":checked,"unrequested_operations_not_downloaded":True,
                "module_symlink_rejected":True,"mke2fs_command_template":"mke2fs -q -t ext4 -F -b 4096 -d TEMP_TREE TEMP_REGULAR_FILE",
                "mke2fs_stderr":result.stderr,"ROM_accessed":False,"OEM_files_used":False,"phone_accessed":False,
                "raw_fixture_or_module_uploaded":False,
                "source_sha256":{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                 for name in ("ext4_fixture.py","vendor_reader.py","test_vendor_reader.py")}}
    with args.report.open("x")as stream:json.dump(report,stream,indent=2);stream.write("\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
