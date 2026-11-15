// SPDX-License-Identifier: MIT
// Explicit OS reload control. R12 survives VM invocation; the FPGA is not reloaded first.
    cmp r12,#0x504C4142
    jp z,reenter
    ld r0,#0
    core r0
    ld r12,#0x504C4142
    ld r8,#0xC1
    ld r10,#0x504C4100
    jp reentry_load
reenter:
    ld r0,#0x60000014
    pmpr r0,r7
    cmp r7,#1
    jp z,reentry_a
    cmp r7,#2
    jp z,reentry_b
    ld r8,#0xE6
    jp reentry_load
reentry_a:
    ld r0,#0
    core r0
    ld r8,#0xC2
    ld r10,#0x504C4100
    jp reentry_load
reentry_b:
    ld r0,#1
    core r0
    ld r8,#0xC2
    ld r10,#0x504C4201
reentry_load:
    ld r0,#0
    loadf r0
    ld r0,#0x60000000
    pmpr r0,r9
    cmp r8,#0xE6
    jp z,reentry_report
    cmp r9,r10
    jp z,reentry_report
    ld r8,#0xE7
reentry_report:
    ld r0,#0x60000010
    ld r1,#1
    pmpw r0,r1
    ld r0,#0x60000020
    pmpw r0,r8
    ld r0,#0x60000024
    pmpw r0,r9
