"""Cloud-only APK build using the runner's existing Android SDK and NDK."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
out = Path("priority-observer-out")
out.mkdir(exist_ok=False)
sdk_value = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
assert sdk_value, "The cloud runner must supply its existing SDK path"
sdk = Path(sdk_value).resolve()
commit = os.environ.get("GITHUB_SHA", "")
assert re.fullmatch(r"[0-9a-f]{40}", commit), "A real source commit is required"
ns = "{http://schemas.android.com/apk/res/android}"
manifest = ET.parse(root / "AndroidManifest.xml").getroot()
assert manifest.attrib["package"] == "cn.chopin.acceptanceprobe4"
assert not manifest.findall("uses-permission") and not manifest.findall("uses-permission-sdk-23")
assert [node.attrib[ns+"name"] for node in manifest.findall("queries/package")] == [
    "cn.chopin.acceptanceprobe2", "cn.chopin.acceptanceprobe3"]
assert not manifest.findall("application/service") and not manifest.findall("application/receiver")


def version(path):
    return tuple(int(value) for value in re.findall(r"\d+", path.name))


def run(parts, capture=False):
    return subprocess.run(list(map(str, parts)), check=True, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


tools = max((path for path in (sdk / "build-tools").iterdir()
             if all((path / name).is_file() for name in ("aapt2", "d8", "zipalign", "apksigner"))), key=version)
platform = next((sdk / "platforms" / ("android-"+str(api)) / "android.jar"
                 for api in (35, 34, 33, 36) if (sdk / "platforms" / ("android-"+str(api)) / "android.jar").is_file()), None)
assert platform, "A preinstalled public Android platform is required"
ndk = max((path for path in (sdk / "ndk").glob("*")
           if (path / "toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang").is_file()), key=version)
llvm = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
compiler = llvm / "aarch64-linux-android29-clang"
native = out / "libchopin_priority.so"
run([compiler, "-std=c11", "-D_GNU_SOURCE", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
     "-fvisibility=hidden", "-fstack-protector-strong", "-Wl,-z,relro,-z,now,--no-undefined",
     root / "native_priority.c", "-o", native])
data = native.read_bytes()
assert data[:6] == b"\x7fELF\x02\x01" and int.from_bytes(data[18:20], "little") == 183
disassembly = run([llvm / "llvm-objdump", "-d", native], capture=True).stdout
symbols = run([llvm / "llvm-readelf", "--dyn-syms", "--wide", native], capture=True).stdout
assert re.search(r"\bsvc\b", disassembly)
assert "Java_cn_chopin_priorityprobe_NativePriority_observe" in symbols
assert not re.search(r"\b(?:setpriority|sched_set\w*|socket|connect|exec\w*|system|popen|fork)\b", symbols)
(out / "native-disassembly.txt").write_text(disassembly)
(out / "native-symbols.txt").write_text(symbols)
with tempfile.TemporaryDirectory(prefix="chopin-priority-build-") as temporary:
    work = Path(temporary)
    host = work / "semantics-fixture"
    run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", root / "semantics_fixture.c", "-o", host])
    semantics = json.loads(run([host], capture=True).stdout)
    assert semantics["cases"] == 4140 and semantics["actual_svc_executed"] is False
    (out / "semantics-fixture.json").write_text(json.dumps(semantics, indent=2)+"\n")
    test_classes = work / "uid-test-classes"
    test_classes.mkdir()
    run(["javac", "-source", "8", "-target", "8", "-d", test_classes,
         root / "TargetUids.java", root / "TargetUidsFixture.java"])
    uid_tests = json.loads(run(["java", "-cp", test_classes, "cn.chopin.priorityprobe.TargetUidsFixture"], capture=True).stdout)
    assert uid_tests["cases"] == 14 and uid_tests["android_package_manager_tested"] is False
    (out / "uid-gate-fixture.json").write_text(json.dumps(uid_tests, indent=2)+"\n")
    controller = subprocess.run(
        ["python3", "-B", "-m", "unittest", "-v", "test_controller"], cwd=root,
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (out / "controller-fixture.txt").write_text(controller.stdout)
    classes = work / "classes"
    classes.mkdir()
    dex = work / "dex"
    dex.mkdir()
    info = work / "BuildInfo.java"
    info.write_text("package cn.chopin.priorityprobe; public final class BuildInfo {\n"
                    "public static final String SOURCE_COMMIT="+json.dumps(commit)+";\n"
                    "public static final String NATIVE_SHA256="+json.dumps(sha(native))+";\n}\n")
    run(["javac", "-source", "8", "-target", "8", "-bootclasspath", platform, "-d", classes,
         root / "TargetUids.java", root / "NativePriority.java", root / "PriorityActivity.java", info])
    run([tools / "d8", "--lib", platform, "--min-api", "29", "--output", dex, *classes.rglob("*.class")])
    unsigned = work / "unsigned.apk"
    aligned = work / "aligned.apk"
    run([tools / "aapt2", "link", "-I", platform, "--manifest", root / "AndroidManifest.xml",
         "--min-sdk-version", "29", "--target-sdk-version", "32", "-o", unsigned])
    with zipfile.ZipFile(unsigned, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(dex / "classes.dex", "classes.dex")
        archive.write(native, "lib/arm64-v8a/libchopin_priority.so")
    run([tools / "zipalign", "-p", "4", unsigned, aligned])
    key = work / "ephemeral-test-key.jks"
    run(["keytool", "-genkeypair", "-keystore", key, "-storepass", "android", "-keypass", "android",
         "-alias", "probe", "-keyalg", "RSA", "-keysize", "2048", "-validity", "3650",
         "-dname", "CN=Chopin Priority Observer Test Fixture"], capture=True)
    apk = out / "Chopin-Priority-Observer-App4.apk"
    run([tools / "apksigner", "sign", "--ks", key, "--ks-key-alias", "probe", "--ks-pass", "pass:android",
         "--v2-signing-enabled", "true", "--v3-signing-enabled", "true", "--out", apk, aligned])
    signature = run([tools / "apksigner", "verify", "--min-sdk-version", "29", "--max-sdk-version", "35",
                     "--verbose", "--print-certs", apk], capture=True).stdout
    # ApkVerifier skips v2 on API >=28 once it finds v3. Check v2 separately.
    signature_v2 = run([tools / "apksigner", "verify", "--min-sdk-version", "24", "--max-sdk-version", "27",
                        "--verbose", "--print-certs", apk], capture=True).stdout
    permissions = run([tools / "aapt2", "dump", "permissions", apk], capture=True).stdout
    badging = run([tools / "aapt2", "dump", "badging", apk], capture=True).stdout
    (out / "signature.txt").write_text(signature)
    (out / "signature-v2-api24-27.txt").write_text(signature_v2)
    (out / "permissions.txt").write_text(permissions)
    (out / "badging.txt").write_text(badging)
    assert "Verified using v3 scheme (APK Signature Scheme v3): true" in signature, signature
    assert "Verified using v2 scheme (APK Signature Scheme v2): true" in signature_v2, signature_v2
    assert "uses-permission:" not in permissions and "package: name='cn.chopin.acceptanceprobe4'" in badging
record = dict(status="PASS_CLOUD_BUILD_SIGNATURE_PERMISSION_AND_OFFLINE_FIXTURES_ONLY", source_commit=commit,
    source_sha256={path.name:sha(path) for path in sorted(root.iterdir()) if path.is_file()},
    apk_sha256=sha(apk), native_sha256=sha(native), native_bytes=native.stat().st_size,
    compiler=run([compiler,"--version"],capture=True).stdout, ndk_version=ndk.name,
    sdk_platform=platform.parent.name, build_tools=tools.name,
    permissions_requested=[], fixed_target_packages=["cn.chopin.acceptanceprobe2","cn.chopin.acceptanceprobe3"],
    raw_decoder_host_cases=4140, uid_gate_host_cases=14, root_requested=False, scheduling_writes=False,
    network_permission=False, apk_runtime_executed=False, real_android_pm_verified=False,
    real_arm64_svc_executed=False, priority_filter_effect_verified=False,
    private_signing_key_uploaded=False, signature_note="Ephemeral test key; a later build may need uninstalling only App4")
record["signature_checks"] = {"v3_platform_range": [29, 35], "v2_platform_range": [24, 27],
    "app_manifest_min_sdk": 29, "older_platform_installability_claimed": False}
(out / "build-record.json").write_text(json.dumps(record, indent=2)+"\n")
print(json.dumps(record, indent=2))
