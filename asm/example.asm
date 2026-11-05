; Example program: build and run it with 'python assemble.py example --run';
; expect x3 = 8 and mem[8] = 8.

.data 5 3                    ; mem[0] = 5, mem[4] = 3

LW   x1, x0, #0              ; x1 = mem[x0 + 0] = 5
LW   x2, x0, #4              ; x2 = mem[x0 + 4] = 3
ADD  x3, x1, x2              ; x3 = 5 + 3 = 8
SW   x3, x0, #8              ; mem[x0 + 8] = x3

ADDI x4, x0, #-1             ; x4 = -1, which is 0xFFFFFFFF
AND  x5, x3, x4              ; x5 = 8 & 0xFFFFFFFF = 8
OR   x6, x1, x2              ; x6 = 5 | 3 = 7
XOR  x7, x1, x2              ; x7 = 5 ^ 3 = 6
SUB  x8, x1, x2              ; x8 = 5 - 3 = 2

HALT
