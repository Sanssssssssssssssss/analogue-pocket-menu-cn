# Pocket 完整前端交付

2026-11-16，本地 Windows 开发预览覆盖 19 组独立原生核心。打开 `PocketLab.exe`，选择卡，识别游戏库，准备并查看报告，再备份安装。助手可放在中文路径，无需安装 Python。公开稳定版为 GB/GBC。

文件名可以直接建库。助手按可核对的 ROM 信息、文件名和中文别名匹配显示内容，缺图时使用文字封面；封面不作为版本识别依据。中文名指菜单显示，游戏语言由用户提供的 ROM 决定。普通存档按各机种经核对的 ROM 或实例关联保留，有不同进度时请选来源。安装前备份，恢复时保留新进度。

| 机种 | 预览能力 | 已约束时序（离线） |
|---|---|---|
| GB / GBC | 封面动画、暂停、手动保存返回、灰度选项、恢复超时保护、版本匹配的 ROM 读取替换 | 116 条，+0.119 ns |
| GBA | [`.10` 封面动画](../experiments/gba_coverflow/README.md)、上传同步与有限重试、普通存档 | 104 条，+0.040 ns |
| FC / NES | 封面动画、版本匹配的 ROM 读取替换 | 128 条，+0.116 ns |
| GG / SMS / SG-1000 | 各自的核心、封面动画、匹配的 Sega 金手指 | 各 72 条，+0.100／+0.071／+0.046 ns |
| PCE | HuCard、SuperGrafx、版本匹配的读取替换、暂停并保存返回 | 64 条，+0.040 ns |
| MD / Genesis | NTSC、版本匹配的读取替换、暂停并保存返回，SVP 不提供暂停 | 112 条，+0.064 ns |
| SFC / SNES | `.3` 修正菜单刷新率，标准 NTSC、版本匹配的读取替换、暂停并保存返回 | 104 条，+0.086 ns |
| CPS2 | `.3` 修正原生路径读取、实例配置、EEPROM 读回与全片擦除，暂停并保存返回 | 124 条，+0.085 ns |
| WS / WSC | 原生双模式、封面菜单、独立 SRAM/EEPROM 与 RTC | 76 条，+0.109 ns |
| Supervision | 原生核心与封面菜单，无普通存档接口 | 104 条，+0.128 ns |
| Atari 2600 / 7800 | 原生核心与封面菜单，保留共享存档 | 76 / 84 条，+0.118 / +0.099 ns |
| Arduboy | 普通 HEX、独立 1 KiB EEPROM，FX 外置数据未适配 | 72 条，+0.068 ns |
| CPS1 / CPS1.5 | 原生实例、旧 128B EEPROM 导入、暂停保存返回、全片擦除修正 | 各 124 条，+0.061 / +0.036 ns |
| Pokémon Mini | 原生核心、封面动画、每个 ROM 独立 8 KiB EEPROM、暂停保存返回 | 104 条，+0.042 ns；外部 SRAM 另做独立读写复核 |
| Neo Geo | 原生实例、八帧封面动画、原格式 8 KiB 记忆卡和共享 64 KiB 备份 RAM | MVS/AES 共 472 条，+0.101 ns；SRAM、SDRAM、两片 CellRAM 另做独立预算复核 |

PCE CD、SFC 特殊卡带和 MD PAL 可由助手补装原作者入口。有可用原版核心时，助手会沿用它。PCE CD 需要受支持的 CUE/BIN 和自备 System Card BIOS。SFC 的 SA-1、Super FX、PAL 兼容性随原核心及具体游戏而定。MD PAL 使用 Spiritualized Genesis 1.0.8，安装时修正两处 JSON 末尾逗号，并加入线性 ROM 的 `.gen` 扩展名。[原作者发布](https://github.com/spiritualized1997/openFPGA-Genesis/releases/tag/1.0.8)

实机已反馈过旧版 GB/GBC、GBA、FC、GG 的菜单和启动。表中新增核心和功能需要统一上机验收。

GBA 中文菜单使用 `.10`。在助手的“图文、金手指与旧存档”页可选装即时存档或金手指原版核心，随后在 GBA 分组使用 Change Core。即时存档用 mincer-ray 的 Memories；金手指用 kroy 的匹配 `.gba.cht` 文件，在 Core Settings 里开启。原版和中文菜单使用各自的存档目录，助手会先备份已有普通进度。[mincer-ray 即时存档](https://github.com/mincer-ray/openfpga-GBA/releases/tag/v1.0.1) · [kroy 金手指用法](https://github.com/kroy-the-rabbit/openfpga-GBA-cheats/releases/tag/v0.9999.20260915)

GBA 中文核心的即时存档试验仍超过芯片容量。定时即时存档与 Lynx 未纳入本包。Neo Geo 中文菜单已完成离线时序和外部内存复核，使用及保存格式见[专页](NEOGEO.md)。新增机种、普通存档边界、Mini 的外部 SRAM 复核，以及 Arduboy/CPS 原生部分时钟和外部引脚尚未完整建模的范围，见[新增核心说明](ADDITIONAL-CORES.md)。

[显示风格](DISPLAY-STYLES.zh-CN.md)保留清晰、原比例的默认值。金手指仅导入明确匹配版本的配置。PCE 暂停停住 CPU，部分定时器和音频芯片继续运行。Windows 以外的系统可用[整批命令行工具](BATCH-UPDATE.md)。

## 成品标准

- 视觉基准是冻结的 `core/src/core/cover_picker.sv`：封面独立移动、缩放、明暗、倒影、标题与分类交互。整页滑动不符合要求，`0.2.0-gba.4` 仅保留为历史原型，停止作为交付候选。
- 各机种使用自己的原生核心，沿用官方 openFPGA 和 Change Core；共用 CoverFlow 绘制逻辑。系统固件不在修改范围内。
- 以最后接卡确认的实际游戏库为准。中文显示名与实际路径分开，作品主入口中文优先，保留备选和恢复映射。缺图、别名推断和改版分别记录。
- 用户可直接用自己的文件名建库，封面与别名可选。[通用生成入口](FILENAME-MENUS.md)覆盖包内 19 组核心，生成整批首装、同核心刷新和配套 GBA 升级所需的配置。
- 金手指必须有运行它的核心、匹配版本和无冲突配置。仅有 `.cht` 文件不能算生效；无法核对或核心不支持的条目不自动启用。
- 屏幕风格在各核心可用能力内整合。默认原比例、居中、无外框；GBA 清晰且无 LCD 网格。可选风格不改变已有默认设置。
- 每个可交付机种都需要加载／返回／存档／输入／视频检查、完整布局布线与时序检查、局部备份、回读和回退。离线结果、实机启动和实际游玩分别记录。
- 资源不足、缺源代码或仍不稳定的机种保留原入口，写清原因，不加入可安装成品包。最终统一请求一轮实机验收，不把零散原型当成完成品。

## 辅助工具

[Pocket Sync](https://github.com/neil-morrison44/pocket-sync) 的 v7.2.0 官方说明及下载包身份已核对，支持桌面中文及备份管理；首次连接会写 `pocket_sync.json`，开发时先使用电脑副本。[使用边界](POCKET-SYNC.md)说明了为何 core-only ZIP 不能替代本项目的 F1→F2 更新。社区 [openFPGA Validator](https://github.com/neil-morrison44/openfpga-validator) 固定版本 `0.7.0` 用于校验打包格式。两者不能替代本项目的原生绘制、游戏加载或硬件验证。

私人游戏目录、版本匹配、工具下载和交付状态保存在游戏实验室 `AnaloguePocket/2026-11-02-complete-frontends/`，不进入公开仓库。公开证据只包含合成用例、源码、编译与已明确范围的设备报告。

## English

The local Windows preview bundles 19 native CoverFlow menu groups, including the offline-validated Pokemon Mini and Neo Geo candidates. Select the card, inspect it, prepare the library, review the result, then back up and install. Filename menus work offline. Artwork and Chinese aliases can be matched from online sources. Ordinary saves follow each core's verified ROM or instance bindings. PCE CD, special SNES cartridges and PAL MD are available through original companion cores. Neo Geo's original save formats and inherited timing boundaries are documented in [its guide](NEOGEO.md); device acceptance remains pending.

The table lists the offline build results. New candidates still need Pocket testing. The GBA CoverFlow build uses ordinary saves. The assistant can optionally install the original mincer-ray Memories and kroy cheat cores for use via Change Core. They use the standard GBA save directory, while CoverFlow uses its own. The combined GBA Memories prototype exceeds logic capacity. Periodic state saves are outside this package.

Neo Geo 已加入本轮预览，使用原生引擎、原实例及保存格式；两模式时序和外部内存检查通过，实机待验收。[使用与验证范围](NEOGEO.md)。
