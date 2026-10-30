"""Cloud-only, bounded official A11 vendor module import intake; no raw outputs."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import resource
import signal
import sys
import zipfile
from pathlib import Path
from vendor_reader import (HELPER_SHA, MAX_NETWORK, MAX_RANGE, MODULES, PayloadPartition,
                           module_manifests, remote_class, reviewed_definitions)

URL = ("https://bigota.d.miui.com/V12.5.7.0.RKPMIXM/"
       "miui_CHOPINGlobal_V12.5.7.0.RKPMIXM_c79b13bbdc_11.0.zip")
BOOT_SHA = "a0fbb496a41d93d171f6fbd72c09023174c98dd396e215dc6af5f3a05089711c"
IMAGE_SHA = "35cc28163c6e0c766418d06f60c22840de2f1b9d8a1b79afc398cb37182d015f"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=Path, required=True, help="Pinned rom_abi_probe.py")
    parser.add_argument("--out", type=Path, required=True, help="New derived-evidence directory")
    parser.add_argument("--inventory", action="store_true", help="Save bounded /lib/modules name/size/type metadata before selected files")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--module", choices=MODULES, action="append")
    selection.add_argument("--all-modules", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.environ.get("GITHUB_ACTIONS") != "true" or not __debug__:
        raise RuntimeError("Only run the real firmware intake in the reviewed cloud job")
    if not re.fullmatch(r"[0-9a-f]{40}", os.environ.get("GITHUB_SHA", "")):
        raise ValueError("A real cloud source commit is required")
    # This process never allocates a vendor-sized buffer or mounts an image.
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    args.out.mkdir(exist_ok=False)
    report = {"status": "IN_PROGRESS", "source_commit": os.environ["GITHUB_SHA"], "official_url": URL,
              "firmware": "V12.5.7.0.RKPMIXM Android11 chopin global", "stage": "dependencies",
              "reference_prior_boot_sha256": BOOT_SHA, "reference_prior_image_sha256": IMAGE_SHA,
              "prior_image_reextracted_this_run": False, "modules": [],
              "limits": {"reserved_HTTP_body_bytes": MAX_NETWORK, "single_HTTP_range_bytes": MAX_RANGE,
                         "parallel_range_workers": 4, "wall_alarm_seconds": 900, "outer_job_timeout_minutes": 20,
                         "address_space_bytes": 768 * 1024 * 1024,
                         "operation_packed_bytes": 16 * 1024 * 1024, "operation_raw_bytes": 32 * 1024 * 1024,
                         "total_FS_read_bytes": 64 * 1024 * 1024, "module_bytes": 16 * 1024 * 1024,
                         "selected_module_bytes": 32 * 1024 * 1024},
              "flashed": False, "hardware_tested": False, "compatibility_claim": False,
              "raw_OEM_image_or_module_written": False, "full_ROM_hash_verified": False,
              "full_payload_ZIP_CRC_verified": False, "full_vendor_partition_hash_verified": False,
              "payload_signature_authentication_verified": False}
    remote = partition = None

    def save(stage=None):
        if stage:
            report["stage"] = stage
        if remote is not None:
            report["transport"] = {"ROM_bytes": remote.total, "reserved_HTTP_body_bytes": remote.reserved_bytes,
                                   "received_HTTP_body_bytes": remote.body_received, "requests": remote.range_requests,
                                   "strong_ETag_present": bool(remote.strong_etag), "HTTP_redirects_allowed": False}
        if partition is not None:
            report["payload"] = {"manifest_sha256": partition.manifest_sha,
                "vendor_partition_bytes": partition.size, "vendor_descriptor_sha256_unverified": partition.expected_sha.hex(),
                "manifest_boot_descriptor_matches_prior_verified_boot": True,
                "total_vendor_operations": len(partition.operations), "operations_read": len(partition.proof),
                "compressed_operation_SHA_checks": sum(item["compressed_sha_verified"] for item in partition.proof.values()),
                "operations": list(partition.proof.values()), "FS_logical_bytes": partition.logical_bytes,
                "FS_read_calls": partition.read_calls}
        report["modules_not_completed"] = [name for name in report.get("selected_modules", [])
                                           if name not in {row["file"] for row in report["modules"]}]
        (args.out / "module-imports.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"stage": report["stage"], "status": report["status"],
                          "received_bytes": remote.body_received if remote else 0}), flush=True)

    def timeout(_signal, _frame):
        raise TimeoutError("900-second bounded intake deadline reached")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(900)
    try:
        expected_versions = {"dissect.extfs": "3.15", "dissect.cstruct": "4.7", "dissect.util": "3.24"}
        report["dependencies"] = {name: importlib.metadata.version(name) for name in expected_versions}
        if report["dependencies"] != expected_versions:
            raise ValueError("Dependency versions differ from the reviewed pure-Python wheel lock")
        namespace = reviewed_definitions(args.helper)
        report["reviewed_ROM_helper_sha256"] = HELPER_SHA
        selected = list(MODULES if args.all_modules else args.module or ("conninfra.ko", "met.ko"))
        if len(set(selected)) != len(selected):
            raise ValueError("Repeated module requests are rejected")
        report["selected_modules"] = selected
        save("open_bounded_official_ROM")
        remote = remote_class(namespace["RemoteZip"])(URL)
        with zipfile.ZipFile(remote) as archive:
            if archive.namelist().count("payload.bin") != 1:
                raise ValueError("A unique payload.bin member is required")
            save("read_manifest_only")
            partition = PayloadPartition(remote, archive.getinfo("payload.bin"), namespace["protobuf"], BOOT_SHA)
            save("read_selected_ext4_module_files")
            def module_received(row):
                report["modules"].append(row)
                save("derived_module_" + row["file"])
            def inventory_received(snapshot):
                report["directory_inventory"] = snapshot
                save("derived_directory_inventory")
            report["modules"], report["filesystem"] = module_manifests(
                partition, selected, module_received, inventory_received if args.inventory else None)
        # Derived import values are the output, never OEM file contents.
        values = [row["imports"].get("module_layout") for row in report["modules"]]
        report["reference_module_layout"] = "2d3d4373"
        report["all_selected_module_layouts_match_prior_A11_boot"] = all(value == "2d3d4373" for value in values)
        report["status"] = "PASS_BOUNDED_VENDOR_MODULE_IMPORTS_ONLY"
        report["limitations"] = [
            "Each accessed compressed operation SHA is checked against the current manifest; that is not OEM signature authentication.",
            "Only visited operations are downloaded. Full vendor, payload CRC and ROM hashes are not checked.",
            "ExtFS is read-only with no journal replay; separate filesystem checksum validation is not claimed.",
            "Module CRC/import evidence does not establish Android11 boot, drivers or fourth-family kernel compatibility."]
        save("complete")
        return 0
    except Exception as error:
        report.update(status="BLOCKED_BOUNDED_INTAKE_NO_COMPATIBILITY_CLAIM", error=type(error).__name__ + ": " + str(error))
        save()
        return 2
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
