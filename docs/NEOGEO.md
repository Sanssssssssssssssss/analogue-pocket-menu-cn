# Neo Geo 中文 CoverFlow

本页用于 `v0.6.0-preview.1` 中的原生 Neo Geo 中文菜单。离线菜单、加载、内存和时序检查已通过；Pocket 上的启动、游玩、声音及保存仍待验收。

## 使用

1. 保留原 Neo Geo 游戏目录、JSON 实例和自备 BIOS。在 PocketLab 助手中选择这次连接的卡与电脑工作目录，识别并勾选 Neo Geo。
2. 准备游戏库，查看缺少文件或不支持格式的提示。文件名可直接显示，也可提供中文别名和封面；缺图显示文字卡片。
3. 使用“备份并安装”，完成后安全弹出卡。Pocket 关机插卡，进入 **openFPGA → CN Menu → NeoGeo**。若没有分类，在 **Settings → Analogue OS → Group openFPGA** 开启分组。

左右滚动封面，A 进入目录或启动，B 返回上级。游戏启动后，使用 Pocket 系统菜单 Quit，再 Run 返回选单。新增、改名、移动游戏或实例后，重新准备并更新菜单。

## 游戏格式

使用原核心 `Assets/ng/Mazamars312.NeoGeo/` 下的 APF JSON 实例，游戏分区在 `Assets/ng/common/`。助手读取实例声明的分区路径和控制寄存器；不会只根据文件名猜测装载设置。

原生分区包括 `prom`、可选 `prom1`、`srom`、`crom0`、`m1rom`、`vroma0`。另需自备 `uni-bios_4_0.rom`、`000-lo.lo`、`sfix.sfix`。`.neo`、街机 ZIP 和 Neo Geo Pocket 游戏不能通过改扩展名加入。

中文菜单名与 ROM 内文的语言分别处理。封面只表示作品，不能用于判断改版、版本、金手指或存档兼容性。

## 存档与设置

沿用原核心两类文件：

| 类型 | 原路径和格式 |
|---|---|
| 记忆卡 | `Saves/ng/Mazamars312.NeoGeo/<实例相对路径>.sav`，8 KiB；将实例路径末尾的 `.json` 换成 `.sav` |
| 共享备份 RAM | `Saves/ng/common/backup.bak`，64 KiB |

已有进度优先保留。缺失文件在电脑准备阶段生成全 `FF` 初值，安装时仅发布仍不存在的文件。核心运行时读取现有文件，缺失或读取失败会停止装载。Overdrive 的存档不自动改名导入。即时存档和休眠现场不能按普通存档处理；新预览的保存行为仍需实机验收。

保留上游输入、音频、游戏显示模式和受支持的实例设置。菜单适配原 320×224 显示区域，共用现有八帧 CoverFlow 动画；进入游戏后交回原生 FPGA 引擎。

## 源码与验证

原生引擎固定为 [Mazamars312/Analogue_Pocket_Neogeo@988163bc](https://github.com/Mazamars312/Analogue_Pocket_Neogeo/tree/988163bcf725271d05858e86ac7bfe48853b938b)。包内附实际编译输入、许可、构建说明及对应检查收据。

离线验证分别覆盖菜单像素、APF 文件装载、退出及迟到响应、保存读取、真实 68000 工作 RAM 操作，以及 MVS/AES 时序。它们不能替代 Pocket 上的启动、游玩、声音和保存验收；上游事件时钟逻辑的原有覆盖限制在回执中列出。

需要自行重编译时，一起阅读包内 `sources/BUILD-NEOGEO.txt` 和 `sources/BUILD-REANALYSIS.md`。源码保留实际拟合输入，另附检查断言修正及完整复核工具；原完整编译退出 3 和之后成功的重新分析分别记录。两种模式、四角共 472 项时序记录的 endpoint TNS 为零，最小实际余量 +0.101 ns；SRAM、SDRAM 和两片 CellRAM 预算分别通过。1121 项继承的事件时钟边界和未测板级条件保留说明，不代表整个原生引擎已完成物理验收。构建 ID 和布局会变化，新位流必须重新核对，不能沿用本次收据。
## English quick start

Supply the original APF JSON instances under `Assets/ng/Mazamars312.NeoGeo/`, their Darksoft partitions under `Assets/ng/common/`, and your own BIOS. Select Neo Geo in PocketLab, prepare the library, inspect the plan, then back up and install. After safe ejection, power off the Pocket before inserting the card and open **openFPGA → CN Menu → NeoGeo**.

Left/right scrolls, A opens or launches, and B returns. Use Pocket Quit then Run to return from a game. Rebuild after moving, renaming or adding files. Existing 8 KiB per-instance memory cards and the shared 64 KiB `backup.bak` are retained. Missing files receive erased seeds only if still absent at installation. `.neo`, arcade ZIP and Neo Geo Pocket files are different formats. ROMs, BIOS and personal library data are not distributed.

The review covers both native modes, four corners, actual SRAM/SDRAM/CellRAM paths, and 472 timing records with zero endpoint TNS. The original failed guard analysis is archived separately from the successful post-fit review. Inherited event-clock and board assumptions remain explicit; device acceptance is pending. Read both bundled BUILD documents before rebuilding.
