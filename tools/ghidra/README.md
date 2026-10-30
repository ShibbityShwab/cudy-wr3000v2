# Ghidra — headless decompilation lane

Ghidra 12.2 (2026-10-22) with **Temurin JDK 25**, installed 2026-10-30. This replaces the hand
`objdump` + `miasm` lane for anything larger than a single function.

## Install (already done on this workstation)

- JDK 25 is REQUIRED. **Ghidra 12.2 refuses JDK 21** and sits at an interactive
  `Enter path to JDK home directory` prompt — which looks exactly like a hung process.
  `winget install EclipseAdoptium.Temurin.25.JDK`
- Ghidra lives OUTSIDE the repo at `C:/tools/ghidra_12.2_PUBLIC` (879 MB) so it is never committed.
  Zip integrity was checked with `unzip -t` before extracting.

## Usage

```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-25.0.5.8-hotspot"
export PATH="$JAVA_HOME/bin:$PATH"
G=/c/tools/ghidra_12.2_PUBLIC/support/analyzeHeadless.bat

"$G" C:/tmp/ghproj <projname> \
  -import "$(cygpath -m path/to/module.ko)" \
  -postScript DumpFuncs.java C:/tmp/out.txt [nameFilter] \
  -scriptPath "$(cygpath -m tools/ghidra)" \
  -deleteProject
```

Use **forward-slash Windows paths** (`C:/tmp/...`). A double-backslash path was mangled to
`C:\\tm` and Ghidra failed with `Directory not found`.

Always redirect to a file and `tail` it — piping through `tail` directly buffers everything until
exit, which makes a program waiting on stdin indistinguishable from one doing work.

## Calibration (2026-10-30, `hi_wdg.ko`, 35 functions)

Checked against this project's hand reversal of `hi_wdt_hw_set_timeout`, which records three
distinct `bfi` paths. Ghidra reproduced all three:

| selector | mask | field | C |
|---|---|---|---|
| 0 | `0xfffff007` | bits 3-11 | `((secs - 1) & 0x1ff) << 3` |
| **1** | `0xfff003ff` | bits 10-19 | **`((secs * 2 - 1) & 0x3ff) << 10`** |
| 2 | `0xfff803ff` | bits 10-18 | `((secs - 1) & 0x1ff) << 10` |

Path 1 is the documented `lsl #11; sub #0x400` case. Masks, field widths and arithmetic all agree,
so ARM/Thumb detection and bitfield lifting are correct **for this binary**.

## Known limitations

- These are **relocatable .ko objects**. Cross-module calls resolve to EXTERNAL stubs and the
  decompiler warns `Unable to disassemble EXTERNAL block location` — expected and harmless for
  intra-module work. To follow mainline helpers, import `vmlinux` alongside it.
- Global pointers appear as `DAT_xxxx` because they are relocation targets, not fixed addresses.
