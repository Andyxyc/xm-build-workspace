chopin 安装与校验工具（未完成实机验收）

check_candidate_abi_gate.py 读取实际 Image 的 kcrctab，逐项核对构建记录，
再解析本地保留的 10 个原机 .ko，检查全部 1299 项导入与模块间依赖。
记录绑定 Image、System.map、Module.symvers 与各原机模块 SHA256。
当前第八次产物仍有两项内存接口差异，返回 FAIL_DO_NOT_FLASH。
这些私有输入不得上传到公开仓库。

build_gated_ak3.py 只有在该记录通过、所有绑定哈希一致、输入原厂 boot
和固定 AnyKernel3 源码校验通过时才打包。它不运行 ADB/Fastboot，不刷分区。
ZIP 名称必须含 TEST-CANDIDATE；打包不代表开机、相机或功耗验证通过。

AnyKernel3 固定 020dfeccf9d7e962a48400fc94d3e451df92eead。
packager 对官方 flash_boot 只插入写入前回调，保留完整官方源码和许可证。
回调核验当前 boot 未变、重包头参数、实际 kernel、原厂 ramdisk/DTB；
在持久备份目录独占记录一次尝试。写后比对完整 128MiB 分区 SHA256。
失败后中止，不自动重刷或恢复。恢复需使用另行保存的原槽位备份与设备核验。

无设备时可做源码和云端检查；不调用官方 flash_boot 做所谓 dry-run。
它同时重包和写分区。当前没有最终可刷成品。

AnyKernel 脚本及工具由 Chris Renshaw (osm0sis @ xda-developers) 和
各原作者提供；保留官方许可证及源地址，打包时附 AnyKernel3-LICENSE。
