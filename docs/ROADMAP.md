# Roadmap / 路线图

Current release: **GB/GBC native Chinese menu**, with a device-confirmed implementation and new public distribution tools.

2026-11-16: the active direction is [independent Chinese visual menus per platform](COMPLETE-DELIVERY.md), retaining the official openFPGA list and Change Core. The local preview includes eighteen menu groups, including Pokémon Mini. GBA `.10`, PCE, MD, standard-NTSC SFC, CPS1/1.5/2 and the added handhelds have completed offline checks; their new builds still need hardware acceptance. NES and GG have single-device menu, animation and basic-launch feedback. The earlier OS layout replacement and merged-launcher studies are archived.

1. Gather independent Pocket reports for normal saves, suspend/resume, sound, controls and representative GB/GBC ROM types. Improve startup delay and game handoff flash.
2. Improve title aliases, optional cover matching, large-directory handling and installation diagnostics using reproducible local fixtures.
3. Complete grouped hardware acceptance of [GBA `.10`](../experiments/gba_coverflow/README.md), including CoverFlow navigation, cover-error recovery, ordinary saves, RTC and return. The old whole-page slide renderer is historical. The new candidate preserves CoverFlow interaction and supports verified upgrades from compatible earlier menus.
4. Complete hardware gameplay and save checks of the [native console candidates](../experiments/console_coverflow/README.md). The new standard-NTSC SFC candidate passes timing; the earlier prototype's negative timing remains documented as history. Each core retains its native loading and save integration.

当前十八组本地预览共用文件名建库和备份更新工具。Pokémon Mini 已增加独立 SRAM 复核；Neo Geo 的中文菜单继续修正内存控制，暂不发布安装包。下一步统一上机核对动画、游戏启动及存档。公开稳定版仍为 GB/GBC，未把离线通过计为实机通过。

Chip32 can select a bitstream during loading. The current [public host/target interface](https://www.analogue.co/developer/docs/openfpga/host-target-commands) does not expose a general command for a running menu to launch another installed core. An offline dispatcher experiment passed seven VM cases, but the simulator only logs CORE/HOST operations and the host explicitly triggers reload. That is not proof of automatic switching on a Pocket.

The earlier [aggregation experiment](../experiments/unified_frontend/README.md) appended a shared Pocket Lab platform association while preserving existing platform indices. One user confirmed its grouping and core selection; the grouping was subsequently removed after backup following the independent-platform decision. OS Change Core remains available. A Chinese icon page that directly switches cores would need a proven runtime reload mechanism or a resource-sharing hardware redesign.

GBA, NES, SNES, an Analogue OS replacement and a universal launcher are **not current release features**. No firmware modification is planned for this project.
