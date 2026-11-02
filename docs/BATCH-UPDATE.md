# 整批预检、更新与回退 / Batch update

开发候选工具 `tools/delivery.py` 将各机种的现有格式／版本校验合成一次交付。GB/GBC 更新保留已用核心；GBA 更新要求已有 `.3` 或本候选入口。NES、GG、SMS、SG-1000 支持首次新增，以及相同 bitstream 的菜单刷新：现有核心身份、数据槽和 scaler 绑定必须相符，核心／平台元数据与画面、输入选择保留。新候选仍须实机验收，公共稳定版仍限 GB/GBC。

先安装源码依赖。将 [配置模板](delivery.example.json) 复制到私人离线包顶层的 `delivery.json`，按实际包／素材位置填写；未完成机种可从 `components` 移除。所有路径相对配置文件，也可使用绝对路径。GB/GBC 映射中的 `cover` 相对映射 JSON；其他封面根目录沿用卡相对路径，如 `covers/Assets/nes/common/Example.png`。核心、BIOS、游戏库和个人配置需要自行准备，不在公共源码中分发。

```powershell
python tools/delivery.py prepare --card X:/ --config D:/PocketOffline/delivery.json --staging D:/PocketStaging/test-1
python tools/delivery.py verify --card X:/ --staging D:/PocketStaging/test-1
```

这两步只读卡，在电脑生成／复查计划。`X:/` 必须重新识别；输入、电脑暂存、备份必须位于卡外且互相分开。实际卡没有挂载时，不能用旧 ROM 备份假冒卡。某个机种失败则不生成整批 `delivery-plan.json`。修正后使用新暂存目录。

NES／世嘉组件可用 `library` 指向已生成的菜单目录，例如 `{"id":"NES","package":"packages/NES","library":"my-menus/libraries/NES"}`。未指定时仍按当前卡重建。预生成菜单也会完整核对当前 ROM、分页／目录链接、存档及金手指身份，不能用旧清单跳过检查。已安装入口自动进入图文刷新，计划标记为 `library_refresh_same_bitstream`；不同 RBF、数据槽、尺寸绑定或不匹配的已有进度大小均停止，独立首装 CLI 继续拒绝覆盖已有入口。

通过后查看电脑暂存目录的 `delivery-plan.json`：`components` 是图文匹配和缺项结果；`changes` 是逐文件变更；`source_refs` 是 ROM 身份。NES／世嘉按当前卡重建目录、去除每个目录内的相同内容，并只生成缺失的独立普通存档种子；不猜测导入其他核心的存档。GB/GBC 只做原菜单局部更新。GBA 必须逐项保持 ROM／SAV／RTC 启动记录；旧库不符即停止。

确认计划后执行：

```powershell
python tools/delivery.py apply --card X:/ --staging D:/PocketStaging/test-1 --backup D:/PocketBackups/test-1
```

写卡前重新核对卡标记／卷身份、全部 ROM、原目标与电脑载荷；局部备份被改菜单和相关 `Saves`，其中始终包含现有 GBA 进度。逐文件原子替换、SHA256 回读并记录日志。GB/GBC／GBA 沿用当前图标、画面比例、已有显示模式及默认值，仅追加受支持的可选模式和菜单 scaler；系统滤镜选择仍在 Pocket OS。原 ROM、既有存档、Settings、固件不在写入范围内。

正常 I/O 错误会尝试恢复菜单。断电、拔卡或进程被终止后，使用收据手动预检和回退：

```powershell
python tools/delivery.py rollback --card X:/ --backup D:/PocketBackups/test-1
python tools/delivery.py rollback --card X:/ --backup D:/PocketBackups/test-1 --execute
```

回退先核对所有菜单与备份；遇到安装后人工改过的文件会停下。它恢复旧菜单、移除本次新增且未变化的菜单文件，保留所有存档（包括本次创建后已有新进度的文件）。`progress/` 只是独立安全副本，不自动覆盖当前进度。文件系统损坏／断电不能由普通文件事务保证修复；保留外置备份，操作完毕安全弹出。

合成用例覆盖全部六个组件适配器、整批失败前置拒绝、ROM／载荷／卡变化、中途写入失败恢复和回退保留进度。它们不能认证真实卡介质或游戏兼容性。

## English

`delivery.py` prepares one card-bound update using the existing native validators. GB/GBC and GBA update existing supported entries. NES/GG/SMS/SG-1000 support first additions and library refreshes with exactly the same bitstream and matching data-slot/scaler bindings. Refresh retains existing core/platform definitions, display/input choices and played progress; changed bindings or unsupported existing save sizes abort. The standalone first-install CLIs still refuse overwrites. Copy the example configuration into your private bundle and provide your own matching packages, artwork and assets. Paths are relative to the configuration; GB/GBC cover paths are relative to its mapping JSON. Remove unsupported components explicitly.

For NES/Sega, optional `library` selects prebuilt output from `build_menus.py`; omitted libraries are rebuilt from the current card. Supplied manifests still undergo complete current-ROM, page-link, save and cheat identity validation. Existing entries report `library_refresh_same_bitstream`, and all changed files use the same backup/readback/rollback transaction as other batch components.

`prepare` and `verify` never write the card. All component checks finish before an installable plan is published. `apply` rechecks card/ROM/payload/original identities, verifies targeted menu and ordinary-progress backups, then atomically publishes files with readback and a journal. Existing GB/GBC/GBA icons, game scalers, display definitions/defaults and progress remain intact; optional supported styles/menu scaler slots are appended. `rollback` previews unless `--execute` is given. It restores/removes owned menu files only, refuses unexpected edits and retains all saves, including new progress. Interrupted I/O attempts menu rollback; power loss or filesystem corruption still needs the external receipt/backup. New candidates require physical acceptance and are not part of the public stable release.
