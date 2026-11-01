# openFPGA 图形主机首页的可行性

2026-11-01 后续决定：本方向收束，当前改为[各机种独立的中文可视化菜单](../../docs/PER-SYSTEM-MENUS.md)，保留官方列表与 Change Core。下文保留本次系统首页方案的边界核对，不作为当前实现计划。

2026-11-01。用户澄清目标：进入 openFPGA 后，第一屏直接显示可选择的主机图形，保留系统的 Change Core 和原生核心加载，并改善 GBA 菜单动画。仅改平台名称和标志图不能完成这个交互。所查官方 SDK 没有提供全局列表布局、字体或动画的替换接口，图形首页尚无已验证实现路径。本轮仅查看官方文档、源码和电脑备份，未访问设备卡。

## 目标与公开接口

```text
期望的 openFPGA 图形主机首页（尚未实现）
  ├─ GB / GBC → pocketlab.CoverFlow → 已有中文分类、封面和游戏
  └─ GBA      → pocketlab.GBA       → 已有中文分类、封面和游戏
```

现有系统列表可以启动各自核心，Change Core 也已验收；把第一屏文字列表改成图形网格或轮播，则需要控制 Analogue OS 的显示与输入层。如果具备该层的源码或受支持的扩展接口，原则上可以沿用原来的加载机制。当前公开的平台配置没有暴露这一层，不能把“加载功能已有”当作“可直接替换界面”的依据。

| 层级 | 公开能力 | 本项目结论 |
|---|---|---|
| 平台名称、分类、厂商、年份 | `Platforms/<id>.json` | 可定制显示信息；分类分组还受 OS 的 Group openFPGA 设置影响 |
| 平台标志图 | `Platforms/_images/<id>.bin` | 官方定义为平台页图像，不能由此把第一屏改为图形选择器 |
| 平台与核心关联 | `core.json` 的 `platform_ids` | 现有 GB/GBC、GBA 专属平台已存在，共同 Pocket Lab 分组也已验收 |
| 每台机种里的中文游戏菜单 | 各核心自行实现 | GB/GBC 与 GBA 已有实现；其他核心需要逐个适配，配置文件不会自动把它们变为中文 |
| 系统字体、Run/Settings、列表布局与动画 | 所查 SDK 未提供替换接口 | 全中文图形主机首页尚未实现；不能仅以换资源完成 |

官方区分开发者可用的主 FPGA 和 Analogue OS 专用的系统 FPGA。openFPGA 提供核心开发、包装和交互接口，不能由名称推断整个 OS 前端均可直接改源码。[官方架构](https://www.analogue.co/developer/docs/openfpga/overview)

平台字段和标志图的位置有公开定义。[平台元数据](https://www.analogue.co/developer/docs/openfpga/platform-metadata)；521×165 平台页图像及 36×36 核心作者图标见[图像规范](https://www.analogue.co/developer/docs/openfpga/packaging-a-core)。类别分组及字母排序见[官方分组说明](https://www.analogue.co/developer/docs/openfpga/changelog/1-1-beta-5)。[Custom Interact UI](https://www.analogue.co/developer/docs/openfpga/custom-interact-ui)是核心设置项接口，也没有定义全局首页绘制。上述接口没有承诺 OS 的汉字字体覆盖；JSON 能存中文不等于系统能显示中文。把汉字画进标志图也不等于系统文字已汉化。

## 当前配置与电脑候选

已核对最新安装前备份中的元数据：

```text
pocketlab.CoverFlow: [gbclab, gb, gbc, pocketlab]
pocketlab.GBA:       [gbalab, gba, pocketlab]
```

GBA BIOS 槽显式使用平台索引 1（`gba`）；菜单槽使用索引 0（`gbalab`）。GB/GBC 的菜单资源也依赖原平台顺序。平台关联会影响素材与保存目录，不能把它当成纯显示字段随意更换。[核心定义](https://www.analogue.co/developer/docs/openfpga/core-definition-files/core-json)

电脑保留两个局部候选：`.work/system-frontend/metadata-preview-1/` 仅有显示名修改；`.work/system-frontend/package-1/` 包含两个名称和两张黑底机型标志图，共四个平台文件、344,107 字节。后者的预览只是两张标志图拼接，不是 Pocket OS 截图或可操作首页。两包均未写卡；不将其作为本次图形首页目标的交付。

局部工具仅允许上述四个显示路径，合成文件验证已通过；没有进行实际 OS 显示或新一轮核心启动验收。GB/GBC 仍为共同入口，名称修改也不能使其分别直达不同菜单。

## GBA 动画与系统首页分别处理

[`cover_picker.sv`](../../core/src/core/cover_picker.sv)缓存封面并预取邻项，再逐帧移动、缩放和调整文字亮度。GBA [`gba_menu.sv`](../gba_menu/gba_menu.sv)每次隐藏画面、读取一整张 240×160 页面，等待上传完成才显示。这是菜单渲染方式的差别，与系统 Change Core 无关。

电脑上的淡入淡出候选已完成定向仿真及编译，但未安装；它不能替代封面移动。要接近 GB/GBC 的手感，需要拆分背景、封面和文字，设计小范围邻项缓存及逐帧位移，并验证读取等待、连续按键、首尾循环和返回行为。不能直接照搬整个 GB/GBC 绘图器：现有 GBA 的片内 RAM、逻辑和 DSP 余量不足，资源细节见[动画与面积研究](FEASIBILITY.md)。缓存容量、内存通路和时序仍需实际设计及测量。

## 后续门槛与安全边界

1. 图形主机首页：先找到受支持的 OS 主题／布局扩展或可审查的系统界面实现，再评估能否复用加载与 Change Core。当前证据不足以给出刷入候选或零风险承诺。
2. GBA 顺滑菜单：可在独立电脑副本继续研究元素绘制与缓存；通过像素、加载和游戏视频隔离验证，再完成布局布线及明确范围的实机验收。
3. 不为名称／标志图包要求重复插卡测试；其他机种仅在加载路径和保存行为明确后逐项接入。

本轮没有修改固件、设备卡或已验收核心。存储卡备份可恢复相应文件，不等于能恢复刷坏的机内固件。先前自动换核探针保留为[研究证据](NATIVE-CORE-ROUTING.md)，不继续追加同类实机测试。

## English

The requested first screen is a graphical console picker retaining native loading and Change Core. Inspected public APF documentation exposes platform metadata, page graphics and core settings, but no global OS layout/font/animation replacement hook. The offline four-file name/art package does not implement that picker and remains uninstalled. GB/GBC animates cached cover elements; GBA uploads whole menu pages. Matching that motion requires a new bounded cache/rendering design; the existing offline fade candidate is insufficient and has no hardware acceptance. No firmware, card or accepted core was modified. Routing evidence remains archived.
