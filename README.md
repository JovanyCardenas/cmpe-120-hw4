# HW4 — 5-Stage Pipelined RISC-V Simulator

Your simulator goes in `main.py`, and that is the file the autograder runs.

> The submitted file must be named exactly `main.py`, and it must be runnable
> as `python main.py --iodir <directory>`. The autograder runs nothing else.

## What is in this repository

```
main.py           the skeleton — fill in the six methods marked TODO;
                  decode the ISA and add pipeline-register fields yourself
run_tests.py      checks your work against the public test cases
assemble.py       turns a .asm file into imem.txt and dmem.txt
asm/              your own test programs (example.asm, hazards.asm to start from)
requirements.txt  no third-party dependencies (empty on purpose)
tests/            the eight public test cases, each with input/ and expected/
README.md         this file
```

## Environment setup

Use a dedicated Python environment so you run the same kind of setup the
autograder does: Python 3.9 or newer, and no extra packages. This will keep local
results consistent with Gradescope. **Choose either Conda or venv**. You do not
need both. If you're unsure, we'd recommend Conda. Note that `requirements.txt`
is deliberately empty.

If you do not already have Conda, install Miniconda from the
[Conda installation instructions](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html)
(macOS, Windows, and Linux are all covered there).

**With Conda:**

```bash
conda create -n hw4 python=3.11 -y
conda activate hw4
pip install -r requirements.txt
```

**With plain `venv`:**

```bash
# Windows
py -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

## Running your simulator

```bash
python main.py --iodir tests/01_rtype_alu/input
```

`--iodir` is the directory that holds `imem.txt` and `dmem.txt`; the four
output files are written back into that same directory. Add `--verbose` to
print one line per clock while it runs.

## Checking your work

```bash
python run_tests.py            # all test cases
python run_tests.py 01 05      # just the test cases 01 and 05
```

Running `python run_tests.py` runs your simulator against all eight public test
cases and reports, per test case and per output file, whether you match the
expected output. It is the same comparison that the autograder performs.

Each public test case has an `expected/` directory next to its `input/`
directory, so you can inspect the correct output directly. `input/code.asm`
lists the program one instruction per line with its address and encoding,
which is the quickest way to find where a trace diverges.

## Writing your own test programs

To try a program of your own, write RISC-V assembly in `asm/` and let
`assemble.py` build the `imem.txt` and `dmem.txt` for you.

```bash
python assemble.py hazards --run     # build asm/hazards.asm, then run it
python assemble.py example           # build only
python assemble.py --all             # build every asm/*.asm
```

Assembling `asm/hazards.asm` creates `asm/hazards/`, containing:

```
asm/hazards/
    imem.txt      the assembled instructions
    dmem.txt      the initial data memory
    code.asm      one line per instruction: address, encoding, instruction
```

That directory is exactly what `--iodir` wants, so you can also run it by hand:

```bash
python main.py --iodir asm/hazards --verbose
```

`asm/hazards.asm` shows the syntax: instructions, labels for branch and jump
targets, and `.data` for putting values in memory before the program starts.
A register may be written `x0`-`x31` or by ABI name (`zero`, `ra`,
`sp`, `a0`, `s0`, `t0`, ...); Copy the example
and edit it. Bad lines are reported with their line number, so if
something does not assemble, the message tells you where to look. The
`code.asm` in each build directory is also the fastest way to see what an
instruction actually encoded to.

Your own programs in `asm/` have nothing to do with grading. The autograder
runs its own test cases, and only ever runs `main.py`. Committing your `asm/`
files is harmless.

## Submitting

Your repository is the submission. Keep `main.py` at the top level and commit
your work:

```bash
git add main.py
git commit -m "Implement 5-stage pipelined RV32I simulator"
git push
```

Then submit your repository on Gradescope using the GitHub submission option.
