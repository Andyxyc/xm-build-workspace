普通应用身份验证工具（不申请 Root、不联网、不常驻）

用途：用真正的应用 UID 和 SELinux 域记录 SUSFS 测试前后差异，
避免把 Root shell 看到的结果误当作普通应用的行为。
只创建/读取本应用私有目录中的 path-probe.txt 和 stat-probe.txt；
记录文件 stat、打开结果、目录列表与本进程 mountinfo。
只有明确使用 capture 模式并获得 CAMERA 权限后才拍摄一张测试照片。
摄像头枚举/单张 JPEG 不能代替原厂相机全部镜头、录像及长期稳定性验收。

编译后的 APK 需先核对包名 cn.chopin.kernelprobe 和 SHA256，再安装。
am start -W -n cn.chopin.kernelprobe/.ProbeActivity --es mode prepare
am start -W -n cn.chopin.kernelprobe/.ProbeActivity --es mode check
am start -W -n cn.chopin.kernelprobe/.ProbeActivity --es mode cameras
am start -W -n cn.chopin.kernelprobe/.ProbeActivity --es mode capture --es camera_id 0

准备后，Root 读取应用私有目录中的报告，核对 uid>=10000 和真实应用域。
再用匹配 SUSFS 客户端只设置上面本任务专用文件，重新启动 check 记录变化。
报告和测试照片仅保留本地，不上传公开仓库。
测试 APK 的签名不同于 SukiSU 管理器，不赋予内核管理器权限。
重建 APK 使用新临时测试签名；若需替换已有测试 APK，先保留其报告，
仅卸载此明确包名后安装新版本，不清理其他应用。
