"""Collect App4 observations. No install, root grant or scheduling/filter writes."""
import argparse
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

APP = "cn.chopin.acceptanceprobe4"
ACTIVITY = APP + "/cn.chopin.priorityprobe.PriorityActivity"
TARGETS = ("cn.chopin.acceptanceprobe2", "cn.chopin.acceptanceprobe3")


def parse_package_uid(text, package):
    if package not in TARGETS + (APP,):
        raise ValueError("Package is outside the fixed allowlist")
    matches = []
    for line in text.splitlines():
        if not line.strip():
            continue
        found = re.fullmatch(r"package:" + re.escape(package) + r"\s+uid:(\d+)", line.strip())
        if not found:
            raise ValueError("PackageManager returned an unexpected record")
        matches.append(int(found.group(1)))
    if len(matches) != 1 or matches[0] < 10000:
        raise ValueError("A unique ordinary-app PackageManager UID is required")
    return matches[0]


def canonical_uuid(text):
    return isinstance(text, str) and str(uuid.UUID(text)) == text


def validate_report(report, request_id, uids, build=None):
    if report.get("controller_run_id") != request_id:
        raise ValueError("Report belongs to a different controller run")
    if not canonical_uuid(report.get("run_id")) or report["run_id"] == request_id:
        raise ValueError("The app did not report its own fresh UUID")
    if report.get("observer_package") != APP or report.get("status") != "observed":
        raise ValueError("App4 did not complete the ordinary-app observation")
    if not re.fullmatch(r"[0-9a-f]{40}", report.get("source_commit", "")) or not re.fullmatch(
        r"[0-9a-f]{64}", report.get("native_sha256", "")
    ):
        raise ValueError("App4 is missing its compiled source identity")
    if build is not None and any(report.get(key) != build.get(key) for key in ("source_commit", "native_sha256")):
        raise ValueError("The installed observer differs from the selected cloud build")
    if report.get("root_requested") is not False or report.get("scheduling_writes") is not False:
        raise ValueError("Unexpected observer capability report")
    if report.get("network_used") is not False or report.get("package_manager_verified") is not True:
        raise ValueError("App4 did not verify its fixed package targets")
    if report.get("target_package_uids") != {package: uids[package] for package in TARGETS}:
        raise ValueError("App4's PackageManager UID pair differs from the controller")
    native = report.get("native", {})
    uid = uids[APP]
    if uid < 10000 or report.get("caller_uid_java") != uid:
        raise ValueError("Wrong Java caller UID")
    if any(native.get(key) != uid for key in ("caller_uid_direct", "caller_euid_direct", "caller_uid_libc")):
        raise ValueError("The native caller UID differs from PackageManager")
    if type(report.get("caller_pid_java")) is not int or report["caller_pid_java"] <= 1 or native.get("caller_pid") != report["caller_pid_java"]:
        raise ValueError("Java and native observations came from different processes")
    if native.get("ordinary_app_context") is not True or not re.fullmatch(
        r"u:r:untrusted_app(?:_\d+)?:s0(?::[A-Za-z0-9_,.:-]+)?", native.get("caller_context", "")
    ):
        raise ValueError("Not an ordinary untrusted-app SELinux context")
    if native.get("syscall_number") != 141 or native.get("queries_are_sequential") is not True:
        raise ValueError("Wrong native observation ABI")
    expected = [("self_uid", 2, uid), ("self_user_zero", 2, 0), ("self_process_zero", 0, 0),
                ("probe2", 2, uids[TARGETS[0]]), ("probe3", 2, uids[TARGETS[1]])]
    queries = native.get("queries", [])
    if len(queries) != len(expected):
        raise ValueError("Unexpected query count")
    contract_ok = True
    for item, scope in zip(queries, expected):
        if (item.get("name"), item.get("which"), item.get("who")) != scope or item.get("direct_arm64_svc") is not True:
            raise ValueError("Query is outside the fixed self/probe scope")
        raw = item.get("raw_return")
        if type(raw) is not int:
            raise ValueError("Missing raw syscall result")
        valid = 1 <= raw <= 40
        error = -raw if -4095 <= raw <= -1 else 0
        if (item.get("raw_errno") != error or item.get("raw_success_1_to_40") != valid
                or item.get("raw_out_of_contract") != (not valid and error == 0)
                or item.get("interpreted_nice") != (20 - raw if valid else None)):
            raise ValueError("Raw priority semantics were misreported")
        for key in ("libc_syscall_return", "libc_syscall_errno", "libc_getpriority_nice", "libc_getpriority_errno"):
            if type(item.get(key)) is not int:
                raise ValueError("A libc comparison result is missing")
        agree = ((item["libc_syscall_return"] == raw and item["libc_syscall_errno"] == 0
                  and item["libc_getpriority_nice"] == 20 - raw and item["libc_getpriority_errno"] == 0)
                 if valid else bool(error) and item["libc_syscall_return"] == -1
                 and item["libc_syscall_errno"] == error and item["libc_getpriority_nice"] == -1
                 and item["libc_getpriority_errno"] == error)
        if item.get("sequential_semantics_agree") is not agree:
            raise ValueError("The sequential libc comparison was misreported")
        contract_ok &= valid or error != 0
    controls_ok = all(item["raw_success_1_to_40"] and item["raw_errno"] == 0 for item in queries[:3])
    return {"raw_contract_valid": bool(contract_ok), "self_controls_valid": controls_ok,
            "all_sequential_views_agree": all(item.get("sequential_semantics_agree") is True for item in queries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New private evidence directory")
    args = parser.parse_args()
    if not args.adb.is_file():
        raise ValueError("Use the actual existing adb executable")
    build = json.loads(args.build_record.read_text(encoding="utf-8"))
    if build.get("status") != "PASS_CLOUD_BUILD_SIGNATURE_PERMISSION_AND_OFFLINE_FIXTURES_ONLY":
        raise ValueError("Use the successful cloud build record for the installed App4 APK")
    args.out.mkdir(parents=False, exist_ok=False)
    request_id = str(uuid.uuid4())
    commands = []

    def call(*parts, check=True):
        result = subprocess.run([str(args.adb.resolve()), "-s", args.serial, *parts],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        commands.append({"argv": list(parts), "exit": result.returncode,
                         "out": result.stdout, "err": result.stderr})
        if check and result.returncode:
            raise RuntimeError("ADB command failed; no root fallback is used")
        return result

    def boot_id():
        value = call("shell", "cat", "/proc/sys/kernel/random/boot_id").stdout.strip()
        if not canonical_uuid(value):
            raise ValueError("Cannot read a canonical boot ID")
        return value

    def uid_pair(user):
        return {package: parse_package_uid(call("shell", "cmd", "package", "list", "packages", "-U",
                    "--user", str(user), package).stdout, package) for package in TARGETS + (APP,)}

    def live_pids():
        result = {}
        for package in TARGETS:
            raw = call("shell", "pidof", package).stdout.strip()
            if not re.fullmatch(r"[0-9]+(?:\s+[0-9]+)*", raw):
                raise ValueError("Both target probes must already be running")
            pids = sorted({int(value) for value in raw.split()})
            if not pids or any(value <= 1 for value in pids):
                raise ValueError("Invalid target PID")
            result[package] = pids
        return result

    final = {"status": "NOT_COMPLETED", "controller_run_id": request_id,
             "root_requested": False, "scheduling_writes": False, "filter_writes": False}
    try:
        before_boot = boot_id()
        user_text = call("shell", "cmd", "activity", "get-current-user").stdout.strip()
        if not re.fullmatch(r"\d+", user_text):
            raise ValueError("Cannot resolve the current Android user")
        user = int(user_text)
        uids = uid_pair(user)
        if len(set(uids.values())) != 3 or any(value // 100000 != user for value in uids.values()):
            raise ValueError("The three task apps need distinct UIDs in the current Android user")
        before_pids = live_pids()
        call("shell", "am", "start", "-W", "-S", "--user", str(user), "-n", ACTIVITY,
             "--es", "controller_run_id", request_id,
             "--ei", "probe2_uid", str(uids[TARGETS[0]]), "--ei", "probe3_uid", str(uids[TARGETS[1]]))
        report = None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            raw = call("exec-out", "run-as", APP, "--user", str(user), "cat", "files/latest.json", check=False)
            try:
                candidate = json.loads(raw.stdout) if raw.returncode == 0 else {}
                if candidate.get("controller_run_id") == request_id:
                    report = candidate
                    break
            except json.JSONDecodeError:
                pass
            time.sleep(0.25)
        if report is None:
            raise RuntimeError("No fresh App4 report; prior reports are not accepted")
        (args.out / "app-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        semantics = validate_report(report, request_id, uids, build)
        after_uids = uid_pair(user)
        after_pids = live_pids()
        after_boot = boot_id()
        stable = before_boot == after_boot and uids == after_uids and before_pids == after_pids
        final.update(status="OBSERVATION_CAPTURED_ONLY" if stable and semantics["self_controls_valid"]
                     and semantics["raw_contract_valid"] else "INCONCLUSIVE_STATE_OR_CONTROLS",
                     before_boot_id=before_boot, after_boot_id=after_boot, before_uids=uids,
                     after_uids=after_uids, before_pids=before_pids, after_pids=after_pids,
                     state_stable_at_endpoints=stable, **semantics)
        final["limits"] = "Endpoint PID checks do not prove continuous liveness; ESRCH alone does not establish filtering. No priority filter was set."
    except Exception as error:
        final.update(status="FAILED_NO_ROOT_OR_RETRY_FALLBACK", error=str(error))
    finally:
        (args.out / "controller-commands-private.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
        (args.out / "controller-final.json").write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, indent=2))
    return 0 if final["status"] == "OBSERVATION_CAPTURED_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
