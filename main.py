#!/usr/bin/env python3
"""CMPE 120 HW4 -- 5-stage pipelined RV32I simulator.

Fill in the six methods marked TODO. Everything else -- argument parsing, the
run loop, and all four output writers -- is already written, and it must not
be modified: the autograder reads the files those writers produce.

HW3 was single-cycle. HW4 is a 5-stage pipeline (IF, ID, EX, MEM, WB): several
instructions are in flight at once. You need forwarding, a load-use stall, and
control-hazard handling for branches and jumps. Do **not** use branch
prediction or speculation: stall and insert a bubble until the branch or jump
is resolved, then fetch the correct next PC.

Run it with:

    python main.py --iodir <directory containing imem.txt and dmem.txt>
"""

import argparse
import os
import sys

MEM_SIZE = 1000
HALT_INSTR = 0xFFFFFFFF
MASK32 = 0xFFFFFFFF
MAX_CYCLES = 1000000

# RISC-V instruction opcodes
OP_RTYPE = 0x33
OP_ITYPE = 0x13
OP_LOAD = 0x03
OP_STORE = 0x23
OP_BRANCH = 0x63
OP_JAL = 0x6F
OP_JALR = 0x67

def sign_extend(value, bits):
    # Convert a signed binary value into a python integer
    sign_bit = 1 << (bits - 1)
    return (value ^ sign_bit) - sign_bit

def decode_instruction(instr):
    # Extract the fields of a 32-bit RISC-V instruction

    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x07
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    # I-type immediate
    imm_i = sign_extend(instr >> 20, 12)

    # S-type immediate (stores)
    imm_s = ((instr >> 25) << 5) | ((instr >> 7) & 0x1F)
    imm_s = sign_extend(imm_s, 12)

    # B-type immediate (branches)
    imm_b = (
        ((instr >> 31) & 1) << 12
        | ((instr >> 7) & 1) << 11
        | ((instr >> 25) & 0x3F) << 5
        | ((instr >> 8) & 0x0F) << 1
    )
    imm_b = sign_extend(imm_b, 13)

    # J-type immediate (JAL)
    imm_j = (
        ((instr >> 31) & 1) << 20
        | ((instr >> 12) & 0xFF) << 12
        | ((instr >> 20) & 1) << 11
        | ((instr >> 21) & 0x3FF) << 1
    )
    imm_j = sign_extend(imm_j, 21)

    return {
        "opcode": opcode,
        "rd": rd,
        "rs1": rs1,
        "rs2": rs2,
        "funct3": funct3,
        "funct7": funct7,
        "imm_i": imm_i,
        "imm_s": imm_s,
        "imm_b": imm_b,
        "imm_j": imm_j,
    }

def alu(operation, a, b):
    # Perform a 32-bit arithmetic or logical operation

    a = a & MASK32
    b = b & MASK32

    if operation == "ADD":
        result = a + b
    elif operation == "SUB":
        result = a - b
    elif operation == "AND":
        result = a & b
    elif operation == "OR":
        result = a | b
    elif operation == "XOR":
        result = a ^ b
    else:
        raise ValueError(f"Unsupported ALU operation: {operation}")

    return result & MASK32

def _stage_pc(stage):
    if stage.get("nop", True):
        return -1
    return int(stage.get("PC", 0)) & MASK32


class InsMem(object):
    def __init__(self, io_dir):
        with open(os.path.join(io_dir, "imem.txt")) as fh:
            self.bytes = [line.strip() for line in fh if line.strip()]

    def readInstr(self, ReadAddress):
        """Return the 32-bit instruction at byte address ``ReadAddress``.

        The four consecutive bytes are concatenated most-significant byte
        first (big-endian). An address that does not have four bytes of
        instruction memory behind it returns 0.
        """
        if ReadAddress < 0 or ReadAddress + 4 > len(self.bytes):
            return 0
        # TODO: Return the 32-bit instruction at byte address ReadAddress.
        # raise NotImplementedError("InsMem.readInstr")

        """ Turns 4 bytes
        00000000
        00000001
        00000000
        10010011

        into one 32-bit instruction
        00000000000100000000000010010011 
        """

        instruction = "".join(self.bytes[ReadAddress:ReadAddress + 4])
        return int(instruction, 2)


class DataMem(object):
    def __init__(self, io_dir):
        self.io_dir = io_dir
        with open(os.path.join(io_dir, "dmem.txt")) as fh:
            initial = [int(line.strip(), 2) for line in fh if line.strip()]
        self.image = initial + [0] * (MEM_SIZE - len(initial))

    def readDataMem(self, ReadAddress):
        """Read the 32-bit word at byte address ``ReadAddress`` (big-endian).

        Bytes that fall outside the memory read as 0.
        """
        # TODO: Return the 32-bit word at byte address ReadAddress.
        # raise NotImplementedError("DataMem.readDataMem")

        """ Read 4 bytes from memory
        << 8 shifts existing value left by 8 bits
        | byte combines the value with the next byte
        """

        value = 0
        for i in range(4):
            address = ReadAddress + i
            byte = self.image[address] if 0 <= address < MEM_SIZE else 0
            value = (value << 8) | byte

        return value

    def writeDataMem(self, Address, WriteData):
        """Write the low 32 bits of ``WriteData`` at byte address ``Address``.

        Bytes that fall outside the memory are silently dropped.
        """
        # TODO: Store WriteData at byte address Address.
        # raise NotImplementedError("DataMem.writeDataMem")

        # Breaking 32-bit number into four separate bytes
        # & 0xFF extracts one byte at a time

        WriteData = WriteData & MASK32

        for i in range(4):
            address = Address + i
            if 0 <= address < MEM_SIZE:
                shift = 8 * (3 - i)
                self.image[address] = (WriteData >> shift) & 0xFF

    def outputDataMem(self):
        with open(os.path.join(self.io_dir, "DMEMResult.txt"), "w") as fh:
            for byte in self.image:
                fh.write(format(byte, "08b") + "\n")


class RegisterFile(object):
    def __init__(self, io_dir):
        self.io_dir = io_dir
        self.regs = [0] * 32

    def readRF(self, Reg_addr):
        """Return the 32-bit value of register ``Reg_addr``."""
        # TODO: Return the value held in register Reg_addr.
        # raise NotImplementedError("RegisterFile.readRF")

        return self.regs[Reg_addr]

    def writeRF(self, Reg_addr, Wrt_reg_data):
        """Write the low 32 bits of ``Wrt_reg_data`` to register ``Reg_addr``.

        x0 is hardwired to zero, so writes to it are discarded.
        """
        # TODO: Store Wrt_reg_data in register Reg_addr. Writes to x0 are ignored.
        # raise NotImplementedError("RegisterFile.writeRF")

        if Reg_addr != 0:
            self.regs[Reg_addr] = Wrt_reg_data & MASK32

    def outputRF(self):
        with open(os.path.join(self.io_dir, "RFResult.txt"), "w") as fh:
            for value in self.regs:
                fh.write(format(value, "032b") + "\n")


class State(object):
    """Pipeline registers.

    The starter only stores ``nop`` and ``PC`` so the given run loop can
    write the trace (``-1`` when ``nop`` is true). Add any other fields
    your datapath needs.
    """

    def __init__(self):
        self.IF = {"nop": False, "PC": 0}
        self.ID = {"nop": True, "PC": 0}
        self.EX = {"nop": True, "PC": 0}
        self.MEM = {"nop": True, "PC": 0}
        self.WB = {"nop": True, "PC": 0}


class Core(object):
    def __init__(self, io_dir, imem, dmem):
        self.io_dir = io_dir
        self.imem = imem
        self.dmem = dmem
        self.myRF = RegisterFile(io_dir)
        self.state = State()
        self.nextState = State()
        self.halted = False
        self.cycle = 0
        self.instructions_executed = 0
        self.trace = []
        self.verbose = False

    def step(self):
        raise NotImplementedError

    def _pipeline_empty(self):
        return (
            self.state.IF["nop"]
            and self.state.ID["nop"]
            and self.state.EX["nop"]
            and self.state.MEM["nop"]
            and self.state.WB["nop"]
        )

    def run(self):
        while True:
            if self.cycle > 0 and self._pipeline_empty():
                self.halted = True
                break
            if self.cycle >= MAX_CYCLES:
                print("Error: exceeded %d cycles" % MAX_CYCLES, file=sys.stderr)
                self.halted = True
                break
            row = (
                self.cycle,
                _stage_pc(self.state.IF),
                _stage_pc(self.state.ID),
                _stage_pc(self.state.EX),
                _stage_pc(self.state.MEM),
                _stage_pc(self.state.WB),
            )
            self.trace.append(row)
            if self.verbose:
                print(
                    "cycle %-4d IF %-6s ID %-6s EX %-6s MEM %-6s WB %-6s"
                    % row
                )
            self.step()
            self.cycle += 1

        self.myRF.outputRF()
        self.dmem.outputDataMem()
        self.outputTrace()
        self.outputMetrics()

    def outputTrace(self):
        with open(os.path.join(self.io_dir, "TraceResult.txt"), "w") as fh:
            fh.write("# cycle IF.PC ID.PC EX.PC MEM.PC WB.PC\n")
            for row in self.trace:
                fh.write("%d %d %d %d %d %d\n" % row)

    def outputMetrics(self):
        cycles = self.cycle
        executed = self.instructions_executed
        cpi = cycles / executed if executed else 0.0
        ipc = executed / cycles if cycles else 0.0
        lines = [
            "Total Cycles: %d" % cycles,
            "Instructions Executed: %d" % executed,
            "CPI: %.6f" % cpi,
            "IPC: %.6f" % ipc,
        ]
        with open(os.path.join(self.io_dir, "PerformanceMetrics.txt"), "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print("\n".join(lines))


class FiveStageCore(Core):
    """5-stage pipeline with forwarding, load-use stall, and ID control."""

    def step(self):
        """Advance the pipeline by one clock.

        Process stages backwards (WB -> MEM -> EX -> ID -> IF) so that
        later stages see this cycle's results. Write ``self.nextState``,
        then copy it onto ``self.state`` at the end of the clock.

        Count a retired instruction in WB (not HALT, not a bubble). HALT
        stops fetching; then drain the remaining stages.

        Control: no speculation. On BEQ/BNE/JAL/JALR in ID, stall IF and
        insert a bubble, then redirect fetch to the correct PC.
        """
        # TODO: Implement the 5-stage pipeline for this clock.
        # --------------------- WB stage ---------------------
        # --------------------- MEM stage --------------------
        # --------------------- EX stage ---------------------
        # --------------------- ID stage ---------------------
        # --------------------- IF stage ---------------------
        # raise NotImplementedError("FiveStageCore.step")

        # Create a fresh state for the next clock cycle
        self.nextState = State()

        # Start with empty pipeline stages
        self.nextState.IF = {"nop": True, "PC": 0}
        self.nextState.ID = {"nop": True, "PC": 0}
        self.nextState.EX = {"nop": True, "PC": 0}
        self.nextState.MEM = {"nop": True, "PC": 0}
        self.nextState.WB = {"nop": True, "PC": 0}

        # This ensures every stage starts as an empty bubble until an actual instruction moves into it

        # --------------------- WB stage ---------------------

        if not self.state.WB["nop"]:
            wb = self.state.WB
            if wb.get("reg_write", False):
                self.myRF.writeRF(
                    wb["rd"],
                    wb["write_data"]
                )
            self.instructions_executed += 1

        # --------------------- MEM stage --------------------

        if not self.state.MEM["nop"]:
            mem = self.state.MEM

            write_data = mem["alu_result"]
            opcode = mem["opcode"]

            # Load Word
            if opcode == OP_LOAD:
                write_data = self.dmem.readDataMem(
                    mem["alu_result"]
                )

            # Store Word
            if opcode == OP_STORE:
                self.dmem.writeDataMem(
                    mem["alu_result"],
                    mem["store_data"]
                )

            # Forward instruction information to WB
            self.nextState.WB = {
                "nop": False,
                "PC": mem["PC"],
                "opcode": opcode,
                "rd": mem["rd"],
                "reg_write": mem["reg_write"],
                "write_data": write_data & MASK32,
            }

        # --------------------- EX stage ---------------------

        if not self.state.EX["nop"]:
            ex = self.state.EX

            opcode = ex["opcode"]
            rd = ex["rd"]
            rs1 = ex["rs1"]
            rs2 = ex["rs2"]
            funct3 = ex["funct3"]
            funct7 = ex["funct7"]

            a = ex["rs1_val"]
            b = ex["rs2_val"]

            # Forward from MEM (newest result first)
            mem = self.state.MEM

            if not mem["nop"] and mem.get("reg_write", False):
                if mem["rd"] != 0 and mem["opcode"] != OP_LOAD:
                    if mem["rd"] == rs1:
                        a = mem["alu_result"]

                    if mem["rd"] == rs2:
                        b = mem["alu_result"]

            # Forward from WB if MEM does not have a newer value
            wb = self.state.WB

            if not wb["nop"] and wb.get("reg_write", False):
                if wb["rd"] != 0:
                    mem_writes = (
                        not mem["nop"]
                        and mem.get("reg_write", False)
                        and mem["rd"] != 0
                        and mem["opcode"] != OP_LOAD
                    )

                    if wb["rd"] == rs1:
                        if not (mem_writes and mem["rd"] == rs1):
                            a = wb["write_data"]

                    if wb["rd"] == rs2:
                        if not (mem_writes and mem["rd"] == rs2):
                            b = wb["write_data"]

            # Execute instruction
            result = 0

            if opcode == OP_RTYPE:
                if funct3 == 0:
                    if funct7 == 0x20:
                        result = alu("SUB", a, b)
                    else:
                        result = alu("ADD", a, b)
                elif funct3 == 7:
                    result = alu("AND", a, b)
                elif funct3 == 6:
                    result = alu("OR", a, b)
                elif funct3 == 4:
                    result = alu("XOR", a, b)
            elif opcode == OP_ITYPE:
                imm = ex["imm_i"]

                if funct3 == 0:
                    result = alu("ADD", a, imm)
                elif funct3 == 7:
                    result = alu("AND", a, imm)
                elif funct3 == 6:
                    result = alu("OR", a, imm)
                elif funct3 == 4:
                    result = alu("XOR", a, imm)
            elif opcode == OP_LOAD:
                result = alu("ADD", a, ex["imm_i"])
            elif opcode == OP_STORE:
                result = alu("ADD", a, ex["imm_s"])
            elif opcode in (OP_JAL, OP_JALR):
                result = (ex["PC"] + 4) & MASK32

            # Pass result to the MEM stage
            self.nextState.MEM = {
                "nop": False,
                "PC": ex["PC"],
                "opcode": opcode,
                "rd": rd,
                "reg_write": ex["reg_write"],
                "alu_result": result & MASK32,
                "store_data": b & MASK32,
            }

        # --------------------- ID stage ---------------------

        stalled = False
        redirected = False
        redirect_pc = 0

        if not self.state.ID["nop"]:
            ide = self.state.ID

            instr = ide["instr"]
            d = decode_instruction(instr)

            opcode = d["opcode"]
            rs1 = d["rs1"]
            rs2 = d["rs2"]
            rd = d["rd"]

            uses_rs1 = opcode in (
                OP_RTYPE, OP_ITYPE, OP_LOAD,
                OP_STORE, OP_BRANCH, OP_JALR
            )

            uses_rs2 = opcode in (
                OP_RTYPE, OP_STORE, OP_BRANCH
            )

            ex = self.state.EX
            if (
                not ex["nop"]
                and ex["opcode"] == OP_LOAD
                and ex["rd"] != 0
                and (
                    (uses_rs1 and ex["rd"] == rs1)
                    or (uses_rs2 and ex["rd"] == rs2)
                )
            ):
                stalled = True
                self.nextState.ID = ide.copy()
                self.nextState.IF = self.state.IF.copy()

            else:
                a = self.myRF.readRF(rs1) if uses_rs1 else 0
                b = self.myRF.readRF(rs2) if uses_rs2 else 0

                # Forward from MEM into ID
                mem = self.state.MEM

                if not mem["nop"] and mem.get("reg_write", False):
                    if mem["rd"] != 0:
                        value = self.nextState.WB["write_data"]

                        if uses_rs1 and mem["rd"] == rs1:
                            a = value

                        if uses_rs2 and mem["rd"] == rs2:
                            b = value

                # Forward from EX into ID
                ex = self.state.EX

                if not ex["nop"] and ex.get("reg_write", False):
                    if ex["rd"] != 0 and ex["opcode"] != OP_LOAD:
                        value = self.nextState.MEM["alu_result"]

                        if uses_rs1 and ex["rd"] == rs1:
                            a = value

                        if uses_rs2 and ex["rd"] == rs2:
                            b = value

                reg_write = opcode in (
                    OP_RTYPE, OP_ITYPE, OP_LOAD,
                    OP_JAL, OP_JALR
                )

                self.nextState.EX = {
                    "nop": False,
                    "PC": ide["PC"],
                    "opcode": opcode,
                    "rd": rd,
                    "rs1": rs1,
                    "rs2": rs2,
                    "funct3": d["funct3"],
                    "funct7": d["funct7"],
                    "imm_i": d["imm_i"],
                    "imm_s": d["imm_s"],
                    "rs1_val": a,
                    "rs2_val": b,
                    "reg_write": reg_write,
                }

                # Branches
                if opcode == OP_BRANCH:
                    if d["funct3"] == 0:
                        taken = (a == b) # BEQ
                    else:
                        taken = (a != b) # BNE

                    redirected = True

                    if taken:
                        redirect_pc = (ide["PC"] + d["imm_b"]) & MASK32
                    else:
                        redirect_pc = self.state.IF["PC"]

                # Jump and Link
                elif opcode == OP_JAL:
                    redirected = True
                    redirect_pc = (ide["PC"] + d["imm_j"]) & MASK32

                # Jump and Link Register
                elif opcode == OP_JALR:
                    redirected = True
                    redirect_pc = (a + d["imm_i"]) & MASK32
                    redirect_pc &= ~1

        # --------------------- IF stage ---------------------

        if not stalled and redirected:
            self.nextState.IF = {
                "nop": False,
                "PC": redirect_pc
            }
        elif not stalled and not self.state.IF["nop"]:
            pc = self.state.IF["PC"]
            instr = self.imem.readInstr(pc)

            if instr != HALT_INSTR:
                self.nextState.ID = {
                    "nop": False,
                    "PC": pc,
                    "instr": instr,
                }

                self.nextState.IF = {
                    "nop": False,
                    "PC": (pc + 4) & MASK32,
                }

        self.state = self.nextState


def main(argv=None):
    parser = argparse.ArgumentParser(description="RV32I 5-stage pipelined processor")
    parser.add_argument(
        "--iodir",
        default=".",
        type=str,
        help="Directory holding imem.txt and dmem.txt. Outputs are written here.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print one pipeline occupancy line per clock.",
    )
    args = parser.parse_args(argv)

    io_dir = os.path.abspath(args.iodir)
    print("IO Directory:", io_dir)

    core = FiveStageCore(io_dir, InsMem(io_dir), DataMem(io_dir))
    core.verbose = args.verbose
    core.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
