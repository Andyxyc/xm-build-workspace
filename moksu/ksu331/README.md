# moksu / KernelSU v3.3.1 迁移工程

## 已核对的来源
- KernelSU 官方：`tiann/KernelSU`，tag `v3.3.1`，commit `0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d`
- 三方功能来源：`hartgerinktarcila-design/7kimisu`，tag `v2.29`，commit `0246ca0f16ea2e3a6af030643bb6f74262e0e26c`
- 三向合并基准：官方 KernelSU `v3.3.0`，commit `932014ab5b2c9b74a3d11e2ec4d17dd10fc9442e`

## 两条独立工作线
1. `apply_core.py`：对**真实官方 v3.3.1 源码**加入 moksu 应用名、原版 KSU 图标/Material 视觉、20 张离线卡密验证、一次登录后保留状态以及二改署名。当前属于**核心集成预览版**，没有宣称完整保留 7kimisu 私有扩展。本次编译产物实际带有 **Android Debug v2 签名**（证书 CN=Android Debug），不是正式版签名；且没有配套 ksud 与匹配的 KMI，所以不得当作正式 Root 管理器成品。
2. `merge331.py`：把 7kimisu 的专有功能按 `v3.3.0 -> v3.3.1` 的变化做三向合并，遇到相互覆盖即中止，避免“号称升级但覆盖安全修复”或“号称保留但功能实际消失”。首次严格审核统计：fork-only 源文件 70、可自动合并更改 94、冲突文件 53；完整功能融合尚未通过构建及实机检查。

## 安全 / 发布条件
- 官方 v3.3.1 同时更新 **kernel、uapi、ksud、ksuinit 和 manager**；不能仅替换 versionName 或 APK。
- 内核 `KSU_PACKAGE_NAME`、签名证书字节大小/指纹，与自签名 APK 必须对应。不能用已编好的他人签名内核模块冒充新 APK 对应模块。
- 私钥与卡密明文禁止提交到 GitHub。需要持有可恢复、可验证的签名库，才能作正式签名并编译匹配的 LKM。
- 禁止把未签名 APK、仅 UI 成品、任何未完成的内核移植包作为可刷入包发布。
- 不进行真实 boot/init_boot 刷写、Root/模块兼容性、账户登录持续性、系统更新恢复、事故回退验证的情况下不声称通过。
- 原有 `moksu-r2-6ee3e003` 分支和构建产物保留，升级工作独立在 `moksu-ksu331-6ee3e003` 进行，不直接覆盖。

## 下步验收
1. 最新 manager 3.3.1 完整编译（含登录 UI、Manifest、Android SDK 37、NDK r29）。
2. 冲突项的代码审查与版本兼容处理：stealth、个性化、网页管理等，以及 Root UAPI/签名信任/模块仓库。
3. 重新编译所有目标 KMI、ksud、ksuinit，并与同一版 APK 签名匹配。
4. 可恢复签名库离线备份及完整 SHA-256/签名内容/实机联测，然后才发布正式 APK。

许可证：保留上游相关 GPL-2.0-only（kernel）与 GPL-3.0-or-later（manager/userspace）以及原有版权归属。
