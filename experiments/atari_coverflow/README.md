# Atari 2600 / 7800 CoverFlow

Native Miasmark cores with a separate CRAM1 CoverFlow renderer, Unicode title rows and folder navigation. Native ROM loaders, settings, all game scaler modes and shared SaveKey/FA2/HSC bindings are retained. Exit games with Pocket Quit.

`prepare.py` verifies pinned upstream ZIP hashes before generating a fresh tree. `package.py` requires complete Quartus fit/assembly and four-corner timing, compares deterministic source inputs, and records bitstream/source hashes. `library.py` scans the original asset directory and builds paginated menus without copying ROMs or generating replacement shared saves.

The 2600 adds a 320×288 menu mode; the 7800 reuses its existing 320×274 PAL slot because all eight scaler entries are already occupied. Content fits above the cropped empty bottom margin. The native NTSC/PAL menu cadence is approximately 51.05/50.58 Hz.

```powershell
python experiments/atari_coverflow/prepare.py 2600 --archive upstream.zip --gba-source pinned-gba-source --out .work/atari-prepared
```

Build `src/fpga/ap_core` with Quartus 22.1std.2, then use the packager with the compiled tree and the same pinned inputs. The GBA source supplies only the separately licensed CellRAM driver. Original licenses and notices remain in corresponding sources.

APF, memory and native download handoff probes use synthetic bytes and do not establish CPU gameplay or physical-device acceptance. Usage and save boundaries: [additional cores](../../docs/ADDITIONAL-CORES.md).
