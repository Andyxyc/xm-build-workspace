# moksu

二次修改维护：闲鱼 心中都是莫。

基于 KernelSU / 7kimisu v2.29，固定上游提交 0246ca0f16ea2e3a6af030643bb6f74262e0e26c。非 KernelSU 官方发行。

本目录包含复用 R1 的离线认证源码及新的 moksu 集成补丁。认证摘要域保持兼容；20 个本地高熵卡密的明文不在仓库。界面默认采用现有 Material 分支，图标来自 tiann/KernelSU；保留上游内核、模块和授权功能源码。新包名 com.moksu.manager，不替换原版安装；JNI 命名空间仍为 com.sevenk.core。

应用补丁：`python3 moksu/apply_ci.py /path/to/pinned-upstream`。仅在固定上游的独立工作副本执行，重复或错版本输入会失败。

Actions 构建会保存对应完整源码、内核模块、未签名 APK 和编译日志。签名私钥只在本地持有；签名证书 SHA-256 与长度见 signing-public.json，内核编译使用同一组信任值。

本修改遵循 GPL-3.0-or-later，上游 kernel/ 保留 GPL-2.0-only。完整 GPL 文本随上游完整源码和构建源码归档保留。上游 https://github.com/hartgerinktarcila-design/7kimisu ，原始项目 https://github.com/tiann/KernelSU 。

离线卡密只是本改版界面的访问门槛，不是不可绕过的 DRM，也不限制接收者依照 GPL 修改和再分发源码的权利。编译通过不等于完成实机 Root、刷写或恢复验证。
