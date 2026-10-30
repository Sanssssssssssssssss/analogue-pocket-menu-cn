# License and attribution

This repository contains components under different licenses. It is not a blanket MIT relicensing of the FPGA core. Existing per-file notices take precedence for their respective components.

| Component | Source and terms |
|---|---|
| Game Boy hardware implementation | MiSTer / MiST Gameboy and budude2 Pocket port; `core/src/gb/gb.v` and other files retain GPL-3.0-or-later notices. Full text: [GPL](LICENSES/GPL-3.0-or-later.txt). Preserve all individual notices, including T80 and other modules. |
| Cover picker, upstream simulation benches and `core/tools/` | [maxsorto/openfpga-GBC](https://github.com/maxsorto/openfpga-GBC/tree/666c4f33b70880047ab9e0a1987fa439ebfd78bb), MIT as declared in its README. Existing authorship retained. |
| Analogue Platform Framework | [Analogue APF notice](LICENSES/APF-Notice.txt), also retained in source; the notice specifies precedence for applicable MIT/GPL terms. |
| GNU Unifont 18.0.01 and menu subset | [Font license](LICENSES/Unifont-LICENSE.txt), [SIL OFL 1.1](LICENSES/Unifont-OFL-1.1.txt). The full compressed font and generated subset are included; font names and source attribution are retained. |
| Upstream 5×7 font | Adafruit GFX glcdfont, [BSD license](LICENSES/Adafruit-GFX.txt); upstream attribution retained. |
| New top-level `tools/`, `tests/`, original placeholder art and project documents | [MIT](LICENSES/MIT.txt), Pocket CoverFlow Chinese contributors. |

Generated Intel/Altera IP keeps its original notices. Source for the distributed bitstream is included under `core/src/`; compiler version, build input hashes, generated build identifier and binary checksum are documented in [BUILD](docs/BUILD.md).

Original placeholder graphics contain no game cover images. ROMs, BIOS, saves and personal library data are not distributed. Game Boy, Game Boy Color and Analogue Pocket are trademarks of their owners; this project is not affiliated with Nintendo, Analogue or ModRetro.
