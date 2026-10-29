#!/usr/bin/env python3
"""Exercise real controller parsing/gates with an in-memory subprocess provider.

No adb/process is executed. The temporary fixture files live under --output's
parent, and are removed. Fake fixture hashes do not represent a built KPM.
"""
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import controller as c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    checks = 0
    for i in range(16):
        result = c.decode_result(str(c.BASE|i)+"\n")
        assert result["raw_return"] == c.BASE|i
        assert result["bitmap_is_null"] == bool(i & 1)
        assert result["app_strings_is_null"] == bool(i & 2)
        assert result["worker_is_idle"] == bool(i & 4)
        assert result["ever_configured_is_false"] == bool(i & 8)
        checks += 1
    for invalid in ["", "0", "-11", str(c.BASE+16), str(c.BASE-1), "1.0", "0x5052010f", str(c.BASE)+"\nextra"]:
        try:
            c.decode_result(invalid)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("accepted unknown result: "+invalid)
    module = b"memory-only-fixture-not-a-kpm"
    module_sha = hashlib.sha256(module).hexdigest()
    build = {"schema": 1, "image_sha256": c.IMAGE_SHA, "paired_kpimg_sha256": c.KPIMG_SHA,
             "source_commit": c.SOURCE, "module_name": c.NAME,
             "module_sha256": module_sha, "status": "PASS_CLOUD_COMPILE_AND_MEMORY_FIXTURES"}
    review = {"schema": 1, "image_sha256": c.IMAGE_SHA, "paired_kpimg_sha256": c.KPIMG_SHA,
              "source_commit": c.SOURCE, "module_name": c.NAME,
              "loaded_module_sha256": module_sha, "operator_reviewed_exact_boot_and_module_load": True,
              "boot_a_sha256": "a"*64, "boot_a_size": 134217728,
              "boot_id": "11111111-2222-4333-8444-555555555555",
              "device": "chopin", "slot_suffix": "_a", "sdk": "31"}
    assert c.validate_review(review, build, module) == module_sha
    checks += 1
    for key, bad in [("image_sha256", "0"*64), ("paired_kpimg_sha256", "0"*64),
                     ("source_commit", "0"*40), ("module_name", "other"),
                     ("operator_reviewed_exact_boot_and_module_load", False),
                     ("loaded_module_sha256", "0"*64), ("boot_a_size", 1),
                     ("boot_id", "not-a-boot-id"), ("device", "other"),
                     ("slot_suffix", "_b"), ("sdk", "33")]:
        changed = {**review, key: bad}
        try:
            c.validate_review(changed, build, module)
        except (AssertionError, ValueError):
            checks += 1
        else:
            raise AssertionError("accepted incompatible review: "+key)
    with tempfile.TemporaryDirectory(prefix="observer-memory-only-", dir=a.output.parent) as tmp:
        p = Path(tmp)
        (p/"review.json").write_text(json.dumps(review), encoding="utf-8")
        (p/"build.json").write_text(json.dumps(build), encoding="utf-8")
        (p/"module.kpm").write_bytes(module)
        commands = []
        answers = {"id -u": "0", "getprop ro.product.device": "chopin",
                   "getprop ro.boot.slot_suffix": "_a", "getprop ro.build.version.sdk": "31",
                   "cat /proc/sys/kernel/random/boot_id": review["boot_id"],
                   "blockdev --getsize64 /dev/block/by-name/boot_a": "134217728",
                   "sha256sum /dev/block/by-name/boot_a": review["boot_a_sha256"]+"  /dev/block/by-name/boot_a",
                   "/data/adb/ksud kpm info "+c.NAME: "fixture module info",
                   "/data/adb/ksud kpm control "+c.NAME+" snapshot": str(c.BASE|15)}

        def fake_run(argv, **kwargs):
            assert argv[:6] == ["NO_ADB_EXECUTED", "-s", "FIXTURE_NO_DEVICE", "shell", "su", "-c"]
            assert kwargs["timeout"] == 45
            command = shlex.split(argv[6])
            assert len(command) == 1 and command[0] in answers, "unexpected device command"
            commands.append(command[0])
            return subprocess.CompletedProcess(argv, 0, answers[command[0]]+"\n", "")

        argv = ["controller.py", "--adb", "NO_ADB_EXECUTED", "--serial", "FIXTURE_NO_DEVICE",
                "--ksud", "/data/adb/ksud", "--review", str(p/"review.json"),
                "--build-evidence", str(p/"build.json"), "--module", str(p/"module.kpm"),
                "--run-id", "memory_fixture", "--output", str(p/"success.json")]
        with patch.object(sys, "argv", argv), patch.object(c.subprocess, "run", fake_run):
            c.main()
        result = json.loads((p/"success.json").read_text(encoding="utf-8"))
        assert result["status"] == "PASS_SCOPED_READONLY_SNAPSHOT" and len(commands) == 16
        assert result["writes_or_config_updates"] == []
        checks += 1
        commands.clear()
        answers["getprop ro.boot.slot_suffix"] = "_b"
        argv[-1] = str(p/"mismatch.json")
        with patch.object(sys, "argv", argv), patch.object(c.subprocess, "run", fake_run):
            try:
                c.main()
            except AssertionError:
                pass
            else:
                raise AssertionError("accepted wrong device slot")
        result = json.loads((p/"mismatch.json").read_text(encoding="utf-8"))
        assert result["status"] == "FAIL"
        assert not any(" kpm control " in x for x in commands)
        checks += 1
    a.output.write_text(json.dumps({"status": "PASS_MEMORY_ONLY_PYTHON", "checks": checks,
                                  "real_processes_or_devices_executed": False}, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
