#!/usr/bin/env python3
"""Host-side, read/control only. Never loads, pushes, unloads or changes config.

Requires a separately reviewed exact-boot record and the already loaded module.
Module-file identity is a parent/operator attestation, not a kernel measurement.
"""
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from make_profile import IMAGE_SHA, KPIMG_SHA, SOURCE

if sys.flags.optimize:
    raise RuntimeError("Assertions must be enabled; refusing an optimized Python run")

NAME = "chopin-priority-ro-r18"
BASE = 0x50520100


def decode_result(stdout):
    value = stdout.strip()
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("official ksud did not return one positive decimal integer")
    number = int(value)
    if number & ~15 != BASE:
        raise ValueError("unknown observer protocol; do not interpret as empty")
    return {"protocol": 1, "raw_return": number,
            "bitmap_is_null": bool(number & 1), "app_strings_is_null": bool(number & 2),
            "worker_is_idle": bool(number & 4), "ever_configured_is_false": bool(number & 8)}


def validate_review(review, build, module_bytes):
    assert review["schema"] == build["schema"] == 1
    assert review["operator_reviewed_exact_boot_and_module_load"] is True
    for obj in [review, build]:
        assert obj["image_sha256"] == IMAGE_SHA and obj["paired_kpimg_sha256"] == KPIMG_SHA
        assert obj["source_commit"] == SOURCE and obj["module_name"] == NAME
    module_sha = hashlib.sha256(module_bytes).hexdigest()
    assert build["module_sha256"] == review["loaded_module_sha256"] == module_sha
    assert build["status"] == "PASS_CLOUD_COMPILE_AND_MEMORY_FIXTURES"
    assert re.fullmatch(r"[0-9a-f]{64}", review["boot_a_sha256"])
    assert review["boot_a_size"] == 134217728
    assert str(uuid.UUID(review["boot_id"])) == review["boot_id"]
    assert review["device"] == "chopin" and review["slot_suffix"] == "_a" and review["sdk"] == "31"
    return module_sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", type=Path, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--ksud", required=True, help="actual absolute official ksud path on device")
    ap.add_argument("--review", type=Path, required=True)
    ap.add_argument("--build-evidence", type=Path, required=True)
    ap.add_argument("--module", type=Path, required=True, help="local exact file already loaded by reviewed operator")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    assert re.fullmatch(r"[A-Za-z0-9:._-]+", a.serial)
    assert re.fullmatch(r"/[A-Za-z0-9._/-]+", a.ksud)
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", a.run_id)
    assert not a.output.exists(), "never overwrite a previous run"
    review = json.loads(a.review.read_text(encoding="utf-8"))
    build = json.loads(a.build_evidence.read_text(encoding="utf-8"))
    module_sha = validate_review(review, build, a.module.read_bytes())
    report = {"schema": 1, "status": "FAIL", "run_id": a.run_id,
              "started_unix": int(time.time()), "image_sha256": IMAGE_SHA,
              "paired_kpimg_sha256": KPIMG_SHA, "module_file_sha256": module_sha,
              "runtime_module_hash_scope": "operator-reviewed prior load; no runtime module hash API",
              "commands": [], "writes_or_config_updates": []}

    def root(command):
        argv = [str(a.adb), "-s", a.serial, "shell", "su", "-c", shlex.quote(command)]
        q = subprocess.run(argv, text=True, encoding="utf-8", capture_output=True, timeout=45)
        report["commands"].append({"command": command, "returncode": q.returncode,
                                   "stdout": q.stdout, "stderr": q.stderr})
        q.check_returncode()
        return q.stdout.strip()

    def boot_gate():
        assert root("id -u") == "0", "root not established"
        assert root("getprop ro.product.device") == "chopin"
        assert root("getprop ro.boot.slot_suffix") == "_a"
        assert root("getprop ro.build.version.sdk") == "31"
        assert root("cat /proc/sys/kernel/random/boot_id") == review["boot_id"]
        assert root("blockdev --getsize64 /dev/block/by-name/boot_a") == "134217728"
        sha = root("sha256sum /dev/block/by-name/boot_a").split()
        assert len(sha) == 2 and sha[0] == review["boot_a_sha256"], "boot readback mismatch"

    try:
        boot_gate()
        root(shlex.quote(a.ksud)+" kpm info "+NAME)
        value = root(shlex.quote(a.ksud)+" kpm control "+NAME+" snapshot")
        report["snapshot"] = decode_result(value)
        boot_gate()
        report["status"] = "PASS_SCOPED_READONLY_SNAPSHOT"
        report["limitations"] = [
            "Snapshot cannot exclude an intervening 0->1->0 writer or future writes.",
            "No UID/list/bitmap contents or persistent SUSFS config were read here.",
            "Four empty flags alone do not authorize replacing a user's list.",
            "Parent must serialize relevant UI/CLI writers and independently prove persistent config empty.",
            "Text anchors are selective identity checks, not a full running-kernel hash."]
    except Exception as e:
        report["error"] = type(e).__name__+": "+str(e)
        raise
    finally:
        report["finished_unix"] = int(time.time())
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
