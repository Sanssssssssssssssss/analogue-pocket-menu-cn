# Pocket 完整前端交付

2026-11-03，交付继续进行。FC/NES、GG 已获单机菜单、动画和基本启动反馈；GBA 恢复可用 `.3`，CoverFlow 继续离线适配。[最新设备反馈与修正](DEVICE-FEEDBACK-2026-11-03.md)优先于早期候选记录。公开工具支持 GB/GBC、GBA、NES、GG、SMS、SG-1000，公开稳定版仍为 GB/GBC。

| 机种 | 当前系统层结果 | 待验收／功能边界 |
|---|---|---|
| GB / GBC | 保留已验收绘制；新增显示模式元数据候选 | 新图文与显示外观待核对；此 UI 核心无集成金手指引擎 |
| GBA | 已恢复用户确认可用的 `.3`；`.6` 实机进入子目录后无封面、按键无响应 | `.5`／`.6` 拒绝重装；首屏／像素／时序通过不能代表子目录可用，继续离线修复；无集成金手指引擎 |
| NES | `.2` 共用 CoverFlow，128 条时序通过，+0.056 ns；单机基本启动／动画反馈正常 | 中文名、封面待补齐；全库游戏／保存未验证；无集成金手指引擎 |
| GG / SMS / SG-1000 | 各自原生核心，72 条时序通过，+0.100／+0.071／+0.046 ns；GG 单机基本启动／动画反馈正常 | SMS／SG-1000 仍无实体反馈；全库游戏、代码效果、保存耐久性待验收；新入口关闭 Memories／休眠 |

PCE、MD、WonderSwan 本批保留原入口：加载／暂停／存档／视频适配未完成验证。SNES 原型时序失败且特殊芯片选择不完整。Atari 2600/7800、Coleco 现有公开入口缺少可适配 RTL。它们不进入本批新菜单安装包，也不承诺后续一定可实现。

实际版本不符的汉化／改版不自动套金手指。显示风格通过[官方可选显示模式](DISPLAY-STYLES.zh-CN.md)集成，默认清晰、原比例；系统滤镜选择由 Pocket OS 管理。中文名／封面生成与校验不认证 ROM 汉化质量或完整游戏兼容性。

[整批更新工具](BATCH-UPDATE.md)可按当前卡统一准备六个组件：任何预检失败都不发布写卡计划；写入前局部备份并复核 ROM，菜单回退保留新旧进度。GB/GBC 与 GBA 的更新沿用现有默认画面、图标和 scaler，追加受支持的可选显示风格。当前离线包仍需实际卡核对及统一上机验收。

## 成品标准

- 视觉基准是冻结的 `core/src/core/cover_picker.sv`：封面独立移动、缩放、明暗、倒影、标题与分类交互。整页滑动不符合要求，`0.2.0-gba.4` 仅保留为历史原型，停止作为交付候选。
- 各机种使用自己的原生核心，沿用官方 openFPGA 和 Change Core；共用 CoverFlow 绘制逻辑。系统固件不在修改范围内。
- 以最后接卡确认的实际游戏库为准。中文显示名与实际路径分开，作品主入口中文优先，保留备选和恢复映射。缺图、别名推断和改版分别记录。
- 陌生用户用自己的 ROM 文件名也能建库，中文直接显示，封面与别名可选。[通用生成入口](FILENAME-MENUS.md)覆盖六组格式并自动生成整批配置；统一首装、同核心安全刷新及旧 GBA 配套升级已接通。软件流程、实体启动与实际游玩分别验证，不能用私人配置替代公共上手体验。
- 金手指必须有运行它的核心、匹配版本和无冲突配置。仅有 `.cht` 文件不能算生效；无法核对或核心不支持的条目不自动启用。
- 屏幕风格在各核心可用能力内整合。默认原比例、居中、无外框；GBA 清晰且无 LCD 网格。可选风格不改变已有默认设置。
- 每个可交付机种都需要加载／返回／存档／输入／视频检查、完整布局布线与时序检查、局部备份、回读和回退。离线结果、实机启动和实际游玩分别记录。
- 资源不足、缺源代码或仍不稳定的机种保留原入口，写清原因，不加入可安装成品包。最终统一请求一轮实机验收，不把零散原型当成完成品。

## 辅助工具

[Pocket Sync](https://github.com/neil-morrison44/pocket-sync) 的 v7.2.0 官方说明及下载包身份已核对，支持桌面中文及备份管理；首次连接会写 `pocket_sync.json`，开发时先使用电脑副本。[使用边界](POCKET-SYNC.md)说明了为何 core-only ZIP 不能替代本项目的 F1→F2 更新。社区 [openFPGA Validator](https://github.com/neil-morrison44/openfpga-validator) 固定版本 `0.7.0` 用于校验打包格式。两者不能替代本项目的原生绘制、游戏加载或硬件验证。

私人游戏目录、版本匹配、工具下载和交付状态保存在游戏实验室 `AnaloguePocket/2026-11-02-complete-frontends/`，不进入公开仓库。公开证据只包含合成用例、源码、编译与已明确范围的设备报告。

## English

Active goal: deliver the supported native-core menus together, reusing the accepted GB/GBC CoverFlow visuals, with Chinese titles, artwork, library organization, supported version-matched cheats and display-style integration. The whole-page GBA slide is superseded by the user's explicit feedback. No firmware replacement or merged cross-core launcher is being pursued. Work is offline until the final card verification. Unsupported or unstable platforms keep their original entry and are excluded from the installable delivery. Simulation, fitting/timing, device launch and play/save acceptance remain separate gates.
