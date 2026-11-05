; PC   ENCODING     INSTRUCTION

0      0x00500093   ADDI R1, R0, #5
4      0x00500113   ADDI R2, R0, #5
8      0x00208463   BEQ R1, R2, #8
12     0x3E700193   ADDI R3, R0, #999
16     0x00100213   ADDI R4, R0, #1
20     0x00209463   BNE R1, R2, #8
24     0x00200293   ADDI R5, R0, #2
28     0x00300313   ADDI R6, R0, #3
32     0xFFFFFFFF   HALT

labels:
  skip             16
  nowhere          28
