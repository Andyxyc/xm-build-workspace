# chopin priority filter 只读观察器

这是测试工具，单独构建，不放入 AK3，不改管理器和内核。当前只接受 r18 legacy 的已核验 Image，不能拿它观察 41098、early 或 T 家族。

- raw Image：`6702e417fc0f731923be2f35e55ba96ffe0644e1a67275d7e5ebd09e91a865f1`
- 内核源码：`16c713d934ab7cfed5c4798497c48bab7e9db025`
- paired kpimg：`554aa43ff1594ea516eb9d74581565aea07e29665ffaf702a3c87d556a7a2425`
- KPM 头文件：官方 `a3965c6e137e46b2c94a69eeb5a7e4696a3abbb0`。沿用已有 KPM bridge ABI1。

## 读什么

只读四个精确全名符号：

| 符号 | 宽度 | 返回信息 |
| --- | --- | --- |
| priority_uid_filter_bitmap | 8 B | 是否为 NULL |
| susfs_priority_app_strings | 8 B | 是否为 NULL |
| susfs_priority_app_strings_running | 4 B | 是否为 0 |
| susfs_set_priority_uid_filter.is_uid_filter_set_before | 1 B | 是否为 0 |

不会解引用前两个指针，不读 UID、包名、字符串或 bitmap，不设置过滤项，不改优先级。模块没有 hook、锁、RCU 回收、分配或 usercopy。模块载入、卸载和官方 loader 保存 ctl_args 本身会改变 KPM 管理状态；这与写 SUSFS 目标变量有明确区别。

首次载入逐一精确匹配完整符号名并拒绝重复，再与 KP 的 lookup_name 结果比对。核对 15 个符号相对 `_text` 的偏移、BSS 范围和六处各 32 B 的真实代码后，才允许观察四个槽位。控制调用会重新核对已缓存地址的布局及实际代码，避免在官方 loader 的 RCU 区间内再做一次全符号扫描。KASLR 的一致滑动可以接受，单个偏移变化不可以。trampoline 是已知的 KPM hook 目标，所以只核对其符号偏移，不要求它被 hook 后还保留原始指令；不读取已释放的 init 函数作锚点。

两轮 acquire-load 的完整指针值和两个标量必须一致，标量只能为 0 或 1。变化返回 `-EAGAIN`；缺符号、重复、偏移、边界或代码变化返回错误。错误不能解释为 NULL。返回整数为 `0x50520100 | flags`，低四位依次对应表中条件，其余值全部拒绝。不会输出原始指针。

这不构成全内存哈希。六段字节是有限身份锚点，仍需主线程独立核对当前启动镜像。两轮样本不能排除中间一次 0→1→0，也不能锁住未来的写入。

## 构建与用例

候选工作流 `chopin-priority-kpm-observer.yml` 在指定工作分支且本工具目录或该工作流变更时触发，也保留手动触发，只读仓库权限。它取固定官方头文件及经 SHA256 约束的 Arm GNU12.2.Rel1，不重编内核或 kpimg，不访问设备，不发布 release。

先用 Linux GCC、ASan、UBSan 编译并执行实际 `priority_observer.c` 和 `observer_core.h` 的 memory-only 用例，再交叉编译 KPM。host provider 只提供内存中的地址表、字节和标量；没有内核或设备。用例覆盖 16 种状态、所有符号缺失和偏移不符、代码变化、合法滑动、四处两轮变化、非法标量、非法参数、完整名称与重复收集、未初始化控制，以及真实 wrapper 的本地对象 acquire-load。编译后的 ARM64 ELF 必须只依赖两个预期 KP 符号，保留四个注册 section，并实际出现 LDAR/LDARB 指令。

Windows 本地仅做 Python/文件静态检查；C 编译和运行必须以云端真实日志为准。`build-evidence.json` 只在 host 用例和 ARM64 编译核验均完成后写成功状态。它也记录源码、头文件、工具链和模块哈希。静态审查通过不代表模块已在手机加载。

重建固定 header 的命令：

```text
python3 make_profile.py --image <exact-raw-Image> --system-map <exact-System.map> --kpimg <exact-paired-kpimg> --output-dir <this-folder>
```

`make_profile.py` 没有选择其他 hash/profile 的参数。可用 `audit_kpimg.py --kpimg ... --elf ... --output ...` 单独复核配套 ELF 的 loadable 内容、真实导出表和两个 8 B 函数指针变量。

## 审阅后的实机步骤

以下是待主线程审阅、云端编译后执行的步骤，本资料不代表已经执行。

1. 核对云端 artifact 与 `build-evidence.json`；保留模块原件的 SHA256。先确认同名模块未加载，不替换别人的模块。
2. 独立核对当前 boot_a 完整回读、boot_id、raw Image 和 kpimg 来源。将 `review-template.json` 另存为本次私有记录并填写，不能保留空项；模板默认拒绝运行。
3. 用已核验的官方 ksud 加载这一个模块。命令来自官方41100 CLI，第二参数是明确的 load args：

```text
<actual-ksud> kpm load <verified-module-path> raw-sha256=6702e417fc0f731923be2f35e55ba96ffe0644e1a67275d7e5ebd09e91a865f1
<actual-ksud> kpm info chopin-priority-ro-r18
```

4. 主机运行控制器。它只调用 `id/getprop/cat/blockdev/sha256sum`、该模块的 `kpm info` 和 `kpm control ... snapshot`，不 push、不安装、不加载、不卸载、不改配置。前后核对 boot_a 完整 SHA、boot_id、机型、槽位和 SDK；失败停止，不反复重试。

```text
python3 controller.py --adb <actual-adb-path> --serial <actual-serial> --ksud <actual-official-ksud-path> --review <private-review.json> --build-evidence <build-evidence.json> --module <local-exact.kpm> --run-id <new-unique-run> --output <new-private-report.json>
```

本地模块文件哈希不能证明内核内已加载模块的字节。因此 review 明确由主线程确认先前加载的就是该文件，报告保留这个边界。官方接口没有运行中模块完整哈希读取功能，本工具不伪造。

5. 主线程在串行、无其他配置写入的条件下，另行读取官方 persistent config。只有它确为空、两个指针 NULL、worker=0、ever-configured=0，并保留观察前后条件，才有足够证据讨论首次 SET。这个观察器自己不会进行 SET。
6. 测试后只卸载本次模块：`<actual-ksud> kpm unload chopin-priority-ro-r18`。不卸载其他模块。

## 与本次 NULL guard 的关系

初始 NULL 下首次 SET 覆盖 setter 的 old_bitmap NULL 路径。包名解析 worker 首先发现 app_strings NULL 时会提前退出，不会走回收；不能用这一次 SET 宣称 worker 的 NULL guard 也做了实机覆盖。`,` 清空只生成空的非 NULL bitmap 和字符串，ever-configured 仍为 true；不等于恢复首次配置前的状态。正常重启后是否回到 NULL，需要同时核对持久配置和新 boot_id，并再做快照。UID-only getpriority 读路径不发布或回收 bitmap，也不能替代 worker 用例。

发生加载/身份错误、无法得到稳定样本或无法回读原配置时，保留日志并停止这项首次 SET 测试，不覆盖用户列表来凑通过。
