#!/usr/bin/env python3
"""Assemble a RISC-V program into the ``imem.txt`` and ``dmem.txt`` the simulator reads.

Put a program in ``asm/`` and run::

    python assemble.py sum            # reads asm/sum.asm, writes asm/sum/
    python assemble.py sum --run      # ...then runs your simulator on it
    python assemble.py --all          # assemble every asm/*.asm
    python assemble.py asm/sum.asm    # an explicit path works too

The build directory (``asm/sum/``) then contains::

    imem.txt      the assembled instructions
    dmem.txt      the initial data memory
    code.asm      one line per instruction: address, encoding, instruction (registers as Rn)

Run it with ``python main.py --iodir asm/sum``.


Instructions
------------
One instruction per line. A register may be written ``x0``-``x31``, ``r0``-``r31``, or an ABI name (``zero``, ``ra``, ``sp``, ``gp``, ``tp``, ``t0``-``t6``, ``s0``-``s11``, ``a0``-``a7``, or ``fp`` for ``x8``); spelling is not case-sensitive. Immediates start with ``#``::

    ADD   x3, x1, x2          ; x3 = x1 + x2
    SUB   x3, x1, x2
    AND   x3, x1, x2
    OR    x3, x1, x2
    XOR   x3, x1, x2

    ADDI  x3, x1, #1          ; x3 = x1 + 1
    ANDI  x3, x1, #255
    ORI   x3, x1, #8
    XORI  x3, x1, #-1

    LW    x1, x0, #0          ; x1 = mem[x0 + 0]
    LW    x1, 0(x0)           ; the standard form means the same thing
    SW    x1, x0, #4          ; mem[x0 + 4] = x1
    SW    x1, 4(x0)

    BEQ   x1, x2, done        ; jump to a label...
    BNE   x1, x2, #-16        ; ...or give the byte offset directly
    JAL   x10, function
    JALR  x0, x10, #0
    JAL   x0, #12             ; JAL with rd = x0 is a plain jump

    HALT                      ; stop. End every program with this.

A label marks an address and is used as a branch or jump target; the offsets are computed for you, so you never count instructions::

    loop:
        ADDI x2, x2, #1
        BNE  x2, x3, loop


Data
----
``.data`` fills data memory with 32-bit words, starting at byte address 0 and continuing from the previous ``.data``::

    .data 0x01234567 42 -1    ; mem[0], mem[4], mem[8]

Values may be decimal, ``0x`` hexadecimal or negative. Memory you do not write is zero, so pad with zeros to place data higher up; the order of the values decides the addresses::

    .data 0 0 0 0 100         ; 100 ends up at byte address 16


Comments
--------
Everything from ``;`` or ``//`` to the end of the line is ignored (``#`` is not a comment character; it starts an immediate).
"""

import argparse
import os
import re
import sys

# --- Encodings ---

# The register fields always occupy the same bit positions.
OP_R_TYPE = 0b0110011
OP_I_TYPE = 0b0010011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_BRANCH = 0b1100011
OP_JAL = 0b1101111
OP_JALR = 0b1100111

R_TYPE = {
    # mnemonic: (funct7, funct3)
    "ADD": ("0000000", "000"),
    "SUB": ("0100000", "000"),
    "XOR": ("0000000", "100"),
    "OR": ("0000000", "110"),
    "AND": ("0000000", "111"),
}

I_TYPE_ALU = {
    # mnemonic: funct3
    "ADDI": "000",
    "XORI": "100",
    "ORI": "110",
    "ANDI": "111",
}

FUNCT3_LW = "010"
FUNCT3_SW = "010"
FUNCT3_BEQ = "000"
FUNCT3_BNE = "001"
FUNCT3_JALR = "000"

# HALT is the reserved all-ones word, not a real RISC-V instruction.
HALT_WORD = 0xFFFFFFFF

INSTRUCTION_NAMES = sorted(
    set(R_TYPE)
    | set(I_TYPE_ALU)
    | {"LW", "SW", "BEQ", "BNE", "JAL", "JALR", "HALT"}
)

ABI_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
]

REGISTERS = {}
for _index in range(32):
    REGISTERS["r%d" % _index] = _index
    REGISTERS["x%d" % _index] = _index
    REGISTERS[ABI_NAMES[_index]] = _index
REGISTERS["fp"] = 8

DATA_DIRECTIVE = ".data"


class AsmError(Exception):
    """Raised with a line number whenever a source line cannot be assembled."""


# --- Packing the fields into a 32-bit word ---

def _check_width(value, bits, what, line_no):
    low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if not low <= value <= high:
        raise AsmError(
            "line %d: %s does not fit in %d bits: %d" % (line_no, what, bits, value)
        )


def pack_r(funct7, rs2, rs1, funct3, rd):
    return (
        (int(funct7, 2) << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (int(funct3, 2) << 12)
        | (rd << 7)
        | OP_R_TYPE
    )


def pack_i(imm, rs1, funct3, rd, opcode, line_no=0):
    _check_width(imm, 12, "immediate", line_no)
    return (
        ((imm & 0xFFF) << 20)
        | (rs1 << 15)
        | (int(funct3, 2) << 12)
        | (rd << 7)
        | opcode
    )


def pack_s(imm, rs2, rs1, funct3, line_no=0):
    _check_width(imm, 12, "offset", line_no)
    imm &= 0xFFF
    # The offset is split around rs2/rs1: top 7 bits at [31:25], low 5 at [11:7].
    return (
        (((imm >> 5) & 0x7F) << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (int(funct3, 2) << 12)
        | ((imm & 0x1F) << 7)
        | OP_STORE
    )


def pack_b(imm, rs2, rs1, funct3, line_no=0):
    _check_width(imm, 13, "branch offset", line_no)
    if imm % 2:
        raise AsmError("line %d: branch offset must be even: %d" % (line_no, imm))
    imm &= 0x1FFF
    # 13 bits with bit 0 always zero, so 12 of them are stored.
    imm_12 = (imm >> 12) & 1
    imm_10_5 = (imm >> 5) & 0x3F
    imm_4_1 = (imm >> 1) & 0xF
    imm_11 = (imm >> 11) & 1
    return (
        (imm_12 << 31)
        | (imm_10_5 << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (int(funct3, 2) << 12)
        | (imm_4_1 << 8)
        | (imm_11 << 7)
        | OP_BRANCH
    )


def pack_j(imm, rd, line_no=0):
    _check_width(imm, 21, "jump offset", line_no)
    if imm % 2:
        raise AsmError("line %d: jump offset must be even: %d" % (line_no, imm))
    imm &= 0x1FFFFF
    # 21 bits with bit 0 always zero, so 20 of them are stored.
    imm_20 = (imm >> 20) & 1
    imm_10_1 = (imm >> 1) & 0x3FF
    imm_11 = (imm >> 11) & 1
    imm_19_12 = (imm >> 12) & 0xFF
    return (
        (imm_20 << 31)
        | (imm_10_1 << 21)
        | (imm_11 << 20)
        | (imm_19_12 << 12)
        | (rd << 7)
        | OP_JAL
    )


# --- Reading the source ---

_MEMORY_OPERAND = re.compile(r"^\s*([#\-\w+]+)\s*\(\s*([\w]+)\s*\)\s*$")
_LABEL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def _strip_comment(line):
    for marker in (";", "//"):
        cut = line.find(marker)
        if cut != -1:
            line = line[:cut]
    return line.strip()


def _parse_register(token, line_no):
    key = token.strip().lower()
    if key not in REGISTERS:
        raise AsmError("line %d: unknown register '%s'" % (line_no, token))
    return REGISTERS[key]


def _is_register(token):
    return token.strip().lower() in REGISTERS


def _parse_number(token, line_no, what="immediate"):
    text = token.strip()
    if text.startswith("#"):
        text = text[1:]
    try:
        return int(text, 0)
    except ValueError:
        raise AsmError("line %d: bad %s '%s'" % (line_no, what, token))


def _parse_memory_operand(text, line_no):
    match = _MEMORY_OPERAND.match(text)
    if match:
        return (
            _parse_number(match.group(1), line_no, "offset"),
            _parse_register(match.group(2), line_no),
        )
    raise AsmError("line %d: bad memory operand '%s'" % (line_no, text))


def _split_operands(text):
    return [part.strip() for part in text.split(",")] if text.strip() else []


class Program(object):
    """The result of assembling one source file."""

    def __init__(self, words, labels, listing, data):
        self.words = words      # instruction words, in address order
        self.labels = labels    # label -> byte address
        self.listing = listing  # (byte address, word, source) per instruction
        self.data = data        # [(byte address, 32-bit value)] from .data

    def memory_size(self):
        """How many bytes of dmem.txt this program needs, at least one word."""
        end = max([address + 4 for address, _ in self.data] or [0])
        return max(4, ((end + 3) // 4) * 4)

    def data_at(self, address):
        for placed, value in self.data:
            if placed == address:
                return value
        return None


def assemble(source):
    """Assemble `source` and return a `Program`."""
    parsed = []
    labels = {}
    data = []

    for line_no, raw in enumerate(source.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line:
            continue

        if line.lower().startswith(DATA_DIRECTIVE):
            rest = line[len(DATA_DIRECTIVE):].strip()
            for token in _split_operands(rest.replace(" ", ",")):
                if token:
                    data.append(
                        (_next_data_address(data),
                         _parse_number(token, line_no, "data value") & 0xFFFFFFFF)
                    )
            continue

        # A line may carry any number of labels before its instruction.
        while True:
            match = _LABEL.match(line)
            if not match:
                break
            name = match.group(1)
            if name.upper() in INSTRUCTION_NAMES:
                break  # not a label after all, it is an instruction
            if name in labels:
                raise AsmError("line %d: duplicate label '%s'" % (line_no, name))
            labels[name] = 4 * len(parsed)
            line = match.group(2).strip()

        if not line:
            continue

        parts = line.split(None, 1)
        mnemonic = parts[0].upper()
        operands = parts[1] if len(parts) > 1 else ""
        if mnemonic not in INSTRUCTION_NAMES:
            raise AsmError(
                "line %d: unknown instruction '%s' (not one of %s)"
                % (line_no, mnemonic, ", ".join(INSTRUCTION_NAMES))
            )
        parsed.append((line_no, mnemonic, operands))

    words = []
    listing = []
    for line_no, mnemonic, operands in parsed:
        address = 4 * len(words)
        word = _encode(line_no, mnemonic, operands, address, labels)
        words.append(word)
        listing.append((address, word, "%s %s" % (mnemonic, operands)))

    return Program(words, labels, listing, data)


def _next_data_address(data):
    return 4 * len(data)


def _encode(line_no, mnemonic, operands, address, labels):
    fields = _split_operands(operands)

    def want(count):
        if len(fields) != count:
            raise AsmError(
                "line %d: %s takes %d operands, got %d"
                % (line_no, mnemonic, count, len(fields))
            )

    if mnemonic == "HALT":
        want(0)
        return HALT_WORD

    if mnemonic in R_TYPE:
        want(3)
        funct7, funct3 = R_TYPE[mnemonic]
        return pack_r(
            funct7,
            _parse_register(fields[2], line_no),
            _parse_register(fields[1], line_no),
            funct3,
            _parse_register(fields[0], line_no),
        )

    if mnemonic in I_TYPE_ALU:
        want(3)
        return pack_i(
            _parse_number(fields[2], line_no),
            _parse_register(fields[1], line_no),
            I_TYPE_ALU[mnemonic],
            _parse_register(fields[0], line_no),
            OP_I_TYPE,
            line_no,
        )

    if mnemonic == "LW":
        want(3)
        destination = _parse_register(fields[0], line_no)
        if _is_register(fields[1]):
            offset = _parse_number(fields[2], line_no, "offset")
            base = _parse_register(fields[1], line_no)
        else:
            offset, base = _parse_memory_operand(fields[1], line_no)
        return pack_i(offset, base, FUNCT3_LW, destination, OP_LOAD, line_no)

    if mnemonic == "SW":
        want(3)
        value = _parse_register(fields[0], line_no)
        if _is_register(fields[1]):
            offset = _parse_number(fields[2], line_no, "offset")
            base = _parse_register(fields[1], line_no)
        else:
            offset, base = _parse_memory_operand(fields[1], line_no)
        return pack_s(offset, value, base, FUNCT3_SW, line_no)

    if mnemonic in ("BEQ", "BNE"):
        want(3)
        target = labels[fields[2]] - address if fields[2] in labels else \
            _parse_number(fields[2], line_no, "offset")
        funct3 = FUNCT3_BEQ if mnemonic == "BEQ" else FUNCT3_BNE
        return pack_b(
            target,
            _parse_register(fields[1], line_no),
            _parse_register(fields[0], line_no),
            funct3,
            line_no,
        )

    if mnemonic == "JAL":
        want(2)
        target = labels[fields[1]] - address if fields[1] in labels else \
            _parse_number(fields[1], line_no, "offset")
        return pack_j(target, _parse_register(fields[0], line_no), line_no)

    if mnemonic == "JALR":
        want(3)
        return pack_i(
            _parse_number(fields[2], line_no, "offset"),
            _parse_register(fields[1], line_no),
            FUNCT3_JALR,
            _parse_register(fields[0], line_no),
            OP_JALR,
            line_no,
        )

    raise AsmError("line %d: unhandled instruction '%s'" % (line_no, mnemonic))


# --- Turning words into the two .txt files ---

def to_imem_lines(words):
    """One byte per line, eight characters of binary, most significant first."""
    lines = []
    for word in words:
        bits = format(word & 0xFFFFFFFF, "032b")
        lines.extend(bits[index:index + 8] for index in range(0, 32, 8))
    return lines


def to_dmem_lines(size, word_placements=None, byte_placements=None):
    """One line of 8-bit binary per byte of a `size`-byte memory image, zero-filled."""
    image = [0] * size
    for address, value in (word_placements or []):
        value &= 0xFFFFFFFF
        for index in range(4):
            if address + index < size:
                image[address + index] = (value >> (8 * (3 - index))) & 0xFF
    for address, value in (byte_placements or []):
        if address < size:
            image[address] = value & 0xFF
    return [format(byte, "08b") for byte in image]


def build_dmem_lines(program):
    """dmem.txt for a program, sized to fit whatever its .data declared."""
    return to_dmem_lines(program.memory_size(), program.data)


def disassemble(word):
    """Decode a word back into something readable, for code.asm."""
    word &= 0xFFFFFFFF
    if word == HALT_WORD:
        return "HALT"
    opcode = word & 0x7F
    rd = (word >> 7) & 0x1F
    funct3 = (word >> 12) & 0x7
    rs1 = (word >> 15) & 0x1F
    rs2 = (word >> 20) & 0x1F
    funct7 = (word >> 25) & 0x7F
    immediate = word >> 20
    if immediate & 0x800:
        immediate -= 1 << 12

    if opcode == OP_R_TYPE:
        names = {(0, 0): "ADD", (0x20, 0): "SUB", (0, 4): "XOR",
                 (0, 6): "OR", (0, 7): "AND"}
        name = names.get((funct7, funct3), "?")
        return "%s R%d, R%d, R%d" % (name, rd, rs1, rs2)
    if opcode == OP_I_TYPE:
        name = {0: "ADDI", 4: "XORI", 6: "ORI", 7: "ANDI"}.get(funct3, "?")
        return "%s R%d, R%d, #%d" % (name, rd, rs1, immediate)
    if opcode == OP_LOAD:
        return "LW R%d, #%d(R%d)" % (rd, immediate, rs1)
    if opcode == OP_STORE:
        value = ((word >> 25) << 5) | ((word >> 7) & 0x1F)
        if value & 0x800:
            value -= 1 << 12
        return "SW R%d, #%d(R%d)" % (rs2, value, rs1)
    if opcode == OP_BRANCH:
        value = (
            (((word >> 31) & 1) << 12)
            | (((word >> 7) & 1) << 11)
            | (((word >> 25) & 0x3F) << 5)
            | (((word >> 8) & 0xF) << 1)
        )
        if value & 0x1000:
            value -= 1 << 13
        return "%s R%d, R%d, #%d" % (
            "BEQ" if funct3 == 0 else "BNE", rs1, rs2, value)
    if opcode == OP_JAL:
        value = (
            (((word >> 31) & 1) << 20)
            | (((word >> 12) & 0xFF) << 12)
            | (((word >> 20) & 1) << 11)
            | (((word >> 21) & 0x3FF) << 1)
        )
        if value & 0x100000:
            value -= 1 << 21
        return "JAL R%d, #%d" % (rd, value)
    if opcode == OP_JALR:
        return "JALR R%d, R%d, #%d" % (rd, rs1, immediate)
    return "?0x%08X" % word


# --- Command line ---

HERE = os.path.dirname(os.path.abspath(__file__))
ASM_DIR = os.path.join(HERE, "asm")
SIMULATOR = os.path.join(HERE, "main.py")

MEMORY_SIZE = 1000


def _display(path):
    """A path relative to this directory, with forward slashes."""
    return os.path.relpath(path, HERE).replace(os.sep, "/")


def find_sources(argument):
    """Turn the command-line argument into a list of .asm paths."""
    if argument is None:
        if not os.path.isdir(ASM_DIR):
            raise AsmError("there is no '%s' directory yet" % _display(ASM_DIR))
        found = sorted(
            os.path.join(ASM_DIR, name)
            for name in os.listdir(ASM_DIR)
            if name.endswith(".asm")
        )
        if not found:
            raise AsmError(
                "no .asm files in %s -- add one, or copy the example"
                % _display(ASM_DIR)
            )
        return found

    if os.sep in argument or "/" in argument or argument.endswith(".asm"):
        path = argument if os.path.isabs(argument) else os.path.join(HERE, argument)
        if not os.path.isfile(path):
            raise AsmError("no such file: %s" % argument)
        return [path]

    path = os.path.join(ASM_DIR, argument + ".asm")
    if not os.path.isfile(path):
        available = []
        if os.path.isdir(ASM_DIR):
            available = sorted(
                name[:-4] for name in os.listdir(ASM_DIR) if name.endswith(".asm")
            )
        hint = ", ".join(available) if available else "none yet"
        raise AsmError(
            "no such program '%s': expected %s\nprograms in asm/: %s"
            % (argument, _display(path), hint)
        )
    return [path]


def build(source_path, output_dir):
    """Assemble one file and write the build directory. Returns the Program."""
    with open(source_path) as handle:
        text = handle.read()

    program = assemble(text)

    if not program.words:
        raise AsmError("%s has no instructions" % _display(source_path))

    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "imem.txt"), "w") as handle:
        handle.write("\n".join(to_imem_lines(program.words)) + "\n")

    with open(os.path.join(output_dir, "dmem.txt"), "w") as handle:
        handle.write("\n".join(build_dmem_lines(program)) + "\n")

    with open(os.path.join(output_dir, "code.asm"), "w") as handle:
        handle.write("; PC   ENCODING     INSTRUCTION\n\n")
        for address, word, _source in program.listing:
            handle.write("%-6d 0x%08X   %s\n" % (address, word, disassemble(word)))
        if program.labels:
            handle.write("\nlabels:\n")
            for name, address in sorted(program.labels.items(), key=lambda kv: kv[1]):
                handle.write("  %-16s %d\n" % (name, address))

    return program


def describe(source_path, output_dir, program):
    name = _display(output_dir)
    print("assembled %s" % _display(source_path))
    print("  %d instructions, %d data words" % (len(program.words), len(program.data)))
    if program.labels:
        print("  labels: %s" % ", ".join(
            "%s=%d" % (label, address)
            for label, address in sorted(program.labels.items(), key=lambda kv: kv[1])
        ))

    highest = max([address + 4 for address, _ in program.data] or [0])
    if highest > MEMORY_SIZE:
        print("  warning: data reaches byte %d, past the 1000-byte memory;"
              " the simulator will read zeros there" % highest)
    if program.words[-1] != HALT_WORD:
        print("  warning: the last instruction is not HALT, so the program will")
        print("           run off the end of instruction memory")

    print("  wrote %s/{imem.txt,dmem.txt,code.asm}" % name)
    print("  run it with:  python main.py --iodir %s" % name)


def run_simulator(output_dir):
    import subprocess
    if not os.path.isfile(SIMULATOR):
        print("cannot run: %s is missing" % os.path.relpath(SIMULATOR, HERE))
        return 1
    print()
    return subprocess.run(
        [sys.executable, SIMULATOR, "--iodir", output_dir], cwd=HERE
    ).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble a RISC-V program into imem.txt and dmem.txt.",
        epilog="With no program name, --all assembles every asm/*.asm.",
    )
    parser.add_argument(
        "program", nargs="?",
        help="a name in asm/ (e.g. 'sum') or a path to a .asm file",
    )
    parser.add_argument("--all", action="store_true", help="assemble every asm/*.asm")
    parser.add_argument("--run", action="store_true",
                        help="run main.py on the result afterwards")
    parser.add_argument("-o", "--out", default=None,
                        help="write the build directory here instead of next to the source")
    args = parser.parse_args(argv)

    if args.all and args.program:
        print("error: give either a program name or --all, not both")
        return 2
    if not args.all and not args.program:
        args.all = True

    try:
        sources = find_sources(None if args.all else args.program)
    except AsmError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2

    last_output_dir = None
    for index, source_path in enumerate(sources):
        if index:
            print()
        output_dir = args.out or source_path[: -len(".asm")]
        try:
            program = build(source_path, output_dir)
        except AsmError as error:
            print("error: %s" % error, file=sys.stderr)
            return 1
        except OSError as error:
            print("error: %s" % error, file=sys.stderr)
            return 1
        describe(source_path, output_dir, program)
        last_output_dir = output_dir

    if args.run:
        if len(sources) > 1:
            print("\n(--run with several programs runs the last one built)")
        return run_simulator(last_output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
