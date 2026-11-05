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
        raise NotImplementedError("InsMem.readInstr")


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
        raise NotImplementedError("DataMem.readDataMem")

    def writeDataMem(self, Address, WriteData):
        """Write the low 32 bits of ``WriteData`` at byte address ``Address``.

        Bytes that fall outside the memory are silently dropped.
        """
        # TODO: Store WriteData at byte address Address.
        raise NotImplementedError("DataMem.writeDataMem")

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
        raise NotImplementedError("RegisterFile.readRF")

    def writeRF(self, Reg_addr, Wrt_reg_data):
        """Write the low 32 bits of ``Wrt_reg_data`` to register ``Reg_addr``.

        x0 is hardwired to zero, so writes to it are discarded.
        """
        # TODO: Store Wrt_reg_data in register Reg_addr. Writes to x0 are ignored.
        raise NotImplementedError("RegisterFile.writeRF")

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
        raise NotImplementedError("FiveStageCore.step")


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
