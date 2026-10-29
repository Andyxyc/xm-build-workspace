#!/usr/bin/env python3
"""Cloud-only module build. Does not rebuild kpimg/kernel or access a device."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from make_profile import IMAGE_SHA, KPIMG_SHA, SOURCE

if sys.flags.optimize:
    raise RuntimeError("Assertions must be enabled; refusing an optimized Python run")

PIN = "a3965c6e137e46b2c94a69eeb5a7e4696a3abbb0"
HEADERS = ["kernel/include/kpmodule.h", "kernel/include/kallsyms.h",
           "kernel/include/compiler.h", "kernel/include/ktypes.h",
           "kernel/patch/include/uapi/scdefs.h"]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kp-dir", type=Path, required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    a.output.mkdir(parents=True, exist_ok=True)
    out = a.output.resolve()
    evidence = {"schema": 1, "status": "FAIL", "image_sha256": IMAGE_SHA,
                "paired_kpimg_sha256": KPIMG_SHA, "source_commit": SOURCE,
                "module_name": "chopin-priority-ro-r18", "pinned_headers_commit": PIN}
    try:
        head = subprocess.check_output(["git", "-C", str(a.kp_dir), "rev-parse", "HEAD"], text=True).strip()
        assert head == PIN, "do not build against a different local HEAD"
        subprocess.run(["git", "-C", str(a.kp_dir), "diff", "--exit-code", PIN, "--"], check=True,
                       stdout=subprocess.DEVNULL)
        for options in [["--others", "--exclude-standard"], ["--others", "--ignored", "--exclude-standard"]]:
            assert not subprocess.check_output(["git", "-C", str(a.kp_dir), "ls-files", *options]), "unexpected untracked KP header/build input"
        header_hashes = {}
        for name in HEADERS:
            wanted = subprocess.check_output(["git", "-C", str(a.kp_dir), "show", PIN+":"+name])
            actual = (a.kp_dir/name).read_bytes()
            assert actual == wanted, "modified pinned header: "+name
            header_hashes[name] = sha(actual)
        evidence["actual_header_sha256"] = header_hashes
        profile = json.loads((here/"profile.json").read_text(encoding="utf-8"))
        assert profile["image_sha256"] == IMAGE_SHA and profile["paired_kpimg_sha256"] == KPIMG_SHA
        assert profile["source_commit"] == SOURCE
        assert sha((here/"profile.h").read_bytes()) == profile["generated_header_sha256"]
        host = json.loads((out/"host-cases.json").read_text(encoding="utf-8"))
        assert host["status"] == "PASS" and host["case_result"]["status"] == "PASS"
        for n, wanted in host["source_sha256"].items():
            assert sha((here/n).read_bytes()) == wanted, "source changed after C host cases"
        assert json.loads((out/"controller-cases.json").read_text(encoding="utf-8"))["status"] == "PASS_MEMORY_ONLY_PYTHON"
        evidence["module_build_repository_commit"] = subprocess.check_output(
            ["git", "-C", str(here), "rev-parse", "HEAD"], text=True).strip()
        cc, ld, readelf, objdump = (a.prefix+x for x in ["gcc", "ld", "readelf", "objdump"])
        compiler = subprocess.check_output([cc, "--version"], text=True)
        assert "12.2.Rel1" in compiler and "12.2.1" in compiler, "wrong compiler family"
        (out/"compiler.txt").write_text(compiler, encoding="utf-8")
        dirs = ["include", "patch/include", "linux/include", "linux/arch/arm64/include", "linux/tools/arch/arm64/include"]
        flags = ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-nostdinc", "-ffreestanding",
                 "-fno-builtin", "-fno-pic", "-fno-pie", "-fno-stack-protector", "-mno-outline-atomics",
                 "-mgeneral-regs-only", "-ffixed-x18", "-fno-tree-loop-distribute-patterns",
                 "-fno-asynchronous-unwind-tables", "-fno-unwind-tables"]
        flags += ["-I"+str(a.kp_dir.resolve()/"kernel"/x) for x in dirs]
        cmd = [cc, *flags, "-c", str(here/"priority_observer.c"), "-o", str(out/"priority_observer.o")]
        evidence["compile_command"] = cmd
        q = subprocess.run(cmd, text=True, capture_output=True)
        (out/"module-compile.log").write_text(q.stdout+q.stderr, encoding="utf-8")
        q.check_returncode()
        module = out/"chopin-priority-ro-r18.kpm"
        subprocess.run([ld, "-r", str(out/"priority_observer.o"), "-o", str(module)], check=True)
        elf = subprocess.check_output([readelf, "-h", "-SW", "-sW", "-rW", str(module)], text=True)
        dis = subprocess.check_output([objdump, "-dr", str(module)], text=True)
        (out/"module-elf.txt").write_text(elf, encoding="utf-8")
        (out/"module-disassembly.txt").write_text(dis, encoding="utf-8")
        assert "AArch64" in elf and "REL (Relocatable file)" in elf
        for sec in [".kpm.info", ".kpm.init", ".kpm.ctl0", ".kpm.exit"]:
            assert sec in elf, "missing module registration section"
        undefined = set()
        for line in elf.splitlines():
            fields = line.split()
            if len(fields) >= 8 and fields[0].rstrip(":").isdigit() and fields[6] == "UND":
                undefined.add(fields[7])
        assert undefined == {"kallsyms_lookup_name", "kallsyms_on_each_symbol"}, undefined
        # Ensure the actual ARM64 reader uses inline acquire operations, no helpers.
        assert re.search(r"\bldar\s+x", dis) and re.search(r"\bldar\s+w", dis)
        assert re.search(r"\bldarb\s+w", dis)
        assert not re.search(r"__atomic|__aarch64|copy_to_user|hook_wrap|mutex_|synchronize_rcu", elf)
        evidence["module_sha256"] = sha(module.read_bytes())
        evidence["profile_header_sha256"] = sha((here/"profile.h").read_bytes())
        evidence["status"] = "PASS_CLOUD_COMPILE_AND_MEMORY_FIXTURES"
        evidence["device_tested"] = False
        evidence["host_fixture_sha256"] = sha((here/"tests/fixture.c").read_bytes())
    except Exception as e:
        evidence["error"] = type(e).__name__+": "+str(e)
        raise
    finally:
        (out/"build-evidence.json").write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
