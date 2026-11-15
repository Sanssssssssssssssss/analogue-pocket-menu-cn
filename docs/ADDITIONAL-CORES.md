# 更多原生中文菜单

2026-11-15 开发批次适配下列原生菜单，复用 GB/GBC 的 CoverFlow 几何、封面滚动和中文标题层。2026-11-16 增加 Pokémon Mini 预览。新增候选须完成编译、总线及文件流程检查后才登记到安装助手；实机游戏、存档和显示仍需分别验收。Neo Geo 暂保留研究源码，不提供中文菜单核心包；可继续使用上游原版核心。

## 入口与游戏目录

| 助手机种 | 原游戏目录，允许子目录 | 文件 | 普通存档与必要文件 |
|---|---|---|---|
| WS | `Assets/wonderswan/common` | `.ws`、`.wsc` | 自备 `bw.rom` 4096 字节和 `color.rom` 8192 字节；每款游戏独立 SRAM/EEPROM，加 12 字节 RTC |
| SUPERVISION | `Assets/supervision/common` | `.sv`、`.bin` | 上游引擎没有普通存档接口，无需 BIOS |
| ATARI2600 | `Assets/2600/common` | `.a26`、`.bin` | 保留原生共享 SaveKey、FA2 文件；部分游戏需要原核心所需的固件 |
| ATARI7800 | `Assets/7800/common` | `.a78`、`.a26`、`.bin` | 保留原生共享 SaveKey、FA2、High Score Cartridge 文件及原生固件槽 |
| ARDUBOY | `Assets/arduboy/common` | 普通 `.hex`，FX 外置数据未适配 | 每款游戏独立 1024 字节 EEPROM；旧全局 EEPROM 不会自动覆盖到每款游戏 |
| CPS1 / CPS15 | `Assets/jtcps1/common`、`Assets/jtcps15/common`，配合各自 `Assets/<平台>/jotego.<平台>` 中的实例 JSON | 实例所引用的 `.rom` | 识别实例的 ROM、按键、DIP 和核心配置；核对旧 128 字节 EEPROM 后，复制到独立存档。已有独立存档优先保留 |
| POKEMINI，预览 | `Assets/poke_mini/common` | `.min` | 内置上游 freebios；每款游戏独立 8192 字节 EEPROM，缺档才生成擦除态种子；旧档不猜测导入 |
| NEOGEO，研究阶段 | `Assets/ng/common` 和 `Assets/ng/Mazamars312.NeoGeo` | 原生多槽实例 JSON | 已实现实例、BIOS 和存档路径核对；新菜单硬件时序未通过，不提供核心包 |

ROM 文件名默认直接成为标题，原有分类目录继续成为子菜单。街机从原实例读取游戏名与配置，不能把所有 ROM 当成相同硬件设置。可选中文别名和封面按相对路径匹配；缺图生成文字卡片。每页至多 127 个游戏加返回，超量自动分页。添加、删除、改名后重新建库；核心尚不在运行时扫描任意文件夹。

Windows 助手中选择有游戏的机种，准备后执行“备份并安装”。源码用户也可运行：

```powershell
python tools/build_menus.py --card X:/ --packages ./packages --systems WS SUPERVISION ATARI2600 ATARI7800 ARDUBOY --out D:/PocketMenus/new-library
python tools/delivery.py prepare --card X:/ --config D:/PocketMenus/new-library/delivery.json --staging D:/PocketMenus/prepared
```

后续安装和回退见[批量更新说明](BATCH-UPDATE.md)。盘符、输出目录需替换；只选择卡上实际有游戏且包内提供的机种。安装会先核对文件和备份现有进度，新增独立存档只在目标不存在时建立。原模拟器存档格式不能自动视为兼容。

## CN 菜单单独显示

打开 **Settings → Analogue OS → Group openFPGA**，所有本项目菜单归入 **CN Menu** 分类，原版核心仍使用原分类。这使用官方平台分类，不移动 `Cores` 子目录，也不改变 ROM 和存档的关联路径。

新批量安装统一使用该分类。已有菜单可以运行一次：

```powershell
python tools/group_cn_menus.py apply --card X:/ --backup D:/PocketBackups/cn-group-1
```

回退分类将 `apply` 改为 `restore`，沿用同一备份目录。此操作只更新平台 JSON；已连接的实体卡仍须重新识别。

## 验证与限制

完整 Quartus 编译检查资源、所有器件角的已约束时序。APF 总线、目录导航、图像传输、ROM 加载和普通存档分别用合成数据验证。离线检查不能证明游戏已在 Pocket 上玩通；结果包附有位流和对应源码校验值。

Pokémon Mini 预览修复原生除法及 LCD 颜色运算的长路径，保留原时钟、CPU 节奏及 3:2 游戏显示。完整四角时序最低 +0.042 ns；穷举除法、逐拍 CPU/视频、117 帧真实 APF 导航、EEPROM 和安装回退验证通过。封面 SRAM 独立审查扣除发收时钟插入差后最小余量 7.749 ns，未含未测板线/负载和未配置的时钟不确定度。游戏中 L+R+Select 可暂停或保存返回；没有即时存档与睡眠支持。需自备 `.min`，包不带游戏；实机游玩与保存仍待验收。详见[Mini 构建与验证](../experiments/pokemonmini_coverflow/README.md)。

Neo Geo 已完成多槽游戏实例和原生存档绑定工具。独立修正内存时钟后，四角检查仍有 SDRAM 输入 setup −2.150 ns、输出 hold −0.976 ns，以及未闭合的配置跨时钟路径，所以未登记中文菜单位流。不要把建库成功理解为硬件菜单可用。

Arduboy 保留上游的一个软件 OLED SPI 时钟，CPS 保留部分上游音频及视频逻辑时钟；这些路径仍有未完整建模的边界。收据中的正时序余量覆盖实际已约束路径，不等于全部电路的物理签核。新增总线、存档和参数读取分别通过真实 RTL 接口的合成数据仿真，不能替代原生游戏实机验收。

Atari 使用 Pocket 系统的 Quit 退出，保留共享存档机制；没有加入每游戏独立 SaveKey 或新暂停层。7800 已用满八个显示槽，菜单复用原 PAL 槽，原游戏显示模式全部保留。这批新增机种没有新增金手指引擎，也不宣称即时存档通用。

NGPC、Lynx、Vectrex 和 PCE CD 尚未提供新的 CoverFlow 包：分别还受资源/时序、来源许可核对、非通用分发条款、持续光盘读取适配限制。它们不是隐藏的已完成机种。上游原核心可以继续独立使用。

## English

This batch adapts the native menu integrations listed above. The 2026-11-16 Pokemon Mini preview fixes the native divider and LCD paths and passes four-corner compilation, CPU/video equivalence, APF navigation, EEPROM and synthetic installer checks. Physical gameplay and saves remain pending; its external SRAM review excludes unmeasured board/loading and unconfigured clock uncertainty. Supply your own `.min` games. Neo Geo remains source research without a Chinese menu package while its SDRAM and configuration timing is unresolved. Use the original asset directories and rebuild libraries after changing files. Filenames supply titles; optional path-based aliases and covers are supported. Arcade menus read original instance configurations. Missing covers get text cards. Select only systems with games and matching packages.

Enable **Settings → Analogue OS → Group openFPGA** to collect these entries under **CN Menu**. The group uses official platform metadata; core folders and save bindings retain their original locations. The grouping command backs up changed platform files and supports `restore`.

New packages require complete FPGA builds and bus/file checks before registration. Physical gameplay, saves and display remain pending. Atari preserves native shared saves and uses Pocket Quit. Supervision exposes no ordinary-save interface. WS, Arduboy and Pokemon Mini use isolated, content-based save names; old formats are not guessed or overwritten. No new cheat or generic savestate engine is implied. See the table for BIOS requirements and the corresponding-source receipts in each package.

CPS1/CPS1.5 retain each original instance's ROM, controls, DIP settings and core mode. A verified native 128-byte EEPROM can seed a missing isolated save; an existing isolated save always takes precedence. Arduboy's inherited software OLED SPI clock and some inherited CPS audio/video clocks remain outside complete timing coverage. Positive receipt margins describe constrained paths, not a full physical sign-off.
