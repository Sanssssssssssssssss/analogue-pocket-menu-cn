# NeoGeo 街机原生 CoverFlow 研究

已完成原生基线与建库核对。SDRAM 针脚和配置跨域时序仍未达到交付要求，中文 CoverFlow 保留为研究项目，尚无可安装的菜单包。

`library.py --source <卡的本地副本> --out <新的输出目录> --titles <可选中文名称JSON>` 已实现普通核心实例的建库。它解析每个实例真正引用的分区文件和控制寄存器，生成 `GBAF2/ng` 页面及 `NGP1` 加载计划；不会复制 ROM 或 BIOS。缺少封面时显示名称卡片。仅有这些数据文件尚不能在 Pocket 上运行，需要通过验证的菜单位流。

记忆卡沿用 `Saves/ng/Mazamars312.NeoGeo/<实例相对路径>.sav` 的 8 KiB 格式；备份 RAM 沿用 `Saves/ng/common/backup.bak` 的 64 KiB 共享文件。已有进度只读取核对；缺失文件生成原格式的全 `FF` 初始内容。Overdrive 存档不自动改名导入。

对接函数为 `available_instances()`、`build()`、`validate_manifest()`、`validate_pages()`、`existing()`。校验覆盖实例到 ROM/BIOS/保存文件的完整对应、菜单路径闭包和种子内容，并重新保护用户游玩后发生变化的保存文件。无效实例在 `excluded` 中记录原因，不静默加入不能启动的入口。

源码固定为 [`Mazamars312/Analogue_Pocket_Neogeo@988163bc`](https://github.com/Mazamars312/Analogue_Pocket_Neogeo/tree/988163bcf725271d05858e86ac7bfe48853b938b)。`Neogeo.sv` 的 Furrtek 引擎为 GPL-2.0-or-later，JT12/JT49 保留各自 GPL 许可，APF 保留官方条款；仓库根目录没有统一 LICENSE，不据此抹去文件内许可。

原核心的游戏格式为 APF JSON 实例和 Darksoft 分区文件：`prom`、可选 `prom1`、`srom`、`crom0`、`m1rom`、`vroma0`。另需用户自己的 `uni-bios_4_0.rom`、`000-lo.lo`、`sfix.sfix`。`.neo` 文件和 NGPC 是不同输入，不以改扩展名方式兼容。

已确认的接口边界：

| 资源 | 原生用途 | 菜单接入考虑 |
| --- | --- | --- |
| SRAM | 68K 工作 RAM；复位期间原控制器持续写入初始化图案 | 可评估菜单/游戏互斥复用；切换必须先停止封面读取，再完成工作 RAM 初始化 |
| CRAM0 | 程序、BIOS、SROM、Z80 ROM | 保留原加载器和地址掩码 |
| CRAM1 | ADPCM / 音频数据 | 保留原加载器和 V1/V2 偏移 |
| SDRAM | 最大 64 MiB CROM | 保留原加载器和精灵访问 |
| M10K | 8 KiB 记忆卡、64 KiB 备份 RAM | 保留原双端口保存格式和 Stop 后宿主读取 |

原 PLL 的实际 MVS 时钟约为 96 MHz / 6 MHz，AES 模式会重配。不能只按端口名称假设频率。原视频配置已有八个 scaler 槽；可评估复用原 320×224 槽，使用与现有 CoverFlow 相同的动画计算并适配较小画面高度。游戏内暂停返回暂不作为接入前提。

`compile.sh <源码目录> <新输出目录>` 使用固定 Quartus 22.1 Docker 完整编译，限 3 CPU / 5 GB。输入输出限于本机 `.work/repair-20261115/neogeo/`，不写卡。原始 archive 和逐文件 SHA256 保存在私有任务目录。资源、实际总线归属、完整游戏加载与两类保存通过前，不登记安装入口。
