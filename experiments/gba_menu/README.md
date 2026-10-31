# GBA 原生中文菜单实验 / Native GBA menu experiment

2026-10-31。**独立 GBA 核心的开发实验，实机游戏、存档及返回菜单尚待验收。** 稳定发行版 `v0.1.2-public.1` 继续只支持 GB/GBC。本目录不提供游戏、BIOS、个人进度或整卡清单；NES/SNES 与跨核心自动切换尚未接通。

实机首次测试在菜单出现前报告 `Error in core setup`。已发现并修正打包错误：目录 `pocketlab.GBA` 必须与 `author: pocketlab`、`shortname: GBA` 对应，见官方[打包要求](https://www.analogue.co/developer/docs/openfpga/packaging-a-core#for-development)。打包器和安装器现在检查此约束；该次身份修正未改变 FPGA 二进制。上游 mincer_ray 的署名与通知保留在源码及本文来源段落中。

后续实机反馈：身份修正后点击 OS Run 黑屏，尚未看到中文菜单。[诊断读数](evidence/black-screen.json)的状态低字节对应 `FRAME_DRAIN`，最近的 Host/Target 命令均成功；高位所有权标记与首次启动预期不一致。`0.2.0-gba.2` 将 76,800 字节帧拆为 5 次、每次最多 16 KiB 的连续读取，并增加画面完成超时及计数诊断。**分块是本项目的传输策略，尚未证明固件存在 16 KiB 大小限制。**

该版[实机复测](evidence/framebuffer-ownership.json)显示中文“操作失败”：首次 E=`0x22`，P=`0x4B000000` 表示 19,200 个桥接字全部到达、像素数为 0；M/V 显示菜单没有缓冲区所有权。按键重试后的 E=`0x53` 是后续保存错误，不能当作首次故障。候选 `0.2.0-gba.3` 在 APF Stop／启动时明确初始化生命周期，每次绘制菜单取得缓冲区所有权，并单独保留首次错误。残留状态注入使旧版失败、新版通过，但**首次实机为何失去所有权仍未完全解释；GBA 菜单可用性尚待复测**。

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
- `0.2.0-gba.2` 的[控制流收据](evidence/frame-fix-control.json)、[像素收据](evidence/frame-fix-pixels.json)与[首屏收据](evidence/frame-fix-boot.json)包含输入哈希。`probe_boot.py` 联接真实菜单、APF 命令引擎、Intel FIFO 与扫描输出，检查首次 Run、页面元数据、五段帧读取、19,200 个桥接字和 38,400 个像素。另模拟宿主返回成功但缺少最后两个像素，检查超时转入可见错误。数据表 RAM、宿主和 ready/idle 输入由测试模型提供；没有 GBA CPU、实体 RAM 或真实 SD 服务。
- `0.2.0-gba.3` 的[控制流收据](evidence/ownership-control.json)验证绘制前丢失所有权、Stop／启动重置及多次错误后保留首次错误；[首屏收据](evidence/ownership-boot.json)覆盖正常启动、残留游戏所有权和缺少末尾数据三种情况。[旧版失败证据](evidence/ownership-reproduction.json)使用残留状态注入；它检验初始化缺口，不等同于证明实体 FPGA 的启动原因。像素模块及视频输出与上一候选保持相同输入哈希，沿用其逐像素扫描验证。
- 仿真不验证实体 SDRAM／PSRAM、SD 写入耐久性、声音、游戏兼容或掉电。完整编译结果与继承时序约束的范围记录在本目录证据中；原始板级例外不能据此升级为外部存储时序签核。

`0.2.0-gba.1` 的[完整编译收据](evidence/build.json)、[资源摘要](evidence/gba.fit.summary)、[时序摘要](evidence/gba.sta.summary)：实际 `5CEBA4F23C8` 全引脚工程通过，15,605 ALM（84%）、277 M10K（90%）、27 DSP，虚拟引脚 0。四个模型的 104 条时序摘要均无负 slack、TNS 均为 0；最差 setup 0.494 ns、hold 0.097 ns。编译错误与 critical warning 均为 0，继承工程仍报告 22,560 条普通 warning。上游已有的 7 个卡槽输出未约束，完整板级／外设签核不在该结论内。

`0.2.0-gba.2` 的[完整编译收据](evidence/frame-fix-build.json)、[资源摘要](evidence/frame-fix.fit.summary)、[时序摘要](evidence/frame-fix.sta.summary)：15,816 ALM（86%）、277 M10K（90%）、27 DSP，虚拟引脚 0。104 条摘要均无负 slack、TNS 为 0，最差 setup 0.493 ns、hold 0.023 ns；0 错误、0 critical warning，22,566 条普通 warning。首次候选出现负时序余量，未用于安装；最终版将分段进度改为固定的 3 位段号，未放宽时序约束。上述 7 个板级例外继续保留。完整编译和电脑仿真通过仍不代表实机启动已通过。

`0.2.0-gba.3` 的[完整编译收据](evidence/ownership-build.json)、[资源摘要](evidence/ownership.fit.summary)、[时序摘要](evidence/ownership.sta.summary)：15,940 ALM（86%）、277 M10K（90%）、27 DSP，虚拟引脚 0。104 条摘要均无负 slack，TNS 为 0；最差 setup 0.491 ns、hold 0.067 ns，0 错误、0 critical warning，22,566 条普通 warning。7 个继承的板级例外保留，完整编译已通过，实机仍待复测。

## 本地构建

需要 Python 3.11+、本仓库 `requirements.txt`；控制流仿真需 Icarus Verilog，完整构建需 Quartus Prime Lite 22.1。所有输出使用新的电脑目录。

```sh
python experiments/multi_system/fetch_sources.py --out .work/upstream
python experiments/gba_menu/prepare_build.py --sources .work/upstream/gba --out .work/gba-menu/build --integrate
python experiments/gba_menu/probe_control.py --build .work/gba-menu/build --out .work/gba-menu/control
```

本机安装了 Quartus 的 Intel 仿真模型时，可运行首屏联接验证；模型路径按自己的安装位置填写，模型不随仓库分发：

```sh
python experiments/gba_menu/probe_boot.py --build .work/gba-menu/build --intel-model /path/to/altera_mf.v --out .work/gba-menu/boot
```

该命令验证完整帧、残留游戏所有权和宿主误报成功但缺少末尾数据的三种情况。`probe_control.py` 同样接受 `--intel-model`，用于运行加载 FIFO 与连续换游戏检查，以及 Stop／启动、绘制所有权恢复和首次错误保留。

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

实验版 Core Settings 中的只读诊断：`M` 为菜单状态／标记，低 8 位 `0x0D` 表示菜单可操作，`0x0B` 表示等待帧完成；`P` 的高 16 位为桥接字数、低 16 位为像素数，完整帧为 `0x4B009600`；`V` 为帧握手标记；`E` 为最后错误码，`0x22` 表示画面未完整到达；`F` 为首次错误码，APF Stop／启动清零；`T` / `H` 为最后的 Target / Host 命令状态。字段名保持单字母以避免 OS 截断数值。它们不会写入游戏、存档或画面设置。

English: isolated experimental GBA integration, native Chinese/icon/cover menus, ordinary saves and RTC. APF Memories/sleep and cross-core switching are disabled/unimplemented. After the core-folder identity fix, hardware black-screened; version 0.2.0-gba.2 then showed a Chinese error screen. First-run error 0x22 and P=0x4B000000 identify all bridge words received but zero pixels accepted, with menu ownership absent. Candidate 0.2.0-gba.3 explicitly initializes the lifecycle on APF Stop/boot, acquires ownership on paint and retains the first error. The original loss of ownership is not fully explained; hardware recovery remains unconfirmed. The joined simulation models the host, RAM table and ready/idle inputs; it does not execute a GBA CPU or validate physical memory/SD. Inherited board exceptions remain. No public GBA binary release or hardware compatibility claim is made.
