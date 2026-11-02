# 用自己的 ROM 文件名生成菜单

开发分支支持一条命令扫描自己的游戏目录，生成六组原生 CoverFlow 菜单。默认标题是 ROM 文件名去掉扩展名，中文／英文／常见日文直接生成字形。封面与显示别名可选；缺图时自动生成带游戏名的文字封面，沿用 GB 菜单的卡片样式。原文件名、ROM 内容和已有进度不变。

在源码目录安装 `requirements.txt` 后执行：

```powershell
python tools/build_menus.py --card X:/ --out D:/PocketMenus/my-menus
```

把 `X:/` 换成实际卡路径，也可读电脑上的卡目录副本。输出使用卡外、源码检出目录外的新私人目录；macOS／Linux 换成对应的本地路径。工具自动检测下列已有游戏目录及其子目录：

| 菜单组 | 游戏目录 | 输出格式 |
|---|---|---|
| GB / GBC | `Assets/gb/common`、`Assets/gbc/common` | v9 |
| GBA | `Assets/gba/common` | GBAF2 |
| FC / NES | `Assets/nes/common` | GBAF2/NES |
| GG | `Assets/gg/common` | GBAF2/Sega |
| SMS | `Assets/sms/common` | GBAF2/Sega |
| SG-1000 | `Assets/sg1000/common` | GBAF2/Sega |

例如 `Assets/gba/common/冒险/我的游戏.gba` 默认显示“我的游戏”。添加、删除或改名后，改用新输出目录重新执行命令。只生成指定机种可加 `--systems GB-GBC GBA NES GG`。

输出 `menus.json` 汇总已生成机种、警告和排除项；`libraries/<组名>/library-manifest.json` 保存实际 ROM 身份及菜单文件校验。自动生成的 `delivery.json` 已填入所选机种的库与 `packages/<组名>` 路径。将自己准备的匹配核心包放到该位置，或编辑这些包路径，再执行[整批预检与备份安装](BATCH-UPDATE.md)。六组格式共用这一入口，不需要逐游戏写配置。

GBA 新建库按每页最多 127 项加返回自动分页，保留生成的中文页名。旧 F1 更新继续要求逐记录一致，不用新分页结果直接覆盖旧菜单。GB/GBC 单页上限 2047 项，过大的目录需再分子目录；NES 与世嘉的容量限制见各实验说明。

可选参数：`--covers my-covers` 按卡相对路径寻找 PNG（例如 `my-covers/Assets/gba/common/冒险/我的游戏.png`）；`--titles names.json` 读取卡相对 ROM 路径到显示名的 UTF-8 对照。二者都不必逐游戏配置。GB/GBC 优先读取卡上已有的 `gbclab/common/gbc_bios.bin` 或 `gbc/common/gbc_bios.bin`，也可用 `--bios` 指定自己的 2304 字节 BIOS。工具不分发 BIOS，未提供时仍可生成 GB/GBC 菜单，但不能作为完整可运行安装。

GBA 安装要求卡上已有自己的 `Assets/gba/common/gba_bios.bin`，大小 16384 字节。核心的 BIOS 槽按平台索引 1 指向 `gba`；规则见 [Analogue 官方文件槽说明](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json)。预检记录 BIOS 身份，文件在安装前改变会停止；文件大小本身不认证内容。

GG／SMS／SG-1000 可加 `--cheats my-cheats.json`，使用[精确版本索引格式](../experiments/sega_coverflow/README.md)，匹配成功的实用条目默认启用；其他 UI 核心不因此获得金手指引擎。刷新时若原本启用的匹配代码将因漏给索引而关闭，预检会停止，要求带上相应索引重新建库。

默认拒绝非法 GBA 文件头；需要排除并记录这些文件时可加 `--skip-invalid`，不会修补 ROM。GG 接受标准 `.gg`，并识别部分传统 `.sms` 扩展名的 GG 镜像；普通 SMS 镜像不会因此加入 GG 菜单。硬件头也存在例外，《Excellent Dizzy Collection》的 GG 版本通过完整已知校验值识别，来源为 [No-Intro 数据库](https://github.com/libretro/libretro-database/blob/da577d2865c2b1b834b2d5f2fd1368fc5110a01c/metadat/no-intro/Sega%20-%20Game%20Gear.dat)，不能仅凭扩展名或平台位断言机种。

此命令只在电脑生成菜单。安装时仍须使用匹配格式的核心、当前卡版本核对和备份工具，见[整批更新](BATCH-UPDATE.md)。它没有实现核心运行时自动扫描目录，也没有自动导入其他模拟器存档。公共稳定二进制仍限 GB/GBC；其他候选的实际游戏、存档和新动画需要设备验收。

六组菜单都支持首次安装及相同 bitstream 的文件名库刷新，保留现有核心／平台定义、画面／输入选择和进度。修改显示名、加入游戏、删除或改名后重新建库；相同内容改名继续使用同一存档身份。GB/GBC 旧式存档命名、原路径下 ROM 内容改变等情况会要求明确迁移，防止悄悄换用空白进度。GBA 的 `.3` → F2 升级仍须使用启动／存档绑定一致的配套包；当前私人旧卡升级包与陌生文件名首装分别验证。菜单回退不恢复用户自行删除或改名的 ROM。

## English

After installing `requirements.txt`, run `python tools/build_menus.py --card X:/ --out D:/PocketMenus/my-menus` with your own local paths. It detects the supported platform directories, recursively scans ROMs and defaults captions to each filename stem. Chinese, English and common Japanese glyphs are generated locally. Covers and per-path aliases are optional; missing artwork produces a text cover bearing the game name in the existing GB card style. Use `--systems` to select a subset. Output belongs in a fresh private directory outside both the input card/copy and the source checkout.

Generated `delivery.json` selects the generated libraries and `packages/<system>` locations. Supply your own matching core packages there or edit their paths, then use the backed-up batch workflow. All six formats share that entry. GBA installation additionally needs your own 16384-byte `Assets/gba/common/gba_bios.bin`; its slot uses platform index 1 under the [official APF rule](https://www.analogue.co/developer/docs/openfpga/core-definition-files/data-json). Its identity is rechecked before writes; size alone does not prove authenticity. GB/GBC needs its separate 2304-byte BIOS as described above.

Optional `--cheats my-cheats.json` supplies the exact-version Sega index. Matching curated effects are enabled by default; other cores do not gain a cheat engine. Refresh aborts if omitting the index would disable an existing matched binding.

The tool writes libraries and a summary only; it never installs to the card or changes ROMs/existing progress. Rebuild into a fresh output after adding/removing/renaming files. New GBA libraries paginate at 128 entries including Back; existing F1 upgrades still require exact launch/save-record compatibility. Optional BIOS/covers/aliases and explicit invalid-header exclusions are described above. Legacy `.sms` GG images use header identification plus a checksum-pinned exception; the filename alone does not establish the platform. Installation and safe refresh still use compatible core-specific validators and verified backups. This is not runtime directory enumeration. The stable public binary remains GB/GBC; other native candidates await hardware acceptance.

All six formats support first installation and same-bitstream filename-library refresh through the batch tool. Refresh retains core/platform definitions, display/input choices and played progress; adding games creates independent content-based identities, and renaming unchanged ROMs reuses their save identity. Legacy GB/GBC save names or changed ROM content at an existing path require explicit migration. GBA `.3` to F2 still requires unchanged launch/save bindings and a matching upgrade bundle. Menu rollback does not restore ROM files renamed or removed separately by the user. These are software workflow checks, separate from physical acceptance.
