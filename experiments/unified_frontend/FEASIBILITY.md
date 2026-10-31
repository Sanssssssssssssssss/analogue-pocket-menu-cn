# 单核心入口与菜单过渡研究

2026-10-31。用户已实机确认 GBA 中文名称、Pocket Lab 分组和 Change Core 正确；随后要求研究单核心入口和 GB/GBC 风格过渡。本次离线研究没有访问设备卡。可用核心与源码标签 `v0.2.0-gba.3-ui-preview.1` 保留。

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

Icarus 仿真已通过：只在帧信号更新亮度、9 档增益各 256 组通道输入、上传期间全黑、游戏绕过以及淡入中的复位。[收据](fade-probe.json)记录输入哈希。模块要求输入帧脉冲位于垂直空白；实际跨时钟同步、菜单／游戏所有权、完整 GBA 视频链、资源和时序尚未验证，未接入或安装到设备。接入时必须让像素写入等待淡出真正结束，不能只延后“显示”信号。

下一步先把淡入淡出接入独立 GBA 构建副本，复用首屏／缺像素／反复进入退出回归，并检查游戏画面绕过；随后完整编译与时序。单核心路线继续以运行时重载触发和共享资源为验收门槛，尚不能交付所需的统一图标启动器。
