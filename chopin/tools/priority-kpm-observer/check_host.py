#!/usr/bin/env python3
"""Linux CI only: compile and execute real C core/wrapper with memory providers."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kp-dir", type=Path, required=True)
    ap.add_argument("--cc", default="gcc")
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    a.output.mkdir(parents=True, exist_ok=True)
    pin = "a3965c6e137e46b2c94a69eeb5a7e4696a3abbb0"
    if subprocess.check_output(["git", "-C", str(a.kp_dir), "rev-parse", "HEAD"], text=True).strip() != pin:
        raise ValueError("wrong pinned KP header revision")
    for name in ["kernel/include/kpmodule.h", "kernel/include/kallsyms.h", "kernel/patch/include/uapi/scdefs.h"]:
        expected = subprocess.check_output(["git", "-C", str(a.kp_dir), "show", pin+":"+name])
        if (a.kp_dir/name).read_bytes() != expected:
            raise ValueError("modified pinned header: "+name)
    binary = a.output.resolve()/"memory-fixture"
    flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-UNDEBUG",
             "-fsanitize=undefined,address", "-fno-omit-frame-pointer",
             "-I"+str(here/"tests/include"),
             "-I"+str(a.kp_dir.resolve()/"kernel/include"),
             "-I"+str(a.kp_dir.resolve()/"kernel/patch/include")]
    cmd = [a.cc, *flags, str(here/"tests/fixture.c"), "-o", str(binary)]
    result = {"status": "FAIL", "scope": "host memory only", "compile_command": cmd,
              "source_sha256": {n: hashlib.sha256((here/n).read_bytes()).hexdigest()
                                for n in ["priority_observer.c", "observer_core.h", "profile.h", "tests/fixture.c"]}}
    try:
        build = subprocess.run(cmd, text=True, capture_output=True)
        (a.output/"host-compile.log").write_text(build.stdout+build.stderr, encoding="utf-8")
        build.check_returncode()
        run = subprocess.run([str(binary)], text=True, capture_output=True)
        (a.output/"host-run.log").write_text(run.stdout+run.stderr, encoding="utf-8")
        run.check_returncode()
        result["case_result"] = json.loads(run.stdout)
        assert result["case_result"]["status"] == "PASS"
        result["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        result["status"] = "PASS"
    except Exception as e:
        result["error"] = str(e)
        raise
    finally:
        (a.output/"host-cases.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
