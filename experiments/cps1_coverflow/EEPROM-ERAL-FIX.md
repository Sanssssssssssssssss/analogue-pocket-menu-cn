# Native EEPROM ERASE_ALL repair

This build repairs an upstream `jt9346` ERASE_ALL initialization defect in addition to the Pocket save transport changes. The original ERAL branch set `newdata` but did not initialize the address or actual RAM write data consumed by `WRITE_ALL`. After a prior write, ERAL could retain old data and erase an incomplete address range.

The fix initializes `addr=0` and `mem_din={DW{1'b1}}` before entering the original sequencer. The existing nonblocking write pipeline visits the remaining addresses and then writes address 0 on entry to WAIT. No save-file format changes are involved.

The defect was reproduced on the unmodified upstream module, SHA-256 `df80023ff68bc65377b1479c5660e185f8e1adaf86126943989e1f54eeb63da1`, using only serial pins and its original RAM. Both 64 × 16-bit and 128 × 8-bit modes failed every erased-word comparison after successful initial serial write/read. The isolated two-line repair passed every address, ERASE disable/enable, repeated erase, subsequent write/read, WRITE_ALL, and ordinary ERASE. The tests used non-FF first and last words.

The integrated candidate additionally verifies full serial commits against native RAM and the Pocket SPI readback mirror in both widths, plus save restore, Stop, late reads and new-game binding. Separate real-SPI launch tests cover loading, instance configuration, save/flush and return to menu. These are simulation and source results; they do not claim commercial-game execution or physical-board acceptance.

The inherited `erase_en` flag gates ERAL only. This repair preserves the original permission behavior of ordinary WRITE, WRITE_ALL and single-address ERASE; it does not introduce a complete hardware write-disable model. EWDS coverage above means that ERAL is refused when disabled.

This file documents the source change and validation scope. It is not a synthesis input.
