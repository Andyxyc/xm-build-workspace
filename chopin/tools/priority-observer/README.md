# Priority observer App4

This ordinary app only reads getpriority. It requests no Android permissions,
does not request Root, and has no network, service, hook, filter setter or
scheduling writer. Its two package queries are fixed to
cn.chopin.acceptanceprobe2 and cn.chopin.acceptanceprobe3. An Intent cannot
select another package or supply a UID that differs from PackageManager.
The three apps must have distinct ordinary UIDs in the same Android user.

The package is cn.chopin.acceptanceprobe4. It is debuggable so the controller
can read its own private JSON with run-as. That collection command does not
run the native queries: those execute in the Activity with an ordinary
untrusted_app context and a directly checked UID of at least 10000. Root,
runas_app and isolated_app observations are rejected. No Root-manager grant
is needed. The controller never installs an APK or changes a Root grant.

Each Activity start creates a new UUID. It also echoes a separate fresh
controller UUID. The report includes the compiled source commit, native
library SHA-256, PackageManager's two UIDs, Java/native caller UID and PID,
SELinux context, monotonic timestamps and five fixed reads:

| Query | which | who |
| --- | --- | --- |
| self_uid | PRIO_USER | This Activity's UID |
| self_user_zero | PRIO_USER | 0, meaning this UID |
| self_process_zero | PRIO_PROCESS | 0, meaning this thread |
| probe2 | PRIO_USER | PackageManager's probe2 UID |
| probe3 | PRIO_USER | PackageManager's probe3 UID |

Every read records the raw ARM64 svc result, decoded kernel errno, a libc
syscall comparison and libc getpriority's nice value. Successful kernel raw
values are 1 through 40; nice is 20 minus raw. Raw 20 means nice 0, and raw 21
means a valid nice -1 when errno is zero. Raw 0 is recorded as outside the
contract. Negative kernel errors are recorded as errno, with no invented nice
value. The three views are sequential, so a scheduling change between reads
can produce a mismatch. A mismatch is evidence to inspect, not an automatic
filtering verdict.

The Linux conversion is in include/linux/sched/prio.h and kernel/sys.c of the
audited vendor tree. Android's mapping is defined by
[AOSP bionic getpriority](https://github.com/aosp-mirror/platform_bionic/blob/android-12.0.0_r1/libc/bionic/getpriority.cpp).
The collector's per-user run-as argument order follows
[AOSP run-as](https://github.com/aosp-mirror/platform_system_core/blob/android-12.0.0_r1/run-as/run-as.cpp).

The cloud workflow uses only the runner's existing SDK/NDK. It builds the
ARM64 library and APK, checks the signature and permission-free manifest,
retains disassembly and source hashes, and runs host decoder, Java UID-gate
and Python controller fixtures. It does not run an Android app or execute an
ARM64 svc. The ephemeral test signing key is not uploaded. Another build can
have a different key; preserve App4 reports before a separately approved
replacement. Probe2 and probe3 are not replaced by this workflow.

After review, building and installing App4 separately, keep both target
probes alive. Run the collector with the real existing ADB executable, the
selected device serial, the downloaded build record and a new private output
directory. For example, with paths supplied by the operator:

```text
python -B observe.py --adb ADB_EXECUTABLE --serial DEVICE_SERIAL --build-record BUILD_RECORD_JSON --out NEW_PRIVATE_DIRECTORY
```

The controller reads only the current Android user/boot ID and these three
task packages' UID records, checks the two targets' PID sets, restarts only
App4, and reads App4's report. It verifies the UUID, scope, native/libc
semantics, build identity and endpoint state. If report collection or run-as
fails, it stops with the evidence retained. It never falls back to Root.
History reports in App4's files directory remain separate UUID-named files;
latest.json is only a convenience pointer to the latest completed report.

An ESRCH result alone does not prove filtering. A target with no live process
can produce it too, and PID checks before/after do not prove continuous
liveness. Positive filtering tests still require the main plan's verified
runtime baseline and controlled filter setup/restore. This observer does not
establish an empty bitmap, exercise the package worker, set a list, or restore
NULL state. APK build success is not a phone acceptance result.
