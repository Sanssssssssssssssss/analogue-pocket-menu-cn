# 整批预检、更新与回退 / Batch update

开发候选工具 `tools/delivery.py` 将各机种的格式／版本校验合成一次交付。六组菜单支持首次安装与相同 bitstream 的文件名库刷新；GB/GBC 还支持保留原记录的显示映射，GBA `.3` → F2 使用绑定一致的配套升级库。刷新要求现有核心身份、数据槽和 scaler 绑定相符，保留核心／平台元数据、画面／输入选择及已玩进度。新候选仍须实机验收，公共稳定版仍限 GB/GBC。

先安装源码依赖。[文件名建库](FILENAME-MENUS.md)会生成已选择所用机种的 `delivery.json`，填好自己的匹配核心包路径即可使用。现有定制目录的图文修订也可从[配置模板](delivery.example.json)开始；未完成机种从 `components` 移除。所有路径相对配置文件，也可使用绝对路径。GB/GBC 的 `library` 与旧目录 `mapping` 二选一；映射中的 `cover` 相对映射 JSON。其他封面根目录沿用卡相对路径，如 `covers/Assets/nes/common/Example.png`。核心、BIOS、游戏库和个人配置需要自行准备，不在公共源码中分发。

```powershell
python tools/delivery.py prepare --card X:/ --config D:/PocketOffline/delivery.json --staging D:/PocketStaging/test-1
python tools/delivery.py verify --card X:/ --staging D:/PocketStaging/test-1
```

这两步只读卡，在电脑生成／复查计划。`X:/` 必须重新识别；输入、电脑暂存、备份必须位于卡外且互相分开。实际卡没有挂载时，不能用旧 ROM 备份假冒卡。某个机种失败则不生成整批 `delivery-plan.json`。修正后使用新暂存目录。

各组的 `library` 可指向已生成的菜单目录，例如 `{"id":"NES","package":"packages/NES","library":"my-menus/libraries/NES"}`；NES／世嘉未指定时仍按当前卡重建。预生成菜单也核对当前 ROM、分页／目录链接、存档及金手指身份，不能用旧清单跳过检查。首装标记为 `first_addition`，同核心刷新标记为 `library_refresh_same_bitstream`；不同 RBF、数据槽、尺寸绑定、旧式存档身份或不匹配的已有进度大小均停止。GBA 从 F1 升级走 `format_upgrade`，保持原启动／存档／RTC 记录。

新计划格式 `POCKET-DELIVERY-2` 将需要创建的专属存档目录列入 `directories`，写入前检查目录冲突与链接。旧 `POCKET-DELIVERY-1` 仍可核对、安装和回退，新计划须用新工具。回退保留目录和所有新旧存档。原 ROM 被用户另行改名／删除时，菜单回退不撤销这些文件操作。

已记录实体失败的 bitstream 不能重新安装，也不能通过旧计划或旧回退包恢复。读取／备份旧文件仍可进行；发布候选及恢复之前会重新检查拒绝清单。

通过后查看电脑暂存目录的 `delivery-plan.json`：`components` 是操作类型、图文匹配和缺项结果；`changes` 是逐文件变更；`source_refs` 是 ROM 身份。文件名库使用内容对应的存档身份；同内容改名继续使用原进度。现有传统 GB/GBC 目录可只做局部显示映射，GBA F1 升级必须逐项保持 ROM／SAV／RTC 启动记录。NES／世嘉按目录去除相同内容，并只生成缺失的独立普通存档种子；不猜测导入其他核心的存档。世嘉已有的匹配金手指若将因漏给索引而关闭，会在预检停止。

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

`delivery.py` prepares one card-bound update. All six formats support first installation and filename-library refresh with exactly the same bitstream and matching data-slot/scaler bindings. GB/GBC additionally retains the existing display-mapping path; GBA F1 upgrades require unchanged launch/save/RTC records. Refresh retains core/platform definitions, display/input choices and played progress; changed bindings, legacy save identities or unsupported save sizes abort. Use the generated filename-builder configuration or customize the example for an existing bespoke menu. Supply your own matching packages and assets. Paths are relative to the configuration; GB/GBC selects either `library` or `mapping`. Remove unsupported components explicitly.

`library` selects prebuilt output from `build_menus.py`; NES/Sega can also rebuild from the current card when omitted. Supplied manifests still undergo current-ROM, page-link, save and cheat identity validation. Operations report `first_addition`, `library_refresh_same_bitstream` or the GBA `format_upgrade`. Omitting an index cannot silently disable an existing matched Sega cheat binding.

New `POCKET-DELIVERY-2` plans explicitly list required owned save directories and reject collisions/links before writes. Old version 1 plans still work with the new tool; new plans need the new tool. Rollback retains save directories and all progress, and does not undo separate user changes to ROM filenames or contents.

Previously device-rejected bitstreams cannot be installed or restored, including through plans/backups made before the rejection was recorded. Reading/backing up old files remains allowed; publication and restoration recheck the rejection list.

`prepare` and `verify` never write the card. All component checks finish before an installable plan is published. `apply` rechecks card/ROM/payload/original identities, verifies targeted menu and ordinary-progress backups, then atomically publishes files with readback and a journal. Existing GB/GBC/GBA icons, game scalers, display definitions/defaults and progress remain intact; optional supported styles/menu scaler slots are appended. `rollback` previews unless `--execute` is given. It restores/removes owned menu files only, refuses unexpected edits and retains all saves, including new progress. Interrupted I/O attempts menu rollback; power loss or filesystem corruption still needs the external receipt/backup. New candidates require physical acceptance and are not part of the public stable release.
