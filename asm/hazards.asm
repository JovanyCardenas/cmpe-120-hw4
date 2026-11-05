; Hazards to test your pipeline against: build and run with
; 'python assemble.py hazards --run'; expect x2 = 14, x5 = 24, x6 = 31.
;
;  * the ADD right after a LW needs the loaded value, so the pipeline must
;    stall for one cycle instead of forwarding a value it does not have yet;
;  * every ADDI/ADD below reads a register the previous instruction is still
;    writing, so ALU-to-ALU forwarding has to be correct.

.data 7 11 13 17             ; mem[0]=7, mem[4]=11, mem[8]=13, mem[12]=17

LW   x1, x0, #0              ; x1 = 7
ADD  x2, x1, x1              ; x2 = 14   (load-use: stall one cycle)
LW   x3, x0, #4              ; x3 = 11
LW   x4, x0, #8              ; x4 = 13
ADD  x5, x3, x4              ; x5 = 24   (load-use: stall one cycle)
ADD  x6, x5, x1              ; x6 = 31
SW   x6, x0, #16             ; mem[16] = 31
HALT
