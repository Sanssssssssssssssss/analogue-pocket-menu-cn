architecture chip32.vm
output "loader.bin", create
// SPDX-License-Identifier: MIT
// Experimental host operations: assemble/check offline before any device trial.
constant early_host = 0
constant base = 0x60000000
constant id_a = 0x504C4100
constant id_b = 0x504C4201
// 0x0000 error vector; 0x0002 boot vector.
jp error
jp start
start:
    ld r0,#0
    core r0
    ld r0,#base
    ld r1,#0
    pmpr r0,r1
    cmp r1,#id_a
    jp nz,missing
    ld r0,#base+0x10
    ld r1,#1
    pmpw r0,r1
    ld r0,#early_host
    cmp r0,#0
    jp z,poll_start
    host r0,r0
poll_start:
    ld r3,#4096
    ld r0,#base+0x14
poll:
    ld r1,#0
    pmpr r0,r1
    cmp r1,#1
    jp z,selected
    cmp r1,#2
    jp z,selected
    sub r3,#1
    jp nz,poll
    ld r0,#timeout_msg
    printf r0
    exit 1
selected:
    ld r0,#1
    core r0
    ld r0,#base
    ld r1,#0
    pmpr r0,r1
    cmp r1,#id_b
    jp nz,mismatch
    ld r0,#0
    core r0
    ld r0,#base
    ld r1,#0
    pmpr r0,r1
    cmp r1,#id_a
    jp nz,mismatch
    ld r0,#0x4002
    host r0,r0
    ld r0,#success_msg
    printf r0
    exit 0
missing:
    ld r0,#missing_msg
    printf r0
    exit 1
mismatch:
    ld r0,#mismatch_msg
    printf r0
    exit 1
error:
    ld r0,#error_msg
    printf r0
    err r0,r1
    hex.b r0
    hex.w r1
    exit 1
missing_msg:
db "NO_FPGA: selector identity unavailable",10,0
timeout_msg:
db "NO_INPUT: bounded poll exhausted",10,0
mismatch_msg:
db "NO_SWITCH: FPGA identity mismatch",10,0
success_msg:
db "IDENTITY_A_B_A: check physical display and input separately",10,0
error_msg:
db "VM_ERROR: ",0
