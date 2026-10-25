"""Patch the pinned official manager; unsigned output is signed only locally."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
def edit(name,old,new):
 p=root/name;s=p.read_text();assert s.count(old)==1,(name,old[:100],s.count(old));p.write_text(s.replace(old,new,1))
edit('manager/app/src/main/java/com/sukisu/ultra/ui/viewmodel/HomeViewModel.kt',
     'val lkmMode = ksuVersion?.let { if (kernelVersion.isGKI()) Natives.isLkmMode else null }',
     'val lkmMode = ksuVersion?.let { Natives.isLkmMode }')
edit('manager/app/src/main/java/com/sukisu/ultra/ui/screen/susfs/viewmodel/SuSFSViewModel.kt',
     'report(context, context.getString(R.string.susfs_tab_basic_settings)) {',
     'report(context, context.getString(R.string.susfs_tab_basic_settings), ConfigRuntimeStatus.APPLIED) {')

p=root/'manager/app/src/main/java/com/sukisu/ultra/ui/screen/susfs/util/SuSFSRepository.kt'
s=p.read_text();start=s.index('    suspend fun setUname(');end=s.index('\n    @SuppressLint',start)
body=s[start:end];old='''        if (success) {
            saveUnameValue(unameValue)'''
new='''        if (success) {
            // A successful setter alone does not prove the visible runtime state.
            val readback = Shell.getShell().newJob().add("uname -r\\nuname -v").exec()
            val visible = android.system.Os.uname()
            val releaseMatches = SuSFSConfig.isDefaultSpoofValue(unameValue) ||
                (readback.out.getOrNull(0) == unameValue && visible.release == unameValue)
            val versionMatches = SuSFSConfig.isDefaultSpoofValue(buildTimeValue) ||
                (readback.out.getOrNull(1) == buildTimeValue && visible.version == buildTimeValue)
            check(readback.isSuccess && readback.out.size == 2 && releaseMatches && versionMatches) {
                "Uname command completed but app/shell runtime readback differs: ${readback.out} / ${visible.release} / ${visible.version}"
            }
            // Apply the same saved values at post-fs-data even when the optional
            // full SUSFS helper module is not enabled. No cleanup/hide-BL actions.
            val script = "#!/system/bin/sh\\n/data/adb/ksud susfs set-uname " +
                SuSFSConfig.shellQuote(unameValue) + " " + SuSFSConfig.shellQuote(buildTimeValue) + "\\n"
            val encoded = android.util.Base64.encodeToString(script.toByteArray(Charsets.UTF_8), android.util.Base64.NO_WRAP)
            val persist = Shell.getShell().newJob().add(
                "umask 077\\nmkdir -p /data/adb/post-fs-data.d\\nprintf '%s' '$encoded' | base64 -d > /data/adb/post-fs-data.d/00-xiaomo-uname.sh.tmp\\n" +
                "chmod 700 /data/adb/post-fs-data.d/00-xiaomo-uname.sh.tmp && mv -f /data/adb/post-fs-data.d/00-xiaomo-uname.sh.tmp /data/adb/post-fs-data.d/00-xiaomo-uname.sh"
            ).exec()
            check(persist.isSuccess) { "Runtime matched but boot persistence failed" }
            saveUnameValue(unameValue)'''
assert body.count(old)==1;body=body.replace(old,new,1);p.write_text(s[:start]+body+s[end:])

# Build a separate package, keep the installed official manager and its data.
p=root/'manager/build.gradle.kts';s=p.read_text();s=s.replace('extra["managerVersionCode"] = getVersionCode()', 'extra["managerVersionCode"] = 41078',1);s=s.replace('extra["managerVersionName"] = getVersionName()', 'extra["managerVersionName"] = "v4.2.1-r2-chopin-r6"',1);p.write_text(s)
p=root/'manager/app/build.gradle.kts';s=p.read_text();assert s.count('    alias(libs.plugins.lsplugin.apksign)')==1;s=s.replace('    alias(libs.plugins.lsplugin.apksign)\n','',1)
start=s.index('apksign {');end=s.index('\n}\n',start)+3;s=s[:start]+s[end:]
old='abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64", "riscv64")';assert s.count(old)==1;s=s.replace(old,'abiFilters += listOf("arm64-v8a")',1);p.write_text(s)
print('Manager mode uses genuine driver flags on Non-GKI; uname success requires app/shell readback and boot persistence')
