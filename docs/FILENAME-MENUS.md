# 用自己的 ROM 文件名生成菜单

开发分支支持一条命令扫描自己的游戏目录，生成六组原生 CoverFlow 菜单。默认标题是 ROM 文件名去掉扩展名，中文／英文／常见日文直接生成字形。封面与显示别名可选，缺图使用占位图；原文件名、ROM 内容和已有进度不变。

在源码目录安装 `requirements.txt` 后执行：

```powershell
python tools/build_menus.py --card X:/ --out ./my-menus
```

把 `X:/` 换成实际卡路径，也可读电脑上的卡目录副本。输出必须是卡外的新目录。工具自动检测下列已有游戏目录及其子目录：

| 菜单组 | 游戏目录 | 输出格式 |
|---|---|---|
| GB / GBC | `Assets/gb/common`、`Assets/gbc/common` | v9 |
| GBA | `Assets/gba/common` | GBAF2 |
| FC / NES | `Assets/nes/common` | GBAF2/NES |
| GG | `Assets/gg/common` | GBAF2/Sega |
| SMS | `Assets/sms/common` | GBAF2/Sega |
| SG-1000 | `Assets/sg1000/common` | GBAF2/Sega |

例如 `Assets/gba/common/冒险/我的游戏.gba` 默认显示“我的游戏”。添加、删除或改名后，改用新输出目录重新执行命令。只生成指定机种可加 `--systems GB-GBC GBA NES GG`。

输出 `menus.json` 汇总已生成机种、警告和排除项；`libraries/<组名>/library-manifest.json` 保存实际 ROM 身份及菜单文件校验。GBA 新建库按每页最多 127 项加返回自动分页，保留生成的中文页名。旧 F1 更新继续要求逐记录一致，不用新分页结果直接覆盖旧菜单。GB/GBC 单页上限 2047 项，过大的目录需再分子目录；NES 与世嘉的容量限制见各实验说明。

可选参数：`--covers my-covers` 按卡相对路径寻找 PNG（例如 `my-covers/Assets/gba/common/冒险/我的游戏.png`）；`--titles names.json` 读取卡相对 ROM 路径到显示名的 UTF-8 对照。二者都不必逐游戏配置。GB/GBC 优先读取卡上已有的 `gbclab/common/gbc_bios.bin` 或 `gbc/common/gbc_bios.bin`，也可用 `--bios` 指定自己的 2304 字节 BIOS。工具不分发 BIOS，未提供时仍可生成 GB/GBC 菜单，但不能作为完整可运行安装。

默认拒绝非法 GBA 文件头；需要排除并记录这些文件时可加 `--skip-invalid`，不会修补 ROM。GG 接受标准 `.gg`，并识别部分传统 `.sms` 扩展名的 GG 镜像；普通 SMS 镜像不会因此加入 GG 菜单。硬件头也存在例外，《Excellent Dizzy Collection》的 GG 版本通过完整已知校验值识别，来源为 [No-Intro 数据库](https://github.com/libretro/libretro-database/blob/da577d2865c2b1b834b2d5f2fd1368fc5110a01c/metadat/no-intro/Sega%20-%20Game%20Gear.dat)，不能仅凭扩展名或平台位断言机种。

此命令只在电脑生成菜单。安装时仍须使用匹配格式的核心、当前卡版本核对和备份工具，见[整批更新](BATCH-UPDATE.md)。它没有实现核心运行时自动扫描目录，也没有自动导入其他模拟器存档。公共稳定二进制仍限 GB/GBC；其他候选的实际游戏、存档和新动画需要设备验收。

## English

After installing `requirements.txt`, run `python tools/build_menus.py --card X:/ --out ./my-menus`. It detects the supported platform directories, recursively scans ROMs and defaults captions to each filename stem. Chinese, English and common Japanese glyphs are generated locally. Covers and per-path aliases are optional. Use `--systems` to select a subset. Output must be a new local directory outside the source card/copy.

The tool writes libraries and a summary only; it never installs to the card or changes ROMs/existing progress. Rebuild into a fresh output after adding/removing/renaming files. New GBA libraries paginate at 128 entries including Back; existing F1 upgrades still require exact launch/save-record compatibility. Optional BIOS/covers/aliases and explicit invalid-header exclusions are described above. Legacy `.sms` GG images use header identification plus a checksum-pinned exception; the filename alone does not establish the platform. Installation and safe refresh still use compatible core-specific validators and verified backups. This is not runtime directory enumeration. The stable public binary remains GB/GBC; other native candidates await hardware acceptance.
