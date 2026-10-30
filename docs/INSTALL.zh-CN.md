# 安装、中文名、封面与回退

适用 `v0.1.2-public.1`。本版为公开预览，GB/GBC 原生菜单已有实机反馈，公共生成器／安装器尚待更多设备验证。

## 准备

1. 退出游戏并关机，用读卡器将卡连接电脑；每次重新确认盘符。先把 `Saves`、`Memories` 和需要保留的旧菜单文件复制到电脑。安装器的自动备份只包含将被替换的菜单文件，不能代替自己的进度备份。
2. 从同一 Release 下载源码和核心 ZIP，在电脑解压，安装 `requirements.txt`。核心 ZIP 解压到 `dist/core`，其下直接有 `Cores`、`Platforms`、`release-manifest.json`。
3. PowerShell 可用 `Get-FileHash <下载文件> -Algorithm SHA256` 对照 `SHA256SUMS.txt`；Linux 用 `sha256sum -c SHA256SUMS.txt`。`Source code.zip` 是 GitHub 自动生成的源码包，不在核心包校验清单中。

Windows 示例卡根为 `X:/`；macOS 可用 `/Volumes/Pocket`，Linux 使用实际挂载点。带空格的路径加引号。卡根应有 `Analogue_Pocket.json` 且 product 为 `Analogue Pocket`；安装器不格式化、不初始化卡。

## 生成自己的菜单

```powershell
python tools/build_library.py --card X:/ --out .work/library --bios X:/Assets/gbc/common/gbc_bios.bin
```

- 只读取 `Assets/gb/common`、`Assets/gbc/common` 下的 `.gb` / `.gbc`，保留子目录；每个目录最多 2046 个条目，另留一个返回入口。
- ROM 留在原处，不复制、不重命名。中文显示名默认来自文件名；原英文文件名不会自动翻译。
- `--out` 必须是电脑上尚不存在的新目录，不能位于卡内。重新生成可换为 `.work/library-2`，旧输出保留。
- BIOS 由你提供，长度必须为 2304 字节。长度检查不代表版本／来源真实性。可先不传 `--bios` 生成菜单，但实际安装前必须重新生成包含 BIOS 的包。
- 工具生成 `library-manifest.json`，其中含你的私有 ROM 路径与哈希，仅保存在本机；请勿上传到公开 Issue。
- 中文字体随源码提供并校验，长标题在 500 像素内截断；缺字与截断列入 manifest 的 `warnings`。

可选的 `titles.json`：

```json
{
  "Assets/gbc/common/Example.gbc": "我们的冒险",
  "Assets/gb/common/Puzzle.gb": "方块练习"
}
```

```powershell
python tools/build_library.py --card X:/ --out .work/library-2 --bios X:/Assets/gbc/common/gbc_bios.bin --titles titles.json --covers my-covers
```

封面位置对应 ROM 的卡内相对路径，例如 `my-covers/Assets/gbc/common/Example.png`。使用自己的图片或已获得使用许可的素材；没有封面时生成卡带占位图。工具不下载商业游戏封面或 ROM。

## 预览与应用

```powershell
python tools/install.py --card X:/ --package dist/core --library .work/library
python tools/install.py --card X:/ --package dist/core --library .work/library --backup .work/backups/first-install --apply
```

默认命令只读取并验证卡标识、源 ROM 和包哈希。`--apply` 会先校验备份，再写入并回读；`core.json` 最后发布。每次应用使用新的备份目录，旧备份不能覆盖。

只允许写 `Cores/pocketlab.CoverFlow/`、`Assets/gbclab/common/`、`Platforms/gbclab.json` 和 `Platforms/_images/gbclab.bin`。会创建空的实验存档目录，但不复制或覆盖存档文件。源 ROM、固件、系统设置均不在写入范围。

文件操作完成后安全弹出，Pocket 关机插卡，选择 **openFPGA → Pocket Lab GB-GBC → CoverFlow**。如有作者选择，选 **pocketlab**。

## 存档

新进度写入 `Saves/gbclab/common/<ROM内容哈希前20位>.sav`；相同 ROM 内容的重复入口共用此实验存档。映射见本机 manifest 的 `source_refs[].save`。

原 GB/GBC 存档不会自动导入。如果要手动迁移：先确认 ROM 版本及普通存档格式一致、备份源和目标、退出核心，再复制到对应的实验路径。不要直接迁移其他模拟器的即时存档或 Pocket 的休眠现场。暂停保存与恢复仍需实机验证，请先用非重要进度测试。

## 回退

最方便的临时退路是退出当前核心，在 Analogue OS 选择原有 GB/GBC 核心。

```powershell
python tools/install.py --card X:/ --backup .work/backups/first-install --rollback
python tools/install.py --card X:/ --backup .work/backups/first-install --rollback --apply
```

第一条只展示回退数量。应用回退时恢复旧菜单文件，并删除该次安装新增且哈希仍匹配的文件；当前 `Saves` 保留。目标文件被手工修改、卡身份变化或备份损坏时会拒绝操作。即使安装中断，已写出的回退收据也可用于恢复完成的部分；不要删除备份目录。

## 常见问题

- **错误 R4**：检查 ROM 是否仍在生成菜单时的位置，且属于声明的 `gb` / `gbc` 平台目录；重新生成并查看安装计划。不要凭名称移动原存档。
- **没有中文**：文件名是英文时需提供 `titles.json`；系统首页和 Core Settings 的英文不属于此菜单的翻译层。
- **游戏启动闪一下／稍慢**：目前保留为已知问题，目录切换闪白已在原开发设备修复。
- **B 返回错误**：本版生成器为每个包保留末尾返回项。不要用旧 v6/v7 上游工具或旧 Companion 导出的包覆盖 v9 菜单。
- **想玩 GBA / NES / SNES**：继续使用对应原核心；本版尚未接入这些平台。
