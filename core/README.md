# Native hardware source

`src/` contains the complete accepted GB/GBC hardware implementation and Chinese menu. `pkg/` retains upstream platform templates; the public release uses the reviewed templates in `../packaging/`. `tools/` retains upstream format helpers and simulation sources, not the old deployment scripts.

Start with the [project README](../README.md), [build guide](../docs/BUILD.md), [v9 format](../docs/FORMAT.md) and [license/attribution](../LICENSE.md). The legacy `make_cover_pack.py` generates v6/v7 and is retained as a format/rendering dependency; use the top-level `tools/build_library.py` for this release.

Upstream: [maxsorto/openfpga-GBC cover-picker](https://github.com/maxsorto/openfpga-GBC/tree/666c4f33b70880047ab9e0a1987fa439ebfd78bb), based on budude2's Pocket port and MiSTer Gameboy. Original source headers and legal notices are retained.
