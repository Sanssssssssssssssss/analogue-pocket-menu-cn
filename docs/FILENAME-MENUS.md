# 用自己的 ROM 文件名生成菜单

开发分支支持一条命令扫描自己的游戏目录，为已有十组及[新增原生机种](ADDITIONAL-CORES.md)生成 CoverFlow 菜单。Pokémon Mini 和 Neo Geo 仅有建库实验，尚无可安装的中文菜单核心。默认显示去掉扩展名的 ROM 文件名，支持中文、英文和常见日文。缺图时生成文字封面。字库外字符以占位符显示，原始路径继续用于启动游戏。

在源码目录安装依赖，再指定卡、核心包与电脑上的新输出目录。

```powershell
python -m pip install -r requirements.txt
python tools/build_menus.py --card X:/ --packages ./packages --out D:/PocketMenus/my-menus
```

把 `X:/` 换成实际卡路径，也可读电脑上的卡目录副本。macOS 和 Linux 使用对应的本地路径。工具会扫描这些目录及其子目录。

| 菜单组 | 游戏目录 | 输出格式 |
|---|---|---|
| GB / GBC | `Assets/gb/common`、`Assets/gbc/common` | v9 |
| GBA | `Assets/gba/common` | GBAF2 |
| FC / NES | `Assets/nes/common` | GBAF2/NES |
| GG | `Assets/gg/common` | GBAF2/Sega |
| SMS | `Assets/sms/common` | GBAF2/Sega |
| SG-1000 | `Assets/sg1000/common` | GBAF2/Sega |
| PCE / SuperGrafx | `Assets/pce/common` | GBAF2/pce |
| MD / Genesis | `Assets/genesis/common` | GBAF2/genesis |
| SFC / SNES | `Assets/snes/common` | GBAF2/SNES |
| CPS2 | `Assets/jtcps2/jotego.jtcps2` 中的实例、`Assets/jtcps2/common` 中的 ROM | GBAF2/jtcps2 |
| WS / WSC | `Assets/wonderswan/common` | GBAF2/wonderswan |
| Supervision | `Assets/supervision/common` | GBAF2/supervision |
| Atari 2600 / 7800 | `Assets/2600/common`、`Assets/7800/common` | GBAF2/2600、GBAF2/7800 |
| Arduboy | `Assets/arduboy/common` | GBAF2/arduboy |
| CPS1 / CPS1.5 | `Assets/jtcps1`、`Assets/jtcps15` 中的原生实例和其 `common` ROM 目录 | GBAF2/jtcps1、GBAF2/jtcps15 |
| Pokémon Mini，开发预览 | `Assets/poke_mini/common` | GBAF2/poke_mini；实机待验收 |
| Neo Geo，研究阶段 | `Assets/ng/Mazamars312.NeoGeo` 中的实例、`Assets/ng/common` 中的 ROM | GBAF2/ng；无可安装中文菜单核心 |

例如 `Assets/gba/common/冒险/我的游戏.gba` 默认显示“我的游戏”。添加、删除或改名后，改用新输出目录重新执行命令。只生成指定机种可加 `--systems GB-GBC GBA NES GG`。

常见作品系列文件夹会显示中文，例如 `01.Zelda` 显示“塞尔达传说”，编号和实际目录不变。PCE、MD、SFC、CPS2 还可选用 `--groups groups.json` 修正菜单分类；文件内容是卡相对游戏路径到虚拟文件夹的映射，例如 `{"Assets/pce/common/旧分类/排球.pce":"5.SPORTS RACING"}`。它只改变菜单树，保留 ROM 路径和存档绑定；同一目录里内容与运行配置完全相同的重复项只显示一次，原文件仍纳入校验。

输出的 `menus.json` 汇总机种、警告和排除项，`libraries/<组名>/library-manifest.json` 记录 ROM 身份和校验值。使用 `--packages` 时会自动填入核心包目录，再用生成的 `delivery.json` 执行[整批预检与备份安装](BATCH-UPDATE.md)。

PCE 支持 HuCard 和 SuperGrafx 卡带，MD 支持 NTSC 线性卡带镜像，SFC 支持标准 NTSC LoROM、HiROM、ExHiROM。CPS2 读取原版 Jotego `.json` 中的 ROM、按键和 DIP 配置。缺少按键映射时使用 JTFRAME 默认映射。找不到对应 ROM 或实例校验值不符时，工具会在报告里列出该条目。CPS2 默认显示实例文件名，别名和封面按实例路径匹配。 [Jotego 安装说明](https://github.com/jotego/jtbin/wiki/Analogue-Pocket-Cores)

GBA 新建库按每页最多 127 项加返回自动分页，保留生成的中文页名。已有 F1 和 F2 菜单可在核对游戏与存档绑定后随核心一起更新。GB/GBC 单页上限 2047 项，过大的目录需再分子目录。NES 与世嘉的容量限制见各实验说明。

可选参数：`--covers my-covers` 按卡相对路径寻找 PNG（例如 `my-covers/Assets/gba/common/冒险/我的游戏.png`）；`--titles names.json` 读取卡相对 ROM 路径到显示名的 UTF-8 对照。二者都不必逐游戏配置。GB/GBC 优先读取卡上已有的 `gbclab/common/gbc_bios.bin` 或 `gbc/common/gbc_bios.bin`，也可用 `--bios` 指定自己的 2304 字节 BIOS。工具不分发 BIOS，未提供时仍可生成 GB/GBC 菜单，但不能作为完整可运行安装。

GBA 安装要求卡上已有自己的 `Assets/gba/common/gba_bios.bin`，大小 16384 字节。核心的 BIOS 槽按平台索引 1 指向 `gba`；规则见 [Analogue 官方文件槽说明](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json)。预检记录 BIOS 身份，文件在安装前改变会停止；文件大小本身不认证内容。

在 Windows 助手的“图文、金手指与旧存档”页可以选版本索引。命令行用 `--cheats my-cheats.json` 和对应的 `--packages`。GG／SMS／SG-1000 使用 [SEGA-CHEATS1](../experiments/sega_coverflow/README.md)；GB/GBC、FC、PCE、MD、SFC 的新候选使用 `POCKET-CHEATS1`。后者只接受 ROM 读取替换，按完整 SHA-256 和长度绑定，每个版本一至两项，最多 16 条替换。用[格式定义](../tools/native_cheats.py)核对字段。

匹配成功的条目在游戏启动时加载。刷新时，助手会保留仍然匹配的现有代码；准备结果会列出命中的版本数量。没有可靠的版本匹配时，游戏仍可按原文件名进入菜单。

Windows 助手默认在报告里列出文件头无效的 GBA ROM，以及容量超出 336 字节至 8 MiB 范围的 GB/GBC ROM，并跳过这些游戏。命令行需要加 `--skip-invalid` 才会跳过；原文件保留，排除原因和校验值写进清单。GG 接受标准 `.gg`，并识别部分传统 `.sms` 扩展名的 GG 镜像；普通 SMS 镜像不会因此加入 GG 菜单。硬件头也存在例外，《Excellent Dizzy Collection》的 GG 版本通过完整已知校验值识别，来源为 [No-Intro 数据库](https://github.com/libretro/libretro-database/blob/da577d2865c2b1b834b2d5f2fd1368fc5110a01c/metadat/no-intro/Sega%20-%20Game%20Gear.dat)，不能仅凭扩展名或平台位断言机种。

此命令只在电脑生成菜单。安装时仍须使用匹配格式的核心、当前卡版本核对和备份工具，见[整批更新](BATCH-UPDATE.md)。它没有实现核心运行时自动扫描目录，也没有自动导入其他模拟器存档。公共稳定二进制仍限 GB/GBC；其他候选的实际游戏、存档和新动画需要设备验收。

菜单共用首次安装和同一核心版本的刷新流程。使用内容哈希存档的机种，改名后相同 ROM 继续对应同一存档；Atari 保留原生共享存档。CPS2 还按实例的有效设置区分存档。旧式存档命名或原路径下 ROM 内容变化需要明确迁移。匹配的 GBA 升级可同时按文件名刷新菜单，已有同版本 ROM 的普通存档和 RTC 继续使用。

## English

After installing `requirements.txt`, run `python tools/build_menus.py --card X:/ --packages ./packages --out D:/PocketMenus/my-menus` with your own paths. The tool scans the menu groups listed above and displays each filename without its extension. Optional PNG covers and title aliases use the card-relative path. Missing artwork gets a text cover. Characters outside the font use a placeholder while the original path stays available for launch. Use `--systems` to select a subset. New native platforms and their save/BIOS requirements are documented in [Additional cores](ADDITIONAL-CORES.md).

The generated `delivery.json` selects matching core packages for the [backed-up batch workflow](BATCH-UPDATE.md). GBA installation needs your own 16384-byte `Assets/gba/common/gba_bios.bin`. GB/GBC needs a separate 2304-byte BIOS. CPS1, CPS1.5 and CPS2 read original Jotego instances and their ROMs under the corresponding `Assets/jtcps1`, `Assets/jtcps15` and `Assets/jtcps2` directories. Instance filenames supply captions; aliases and covers use the instance path. Pokemon Mini is an offline-validated native preview awaiting device acceptance. Neo Geo remains research without an installable menu binary.

Known series folder names display in Chinese without renaming directories. PCE, MD, SFC and CPS2 also accept `--groups groups.json`, mapping card-relative cartridge paths to virtual menu folders. ROM paths and save bindings stay intact. Entries with identical content and machine settings in the same folder appear once; every source file is still verified.

The Windows assistant records and skips invalid GBA headers and GB/GBC files outside the supported 336-byte to 8 MiB size range. The CLI requires `--skip-invalid`. Excluded files remain untouched; their reasons and hashes are recorded in the manifest.

Optional `--cheats my-cheats.json` supplies the exact-version Sega index. Matching curated effects are enabled by default; other cores do not gain a cheat engine. Refresh aborts if omitting the index would disable an existing matched binding.

The tool writes libraries and a summary. Rebuild into a fresh output after adding, removing or renaming files. New GBA libraries paginate at 128 entries including Back. The batch installer verifies the save and RTC bindings of both the installed menu and the new menu. Legacy `.sms` GG images use header identification plus a checksum-pinned exception. Installation uses compatible core packages and verified backups. The stable public binary remains GB/GBC. Other native candidates await hardware acceptance.

The batch tool supports first installation and refresh with the same core version. Renaming an unchanged ROM reuses its save identity. CPS2 also keys NVRAM by the effective instance settings. Legacy save names or new ROM content at an existing path require explicit migration. A matching GBA upgrade can retain existing F2 launch and save bindings.
