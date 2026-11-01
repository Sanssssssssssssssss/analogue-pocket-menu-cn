# 各机种独立的中文可视化菜单

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

## English

The active direction retains Analogue's native openFPGA platform list and Change Core. Each platform gets its own Chinese visual game menu inside its native core. GB/GBC and GBA remain separate implementations; no merged launcher or OS UI replacement is being pursued. GB/GBC menus and the GBA experimental menu/game launch have user reports; GBA save/RTC/return coverage is pending. NES/SNES have offline interface work only. Shared artwork/title tools do not remove platform-specific loading, rendering and save integration. No card or firmware changes were made for this direction update.
