"""Route actual AK3 content before the official GKI image patcher is entered."""
from pathlib import Path
import sys
root=Path(sys.argv[1]);here=Path(__file__).resolve().parent
target=root/'manager/app/src/main/java/com/sukisu/ultra/ui/screen/install'
(target/'InstallInput.kt').write_bytes((here/'manager-install/InstallInput.kt').read_bytes())
test=root/'manager/app/src/test/java/com/sukisu/ultra/ui/screen/install/InstallInputTest.kt'
test.parent.mkdir(parents=True,exist_ok=True)
test.write_bytes((here/'manager-install/InstallInputTest.kt').read_bytes())
p=target/'InstallScreen.kt';s=p.read_text(encoding='utf-8')
old='''            add(InstallMethod.SelectFile(summary = if (isGkiDevice) selectFileTip else selectFileTipNoGki))
            add(InstallMethod.DownloadFile(summary = downloadFileMsg))'''
new='''            if (isGkiDevice) {
                add(InstallMethod.SelectFile(summary = selectFileTip))
                add(InstallMethod.DownloadFile(summary = downloadFileMsg))
            } else {
                add(InstallMethod.HorizonKernel(summary = horizonKernelSummary))
            }'''
assert s.count(old)==1;s=s.replace(old,new,1)
start=s.index('                val option = when (installMethod) {')
end=s.index('\n            }\n        }\n    }\n\n    val state = InstallUiState(',start)
s=s[:start]+'''                scope.launch {
                    val kind = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                        inspectInstallInput { context.contentResolver.openInputStream(uri) }
                    }
                    when (routeInstallInput(kind, isGkiDevice)) {
                        InstallInputRoute.ANYKERNEL3 -> {
                            val option = InstallMethod.HorizonKernel(uri, summary = horizonKernelSummary)
                            installMethod = option
                            installMethodState.value = option
                            anyKernel3State.onHorizonKernelSelected(option)
                        }
                        InstallInputRoute.BOOT_PATCH -> {
                            installMethod = InstallMethod.SelectFile(uri, summary = selectFileTip)
                        }
                        InstallInputRoute.REJECT -> {
                            installMethod = null
                            installMethodState.value = null
                            showMessage(resources.getString(R.string.select_ak3_zip))
                        }
                    }
                }'''+s[end:]
p.write_text(s,encoding='utf-8',newline='\n')
# A second check protects restored navigation state and other callers.
p=root/'manager/app/src/main/java/com/sukisu/ultra/ui/util/KsuCli.kt'
s=p.read_text(encoding='utf-8')
imports='import com.sukisu.ultra.ui.screen.install.InstallInputRoute\nimport com.sukisu.ultra.ui.screen.install.inspectInstallInput\nimport com.sukisu.ultra.ui.screen.install.routeInstallInput\n'
pos=s.index('\nimport ');s=s[:pos+1]+imports+s[pos+1:]
start=s.index('fun installBoot(');at=s.index('    val bootFile = bootUri?.let { uri ->',start)
guard='''    if (bootUri != null) {
        val kind = inspectInstallInput { resolver.openInputStream(bootUri) }
        if (routeInstallInput(kind, com.sukisu.ultra.getKernelVersion().isGKI()) != InstallInputRoute.BOOT_PATCH) {
            val message = ksuApp.getString(R.string.select_ak3_zip)
            onStderr(message)
            return FlashResult(-1, message, false)
        }
    }

'''
s=s[:at]+guard+s[at:];p.write_text(s,encoding='utf-8',newline='\n')
# Both current UI themes consume the same method list and callback above.
for folder,text in [('values','Select an AnyKernel3 kernel ZIP.'),('values-zh-rCN','请选择 AK3 内核 ZIP。'),('values-zh-rTW','請選擇 AK3 核心 ZIP。')]:
 p=root/'manager/app/src/main/res'/folder/'strings.xml'
 if p.is_file():
  s=p.read_text(encoding='utf-8');assert s.count('</resources>')==1 and 'name="select_ak3_zip"' not in s
  s=s.replace('</resources>',f'    <string name="select_ak3_zip">{text}</string>\n</resources>')
  p.write_text(s,encoding='utf-8',newline='\n')
print('Non-GKI exposes AK3; content determines routing before boot patching')
