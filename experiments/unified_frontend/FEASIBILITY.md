# 单核心入口与菜单过渡研究

2026-10-31。用户已实机确认 GBA 中文名称、Pocket Lab 分组和 Change Core 正确；随后要求研究单核心入口和 GB/GBC 风格过渡。本次离线研究没有访问设备卡。可用核心与源码标签 `v0.2.0-gba.3-ui-preview.1` 保留。

用户随后明确要求按游戏使用各自原生核心，拒绝 GBA 内的软件模拟。当前主线见[原生程序路由](NATIVE-CORE-ROUTING.md)：SNES 已有加载时按 ROM 选择 bitstream 的实例；以下同时容纳两套电路的面积研究仅是另一条备选路线，不是实现该目标的前提。

## 一个入口包含多个硬件程序

[core.json](https://www.analogue.co/developer/docs/openfpga/core-definition-files/core-json)允许一个包列出最多 8 个 bitstream、关联 4 个平台。[Chip32](https://www.analogue.co/developer/docs/openfpga/chip32-vm/initialization-of-the-chip32-vm)可在加载时选程序，OS 中重选可重载文件也会再次调用它。这支持研究一个入口在启动时按机种选择硬件程序，但不等于中文图标页已经能直接切换。

已查的 [Target 命令](https://www.analogue.co/developer/docs/openfpga/host-target-commands)、[Chip32 指令](https://www.analogue.co/developer/docs/openfpga/chip32-vm/special)和 [Interact UI](https://www.analogue.co/developer/docs/openfpga/custom-interact-ui)没有提供已验证的“FPGA 按钮唤起 Chip32 并换程序”链路。`CORE` 在程序已经加载时的行为也不能用旧日志模型证明；官方例子的重载只载入数据，bitstream 首次加载后保留。仍需独立无存档的 A→B→A 实机探针，验证触发、重新配置及返回，而不是把 OS 文件重选当作图标切核。

现有两个包还存在具体冲突，不能仅合并 JSON：

| 接口 | GB/GBC | GBA |
|---|---|---|
| 数据槽 4 | 2,304 字节 GBC BIOS，桥接地址 `0x10000000` | 16,384 字节 GBA BIOS，`0x30000000` |
| 数据槽 100 | v9 `covers.bin` | GBAF1 `menu.bin` |
| 菜单游戏槽 | 101 | 1 |
| 平台目录集合 | gbclab、gb、gbc | gbalab、gba |

目录集合合计 5 个，超过每包 4 个关联。可把两套菜单资源迁到共同命名空间、重新约定 BIOS／游戏槽和保存格式，再分别重编两套加载器；4 个关联并非机种数量的绝对上限。该迁移未实现，现有路径与进度没有迁移。

## 一个 bitstream 同时包含 GB/GBC 和 GBA

读取两次实际完整 Quartus Fitter 的逐模块报告，摘要与报告哈希保存在 [fit-hierarchy.json](fit-hierarchy.json)。下面是包含子模块的数值，不能再加到其父项上：

| 模块 | ALM | M10K | DSP |
|---|---:|---:|---:|
| 芯片总量 | 18,480 | 308 | 66 |
| GB/GBC 整体 | 13,753 | 299 | 56 |
| GB/GBC 的游戏逻辑 `gb` | 5,389.5 | 54 | 2 |
| GB/GBC 的菜单 `cover_picker` | 4,328.7 | 23 | 44 |
| GBA 整体 | 15,940 | 277 | 27 |
| GBA 的游戏逻辑 `gba_top` | 13,400.6 | 175 | 26 |
| GBA 的视频适配器 | 94.4 | 92 | 0 |

把 GB 游戏逻辑直接加到现有 GBA 已需 331 个 M10K，尚未计入 GB 的卡带缓存、视频与存档模块。两套完整游戏逻辑的独立布局 ALM 相加也已高于总量。重新综合的布局、共享 RAM、简化卡带缓存和外置内存可能改变占用，因此这些数值不是“任何重设计都不可能”的数学证明；它们说明现有核心无法原样拼接。

若继续这条路线，应先统一桥接、时钟、视频、输入与外置内存接口，再比较精简后的两个游戏模块能否同时放入。只有完整综合／布局布线、时序和普通存档验证通过，才能声称单 bitstream 可用。当前没有合并核心二进制。

## GBA 为什么缺少过渡

GB/GBC 的 [`cover_picker.sv`](../../core/src/core/cover_picker.sv)有独立封面缓存、8 帧缓动位移／缩放、封面亮度和文字淡入淡出。GBA 的 [`gba_menu.sv`](../gba_menu/gba_menu.sv)每次载入一整张 240×160 菜单图，先等画面隐藏，再上传全部像素后重新显示；[`gba_menu_pixels.sv`](../gba_menu/gba_menu_pixels.sv)与游戏共用帧缓冲。这避免额外大缓存，也使换图显得突然。

不能照搬完整 GB/GBC 绘图器：该模块独立报告占 44 个 DSP，现有 GBA 只剩 39 个；ALM 也不足。新加第二张完整 RGB565 帧即使理想密集存储也至少要 60 个 M10K，现有余量只有 31 个。源码中的视频 BRAM 估算注释不代表实际布局结果，应采用上表的 Fitter 数值。

先试不新增整帧 RAM 的淡入淡出：保持旧图 → 淡出 → 全黑后上传 → 等待完整帧 → 淡入。当前 [`menu_fade.sv`](menu_fade.sv)是独立原型，8 帧淡入、4 帧淡出；游戏像素绕过增益时逐字节一致。约 60 Hz 时动画本身约 200 ms，上传耗时另计，不会加速 SD 读取。它尚不含封面滑动／缩放。

```sh
python experiments/unified_frontend/probe_fade.py --out .work/unified-frontend/fade-probe
```

首轮 Icarus 仿真通过了帧信号更新亮度、9 档增益各 256 组通道输入、上传期间全黑、游戏绕过以及淡入中的复位。[首轮收据](fade-probe.json)只记录独立模块，当时未接入 GBA。本轮接入结果见下文；完整硬件时序及实机验收仍须另行验证。接入时必须让像素写入等待淡出真正结束，不能只延后“显示”信号。

## 续查：共享外部存储

进一步阅读 [Pocket 32X 的实际实现](https://github.com/armyofgnomes/analogue-pocket-32x/blob/bf1ca098209696c79fecf7339e2c239e45f1619f/docs/architecture.md)，它把画面缓存移到外部 SRAM，并通过逐项面积实验压缩逻辑。这提供了可研究的工程方向，不能把该项目的资源结果直接套到 GBA。两者的内存访问节奏不同。

本地源代码还确认了两个目标：

| 目标 | 已测占用 | 需要验证的改造 |
|---|---|---|
| GBA `video_adapter` | 模块总计 92 M10K | 把其中的大帧缓冲放外部 SRAM，保留行缓存；净回收数量须重新综合 |
| GB `cart_top` 的 `cram_l` / `cram_h` | 各 64 M10K，共 128 | 保留完整 128 KiB 卡带 RAM 容量，研究复用 GBA 已有 PSRAM 通路与保存接口 |

Pocket SRAM 的接口是 17 位地址 ×16 位数据，可寻址 256 KiB。GBA 单帧 38,400 个 18 位像素，按每像素两个 16 位字存储需 150 KiB，容量放得下；双帧这样存储则放不下。容量计算不证明实时带宽足够：需要验证 GPU 突发写入、行预取、显示读取和 APF 菜单上传仲裁，不能只按平均帧率估算。128 KiB GB 卡带 RAM 也不能随意缩减，否则会改变存档兼容性。

共享存储还必须保留暂停时的游戏 RAM，并让“保存完成／flush 成功 → 停止旧机种 → 切换映射 → 载入新进度 → 启动”顺序成立。两个游戏电路即使只运行其中之一，也仍占 FPGA 逻辑；外置 RAM 解决不了全部 ALM 问题。没有找到新的已验证图标切核接口；单 bitstream 方案仍需实际合并综合。

另完成一次独立 GBA 面积优先编译：仅调整 `AGGRESSIVE AREA` / `AREA` 设置，结果为 15,777 ALM、280 M10K、27 DSP，104 条时序摘要均无负 slack，最小 0.109 ns。相对旧报告少 163 ALM、多 3 M10K；单次独立构建没有控制布局和构建标识变化，不能当作严格成对基准，更不能据此声称合并核心能放下。未生成或安装该实验的 bitstream，详见[收据](area-probe.json)。

## 续查：过渡已接入电脑副本

[`prepare_gba_fade.py`](prepare_gba_fade.py)从冻结的上游源码创建新 GBA 副本，接入菜单增益及所有权同步。`menu_visible` 要等亮度降到零才清除，原加载器据此等待全黑再覆盖帧；游戏像素绕过增益。原可用核心、稳定硬件目录与设备卡没有改动。

```sh
python experiments/unified_frontend/prepare_gba_fade.py --sources .work/multi-system/sources/gba --out .work/gba-menu/fade-build
python experiments/unified_frontend/probe_fade.py --build .work/gba-menu/fade-build --out .work/unified-frontend/fade-video
python experiments/gba_menu/probe_boot.py --fade --build .work/gba-menu/fade-build --intel-model /path/to/altera_mf.v --out .work/gba-menu/fade-boot
python experiments/gba_menu/probe_pixels.py --fade --build .work/gba-menu/fade-build --page .work/gba-menu/fade-boot/library/Assets/gbalab/common/menu.bin --intel-model /path/to/altera_mf.v --out .work/gba-menu/fade-pixels
```

本机已通过正常首屏、残留游戏所有权启动、缺少末尾像素三项联合仿真。实际 FIFO／加载器／视频模块逐像素比对了 8 档淡入，共 307,200 个像素，并继续检查不完整上传、错误顺序和重试；另以真实视频适配器比对了 38,400 个合成游戏帧像素，检查游戏输出绕过动画及返回菜单时全黑。它们不执行游戏 CPU，也不验证真实存档与 SD 耐久性。

![实际 RTL 采集的八档淡入循环预览](gba-fade.gif)

图中为自绘机型和合成测试库；GIF 只循环播放采集到的八档淡入，没有把反向播放当作淡出验证。

实际 Quartus 综合、布局布线、Assembler 和 STA 已完成：15,784 ALM、277 M10K、30 DSP；104 条时序摘要无负 slack、TNS 均为零，最小 Setup / Hold slack 分别为 0.418 / 0.114 ns。继承的 7 个板级输出仍未约束，部分存档通配约束未匹配。整体流程包装器在综合成功后发生管道错误，随后在不改 RTL 的情况下直接完成 Fit → ASM → STA；未把失败的流程报告改为成功，也未走现有安装包验收。详见[验证收据](gba-fade-validation.json)、[布局摘要](gba-fade.fit.summary)与[时序摘要](gba-fade.sta.summary)。

单入口自动换核尚未实现；过渡候选仅保存在电脑，未安装、未获实机验收。
