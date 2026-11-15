# CPS timing scope

The packaged bitstream must complete the full Quartus 22.1 Fitter and pass setup, hold, recovery, removal and pulse-width summaries at all four supported operating corners. The receipt records the actual minimum slack and report count; a successful compile command alone is insufficient.

The native clock chain is 74.25 MHz → 27 MHz → 48 MHz, then the game PLL provides 96/48/24 MHz. `clk_sys` and `clk_rom` are 96 MHz. The menu uses the actual 24 MHz output with a divide-by-four pixel enable: 6 MHz and 438 × 250 total pixels, about 54.79 Hz. The game clocks and raster remain native.

The EEPROM chip, host restore port and four-byte commit mirror share `clk_rom`. The SPI address crosses from 74.25 MHz through `lab_nv_addr_meta` and `lab_nv_addr_sync`. Only the first five-bit synchronizer register is excepted as asynchronous. Its second stage, EEPROM read and command response remain ordinary timed paths. The native SPI read strobe takes a longer crossing path; physical SPI simulations assert that the complete address and data are ready at every read strobe.

Three inherited clocks remain outside the original clock definitions:

- `u_frame|u_base|audio|aud_mclk_divider[1]`
- `u_frame|u_base|u_video|pck_rgb_clk`
- `u_frame|u_base|u_video|pck_rgb_clkq`

Native DDR video outputs, I2S, and external pins without input/output delays therefore are not a complete pin-level timing signoff. In particular, the inherited constraints do not describe the CRAM1 art-cache external timing. No new exception was added to hide those paths. The full SPI, renderer, serializer, memory protocol and source checks supplement this limited STA evidence; hardware acceptance remains required.

Separate read-path diagnostics on copies of the completed fits evaluate the 96 MHz CRAM1 controller's nine-cycle access (93.75 ns) against the memory's 70 ns address/ADV/CE access requirement. The [manufacturer datasheet, Table 13 and Figure 24](https://www.alliancememory.com/wp-content/uploads/AS1C8M16PL-70BIN_AllianceMemory_128M_LP-PSRAM-CellularRAM_x2stack_AS1C8M16PL-70BIN_August2018-v1.0.pdf) defines this asynchronous timing. All four corners retain the following minimum calculated read budget after pad paths, earliest capture, latest launch and capture setup:

| Core bitstream SHA-256 prefix | Read budget remaining |
|---|---:|
| CPS1 `0a2560d24a979979` | about 5.63 ns |
| CPS1.5 `cb91a01c9e8721a6` | about 5.21 ns |
| CPS2 `3df11ca2fe8919e7` | about 5.64 ns |

These figures still exclude PCB delay and clock uncertainty absent from the diagnostic paths. Temporary 100 ns max-delay exceptions only expose pad delays in copied databases; their reported slack is not an acceptance metric. The exact controller also passed the synthetic 70 ns pin model with 45,568 writes, 3,321 reads, overlapping uploads and cancellation. Full external read-hold/write closure and physical-board behavior remain outside this evidence.

The [EEPROM ERASE_ALL repair](EEPROM-ERAL-FIX.md) documents the separate native command fix and its serial/SPI verification scope.

The only accepted critical warnings concern zero padding beyond the used native ADPCM table or pause-text ROM. Timing failures and other critical warnings reject packaging.
