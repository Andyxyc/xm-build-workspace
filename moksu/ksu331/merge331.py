#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Three-way port 7kimisu v2.29 modifications onto official KernelSU v3.3.1.

Base  = official v3.3.0 (Aug 28)
Ours  = 7kimisu v2.29  (Sep 30)
Other = official v3.3.1 (Oct 12)
All root, userspace, and manager source paths are merged; no boot writes occur.
Unresolved conflicts halt all release builds (never silently drop a feature).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SKIP_PARTS = {".git", ".gradle", ".cxx", "build", "target", "node_modules", "dist"}
SRC_PREFIX = "manager/app/src/main/java/com/sevenk/core/"
DEST_PREFIX = "manager/app/src/main/java/me/weishu/kernelsu/"
SECTIONS = ("manager/", "kernel/", "userspace/", "uapi/", "Cargo.toml", "Cargo.lock", "manager/build.gradle.kts")
TEXT_EXT = {".kt", ".java", ".cpp", ".cc", ".c", ".h", ".hpp", ".rs",
            ".py", ".sh", ".bash", ".kts", ".toml", ".lock", ".xml",
            ".json", ".js", ".html", ".css", ".md", ".gradle", ".properties",
            ".pro", ".txt", ".map", ".mk", ".s", ".S"}
TEXT_NAMES = {"Cargo.lock", "Cargo.toml", "Kbuild", "Kconfig", "Makefile", "gradlew"}
TOP_FILE = {"Cargo.toml", "Cargo.lock"}

def allowed(relative):
    p = Path(relative)
    if any(part in SKIP_PARTS for part in p.parts): return False
    if relative in TOP_FILE: return True
    return relative.startswith(("manager/", "kernel/", "userspace/", "uapi/"))

def mapped(relative):
    if relative.startswith(SRC_PREFIX):
        return DEST_PREFIX + relative[len(SRC_PREFIX):]
    return relative

def normalized(relative, raw):
    # Only normalize package/namespace identity. All 7kimisu behaviors and names
    # are intentionally retained for the semantic merge.
    if not is_text(relative, raw): return raw
    try: s = raw.decode("utf-8")
    except UnicodeDecodeError: return raw
    s = s.replace("com.sevenk.core", "me.weishu.kernelsu")
    s = s.replace("com/sevenk/core", "me/weishu/kernelsu")
    return s.encode("utf-8")

def is_text(relative, raw):
    name = Path(relative).name
    if name not in TEXT_NAMES and Path(relative).suffix not in TEXT_EXT:
        return False
    return b"\x00" not in raw

def sha(data):
    return hashlib.sha256(data).hexdigest()

def filemap(root):
    files = {}
    for p in root.rglob("*"):
        if p.is_symlink():
            continue
        if not p.is_file(): continue
        rel = p.relative_to(root).as_posix()
        if allowed(rel): files[rel] = p
    return files

def merge_bytes(ours, base, theirs):
    with tempfile.TemporaryDirectory(prefix="moksu331_merge_") as td:
        args = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(td) / name
            path.write_bytes(data)
            args.append(str(path))
        p = subprocess.run(
            ["git", "merge-file", "-p", "--diff3",
             "-L", "7kimisu-v2.29", "-L", "KernelSU-v3.3.0",
             "-L", "KernelSU-v3.3.1", *args],
            capture_output=True, check=False
        )
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")

def apply(base_dir, fork_dir, latest_dir, report_dest):
    base_dir = Path(base_dir).resolve(strict=True)
    fork_dir = Path(fork_dir).resolve(strict=True)
    latest_dir = Path(latest_dir).resolve(strict=True)
    out = Path(report_dest).resolve()
    old = filemap(fork_dir)
    base = filemap(base_dir)
    theirs = filemap(latest_dir)
    summary = {
      "official_release": "3.3.1",
      "official_commit": "0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d",
      "merge_base_release": "3.3.0",
      "merge_base_commit": "932014ab5b2c9b74a3d11e2ec4d17dd10fc9442e",
      "fork_release": "7kimisu v2.29",
      "fork_commit": "0246ca0f16ea2e3a6af030643bb6f74262e0e26c",
      "counts": {},
      "conflicts": [],
      "copied_fork_only": [],
      "merged": [],
      "binary_conflicts": [],
      "upstream_only_kept": [],
      "never_tested_on_device": True,
    }
    stats = dict(unchanged=0, fork_added=0, fork_merged=0,
                 base_only_fork_deleted=0, upstream_unchanged=0, conflicted=0)
    for oldrel, oldfile in sorted(old.items()):
        rel = mapped(oldrel)
        baserel = rel
        basefile = base.get(baserel)
        newfile = latest_dir / rel
        wasfile = theirs.get(rel)
        ourdata = normalized(oldrel, oldfile.read_bytes())
        basedata = basefile.read_bytes() if basefile else None
        newdata = wasfile.read_bytes() if wasfile else None
        if oldrel.startswith("manager/app/src/main/java/com/sevenk/core"):
            # Forked Java namespace was rewritten above to the official namespace.
            pass
        if basefile is None:
            if newdata is None:
                newfile.parent.mkdir(parents=True, exist_ok=True)
                newfile.write_bytes(ourdata)
                stats["fork_added"] += 1
                summary["copied_fork_only"].append(rel)
            elif newdata != ourdata:
                summary["conflicts"].append("Unrelated old/new file: " + rel)
                stats["conflicted"] += 1
            continue
        if basedata == ourdata:
            stats["unchanged"] += 1
            continue
        if newdata == ourdata:
            stats["unchanged"] += 1
            continue
        if newdata == basedata or newdata is None:
            if newdata is None:
                summary["conflicts"].append("Official removed file changed by fork: " + rel)
                stats["conflicted"] += 1
                continue
            newfile.write_bytes(ourdata)
            stats["fork_merged"] += 1
            summary["merged"].append(rel)
            continue
        if not is_text(rel, ourdata) or not is_text(rel, basedata) or not is_text(rel, newdata):
            summary["binary_conflicts"].append(rel)
            stats["conflicted"] += 1
            continue
        rc, contents, err = merge_bytes(ourdata, basedata, newdata)
        if rc != 0 or b"<<<<<<<" in contents:
            summary["conflicts"].append(rel + (" => " + err if err else ""))
            stats["conflicted"] += 1
            continue
        newfile.write_bytes(contents)
        stats["fork_merged"] += 1
        summary["merged"].append(rel)
    summary["counts"] = stats
    summary["file_count_in_fork"] = len(old)
    summary["file_count_in_base"] = len(base)
    summary["file_count_in_new"] = len(theirs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("MOKSU331_PORT_COUNTS", json.dumps(stats, ensure_ascii=False))
    print("MOKSU331_CONFLICT_COUNT", len(summary["conflicts"]), len(summary["binary_conflicts"]))
    for c in summary["conflicts"][:120]: print("MOKSU331_CONFLICT", c)
    for c in summary["binary_conflicts"][:120]: print("MOKSU331_BINARY_CONFLICT", c)
    if stats["conflicted"]:
        raise SystemExit("Migration halted: unresolved conflicts; consult report")
    return summary

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("fork")
    ap.add_argument("latest")
    ap.add_argument("report")
    args = ap.parse_args()
    apply(args.base, args.fork, args.latest, args.report)
