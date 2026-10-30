# Build and binary provenance

Public release `v0.1.2-public.1` packages the accepted 0.1.2 FPGA program without HDL changes. Public metadata/version and Python distribution tooling are new.

| Item | Value |
|---|---|
| Upstream | maxsorto/openfpga-GBC, `cover-picker`, commit `666c4f33b70880047ab9e0a1987fa439ebfd78bb` |
| FPGA | Intel Cyclone V `5CEBA4F23C8` |
| Compiler | Quartus Prime Lite 22.1std.2, Build 922 |
| Original RBF SHA-256 | `4debe91f4035e0bd87e7dc470c4f3a65388dbd8cd83b6ece98c87304335a8ebb` |
| Distributed bit-reversed RBF SHA-256 | `1cb62f954484be8c002e2f6c74e7813d34ef0cbe2fb910f3916dab1c43d766d9` |
| Distributed program size | 2,097,492 bytes |
| Resources | 13,753 / 18,480 ALMs; 299 / 308 M10K; 56 / 66 DSP |
| Constrained timing | Minimum setup 1.576 ns; hold 0.080 ns; TNS 0 |

The upstream SDC leaves 30 input and 63 output ports without I/O timing constraints; there are no unconstrained clocks. Passing constrained timing does not prove every hardware path. The build did not relax constraints.

## Compile

Use Linux/WSL and an installed Quartus 22.1 compiler:

```sh
sh tools/build_core.sh
```

`QUARTUS_SH=/path/to/quartus_sh sh tools/build_core.sh` selects an explicit executable. The script creates a fresh `.build/native/src` copy and refuses to overwrite an existing build directory. It does not access a card.

The original build used the upstream-recommended `didiermalenfant/quartus:22.1-apple-silicon` image on Linux x86-64, frozen at manifest `sha256:04167adc3a41558df0d76404f4748278d4552bd07f3cb396019ce5fb5fedcfe1`. Docker is optional if Quartus is installed locally; CI does not download this large toolchain or claim FPGA compilation.

The complete hardware source and pre-generated Chinese glyphs are in `core/src/`. [Source input hashes](build/source-inputs.json) match the accepted source after line-ending normalization. APF's pre-flow hook generates a timestamp/random build identifier; the [identifier used for the accepted build](build/generated-build-id.mif) is retained for provenance. Rebuilding normally changes binary bytes, so exact binary reproducibility is not claimed.

The upstream compile-time `BootROMs/cgb_boot.mif` is absent. APF's required BIOS data slot 4 loads a separately supplied 2304-byte GBC BIOS at runtime. ROMs and BIOS are not needed to compile, and are not included in source or release artifacts.

Inspect the complete compiler log, fitter utilization and timing reports before using a newly built bitstream. `tools/build_release.py` intentionally accepts only the reviewed binary hash above; a new hardware revision requires a new review and release record.

## Package the accepted binary

From a committed source checkout, with the reviewed bit-reversed program supplied locally:

```sh
python tools/build_release.py --bitstream /path/to/gbc.rbf_r --out .work/release
```

This creates a core ZIP, a release manifest and `SHA256SUMS.txt`. It contains no ROMs, BIOS, covers or saves. Source is provided by the corresponding immutable public Git tag. Bring your own assets through the local library builder.
