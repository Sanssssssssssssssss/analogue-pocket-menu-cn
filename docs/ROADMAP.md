# Roadmap / 路线图

Current release: **GB/GBC native Chinese menu**, with a device-confirmed implementation and new public distribution tools.

2026-11-01: the active direction is [independent Chinese visual menus per platform](PER-SYSTEM-MENUS.md), retaining the official openFPGA list and Change Core. GB/GBC and GBA remain separate native cores. The earlier OS layout replacement and merged-launcher studies are archived.

1. Gather independent Pocket reports for normal saves, suspend/resume, sound, controls and representative GB/GBC ROM types. Improve startup delay and game handoff flash.
2. Improve title aliases, optional cover matching, large-directory handling and installation diagnostics using reproducible local fixtures.
3. Complete acceptance of the separate GBA experiment: menu and game launch are user-confirmed in `0.2.0-gba.3`; ordinary saves, RTC, save-return and broader compatibility remain pending. The [slide animation candidate](../experiments/gba_menu/MOTION.md) passed a full local build and awaits device acceptance.
4. Finish the [native NES candidate](../experiments/nes_menu/README.md), library and device tests; resolve the [standard-NTSC SNES prototype's](../experiments/snes_menu/README.md) failing timing before any installation. Each native core needs its own loading, save and return acceptance. Share title/artwork tooling where applicable.

Chip32 can select a bitstream during loading. The current [public host/target interface](https://www.analogue.co/developer/docs/openfpga/host-target-commands) does not expose a general command for a running menu to launch another installed core. An offline dispatcher experiment passed seven VM cases, but the simulator only logs CORE/HOST operations and the host explicitly triggers reload. That is not proof of automatic switching on a Pocket.

The earlier [aggregation experiment](../experiments/unified_frontend/README.md) appended a shared Pocket Lab platform association while preserving existing platform indices. One user confirmed its grouping and core selection; the grouping was subsequently removed after backup following the independent-platform decision. OS Change Core remains available. A Chinese icon page that directly switches cores would need a proven runtime reload mechanism or a resource-sharing hardware redesign.

GBA, NES, SNES, an Analogue OS replacement and a universal launcher are **not current release features**. No firmware modification is planned for this project.
