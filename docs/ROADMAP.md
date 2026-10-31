# Roadmap / 路线图

Current release: **GB/GBC native Chinese menu**, with a device-confirmed implementation and new public distribution tools.

1. Gather independent Pocket reports for normal saves, suspend/resume, sound, controls and representative GB/GBC ROM types. Improve startup delay and game handoff flash.
2. Improve title aliases, optional cover matching, large-directory handling and installation diagnostics using reproducible local fixtures.
3. Complete acceptance of the separate GBA experiment: menu and game launch are user-confirmed in `0.2.0-gba.3`; ordinary saves, RTC, save-return and broader compatibility remain pending. NES/SNES need their own memory, ROM-loading and save-format work.
4. Investigate a unified platform chooser only after proving runtime core handoff and return on hardware.

Chip32 can select a bitstream during loading. The current [public host/target interface](https://www.analogue.co/developer/docs/openfpga/host-target-commands) does not expose a general command for a running menu to launch another installed core. An offline dispatcher experiment passed seven VM cases, but the simulator only logs CORE/HOST operations and the host explicitly triggers reload. That is not proof of automatic switching on a Pocket.

The [aggregation experiment](../experiments/unified_frontend/README.md) appends a shared Pocket Lab platform association while preserving existing platform indices. This still relies on OS Change Core and awaits confirmation of its grouping on hardware. A Chinese icon page that directly switches cores needs a proven runtime reload mechanism or a resource-sharing hardware redesign.

GBA, NES, SNES, an Analogue OS replacement and a universal launcher are **not current release features**. No firmware modification is planned for this project.
