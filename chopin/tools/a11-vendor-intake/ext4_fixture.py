"""Cloud-only generated ext4 -> synthetic payload -> fixed-module integration."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import sys
from unittest.mock import patch
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
        (modules/"r_only_fixture.ko").write_bytes(b"inventory metadata only; not an ELF module")
        (modules/"subdirectory").mkdir()
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
        snapshots=[]
        inventory_reader=fixture.partition_from(payload)
        with_inventory,_=module_manifests(inventory_reader,["conninfra.ko","met.ko"],on_inventory=snapshots.append)
        assert with_inventory==parsed and len(snapshots)==1 and snapshots[0]["complete"]
        inventory={entry["name"]:entry for entry in snapshots[0]["entries"]}
        assert inventory["r_only_fixture.ko"]=={"name":"r_only_fixture.ko","size":len(b"inventory metadata only; not an ELF module"),"type":"regular"}
        assert inventory["subdirectory"]["type"]=="directory"
        # Exercise the real CLI's failure report with a fake HTTP transport, never a live URL.
        import intake
        from vendor_reader import remote_class
        def synthetic_remote(base):
            parent=remote_class(base)
            class Reader(parent):
                def __init__(self,url):super().__init__(url,fixture.FakeHTTP(payload))
            return Reader
        missing_out=work/"missing-report"
        argv=["intake.py","--helper",str(args.helper),"--out",str(missing_out),"--inventory","--module","connfem.ko"]
        with patch.object(intake,"remote_class",synthetic_remote),patch.object(sys,"argv",argv):
            code=intake.main()
        failed=json.loads((missing_out/"module-imports.json").read_text())
        assert code==2 and failed["status"]=="BLOCKED_BOUNDED_INTAKE_NO_COMPATIBILITY_CLAIM"
        assert failed["directory_inventory"]["complete"] and failed["directory_inventory"]["entries"]==snapshots[0]["entries"]
        assert failed["modules_not_completed"]==["connfem.ko"] and not failed["modules"]
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
        symlink_inventory=[]
        try:module_manifests(symlink_reader,["met.ko"],on_inventory=symlink_inventory.append)
        except ValueError:rejected=True
        assert rejected,"Module symlink was followed"
        assert symlink_inventory[0]["complete"]
        assert next(entry for entry in symlink_inventory[0]["entries"]if entry["name"]=="met.ko")["type"]=="symlink"
        report={"status":"PASS_GENERATED_EXT4_AND_SYNTHETIC_PAYLOAD_ONLY","regular_file_fixture_bytes":len(data),
                "requested_modules":parsed,"filesystem":filesystem,"payload_operations_total":len(rows),
                "payload_operations_read":checked,"unrequested_operations_not_downloaded":True,
                "module_symlink_rejected":True,"mke2fs_command_template":"mke2fs -q -t ext4 -F -b 4096 -d TEMP_TREE TEMP_REGULAR_FILE",
                "directory_inventory":snapshots[0],"default_import_result_unchanged_with_inventory":True,
                "real_CLI_missing_selected_module_report_preserved_inventory":True,
                "missing_selected_module_returned_BLOCKED_and_exit2":True,"CLI_transport_was_synthetic_only":True,
                "mke2fs_stderr":result.stderr,"ROM_accessed":False,"OEM_files_used":False,"phone_accessed":False,
                "raw_fixture_or_module_uploaded":False,
                "source_sha256":{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                 for name in ("ext4_fixture.py","vendor_reader.py","test_vendor_reader.py","intake.py")}}
    with args.report.open("x")as stream:json.dump(report,stream,indent=2);stream.write("\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
