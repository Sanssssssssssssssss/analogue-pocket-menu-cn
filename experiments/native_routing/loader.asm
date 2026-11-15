architecture chip32.vm
output "loader.bin", create
// SPDX-License-Identifier: MIT
constant early_host = 0
constant base = 0x60000000
constant id_a = 0x504C4100
constant id_b = 0x504C4201
// 0x0000 error vector; 0x0002 boot vector.
jp error
jp start
start:
    ld r13,#0
    ld r0,#0
    core r0
    ld r0,#0
    loadf r0
    ld r0,#base
    ld r1,#0
    pmpr r0,r1
    cmp r1,#id_a
    jp nz,missing
    ld r8,#0x10
    ld r9,r1
    call report
    // Explicit literals avoid BASS choosing a truncated 16-bit expression encoding.
    ld r0,#0x60000010
    ld r1,#1
    pmpw r0,r1
    ld r8,#0x20
    ld r9,#early_host
    call report
    ld r0,#early_host
    cmp r0,#0
    jp z,poll_start
    host r0,r0
    ld r0,#early_host
    cmp r0,#0x4002
    jp nz,poll_start
    ld r13,#1
poll_start:
    ld r8,#0x21
    call report
    ld r0,#0x60000008
    pmpr r0,r4
    ld r3,#0x20000
poll:
    ld r0,#0x60000014
    ld r1,#0
    pmpr r0,r1
    cmp r1,#1
    jp z,selected
    cmp r1,#2
    jp z,selected
    ld r0,#0x60000008
    pmpr r0,r5
    sub r5,r4
    cmp r5,#5000
    jp nc,no_input
    sub r3,#1
    jp nz,poll
no_input:
    ld r8,#0xE2
    ld r0,#0x6000000C
    pmpr r0,r9
    jp finish
selected:
    ld r8,#0x30
    ld r9,r1
    call report
    ld r13,#0
    ld r0,#1
    core r0
    ld r0,#0
    loadf r0
    ld r0,#base
    ld r1,#0
    pmpr r0,r1
    ld r9,r1
    cmp r1,#id_b
    jp nz,b_failed
    ld r0,#0
    core r0
    ld r0,#0
    loadf r0
    ld r0,#base
    ld r1,#0
    pmpr r0,r1
    ld r9,r1
    cmp r1,#id_a
    jp nz,a_failed
    ld r8,#0xA0
    jp finish
b_failed:
    ld r8,#0xE3
    jp finish
a_failed:
    ld r8,#0xE4
finish:
    call report
    // EXIT 0 means the diagnostic screen can boot; inspect M for routing success.
    cmp r13,#1
    jp z,done
    ld r0,#0x4002
    host r0,r0
done:
    exit 0
report:
    ld r0,#0x60000020
    pmpw r0,r8
    ld r0,#0x60000024
    pmpw r0,r9
    ret
missing:
    ld r0,#missing_msg
    printf r0
    exit 1
error:
    ld r0,#error_msg
    printf r0
    err r0,r1
    hex.b r0
    hex.w r1
    ld r0,#newline
    printf r0
    exit 1
missing_msg:
db "NO_FPGA: selector identity unavailable",10,0
error_msg:
db "VM_ERROR: ",0
newline:
db 10,0
