// SPDX-License-Identifier: MIT
// M high byte: D1 choice, D2 timer, D3 loop cap; low 16 bits: keys observed by VM.
// D: elapsed FPGA milliseconds. No switching in this diagnostic.
    ld r0,#0
    core r0
    ld r0,#0
    loadf r0
    ld r0,#0x60000010
    ld r1,#1
    pmpw r0,r1
    ld r0,#0x4002
    host r0,r0
    ld r0,#0x60000008
    pmpr r0,r4
    ld r3,#0x20000
    ld r6,#0
timing_poll:
    ld r0,#0x6000000C
    pmpr r0,r9
    or r6,r9
    ld r0,#0x60000014
    pmpr r0,r1
    cmp r1,#1
    jp z,timing_choice
    cmp r1,#2
    jp z,timing_choice
    ld r0,#0x60000008
    pmpr r0,r5
    sub r5,r4
    cmp r5,#15000
    jp nc,timing_expired
    sub r3,#1
    jp nz,timing_poll
    ld r8,#0xD3000000
    jp timing_report
timing_expired:
    ld r8,#0xD2000000
    jp timing_report
timing_choice:
    ld r8,#0xD1000000
timing_report:
    and r6,#0xFFFF
    or r8,r6
    ld r0,#0x60000008
    pmpr r0,r9
    sub r9,r4
    ld r0,#0x60000020
    pmpw r0,r8
    ld r0,#0x60000024
    pmpw r0,r9
    exit 0
