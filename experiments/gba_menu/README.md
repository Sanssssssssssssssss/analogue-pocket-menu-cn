# GBA 原生中文菜单实验 / Native GBA menu experiment

2026-10-31。**独立 GBA 核心的开发实验，实机游戏、存档及返回菜单尚待验收。** 稳定发行版 `v0.1.2-public.1` 继续只支持 GB/GBC。本目录不提供游戏、BIOS、个人进度或整卡清单；NES/SNES 与跨核心自动切换尚未接通。

实机首次测试在菜单出现前报告 `Error in core setup`。已发现并修正打包错误：目录 `pocketlab.GBA` 必须与 `author: pocketlab`、`shortname: GBA` 对应，见官方[打包要求](https://www.analogue.co/developer/docs/openfpga/packaging-a-core#for-development)。打包器和安装器现在检查此约束；FPGA 二进制未改变。该修正通过离线检查，是否消除实机报错仍待复测。上游 mincer_ray 的署名与通知保留在源码及本文来源段落中。

![实际 RTL 输出的 GBA 中文机种页](evidence/menu.png)

截图来自实际 `data_loader`、Intel FIFO 模型及修改后的 GBA `video_adapter`；不含游戏 CPU，也不是掌机照片。黑底、中文标题、机种／分类图标、可选游戏封面。菜单复用 GBA 的 240×160 帧缓冲区，在完整画面写完且到达垂直空白后显示；游戏保持 3:2 输出。

## 入口和操作

独立入口为 **openFPGA → GBA Menu CN → GBA Menu CN**，核心目录 `Cores/pocketlab.GBA`。原 GBA 与 GB/GBC 核心可继续选择。GBA、GB/GBC 的暂停组合不同：

| 按键 | GBA 实验入口 |
|---|---|
| 方向键 | 切换条目；按一次切换一项 |
| A / B | 进入／返回父目录 |
| 游戏中 L + R + Select | 打开中文暂停菜单 |
| 暂停菜单 B | 继续游戏 |
| 暂停菜单“保存并返回” | 写普通存档、刷新、写 RTC、刷新，成功后回列表 |

保存失败时保留运行中的游戏，A 重试保存，B 继续。首版关闭 APF Memories 和休眠；不导入即时存档。请先用可舍弃进度验证“启动 → 游戏内保存 → 保存并返回 → 再次启动”的完整过程，再验证重要进度。

这里持久化的是游戏原本的普通存档：先在游戏内执行保存，再从中文暂停菜单“保存并返回”。它不会记录尚未写入游戏存档的当前房间、战斗或即时现场。

普通进度按 ROM SHA256 前 20 位隔离到 `Saves/gbalab/common/<hash>.sav`，RTC 为同名 `.rtc`。64KB 默认容量覆盖 SRAM／EEPROM／64KB Flash，检测到 `FLASH1M_V` 后使用 128KB。每次换游戏先清空存档 RAM、重置类型检测和 RTC 加载状态，然后载入对应进度；暂停使用现有暂停接口，不重置 CPU。

## 验证范围

- Python 检查覆盖菜单图与原文件保护、拒绝越界路径、无损复制普通进度、同 ROM 多份存档冲突，以及回退保留新进度。
- [控制流仿真](evidence/control.json)：A/B、连续三次启动、64K/128K、暂停继续、普通存档＋RTC＋刷新后返回、保存失败保留游戏、超时和路径拒绝。另运行真实 `core_bridge_cmd`；带本地 Intel 模型时运行真实加载 FIFO、类型检测、RTC 加载模块。
- [像素仿真](evidence/pixels.json)：38,400 个像素与实际扫描输出逐像素比对；不完整／错序帧拒绝、重试及游戏画面交接。
- 仿真不验证实体 SDRAM／PSRAM、SD 写入耐久性、声音、游戏兼容或掉电。完整编译结果与继承时序约束的范围记录在本目录证据中；原始板级例外不能据此升级为外部存储时序签核。

[完整编译收据](evidence/build.json)、[资源摘要](evidence/gba.fit.summary)、[时序摘要](evidence/gba.sta.summary)：实际 `5CEBA4F23C8` 全引脚工程通过，15,605 ALM（84%）、277 M10K（90%）、27 DSP，虚拟引脚 0。四个模型的 104 条时序摘要均无负 slack、TNS 均为 0；最差 setup 0.494 ns、hold 0.097 ns。编译错误与 critical warning 均为 0，继承工程仍报告 22,560 条普通 warning。上游已有的 7 个卡槽输出未约束，完整板级／外设签核不在该结论内。

## 本地构建

需要 Python 3.11+、本仓库 `requirements.txt`；控制流仿真需 Icarus Verilog，完整构建需 Quartus Prime Lite 22.1。所有输出使用新的电脑目录。

```sh
python experiments/multi_system/fetch_sources.py --out .work/upstream
python experiments/gba_menu/prepare_build.py --sources .work/upstream/gba --out .work/gba-menu/build --integrate
python experiments/gba_menu/probe_control.py --build .work/gba-menu/build --out .work/gba-menu/control
```

进入 `.work/gba-menu/build/src/fpga/build` 执行 `quartus_sh --flow compile ap_core.qpf`。完整编译、布局布线、多温度模型时序均通过后，返回仓库根目录：

```sh
python experiments/gba_menu/package.py --build .work/gba-menu/build --sources .work/upstream/gba --out .work/gba-menu/package
python experiments/gba_menu/library.py --card X:/ --out .work/gba-menu/library
python experiments/gba_menu/import_saves.py --card X:/ --library .work/gba-menu/library/library-manifest.json --out .work/gba-menu/saves
python experiments/gba_menu/install.py --card X:/ --package .work/gba-menu/package --library .work/gba-menu/library --saves .work/gba-menu/saves
```

最后一条仅核对和计划。确认重新识别的卡与目标内容后，加 `--apply --backup <新的电脑备份目录>`；工具先复制、校验原进度及相关核心，只增加新 GBA 命名空间，已存在的实验入口会被拒绝。安装中断也不会覆盖原游戏、原存档或固件。完成后安全弹出再插回 Pocket。

提供自己的 **16,384 字节** BIOS 到原有 `Assets/gba/common/gba_bios.bin`；通过平台索引读取，不复制到公开包。ROM 仍放原 `Assets/gba/common`。`--titles` 接受路径到中文标题的 JSON，`--folders` 接受 `gba/...` 目录到中文名的 JSON；`--covers` 使用与卡内 ROM 路径对应、扩展名改成 `.png` 的图片。检查未通过时默认停止；显式 `--skip-invalid` 会保留原文件、逐项记录排除原因。当前加载器要求 ROM 长度为四字节倍数，排除不代表原核心不能运行它。

`import_saves.py` 只向电脑副本复制普通存档；保留旧版 16 字节 RTC 尾部，短存档以 FF 补足，拒绝截断。相同 ROM 的原存档不一致时跳过；已知该使用哪份时，用 `--prefer Saves/gba/common/.../Example.sav` 指明。所有候选原文件保留。

回退默认核对，补 `--apply` 才执行：

```sh
python experiments/gba_menu/install.py --card X:/ --backup <该次备份目录> --rollback
```

回退只移除该次新增且未改变的核心／菜单／平台文件，保留全部 `Saves/gbalab` 进度；原核心始终可从系统菜单选择。

## 来源和边界

基于 [mincer-ray/openfpga-GBA](https://github.com/mincer-ray/openfpga-GBA/tree/a61eaf2e8d50631f5dd32bda5c84229a0c54ab78) `a61eaf2`（1.0.1）。[冻结清单](upstream-lock.json)校验 128 个原文件和源压缩包；`prepare_build.py` 在副本中清除上游嵌入的 BIOS 初值，再按精确锚点修改。已有通知及许可保持原样，新工具和独立菜单模块为 MIT。上游没有根目录许可文件，因此本分支公开接入脚本和新代码；合并核心二进制不作为公共发行包发布。

数据槽顺序固定为 `[100 菜单, 4 BIOS, 1 ROM, 10 Save, 11 RTC]`；存档大小写入对应 datatable 索引 7、9。目标命令使用官方[读／写／打开／刷新接口](https://www.analogue.co/developer/docs/openfpga/host-target-commands)，槽参数见 [data.json 文档](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json)。这些命令没有通用换核心操作；当前通过 Analogue OS 选择不同平台。

English: isolated experimental GBA integration, native Chinese/icon/cover menus, ordinary saves and RTC. APF Memories/sleep and cross-core switching are disabled/unimplemented. Full Quartus fit passed at 84% ALMs with positive reported timing; seven inherited cartridge output exceptions remain. The first hardware attempt failed with `Error in core setup` before the menu. Packaging now enforces folder/author/shortname consistency and fixes the observed mismatch; the bitstream is unchanged and a hardware retest is pending. The scripts stage and verify a new `pocketlab.GBA` entry, preserve original ROMs/saves, and retain newly played progress during rollback. See the commands and evidence above; no public GBA binary release or hardware compatibility claim is made.
