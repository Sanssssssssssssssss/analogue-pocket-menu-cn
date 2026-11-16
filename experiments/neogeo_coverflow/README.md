# Neo Geo 原生 CoverFlow

原生开发预览已接入 320×224 中文封面菜单、多槽装载和原格式存档。[使用说明与验证边界](../../docs/NEOGEO.md)列出游戏格式、BIOS、操作和实机待验收项。

`library.py` 解析 `Assets/ng/Mazamars312.NeoGeo/` 下的原 JSON 实例，核对其分区、控制寄存器及保存文件，生成 `GBAF2/ng` 页面和 `NGP1` 计划。名称可用原文件名或可选中文映射，缺图显示文字卡片；新增、改名或移动文件后重新建库。不会复制 ROM 或 BIOS。

接口为 `available_instances()`、`build()`、`validate_manifest()`、`validate_pages()`、`existing()`。无效实例会给出排除原因；已有进度优先保留，缺档种子仅在目标仍不存在时安装。

游戏使用 [Mazamars312 Neo Geo](https://github.com/Mazamars312/Analogue_Pocket_Neogeo/tree/988163bcf725271d05858e86ac7bfe48853b938b) 原生引擎。中文菜单与工作 RAM 互斥使用 SRAM，游戏启动前完成交接与初始化；原生 BIOS、图像、音频分区及 8 KiB/64 KiB 保存格式保留。

发布包的 `packages/NEOGEO/sources/` 提供实际编译源与 `BUILD-NEOGEO.txt`、`BUILD-REANALYSIS.md`。原拟合输入与后续约束检查修订分别记录。每个新位流须重新完成相应时序和针脚复核，旧收据不能自动批准新拟合。上游 GPL、FX68K、APF 和 IP 通知保留。
