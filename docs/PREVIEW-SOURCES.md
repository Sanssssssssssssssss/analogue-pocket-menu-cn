# 开发预览配套源码 / Preview sources

Windows 开发预览随包附上对应源码。2026-11-15 批次的 GBA、GB/GBC、FC、PCE、MD、SFC、CPS2 及新增七组的实际编译输入在 `packages/<机种>/sources/`，同级 `build-receipt.json` 记录输入与位流的 SHA-256。GG、SMS、SG-1000 仍使用 `PocketLab-Upstream-Source-2026-11-09.zip`；其中保留的旧 GBA 快照不对应新的 `.10` 位流。分享时一起保留这些文件。

四机种源码 ZIP 内的 `source-manifest.json` 记录工程位置、输入和路径调整，解包后可运行 `python verify_sources.py`。CPS2 对应源码包含四个用于综合的内存初始化文件。冻结的 GB/GBC `core/src/` 对应[公开版构建说明](BUILD.md)。

2026-11-16 Pokémon Mini 预览包另外提供 86 份实际编译源码，含 QPF/QIP、FreeBIOS、字体、暂停/错误文字和 CPU 微码初始化文件。八级除法流水线和 LCD 颜色表已有原生逐拍对照；四角 STA 与独立 SRAM 发收时钟证据放在 `evidence/`。公开注册只认精确位流及收据哈希，仍标记实机验收待完成。此前冻结的 Desktop3 不因此改变，也不自动获得 Mini 核心。

| 菜单组 | 工程目录（相对该组源码） | Quartus revision |
|---|---|---|
| GB / GBC | `.` | `ap_core` |
| GBA | `src/fpga/build` | `ap_core` |
| FC / NES | `projects` | `nes_pocket` |
| GG / SMS / SG-1000 | `projects` | `gg_pocket` |
| PCE | `projects` | `pce_pocket` |
| MD | `src/fpga` | `ap_core` |
| SFC | `projects` | `snes_pocket` |
| CPS2 | `cores/cps2/pocket` | `jtcps2` |
| CPS1 / CPS1.5 | `cores/cps1/pocket`、`cores/cps15/pocket` | `jtcps1`、`jtcps15` |
| WS / Atari 2600 / Atari 7800 / Arduboy | `src/fpga` | `ap_core` |
| Supervision | `projects` | `supervision_pocket` |
| Pokémon Mini，2026-11-16 预览 | `src/fpga` | `ap_core` |

安装自己的 Quartus Prime 22.1std.2 工具后，在对应工程目录运行 `quartus_sh --flow compile <revision>`。使用包内原有种子与约束。重新编译的核心仍须检查完整 fit、全部器件角的时序，以及该平台的 SRAM/CellRAM 路径；编译器版本、生成的构建日期和工程路径可能影响最终二进制，不能只以文件大小判断结果。

GBA 源码中的原始内嵌 BIOS 初值已清零，实际 BIOS 由玩家自行提供。源码包不含个人游戏、存档、完整商业工具或授权仿真模型。各上游通知按原文件保留，见[许可与来源](../LICENSE.md)。

## English

Keep the bundled sources with the desktop preview. The 2026-11-15 batch contains compiled inputs for GBA, GB/GBC, NES, PCE, MD, SNES, CPS2 and the seven added native groups under `packages/<system>/sources/`, with corresponding receipts. GG, SMS and SG-1000 use `PocketLab-Upstream-Source-2026-11-09.zip`; the older GBA snapshot inside that ZIP does not correspond to the new `.10` binary. Extract the companion and run `python verify_sources.py` to check its manifest. The CPS2 source includes its four memory initialization files. The frozen GB/GBC `core/src/` tree corresponds to the public build.

Use your own Quartus Prime 22.1std.2 installation and run `quartus_sh --flow compile <revision>` in the project directory listed above. Keep the recorded seeds and constraints. Rebuilding requires full fit, multi-corner timing and the platform-specific external-memory checks before packaging. Compiler versions, generated build identifiers and project locations may affect the resulting binary. The source snapshot is not a claim of bit-identical recompilation or physical-device acceptance.

The separate 2026-11-16 Pokemon Mini preview provides 86 actual build inputs, including project/IP files and all font, FreeBIOS and microcode initializers. Its evidence includes four-corner reports and an independent SRAM launch/capture review. The divider and LCD replacements were compared with native RTL. Registration binds the exact bitstream and receipt; hardware acceptance remains pending. The previously frozen Desktop3 bundle is unchanged and does not gain Mini automatically.

The prepared GBA source has its embedded BIOS initializer cleared. Users supply their own external BIOS. Personal games, saves, proprietary compilers and licensed simulation models are not included. Preserve the upstream terms described in [LICENSE.md](../LICENSE.md).

## Neo Geo

`packages/NEOGEO/sources/` 附 696 文件的实际源输入与复核补件。原拟合 SDC、原源码收据保留；完整清单覆盖新增断言补丁、两类约束及已实际执行的复核脚本。请一起阅读 `BUILD-NEOGEO.txt` 和 `BUILD-REANALYSIS.md`。新位流需要新复核；不能将原编译退出 3 改写成成功。

The Neo Geo package includes its actual fit inputs, original receipt, exact guard patch and executed post-fit tools. Both BUILD documents explain the original failed guard analysis and the separate successful timing review. The full source inventory includes the original FX68K author notice and GPL-3.0 text. Rebuilding requires a new review for the resulting binary.
