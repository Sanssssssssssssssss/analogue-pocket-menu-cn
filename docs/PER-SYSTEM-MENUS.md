# 各机种独立的中文可视化菜单

2026-11-02 当前结果：GBA、NES、GG、SMS、SG-1000 独立候选均复用已认可的 CoverFlow，完成离线接口及完整编译／时序检查；尚未上机。见[完整交付状态](COMPLETE-DELIVERY.md)及[世嘉适配](../experiments/sega_coverflow/README.md)。本页其余内容保留早期反馈和备份证据；其中 `.4` 整页滑动、NES 静态页已经由 CoverFlow 候选取代。

2026-11-01，当前开发方向：保留官方 openFPGA 的机种入口与 Change Core；进入机种后，用该机种自己的原生 FPGA 核心显示中文游戏库。GB/GBC 和 GBA 分别维护，不继续合并入口或替换系统首页。

```text
官方 openFPGA 机种列表
  ├─ GB / GBC → 中文分类、封面选择 → GB / GBC 游戏
  ├─ GBA      → 中文分类、封面选择 → GBA 游戏
  └─ FC / NES 等 → 逐个适配各自核心（尚未完成）
```

openFPGA 是 Analogue 官方的核心开发平台；开发者可使用主 FPGA，Analogue OS 使用独立系统 FPGA。平台内的具体核心可来自社区。[官方架构](https://www.analogue.co/developer/docs/openfpga/overview)。本方案沿用官方选择和加载机种的流程，各核心中的中文菜单由本项目适配。

## 当前状态和顺序

| 机种 | 已有证据 | 下一步 |
|---|---|---|
| GB / GBC | 用户确认中文菜单、封面布局、游戏启动及目录切换闪白修复 | 作为菜单风格参考，保留可用版；加载时闪屏和更多保存场景仍待完善 |
| GBA | 用户确认 `0.2.0-gba.3` 中文菜单、游戏启动和显示名 | 完善独立菜单；先核实普通存档、RTC、保存后返回，再验证更顺滑的封面动画 |
| FC / NES | 已有离线页面、容器检查和上游加载入口测试 | 在独立副本接入实际游戏核心、封面、存档和返回；未有可安装菜单包 |
| SFC / SNES | 已有离线页面与上游加载器用例 | 在 NES 之后评估，保留原加载器对特殊芯片及 bitstream 的选择 |
| 其他机种 | 尚无完成声明 | 按实际核心逐个评估内存、加载、存档、视频和菜单资源 |

GB/GBC 目前共用已经验收的 GB/GBC 核心；GBA 使用自己的核心。此前共同 Pocket Lab 分组是已验收的系统关联记录，本轮未改卡。开发目标不再依赖该共同分组，也不把修改平台关联顺序当作纯显示操作。

## 可共用与需单独接入的部分

中文显示名、封面匹配、分类规则和黑底视觉可以共用工具与规范。实际绘图器、菜单与游戏的控制权交接、ROM／BIOS 加载、普通存档、RTC、暂停和返回由各核心分别处理；不能复制一份菜单配置就让所有机种可用。

GBA 当前上传整张页面；GB/GBC 缓存封面后逐帧移动、缩放。接近 GB/GBC 手感需要适合 GBA 资源预算的元素绘制与缓存。现有淡入淡出小样只保存在电脑，不是实机已安装功能，也没有实现封面运动，见[动画证据](../experiments/unified_frontend/FEASIBILITY.md)。

## 验证与备份

每个新机种先保留源码、资源和可用包，在独立电脑目录完成加载／像素／保存接口检查及完整布局布线、时序审阅，再准备独立测试入口。写卡前重新识别设备、备份受影响文件和重要存档，回读校验；游戏显示设置沿用用户当前要求。菜单截图、编译通过、启动游戏和实际保存返回分别报告。

本次仅更新电脑上的开发方向与文档，没有写卡、刷固件或修改已验收核心。先前[系统首页研究](../experiments/unified_frontend/SYSTEM-FRONTEND.md)和[自动换核探针](../experiments/unified_frontend/NATIVE-CORE-ROUTING.md)保留为历史依据。

## 同日后续：清理与首轮测试包

用户随后授权移除测试入口、测试各机种菜单与封面。已备份后移除 Route0～15 及其专用文件，共 201 个；4,420 个保护文件哈希未变。可用 GB/GBC、GBA 核心继续保留。相关源码、控制组和实机记录仍可在电脑备份及 Git 历史中查询。

卡内 GB/GBC 的 33 个可达页面、GBA 的 81 个页面与保留版本一致，未发现断开的文件链接。本轮 GBA 新增 9 个已核对原作的封面，修正一处把 Tootuff 误称为丁丁的显示别名；写入 5 张菜单资源页后回读全部 81 页，启动／存档／RTC 记录逐字节不变。GBA 当前 499 个游戏条目中 468 个有封面，31 个保留占位；GB/GBC 仍有未匹配封面来源的条目，不能声称全库图文已齐。

公开工具本轮 24 项通过、1 项因 Windows 符号链接权限跳过；GBA 工具 9 项、离线机种契约 18 项通过。另完成真实 GB/GBC 菜单 RTL 导航、GBA 控制／启动／38,400 像素输出检查；动画候选的游戏画面绕过复测通过。详细范围见[检查记录](build/per-system-qa-2026-11-01.json)。本轮未更新核心二进制或动画。

上机首轮只测 GB、GBC、GBA：各切换约 10 次，A 进入分类、B 返回，各启动一款游戏，记录黑屏、错图、闪白或按键卡住。之后再用无重要进度的 GBA 游戏验证游戏内保存 → L+R+Select → 保存并返回 → 再次启动；这不等同即时存档，优先保护《缩小帽》。新一轮实机反馈待收集，FC/NES、SFC/SNES 可视化菜单仍未完成。

## 本轮用户反馈与离线候选

用户确认 GB/GBC CoverFlow 在多次切换、进入／返回与游戏启动测试中稳定，未遇到本轮询问的黑屏、错图、闪白或按键卡住。GBA CN 菜单能够进入，动画仍未验收。此反馈不扩展为所有游戏、存档或 RTC 已通过。

已在备份后移除共同 Pocket Lab 分组：只更新两个本项目核心的关联元数据，删除一份共同平台元数据；4,416 个保护文件哈希未变。可用核心继续保留。用户提出拔卡后，后续开发只在电脑进行，没有继续写卡。

| 候选 | 目前范围 |
|---|---|
| [GBA 动画](../experiments/gba_menu/MOTION.md) | 小缓存保留旧封面，正反向 8 帧缓动整页滑动。完整编译和 104 条时序记录通过，最小 slack +0.080 ns；菜单像素、首屏及与可用版的游戏光栅对照通过。已打本地包，待实机。尚非 GB/GBC 的独立封面移动／缩放。 |
| [FC / NES](../experiments/nes_menu/README.md) | 原生菜单、独立普通存档接口及光栅已有离线检查；完整编译与 128 条时序记录通过，最小 slack +0.126 ns。已准备本地核心候选，实际卡目录生成与上机验证未完成，动画仍为静态。 |
| [SFC / SNES](../experiments/snes_menu/README.md) | 只适配标准 NTSC 游戏的原型；用原上游加载器判定映射和存档大小。完整编译有负时序余量，最小 −2.823 ns，因此没有安装包。特殊芯片和 PAL 继续使用原入口。 |

本轮没有安装上述候选。先在电脑完成 GBA 动画和新机种的验证，之后重新识别卡、备份，再准备一次上机测试；现有可用版可以继续使用。

FC/SFC 精选主目录的 83／27 个中文显示别名和 53 张封面已在电脑准备。别名与作品封面根据现有文件名／系列匹配，不能据此认证 ROM 的语言、版本或运行稳定性。完整范围见[本轮记录](build/per-system-development-2026-11-01.json)。

## English update

The user reports stable GB/GBC CoverFlow navigation and game launch in this round, and confirms that GBA CN opens while its animation remains unaccepted. The shared Pocket Lab grouping was removed after backup; 4,416 protected files stayed unchanged. Subsequent work is local only. A separate GBA slide renderer passed full-frame raster/cache comparisons, including full-depth game pixels. Native NES has one fitted candidate with positive inherited multi-corner timing, but no device or completed library/artwork acceptance. Standard-NTSC SNES remains blocked by negative timing and has no installable package. None of these new candidates has been installed.

## Earlier English overview

The active direction retains Analogue's native openFPGA platform list and Change Core. Each platform gets its own Chinese visual game menu inside its native core. GB/GBC and GBA remain separate implementations; no merged launcher or OS UI replacement is being pursued. GB/GBC menus and the GBA experimental menu/game launch have user reports; GBA save/RTC/return coverage is pending. NES/SNES have offline interface work only. Shared artwork/title tools do not remove platform-specific loading, rendering and save integration. The direction update was documentation only. A subsequent authorized cleanup removed Route0–15 after backup; nine GBA covers and one display alias were updated in five menu pages. All 81 GBA pages were read back and 4,420 protected files stayed unchanged. No game, save, core binary, firmware or animation updates were installed. The linked receipt separates computer checks from pending device feedback.
