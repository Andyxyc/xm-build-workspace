#!/usr/bin/env python3
"""Cloud-only: MiCode R plus a recorded C prototype fix, then 434 known R imports.

This file is a reviewed proposal. It has not compiled a kernel locally. It
does not compose boot/AK3 or access a device. No config options are changed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

R = "2af31af37e12a338fddca780044f8b182c23ed9a"
CLANG = "b62936c20dfd8fabd680b8879e2aa0a3cc1b024a"
DEFCFG_SHA = "414f9454e7a177f22d9531987ff980bff2eea68c6b0858dabdf132ca0453d06d"
IMPORTS_SHA = "38010f415674d298937122c20a0d407a0aaa3accfc76dbd813f8ed6dc5416f43"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_logged(args, path, env):
    with path.open("w", encoding="utf-8") as log:
        log.write(json.dumps(args)+"\n"); log.flush()
        child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, errors="replace", env=env)
        for line in child.stdout:
            log.write(line); log.flush(); print(line, end="", flush=True)
        if child.wait():
            raise subprocess.CalledProcessError(child.returncode, args)


def main():
    if os.name != "posix" or not os.environ.get("GITHUB_ACTIONS"):
        raise SystemExit("Cloud CI only; do not compile on the Windows PC")
    if sys.flags.optimize:
        raise SystemExit("Assertions must stay enabled")
    workspace = Path(os.environ["WORKSPACE"]).resolve()
    kernel = workspace/"android-kernel"
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    imports = repo/"chopin/abi-profiles/android11-three-module-imports.json"
    output = Path(os.environ["GITHUB_WORKSPACE"])/"r-baseline-evidence"
    output.mkdir(parents=True, exist_ok=True)
    out = kernel/"out"
    report = {"status": "FAIL", "stage": "preflight", "kernel_source": R,
              "profile": "R_ANDROID11_NATIVE_UNPORTED_BASELINE",
              "stock_image_reference": "35cc28163c6e0c766418d06f60c22840de2f1b9d8a1b79afc398cb37182d015f",
              "compiler_is_stock_clang11": False, "root_susfs_kpm_integrated": False,
              "source_or_config_patches_applied": [], "flashed": False,
              "hardware_tested": False, "full_R_vendor_graph_verified": False}
    env = os.environ.copy()
    env["PATH"] = ":".join(str(workspace/x/"bin") for x in ["clang", "gcc-64", "gcc-32"])+":"+env["PATH"]
    env["LD_LIBRARY_PATH"] = str(workspace/"clang/lib64")+":"+env.get("LD_LIBRARY_PATH", "")
    try:
        head = subprocess.check_output(["git", "-C", str(kernel), "rev-parse", "HEAD"], text=True).strip()
        assert head == R
        assert not subprocess.check_output(["git", "-C", str(kernel), "status", "--porcelain"])
        # The prior real clang13 build stopped here with -Wstrict-prototypes.
        # Only spell the existing no-argument declaration explicitly; retain its body.
        dsi = kernel/"drivers/gpu/drm/mediatek/mtk_dsi.c"
        assert sha(dsi) == "385067c365eee761f6d83832e538822e1b8ebe295e1f31b26c13fa010db40961"
        text = dsi.read_text(encoding="utf-8")
        old = "bool get_dsi_doze_state()\n"
        assert text.count(old) == 1
        dsi.write_text(text.replace(old, "bool get_dsi_doze_state(void)\n", 1), encoding="utf-8")
        assert sha(dsi) == "38385114e51f29efffa4c2b630e2ee38c531392832e479629612295a7452239c"
        report["profile"] = "R_ANDROID11_NATIVE_PLUS_EXPLICIT_VOID_COMPILER_FIX"
        report["source_or_config_patches_applied"] = [{"file": "drivers/gpu/drm/mediatek/mtk_dsi.c", "change": "get_dsi_doze_state() -> get_dsi_doze_state(void)", "config_changed": False}]
        assert subprocess.check_output(["git", "-C", str(workspace/"clang"), "rev-parse", "HEAD"], text=True).strip() == CLANG
        assert sha(kernel/"arch/arm64/configs/chopin_user_defconfig") == DEFCFG_SHA
        assert sha(imports) == IMPORTS_SHA
        intake = json.loads(imports.read_text(encoding="utf-8"))
        assert len(intake["unique_vmlinux_import_crc_expected"]) == 434
        assert intake["unique_vmlinux_import_crc_expected"]["module_layout"] == "2d3d4373"
        report["known_R_kernel_imports"] = 434
        report["imports_manifest_sha256"] = IMPORTS_SHA
        report["imports_scope"] = intake["scope"]
        loader = (kernel/"kernel/module.c").read_text(encoding="utf-8")
        assert "flags |= MODULE_INIT_IGNORE_" not in loader
        assert "check_modstruct_version(info, mod)" in loader and "same_magic(modmagic, vermagic, info->index.vers)" in loader
        compiler = subprocess.check_output([str(workspace/"clang/bin/clang"), "--version"], text=True)
        assert "13.0.0" in compiler
        (output/"actual-compiler.txt").write_text(compiler, encoding="utf-8")
        report["actual_compiler"] = compiler
        report["clang_source_commit"] = CLANG
        tools = [workspace/"clang/bin"/n for n in ["clang", "ld.lld", "llvm-ar", "llvm-nm", "llvm-objcopy"]]
        # These AOSP snapshots provide binutils; the compiler is the pinned clang above.
        tools += [workspace/"gcc-64/bin"/('aarch64-linux-android-'+name) for name in ['as', 'ld']]
        tools += [workspace/"gcc-32/bin"/('arm-linux-androideabi-'+name) for name in ['as', 'ld']]
        report["tool_binary_sha256"] = {str(p.relative_to(workspace)): sha(p) for p in tools}
        for p in workspace.glob("gcc-*.tar.gz"):
            report.setdefault("gcc_archive_sha256", {})[p.name] = sha(p)
        base = ["make", "-C", str(kernel), "O=out", "ARCH=arm64", "CC=ccache "+str(workspace/"clang/bin/clang"),
                "LD=ld.lld", "AR=llvm-ar", "NM=llvm-nm", "STRIP=llvm-strip", "OBJCOPY=llvm-objcopy",
                "OBJDUMP=llvm-objdump", "CLANG_TRIPLE=aarch64-linux-gnu-",
                "CROSS_COMPILE="+str(workspace/"gcc-64/bin/aarch64-linux-android-"),
                "CROSS_COMPILE_ARM32="+str(workspace/"gcc-32/bin/arm-linux-androideabi-"), "KBUILD_SYMTYPES=1"]
        report["stage"] = "native_defconfig"
        run_logged(base+["chopin_user_defconfig"], output/"defconfig.log", env)
        cfg = (out/".config").read_text(encoding="utf-8")
        for line in ["CONFIG_MODULES=y", "CONFIG_MODVERSIONS=y", "CONFIG_MODULE_UNLOAD=y"]:
            assert line in cfg.splitlines(), "native R config lacks "+line
        assert "CONFIG_MODULE_FORCE_LOAD=y" not in cfg.splitlines()
        assert 'CONFIG_MTK_GPU_VERSION="mali valhall r25p0"' in cfg.splitlines()
        assert not any(x in cfg.splitlines() for x in ["CONFIG_KSU=y", "CONFIG_KSU_SUSFS=y", "CONFIG_KPM=y"])
        report["stage"] = "native_compile"
        # The previous real build hit a missing vendor-generated cust.dtsi in
        # the default DTB target. ABI investigation needs the actual Image and
        # modules, not an invented device tree; retain the DTB limitation.
        report["build_targets"] = ["Image", "modules"]
        report["device_tree_status"] = "NOT_BUILT_MISSING_VENDOR_GENERATED_k6891v1_64_cust_dtsi"
        run_logged(base+["-j2", "Image", "modules"], output/"compile.log", env)
        report["stage"] = "R_known_imports_gate"
        checker = here.parent/"verify_vendor_imports.py"
        run_logged([sys.executable, str(checker), str(out/"Module.symvers"), str(imports),
                    str(output/"R-three-module-434-imports.json")], output/"imports-gate.log", env)
        assert sha(kernel/"arch/arm64/configs/chopin_user_defconfig") == DEFCFG_SHA
        report["status"] = "PASS_NATIVE_R_COMPILE_AND_434_KERNEL_IMPORTS_ONLY"
        report["stage"] = "complete"
        report["acceptance_boundary"] = "three selected R modules' known kernel imports only; unresolved peers, complete vendor graph, binary/layout independence and device tests remain"
    except Exception as e:
        report["error"] = type(e).__name__+": "+str(e)
        raise
    finally:
        for name in [".config", "Module.symvers", "System.map", "include/generated/compile.h", "include/generated/utsrelease.h",
                     "arch/arm64/boot/Image", "arch/arm64/boot/Image.gz-dtb", "arch/arm64/boot/dts/mediatek/chopin.dtb",
                     "kernel/module.symtypes", "kernel/fork.symtypes", "mm/memory.symtypes", "mm/mmap.symtypes",
                     "arch/arm64/kernel/cpufeature.symtypes"]:
            src = out/name
            if src.is_file():
                dst = output/"native-output"/name
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
                report.setdefault("output_sha256", {})[name] = sha(src)
        if imports.is_file():
            shutil.copyfile(imports, output/"R-imports-source-manifest.json")
        (output/"baseline-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
