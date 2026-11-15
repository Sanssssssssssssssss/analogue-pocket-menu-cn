architecture chip32.vm
output "loader.bin", create
// SPDX-License-Identifier: MIT
// No polling, input, CALL/RET or early HOST; one diagnostic operation per entry.
jp error
jp start
start:
// BODY
    ld r0,#0x4002
    host r0,r0
    exit 0
error:
    ld r0,#error_msg
    printf r0
    err r0,r1
    hex.b r0
    ld r2,#pc_msg
    printf r2
    hex.w r1
    ld r0,#newline
    printf r0
    exit 1
error_msg:
db "VME ",0
pc_msg:
db " PC ",0
newline:
db 10,0
