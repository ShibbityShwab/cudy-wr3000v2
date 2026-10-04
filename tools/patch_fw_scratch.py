#!/usr/bin/env python3
"""Firmware scratch-patch tool for the WiFi-forward L3 instrument (plan task 7).

Builds two patched copies of the pinned firmware blob:

  probe    - exactly ONE byte flipped at a non-executed offset (walking downward from the
             last file byte until the runtime address has no reference anywhere in the image).
             Proves the load path carries a modified blob.
  scratch  - two instrumentation stores added, WITHOUT changing the file size and WITHOUT
             removing the original GIC bitmap write:
               scratch(i)  at the enable(0x4c) thunk (file 0x86ff4 region):
                             S1   <- the enable bitmap word (1 << (id % 32))
                             S1+4 <- the destination word 0x40161108 (for id 0x4c)
               scratch(ii) at the distributor bring-up end (file 0x6e5c-0x6ed4):
                             S2   <- the bring-up's final computed state word
                             S2+4 <- the fixed marker 0x50aa7e49
             Both additions enter through a `bl` trampoline into a non-referenced 0x00
             padding region inside the loaded image. Register liveness is preserved, and the
             condition flags the surrounding IT blocks depend on are saved/restored (MRS/MSR
             APSR) around the thunk pad.

S1/S2 are chosen by rule from barmap_ep0_bar0.bin: a 4-byte aligned firmware runtime
address whose 4-byte word is 0x00000000 at BAR0 offset == addr AND at the ACP alias
BAR0 0x6b8000+addr, outside the four named tables.

The input blob is only ever read; every artifact is written under --out.

usage:
  patch_fw_scratch.py --fw <FIRMWARE.bin> --out <variant.bin> --variant probe|scratch
  patch_fw_scratch.py --selftest [--fw <FIRMWARE.bin>] [--barmap <barmap.bin>]

exit codes: 0 ok, 2 usage/refusal, 3 patch or verification failure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_REG_PC

# ---------------------------------------------------------------- pinned constants

FW_MD5 = "0e530b976d5a20e87358671f1a577695"
FW_SIZE = 928920                       # 0xe2c98
PROBE_MD5 = "2a9a9f1d1340fc63019a69ee8eeca9e0"     # frozen probe-variant output (selftest regression)
SCRATCH_MD5 = "b08699bd902d35e697e24b94edb6fa2c"   # frozen scratch-variant output (selftest regression)
BIAS = 0x40000                         # runtime address = file offset + BIAS
BARMAP_MD5 = "40a1da524539c3392d3c04694ffafb4d"
ALIAS_OFF = 0x6b8000                   # ACP alias: BAR0 offset 0x6b8000+addr == BAR0 addr
LOADED_SIZE = 0xCC0CC                  # FIRMWARE.bin[0:835788] appears in BAR0 (phase 17 A.6)

ENABLE_THUNK = 0x86FF4                 # enable(id) - the ISENABLER writer
SITE_THUNK = 0x87024                   # `it lo` + `ldrlo r3,[pc,#0x1c]`
CONT_THUNK = 0x87028                   # `ldr r0,[pc,#0x1c]` (left intact)
GIC_CA_BASE = 0x40161100
GIC_DEST_0X4C = 0x40161108
BITMAP_0X4C = 0x1000
BRINGUP_SITE = 0x6ED4                  # `str.w sl,[r7]` -> distributor CTLR = 1
BRINGUP_CONT = 0x6ED8
MARKER = 0x50AA7E49

# ---- gicview: the device-side GIC readback map (variant "gicview") -------------
# Verified against the image (disassembly below) and phase32/phase47 before use:
#   * GICD base = 0x40161000.  The bring-up's final store `str.w sl,[r7]` (file 0x6ed4, sl=1)
#     uses r7, loaded at file 0x6e88 from the literal at file 0x716c = 0x40161000; phase47
#     calls the same store "distributor CTLR = 1".
#   * GICD_ISENABLER base = 0x40161100 - the enable thunk's literal-pool word at file 0x87044
#     (`ldrlo r3,[pc,#0x1c]` at file 0x87026); the firmware's own write `str r4,[r3,r2,lsl #2]`
#     (file 0x8702c) then reaches word 2 / bit 12 = CA 0x40161108 for id 0x4c (phase32: "for id
#     0x4C: word 2, bit 12 -> CA 0x40161108"; phase47 section 1).
#   * Therefore, by the GIC-400/PL390 relative layout within the same page,
#     ISPENDR word 2 = base+0x208 and ISACTIVER word 2 = base+0x308.  Corroborated by phase32's
#     clear pair `enableA 0x86DB8 -> 0x40161180 + mirror 0x40161280` (base+0x180 ICENABLER /
#     base+0x280 ICPENDR) and phase47's "slot 1 is 0x40161c00 ICFGR" (base+0xC00).
#   * GICC (CPU interface) page base = 0x40160100 (phase32: IAR 0x4016010c, EoI 0x40160110;
#     phase47 section 3 keys on those) -> HPPIR = base+0x18 = 0x40160118, NON-acknowledging.
# The plan's first-draft map gave ISPENDR2/ISACTIVER2 as 0x40160208/0x40160308 (a 0x40160000
# base).  Those addresses fall in the GICC page's reserved area (RAZ), so reading them would
# return a guaranteed zero and fake a "nothing pending" result.  This variant reads the two
# words that actually decode as the named registers.
# NEVER read the acknowledging IAR CA 0x4016010c (a read acknowledges the pending interrupt).
GICD_ISENABLER2 = 0x40161108           # the word the firmware's enable(0x4c) writes
GICD_ISPENDR2 = 0x40161208             # ISPENDR word 2: bit 12 = source id 0x4c
GICD_ISACTIVER2 = 0x40161308           # ISACTIVER word 2: bit 12 = delivered/active
GICC_HPPIR = 0x40160118                # CPU interface highest-pending-priority (0x3ff = none)
GICV_NCELLS = 6                        # C0..C5
GIC_THUNK_READS = (GICD_ISENABLER2, GICD_ISPENDR2, GICC_HPPIR)      # -> C0, C1, C2
GIC_BRINGUP_READS = (GICD_ISPENDR2, GICD_ISACTIVER2, GICC_HPPIR)    # -> C3, C4, C5

S_CELL_LO, S_CELL_HI = 0xE7000, 0xFFF00
S_CELL_ALIAS_HI = 0x1BFFFF             # descriptor 0 (ROM_WRAM) device limit
S_CELL_EXCLUDE = (
    0x118D68 + 0x50,
    0x17D430 + 0xC0,
    0x105F80 + 0xA0,
    0x172130 + 0x10,
)
PROBE_WALK_LO = 0xE2C00
PAD_MIN = 64
PAD_LO = 0x4000                        # keep clear of the image head / boot-stub area

NOTE_RANGE = (
    "the spec range [0xE7000,0xFFF00] holds ZERO 4-byte zero words in the named barmap "
    "(the range is loaded code), so the primary rule is unsatisfiable as written; the search "
    "starts at 0xE7000 and extends upward to descriptor 0's limit 0x1BFFFF - the ROM_WRAM "
    "band that actually contains the four excluded tables - taking 4-byte aligned cells that "
    "are zero at BOTH BAR0 aliases and outside the exclusion set. See selection.range_used."
)
NOTE_THUNK = (
    "scratch(i) instruments the enable(0x4c) path inside the required enable-thunk region "
    "0x86ff4. The thunk is shared by 28 enable call sites and has no spare instruction/literal "
    "slot (its 3-word pool at 0x87040-0x8704B is fully used), so the store is gated on the "
    "computed bitmap == 0x1000 (id 0x4c is the only enabled source with bit 12 set) and added "
    "through a `bl` trampoline. The original ISENABLER write at file 0x8702c "
    "(strlo.w r4,[r3,r2,lsl #2] -> CA 0x40161100+(id/32)*4) is left byte-for-byte intact and "
    "still reachable; its condition flags are restored before the itet block re-reads them."
)
NOTE_BRINGUP = (
    "scratch(ii) sits at the region's final instruction 0x6ed4 (str.w sl,[r7]); the recorded "
    "'final computed state word' is the word that instruction writes (the distributor enable "
    "state), relocated into a trampoline that also stores the marker. The marker at S2+4 is "
    "the load-bearing presence proof for the bring-up having run."
)
NOTE_GICVIEW_I = (
    "gicview(i) keeps the scratch(i) enable-thunk trampoline (gate r4==0x1000, S1/S1+4 stores) and, "
    "after them, adds three side-effect-free device-side GICD/GICC reads deposited into the fresh "
    "WRAM cells C0/C1/C2: CA 0x40161108 -> C0 (the word the firmware's own enable writes), "
    "CA 0x40161208 -> C1 (ISPENDR word 2; bit 12 = source id 0x4c) and CA 0x40160118 -> C2 "
    "(GICC HPPIR, non-acknowledging). C0 answers whether the device side can read back the "
    "enable bit the host cannot see; C1 answers whether the source is already pending at the GIC "
    "at the enable point."
)
NOTE_GICVIEW_II = (
    "gicview(ii) keeps the scratch(ii) bring-up-end trampoline (S2/S2+4 stores, then the reproduced "
    "distributor CTLR write str.w sl,[r7] with r7 = CA 0x40161000) and, between the stores and the "
    "CTLR write, adds three further side-effect-free reads into C3/C4/C5: CA 0x40161208 -> C3 "
    "(ISPENDR word 2 at the bring-up end), CA 0x40161308 -> C4 (ISACTIVER word 2; bit 12 set means "
    "the source was delivered/active) and CA 0x40160118 -> C5 (HPPIR again)."
)
NOTE_GIC_MAP = (
    "The GIC map was verified against the image and phase32/phase47 before use. GICD base "
    "0x40161000: the bring-up's CTLR literal at file 0x716c = 0x40161000 is loaded into r7 (file "
    "0x6e88) and written 1 at file 0x6ed4. GICD_ISENABLER base 0x40161100: the enable thunk's "
    "literal-pool word at file 0x87044; its `str r4,[r3,r2,lsl #2]` (file 0x8702c) reaches word 2 / "
    "bit 12 = CA 0x40161108 for id 0x4c (phase32 'for id 0x4C: word 2, bit 12 -> CA 0x40161108'). "
    "Hence GICD_ISPENDR2 = 0x40161208 and GICD_ISACTIVER2 = 0x40161308 by the GIC-400 relative "
    "layout (corroborated by phase32's clear pair 0x40161180/0x40161280 = base+0x180/0x280 and "
    "phase47's ICFGR 0x40161c00 = base+0xC00). GICC page base 0x40160100 (phase32 IAR "
    "0x4016010c / EoI 0x40160110) -> HPPIR 0x40160118. The first-draft map's ISPENDR2/ISACTIVER2 "
    "(0x40160208/0x40160308, off a 0x40160000 base) fall inside the GICC page's reserved area "
    "(RAZ); they were NOT used, because a read there returns a guaranteed zero and would fake a "
    "'nothing pending' result. The acknowledging IAR CA 0x4016010c is never read by this variant."
)


class PatchError(RuntimeError):
    pass


# ---------------------------------------------------------------- thumb encoders

def movw(rd: int, imm16: int) -> bytes:
    hw1 = 0xF240 | (((imm16 >> 11) & 1) << 10) | ((imm16 >> 12) & 0xF)
    hw2 = (((imm16 >> 8) & 0x7) << 12) | (rd << 8) | (imm16 & 0xFF)
    return struct.pack("<HH", hw1, hw2)


def movt(rd: int, imm16: int) -> bytes:
    hw1 = 0xF2C0 | (((imm16 >> 11) & 1) << 10) | ((imm16 >> 12) & 0xF)
    hw2 = (((imm16 >> 8) & 0x7) << 12) | (rd << 8) | (imm16 & 0xFF)
    return struct.pack("<HH", hw1, hw2)


def cmp_reg(rn: int, rm: int) -> bytes:
    return struct.pack("<H", 0x4500 | ((rm & 0xF) << 3) | (rn & 0x7))


def mov_reg(rd: int, rm: int) -> bytes:
    return struct.pack("<H", 0x4600 | ((rd >> 3) << 7) | ((rm & 0xF) << 3) | (rd & 0x7))


def str_imm(rt: int, rn: int, imm: int) -> bytes:
    return struct.pack("<H", 0x6000 | ((imm // 4) << 6) | ((rn & 0x7) << 3) | (rt & 0x7))


def str_imm_w(rt: int, rn: int, imm: int) -> bytes:
    return struct.pack("<HH", 0xF8C0 | rn, ((rt & 0xF) << 12) | (imm & 0xFFF))


def ldr_imm(rt: int, rn: int, imm: int) -> bytes:
    """LDR (immediate) T1: `ldr Rt, [Rn, #imm]`, low registers, imm a multiple of 4 in 0..124."""
    if imm % 4 or not 0 <= imm <= 124:
        raise PatchError(f"ldr immediate out of range: {imm}")
    return struct.pack("<H", 0x6800 | ((imm // 4) << 6) | ((rn & 0x7) << 3) | (rt & 0x7))


def push(regs: list[int]) -> bytes:
    lst = 0
    m = 0
    for r in regs:
        if r == 14:
            m = 1
        else:
            lst |= 1 << r
    return struct.pack("<H", 0xB400 | (m << 8) | lst)


def pop(regs: list[int]) -> bytes:
    # POP T1 restores r0-r7 and PC only; LR cannot appear in the list.
    lst = 0
    p = 0
    for r in regs:
        if r == 15:
            p = 1
        else:
            lst |= 1 << r
    return struct.pack("<H", 0xBC00 | (p << 8) | lst)


PAD_SAVE = [0, 1, 2, 3, 4, 5]   # 6 registers -> 24 bytes -> SP stays 8-aligned; no LR (POP cannot take it)


def mrs_apsr(rd: int) -> bytes:
    return struct.pack("<HH", 0xF3EF, 0x8000 | (rd << 8))


def msr_apsr(rd: int) -> bytes:
    return struct.pack("<HH", 0xF380 | rd, 0x8800)


def _off24(addr: int, target: int) -> int:
    off = target - (addr + 4)
    if off % 2 or not (-(1 << 24) <= off < (1 << 24)):
        raise PatchError(f"branch out of range: {addr:#x} -> {target:#x}")
    return off


def _branch(addr: int, target: int, link: bool) -> bytes:
    off = _off24(addr, target)
    s = (off >> 24) & 1
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    imm10 = (off >> 12) & 0x3FF
    imm11 = (off >> 1) & 0x7FF
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = (0xD000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def b_w(addr: int, target: int) -> bytes:
    return _branch(addr, target, link=False)


def bl(addr: int, target: int) -> bytes:
    return _branch(addr, target, link=True)


def b_cond(addr: int, target: int, cond: int) -> bytes:
    off = target - (addr + 4)
    if off % 2 or not (-256 <= off <= 254):
        raise PatchError(f"short branch out of range: {addr:#x} -> {target:#x}")
    return struct.pack("<H", 0xD000 | (cond << 8) | ((off >> 1) & 0xFF))


COND_NE = 1


# ---------------------------------------------------------------- image helpers

def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def rd(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def check_md5(data: bytes, path: str) -> None:
    got = md5(data)
    if got != FW_MD5:
        raise PatchError(f"input refused: md5 check failed for {path}: got {got}, want {FW_MD5}")


def check_size(data: bytes, path: str) -> None:
    if len(data) != FW_SIZE:
        raise PatchError(f"input refused: size check failed for {path}: got {len(data)}, want {FW_SIZE}")
    if len(data) % 2:
        raise PatchError(f"input refused: length check failed for {path}: not an even (Thumb) image")


def check_input(data: bytes, path: str) -> list[str]:
    errs = []
    for fn in (check_size, check_md5):
        try:
            fn(data, path)
        except PatchError as exc:
            errs.append(str(exc))
    if errs:
        raise PatchError("input refused for " + path + ": " + "; ".join(errs))
    return ["size", "md5"]


def check_barmap(barmap: bytes) -> None:
    if md5(barmap) != BARMAP_MD5:
        raise PatchError(f"barmap refused: md5 check failed: got {md5(barmap)}, want {BARMAP_MD5}")
    if len(barmap) <= ALIAS_OFF + S_CELL_ALIAS_HI:
        raise PatchError("barmap refused: too short for the alias range")


def word_at(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


# ---------------------------------------------------------------- cross references

def build_refs(data: bytes) -> set[int]:
    """Runtime addresses reached by code: branch targets, PC-relative literal addresses, and
    the image-space pointer values those literals hold (the phase-47 verification method)."""
    refs: set[int] = set()
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    md.skipdata = True
    for ins in md.disasm(data, 0):
        if ins.id == 0:
            continue
        for op in ins.operands:
            if op.type == ARM_OP_IMM:
                if ins.group(1) or ins.group(2):              # JUMP / CALL
                    refs.add(op.imm + BIAS)
                elif 0x40000 <= op.imm < 0x1400000:           # adr-style immediate
                    refs.add(op.imm)
        for op in ins.operands:
            if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                lit = ((ins.address + 4) & ~3) + op.mem.disp
                refs.add(lit + BIAS)
                if 0 <= lit and lit + 4 <= len(data):
                    val = struct.unpack_from("<I", data, lit)[0]
                    if 0x40000 <= val < 0x1400000:
                        refs.add(val)
    return refs


def padding_runs(data: bytes, refs: set[int], taken: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """All 0x00-filled, unreferenced runs (>= PAD_MIN) inside the loaded image, longest first."""
    runs = []
    i = 0
    n = min(len(data), LOADED_SIZE)
    while i < n:
        if data[i] == 0:
            j = i
            while j < n and data[j] == 0:
                j += 1
            if j - i >= PAD_MIN:
                start = i + (i & 1)
                length = j - start
                if length >= PAD_MIN and all((start + k + BIAS) not in refs for k in range(length)):
                    if not any(start < e and t < start + length for t, e in taken):
                        runs.append((start, length))
            i = j
        else:
            i += 1
    runs = [r for r in runs if r[0] >= PAD_LO]
    runs.sort(key=lambda t: (-t[1], t[0]))
    return runs


def find_padding(data: bytes, refs: set[int], need: int, taken: list[tuple[int, int]]):
    for start, length in padding_runs(data, refs, taken):
        if length >= need:
            return start, length
    raise PatchError(f"no non-referenced 0x00 padding run of {need} bytes inside the loaded image")


# ---------------------------------------------------------------- S1 / S2 selection

def _cell_ok(barmap: bytes):
    """The cell rule: 4-byte aligned, 4-byte word 0 at BAR0 offset a AND at alias 0x6b8000+a,
    outside the four excluded tables."""
    def ok(a: int) -> bool:
        if a % 4 or a in S_CELL_EXCLUDE:
            return False
        return word_at(barmap, a) == 0 and word_at(barmap, ALIAS_OFF + a) == 0
    return ok


def walk_cells(barmap: bytes, n: int, ok=None) -> list[int]:
    """The tool's cell walk from S_CELL_LO upward; each accepted cell is >= 8 bytes from the
    previous one.  Deterministic: the first n cells are a fixed prefix of the same sequence."""
    check_barmap(barmap)
    ok = ok or _cell_ok(barmap)
    cells: list[int] = []
    a = S_CELL_LO
    while a + 8 <= S_CELL_ALIAS_HI and len(cells) < n:
        if ok(a) and (not cells or a - cells[-1] >= 8):
            cells.append(a)
        a += 4
    return cells


def select_cells(barmap: bytes):
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    cells = walk_cells(barmap, 2, ok=ok)
    if len(cells) < 2:
        raise PatchError("S1/S2 selection failed: fewer than two usable zero cells found")
    return cells[0], cells[1], {
        "rule": "4-byte aligned runtime addr; 4-byte word == 0x00000000 at BAR0 offset addr and "
                "at alias 0x6b8000+addr; outside the four excluded tables; S1/S2 >= 8 bytes apart",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "note": NOTE_RANGE,
    }


def select_cells_gicview(barmap: bytes):
    """Eight cells by the same rule: S1, S2 (identical to the scratch variant - the walk's first
    two), then the six fresh deposit cells C0..C5.  All eight are mutually >= 8 bytes apart."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    cells = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(cells) < 2 + GICV_NCELLS:
        raise PatchError("gicview selection failed: fewer than eight usable zero cells found")
    sel = {
        "rule": "4-byte aligned runtime addr; 4-byte word == 0x00000000 at BAR0 offset addr and "
                "at alias 0x6b8000+addr; outside the four excluded tables; each cell >= 8 bytes "
                "from the previous one; S1/S2 = the first two cells (as in the scratch variant)",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "note": NOTE_RANGE,
        "fresh_cell_justification": (
            "C0..C5 are freshly selected by the same rule as S1/S2 in the same walk (so S1/S2 keep "
            "their scratch-variant values and are directly comparable across variants), are >= 8 "
            "bytes apart from each other and from S1/S2, are zero in barmap_ep0_bar0.bin at BOTH "
            "the BAR0 and the ACP-alias offsets, and lie outside the four excluded tables."
        ),
    }
    return cells, sel


def cell_record(barmap: bytes, addr: int) -> dict:
    return {
        "addr": hex(addr),
        "file_offset": hex(addr - BIAS),
        "barmap_value": hex(word_at(barmap, addr)),
        "barmap_alias_addr": hex(ALIAS_OFF + addr),
        "barmap_alias_value": hex(word_at(barmap, ALIAS_OFF + addr)),
    }


# ---------------------------------------------------------------- trampolines

def gic_read_store_block(read_ca: int, cell: int) -> bytes:
    """A side-effect-free device-side GIC read: movw/movt the mapped CA into r1, `ldr r1,[r1]`,
    then movw/movt the WRAM cell into r0 and `str r1,[r0]`.  r0/r1 are saved by the pad's push."""
    return b"".join([
        movw(1, read_ca & 0xFFFF),
        movt(1, read_ca >> 16),
        ldr_imm(1, 1, 0),
        movw(0, cell & 0xFFFF),
        movt(0, cell >> 16),
        str_imm(1, 0, 0),
    ])


def pad_thunk(pad: int, s1: int, gic_cells: list[int] | None = None) -> bytes:
    head = b"".join([
        mrs_apsr(12),                     # +0  save condition flags
        push(PAD_SAVE),                   # +4  24 bytes, keeps SP 8-aligned
        movw(0, BITMAP_0X4C),             # +6
        cmp_reg(4, 0),                    # +10
    ])
    bne_addr = pad + len(head)            # +12
    body = b"".join([
        movw(0, s1 & 0xFFFF),             # +14
        movt(0, s1 >> 16),                # +18
        str_imm(4, 0, 0),                 # +22  S1   <- bitmap
        movw(5, GIC_DEST_0X4C & 0xFFFF),  # +24
        movt(5, GIC_DEST_0X4C >> 16),     # +28
        str_imm(5, 0, 4),                 # +32  S1+4 <- 0x40161108
    ])
    if gic_cells:
        for read_ca, cell in zip(GIC_THUNK_READS, gic_cells[:3]):
            body += gic_read_store_block(read_ca, cell)   # +34.. gicview: C0, C1, C2
    l1 = bne_addr + 2 + len(body)         # +34 (scratch); later when the GIC blocks are added
    tail = b"".join([
        pop(PAD_SAVE),
        movw(3, GIC_CA_BASE & 0xFFFF),    # r3 = 0x40161100 (the replaced ldrlo r3)
        movt(3, GIC_CA_BASE >> 16),
        msr_apsr(12),                     # restore flags for the itet block
    ])
    back = l1 + len(tail)
    return head + b_cond(bne_addr, l1, COND_NE) + body + tail + b_w(back, CONT_THUNK)


def pad_bringup(pad: int, s2: int, gic_cells: list[int] | None = None) -> bytes:
    head = b"".join([
        push(PAD_SAVE),                   # +0
        movw(0, s2 & 0xFFFF),             # +2
        movt(0, s2 >> 16),                # +6
        mov_reg(1, 10),                   # +10  r1 = sl
        str_imm(1, 0, 0),                 # +12  S2   <- state word
        movw(1, MARKER & 0xFFFF),         # +14
        movt(1, MARKER >> 16),            # +18
        str_imm(1, 0, 4),                 # +22  S2+4 <- marker
    ])
    if gic_cells:
        for read_ca, cell in zip(GIC_BRINGUP_READS, gic_cells[3:6]):
            head += gic_read_store_block(read_ca, cell)   # gicview: C3, C4, C5
    tail = b"".join([
        pop(PAD_SAVE),
        str_imm_w(10, 7, 0),              # reproduce str.w sl,[r7]
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, BRINGUP_CONT)


# ---------------------------------------------------------------- guards / verify

def patch_sites(data: bytes, pad_i: int, pad_b: int) -> bytes:
    buf = bytearray(data)
    buf[SITE_THUNK:SITE_THUNK + 4] = bl(SITE_THUNK, pad_i)
    buf[BRINGUP_SITE:BRINGUP_SITE + 4] = bl(BRINGUP_SITE, pad_b)
    return bytes(buf)


def check_original_gic_write(data: bytes) -> None:
    """The original ISENABLER write must still be present in the thunk's executable stream."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    region = data[ENABLE_THUNK:ENABLE_THUNK + 0x50]
    for ins in md.disasm(region, ENABLE_THUNK):
        if ins.mnemonic.startswith("str") and "r4" in ins.op_str and "r3, r2, lsl #2" in ins.op_str:
            return
    raise PatchError(
        "patch refused: the original GIC ISENABLER write `str r4,[r3,r2,lsl #2]` "
        f"(CA 0x40161100+(id/32)*4) is not present in region {ENABLE_THUNK:#x}.."
        f"{ENABLE_THUNK + 0x50:#x} - refusing to ship a blob that removes it"
    )


def verify_disasm(data: bytes, pad_i: int, pad_b: int, s1: int, s2: int,
                  gic_cells: list[int] | None = None) -> dict:
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    thunk = dis(ENABLE_THUNK, 0x4C)
    if not any(s.startswith("strlo") and "r4, [r3, r2, lsl #2]" in s for s in thunk):
        raise PatchError(f"the original ISENABLER write is missing from the patched thunk: {thunk!r}")
    site = dis(SITE_THUNK, 4)
    if not (len(site) == 1 and site[0].startswith("bl ")):
        raise PatchError(f"thunk site 0x{SITE_THUNK:x} did not re-disassemble to a bl: {site!r}")

    p_i = dis(pad_i, len(pad_thunk(pad_i, s1, gic_cells)))
    if not any(s.startswith("str r4, [r0]") for s in p_i):
        raise PatchError(f"thunk pad missing the S1 bitmap store: {p_i!r}")
    if not any(s.startswith("str r5, [r0, #4]") for s in p_i):
        raise PatchError(f"thunk pad missing the S1+4 destination store: {p_i!r}")

    b_site = dis(BRINGUP_SITE, 4)
    if not (len(b_site) == 1 and b_site[0].startswith("bl ")):
        raise PatchError(f"bring-up site 0x{BRINGUP_SITE:x} did not re-disassemble to a bl: {b_site!r}")
    p_b = dis(pad_b, len(pad_bringup(pad_b, s2, gic_cells)))
    if not any(s.startswith("str r1, [r0]") for s in p_b):
        raise PatchError(f"bring-up pad missing the S2 state store: {p_b!r}")
    if not any(s.startswith("str r1, [r0, #4]") for s in p_b):
        raise PatchError(f"bring-up pad missing the S2+4 marker store: {p_b!r}")
    if not any(s.startswith("str.w sl, [r7]") for s in p_b):
        raise PatchError(f"bring-up pad missing the reproduced distributor enable: {p_b!r}")

    if gic_cells:
        code_i = pad_thunk(pad_i, s1, gic_cells)
        code_b = pad_bringup(pad_b, s2, gic_cells)
        for read_ca, cell in zip(GIC_THUNK_READS, gic_cells[:3]):
            block = gic_read_store_block(read_ca, cell)
            if block not in code_i or block not in data[pad_i:pad_i + len(code_i)]:
                raise PatchError(f"thunk pad missing the GIC read/store for CA {read_ca:#x} "
                                 f"-> cell {cell:#x}")
        for read_ca, cell in zip(GIC_BRINGUP_READS, gic_cells[3:6]):
            block = gic_read_store_block(read_ca, cell)
            if block not in code_b or block not in data[pad_b:pad_b + len(code_b)]:
                raise PatchError(f"bring-up pad missing the GIC read/store for CA {read_ca:#x} "
                                 f"-> cell {cell:#x}")
        n_ldr = sum(1 for s in p_i + p_b if s.startswith("ldr r1, [r1]"))
        if n_ldr != len(GIC_THUNK_READS) + len(GIC_BRINGUP_READS):
            raise PatchError(f"expected six device-side GIC loads, disassembly shows {n_ldr}")

    return {"enable_thunk": thunk, "thunk_site": site, "thunk_pad": p_i,
            "bringup_site": b_site, "bringup_pad": p_b}


# ---------------------------------------------------------------- variants

def make_probe(data: bytes, refs: set[int]):
    off = FW_SIZE - 1
    chosen = None
    while off >= PROBE_WALK_LO:
        if (off + BIAS) not in refs:
            chosen = off
            break
        off -= 1
    if chosen is None:
        raise PatchError(
            f"probe walk from file 0x{FW_SIZE - 1:x} down to 0x{PROBE_WALK_LO:x} found no offset "
            "whose runtime address is unreferenced - STOP (nothing patched)"
        )
    buf = bytearray(data)
    before = buf[chosen]
    after = before ^ 0x01
    buf[chosen] = after
    inside = chosen < LOADED_SIZE
    patch = {
        "kind": "single-byte-flip",
        "file_offset": hex(chosen),
        "runtime_addr": hex(chosen + BIAS),
        "before": f"0x{before:02x}",
        "after": f"0x{after:02x}",
        "inside_loaded_image": inside,
        "referenced": False,
        "note": "first byte walked downward from the last file byte whose runtime address has no "
                "reference anywhere in the image",
    }
    if not inside:
        patch["warning"] = (
            f"the chosen byte lies beyond the loaded image ({LOADED_SIZE:#x} bytes are loaded per "
            "phase 17 A.6), so this probe changes a byte the loader does not carry - the probe "
            "proves only that a byte-differing blob is accepted/ignored, not that a modified "
            "loaded byte survives the load path"
        )
    return bytes(buf), {"variant": "probe", "patches": [patch]}


def make_scratch(data: bytes, barmap: bytes, refs: set[int]):
    s1, s2, sel = select_cells(barmap)
    need_i = len(pad_thunk(0, s1))
    pad_i, len_i = find_padding(data, refs, need_i, [])
    need_b = len(pad_bringup(0, s2))
    pad_b, len_b = find_padding(data, refs, need_b, [(pad_i, pad_i + len_i)])

    code_i = pad_thunk(pad_i, s1)
    code_b = pad_bringup(pad_b, s2)
    out = bytearray(patch_sites(data, pad_i, pad_b))
    out[pad_i:pad_i + len(code_i)] = code_i
    out[pad_b:pad_b + len(code_b)] = code_b
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    if out[SITE_THUNK:SITE_THUNK + 4] != bl(SITE_THUNK, pad_i):
        raise PatchError("internal error: the thunk site bytes are not the intended bl")
    if out[BRINGUP_SITE:BRINGUP_SITE + 4] != bl(BRINGUP_SITE, pad_b):
        raise PatchError("internal error: the bring-up site bytes are not the intended bl")

    check_original_gic_write(out)
    seen = verify_disasm(out, pad_i, pad_b, s1, s2)

    manifest = {
        "variant": "scratch",
        "selection": sel,
        "cells": {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)},
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "runtime_addr": hex(pad_i + BIAS),
                      "run_length": hex(len_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "runtime_addr": hex(pad_b + BIAS),
                        "run_length": hex(len_b), "code_length": len(code_b), "code_hex": code_b.hex()},
        },
        "patches": [
            {"kind": "trampoline-entry", "region": "enable thunk 0x86ff4", "file_offset": hex(SITE_THUNK),
             "before": data[SITE_THUNK:SITE_THUNK + 4].hex(),
             "after": bl(SITE_THUNK, pad_i).hex(), "note": NOTE_THUNK},
            {"kind": "trampoline-entry", "region": "distributor bring-up 0x6e5c-0x6ed4",
             "file_offset": hex(BRINGUP_SITE), "before": data[BRINGUP_SITE:BRINGUP_SITE + 4].hex(),
             "after": bl(BRINGUP_SITE, pad_b).hex(), "note": NOTE_BRINGUP},
        ],
        "preserved": {
            "original_gic_write": {
                "file_offset": "0x8702c",
                "instruction": "strlo.w r4, [r3, r2, lsl #2]",
                "ca": "0x40161100 + (id/32)*4",
                "verified_present": True,
            }
        },
        "disasm": seen,
    }
    return out, manifest


def make_gicview(data: bytes, barmap: bytes, refs: set[int]):
    """scratch + six device-side GIC reads deposited into fresh cells C0..C5 (see NOTE_GIC_MAP)."""
    cells, sel = select_cells_gicview(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]

    need_i = len(pad_thunk(0, s1, gc))
    pad_i, len_i = find_padding(data, refs, need_i, [])
    need_b = len(pad_bringup(0, s2, gc))
    pad_b, len_b = find_padding(data, refs, need_b, [(pad_i, pad_i + len_i)])

    code_i = pad_thunk(pad_i, s1, gc)
    code_b = pad_bringup(pad_b, s2, gc)
    out = bytearray(patch_sites(data, pad_i, pad_b))
    out[pad_i:pad_i + len(code_i)] = code_i
    out[pad_b:pad_b + len(code_b)] = code_b
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    if out[SITE_THUNK:SITE_THUNK + 4] != bl(SITE_THUNK, pad_i):
        raise PatchError("internal error: the thunk site bytes are not the intended bl")
    if out[BRINGUP_SITE:BRINGUP_SITE + 4] != bl(BRINGUP_SITE, pad_b):
        raise PatchError("internal error: the bring-up site bytes are not the intended bl")

    check_original_gic_write(out)
    seen = verify_disasm(out, pad_i, pad_b, s1, s2, gc)

    cell_records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        cell_records[f"C{i}"] = cell_record(barmap, a)

    manifest = {
        "variant": "gicview",
        "selection": sel,
        "cells": cell_records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICD_CTLR": "0x40161000",
            "GICD_ISENABLER2": hex(GICD_ISENABLER2),
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICD_ISACTIVER2": hex(GICD_ISACTIVER2),
            "GICC_base": "0x40160100",
            "GICC_HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging)",
            "note": NOTE_GIC_MAP,
            "read_order": {
                "C0": {"ca": hex(GICD_ISENABLER2), "point": "enable thunk, after the S1/S1+4 stores"},
                "C1": {"ca": hex(GICD_ISPENDR2), "point": "enable thunk, after the S1/S1+4 stores"},
                "C2": {"ca": hex(GICC_HPPIR), "point": "enable thunk, after the S1/S1+4 stores"},
                "C3": {"ca": hex(GICD_ISPENDR2), "point": "bring-up end, after the S2/S2+4 stores"},
                "C4": {"ca": hex(GICD_ISACTIVER2), "point": "bring-up end, after the S2/S2+4 stores"},
                "C5": {"ca": hex(GICC_HPPIR), "point": "bring-up end, after the S2/S2+4 stores"},
            },
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "runtime_addr": hex(pad_i + BIAS),
                      "run_length": hex(len_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "runtime_addr": hex(pad_b + BIAS),
                        "run_length": hex(len_b), "code_length": len(code_b), "code_hex": code_b.hex()},
        },
        "patches": [
            {"kind": "trampoline-entry", "region": "enable thunk 0x86ff4", "file_offset": hex(SITE_THUNK),
             "before": data[SITE_THUNK:SITE_THUNK + 4].hex(),
             "after": bl(SITE_THUNK, pad_i).hex(), "note": NOTE_GICVIEW_I},
            {"kind": "trampoline-entry", "region": "distributor bring-up 0x6e5c-0x6ed4",
             "file_offset": hex(BRINGUP_SITE), "before": data[BRINGUP_SITE:BRINGUP_SITE + 4].hex(),
             "after": bl(BRINGUP_SITE, pad_b).hex(), "note": NOTE_GICVIEW_II},
        ],
        "preserved": {
            "original_gic_write": {
                "file_offset": "0x8702c",
                "instruction": "strlo.w r4, [r3, r2, lsl #2]",
                "ca": "0x40161100 + (id/32)*4",
                "verified_present": True,
            }
        },
        "disasm": seen,
    }
    return out, manifest


# ---------------------------------------------------------------- selftest

def _encoder_roundtrip() -> None:
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def one(name: str, code: bytes, expect: str, addr: int = 0) -> None:
        ins = list(md.disasm(code, addr))
        got = f"{ins[0].mnemonic} {ins[0].op_str}".strip() if ins else "<undecoded>"
        if not got.startswith(expect):
            raise PatchError(f"encoder selftest: {name}: expected {expect!r}, capstone says {got!r}")

    one("movw", movw(12, 0x1000), "movw ip, #0x1000")
    one("movw2", movw(0, 0x8198), "movw r0, #0x8198")
    one("movt", movt(0, 0x4016), "movt r0, #0x4016")
    one("movt2", movt(5, 0x50AA), "movt r5, #0x50aa")
    one("cmp", cmp_reg(4, 0), "cmp r4, r0")
    one("mov", mov_reg(1, 10), "mov r1, sl")
    one("str", str_imm(4, 0, 0), "str r4, [r0]")
    one("str4", str_imm(5, 0, 4), "str r5, [r0, #4]")
    one("strw", str_imm_w(10, 7, 0), "str.w sl, [r7]")
    one("ldr", ldr_imm(1, 1, 0), "ldr r1, [r1]")
    one("ldr4", ldr_imm(0, 5, 4), "ldr r0, [r5, #4]")
    one("push", push(PAD_SAVE), "push {r0, r1, r2, r3, r4, r5}")
    one("pop", pop(PAD_SAVE), "pop {r0, r1, r2, r3, r4, r5}")
    one("mrs", mrs_apsr(12), "mrs ip, apsr")
    one("msr", msr_apsr(12), "msr apsr_nzcvq, ip")
    one("bl", bl(0x1000, 0x8000), "bl #0x8000", addr=0x1000)
    one("bw", b_w(0x1000, 0x800000), "b.w #0x800000", addr=0x1000)
    one("bcond", b_cond(0x1000, 0x1010, COND_NE), "bne #0x1010", addr=0x1000)


def selftest(fw_path: str, barmap_path: str) -> int:
    data = rd(fw_path)
    barmap = rd(barmap_path)
    check_input(data, fw_path)
    check_barmap(barmap)
    _encoder_roundtrip()

    refs = build_refs(data)

    # ---- probe: exactly one byte differs, size unchanged, deterministic
    probe, pm = make_probe(data, refs)
    assert len(probe) == len(data), "probe changed the size"
    diff = [i for i in range(len(data)) if probe[i] != data[i]]
    assert len(diff) == 1 and hex(diff[0]) == pm["patches"][0]["file_offset"], "probe byte mismatch"
    probe2, pm2 = make_probe(data, refs)
    assert probe == probe2 and json.dumps(pm, sort_keys=True) == json.dumps(pm2, sort_keys=True)

    # ---- scratch: size unchanged, deterministic, confined to the named regions + pads
    scratch, sm = make_scratch(data, barmap, refs)
    assert len(scratch) == len(data), "scratch changed the size"
    scratch2, sm2 = make_scratch(data, barmap, refs)
    assert scratch == scratch2, "scratch patch is not deterministic"
    assert json.dumps(sm, sort_keys=True) == json.dumps(sm2, sort_keys=True), "manifest not deterministic"

    s1 = int(sm["cells"]["S1"]["addr"], 16)
    s2 = int(sm["cells"]["S2"]["addr"], 16)
    assert sm["cells"]["S1"]["barmap_value"] == "0x0", "S1 baseline is not zero"
    assert sm["cells"]["S2"]["barmap_value"] == "0x0", "S2 baseline is not zero"
    assert sm["selection"]["spec_range_zero_words"] == 0, "expected the spec range to be unsatisfiable here"
    pad_i = int(sm["padding"]["thunk"]["file_offset"], 16)
    pad_b = int(sm["padding"]["bringup"]["file_offset"], 16)
    assert s1 not in S_CELL_EXCLUDE and s2 not in S_CELL_EXCLUDE, "S1/S2 inside an excluded table"

    allowed = set(range(SITE_THUNK, SITE_THUNK + 4)) | set(range(BRINGUP_SITE, BRINGUP_SITE + 4))
    allowed |= set(range(pad_i, pad_i + len(pad_thunk(pad_i, s1))))
    allowed |= set(range(pad_b, pad_b + len(pad_bringup(pad_b, s2))))
    changed = [i for i in range(len(data)) if scratch[i] != data[i]]
    assert changed and all(c in allowed for c in changed), "scratch changed bytes outside its regions"
    assert not (set(range(pad_i, pad_i + 64)) & set(range(pad_b, pad_b + 64))), "the two pads overlap"

    # ---- original write present, added stores present (re-disasm)
    check_original_gic_write(scratch)
    verify_disasm(scratch, pad_i, pad_b, s1, s2)

    # ---- frozen sibling variants: the probe/scratch blobs must not have moved
    assert md5(probe) == PROBE_MD5, f"probe output changed: {md5(probe)} != {PROBE_MD5}"
    assert md5(scratch) == SCRATCH_MD5, f"scratch output changed: {md5(scratch)} != {SCRATCH_MD5}"

    # ---- gicview: size unchanged, deterministic, six GIC reads, fresh distinct cells
    gic, gm = make_gicview(data, barmap, refs)
    assert len(gic) == len(data), "gicview changed the size"
    gic2, gm2 = make_gicview(data, barmap, refs)
    assert gic == gic2, "gicview patch is not deterministic"
    assert json.dumps(gm, sort_keys=True) == json.dumps(gm2, sort_keys=True), "gicview manifest not deterministic"
    assert gm["cells"]["S1"]["addr"] == sm["cells"]["S1"]["addr"], "gicview moved S1"
    assert gm["cells"]["S2"]["addr"] == sm["cells"]["S2"]["addr"], "gicview moved S2"
    gc = [int(gm["cells"][f"C{i}"]["addr"], 16) for i in range(GICV_NCELLS)]
    assert len(set(gc + [s1, s2])) == 2 + GICV_NCELLS, "C0..C5 are not distinct from S1/S2"
    assert all(gc[i + 1] - gc[i] >= 8 for i in range(GICV_NCELLS - 1)), "C cells are not distinct"
    assert all(gm["cells"][f"C{i}"]["barmap_value"] == "0x0" for i in range(GICV_NCELLS)), \
        "a C cell baseline is not zero"
    assert all(c not in S_CELL_EXCLUDE for c in gc), "a C cell is inside an excluded table"
    assert gm["gic_map"]["GICD_ISPENDR2"] == hex(GICD_ISPENDR2) == "0x40161208"
    assert gm["gic_map"]["GICD_ISACTIVER2"] == hex(GICD_ISACTIVER2) == "0x40161308"
    pad_i_g = int(gm["padding"]["thunk"]["file_offset"], 16)
    pad_b_g = int(gm["padding"]["bringup"]["file_offset"], 16)
    code_i_g = pad_thunk(pad_i_g, s1, gc)
    code_b_g = pad_bringup(pad_b_g, s2, gc)
    for read_ca, cell in zip(GIC_THUNK_READS, gc[:3]):
        assert gic_read_store_block(read_ca, cell) in code_i_g, f"thunk pad missing CA {read_ca:#x}"
    for read_ca, cell in zip(GIC_BRINGUP_READS, gc[3:6]):
        assert gic_read_store_block(read_ca, cell) in code_b_g, f"bring-up pad missing CA {read_ca:#x}"
    allowed_g = set(range(SITE_THUNK, SITE_THUNK + 4)) | set(range(BRINGUP_SITE, BRINGUP_SITE + 4))
    allowed_g |= set(range(pad_i_g, pad_i_g + len(code_i_g)))
    allowed_g |= set(range(pad_b_g, pad_b_g + len(code_b_g)))
    changed_g = [i for i in range(len(data)) if gic[i] != data[i]]
    assert changed_g and all(c in allowed_g for c in changed_g), "gicview changed bytes outside its regions"
    assert gic[0x8702C:0x87030] == data[0x8702C:0x87030], "gicview altered the original ISENABLER write"
    assert gic[SITE_THUNK + 8:SITE_THUNK + 0x50] == data[SITE_THUNK + 8:SITE_THUNK + 0x50], \
        "gicview altered the enable thunk's executable stream"
    check_original_gic_write(gic)
    verify_disasm(gic, pad_i_g, pad_b_g, s1, s2, gc)
    assert not (set(range(pad_i_g, pad_i_g + 64)) & set(range(pad_b_g, pad_b_g + 64))), "the gicview pads overlap"

    # ---- input untouched
    assert rd(fw_path) == data, "the input file changed during the run"

    # ---- rejection path: a blob whose original GIC write was removed must be refused
    broken = bytearray(data)
    broken[0x8702C:0x87030] = b"\x00\xbf\x00\xbf"
    try:
        check_original_gic_write(bytes(broken))
    except PatchError as exc:
        assert "refusing" in str(exc), "rejection message is not explicit"
    else:
        raise PatchError("rejection path missing: a blob without the original GIC write was accepted")

    # ---- refusals name the failing check
    mutated = bytes([data[0] ^ 0x01]) + data[1:]
    try:
        check_md5(mutated, "<bad>")
    except PatchError as exc:
        assert "md5" in str(exc), f"refusal did not name the md5 check: {exc}"
    else:
        raise PatchError("a blob with the wrong md5 was accepted")
    try:
        check_size(data[:-1], "<bad>")
    except PatchError as exc:
        assert "size" in str(exc), f"refusal did not name the size check: {exc}"
    else:
        raise PatchError("a blob with the wrong size was accepted")

    print("SELFTEST PASS")
    print(f"  probe byte        : {pm['patches'][0]['file_offset']} "
          f"{pm['patches'][0]['before']} -> {pm['patches'][0]['after']} "
          f"(loaded={pm['patches'][0]['inside_loaded_image']})")
    print(f"  S1                : {sm['cells']['S1']['addr']} baseline {sm['cells']['S1']['barmap_value']}")
    print(f"  S2                : {sm['cells']['S2']['addr']} baseline {sm['cells']['S2']['barmap_value']}")
    print(f"  padding (thunk)   : {sm['padding']['thunk']['file_offset']} len {sm['padding']['thunk']['run_length']}")
    print(f"  padding (bringup) : {sm['padding']['bringup']['file_offset']} len {sm['padding']['bringup']['run_length']}")
    print(f"  changed bytes     : {len(changed)} (sites 8, pads {len(pad_thunk(pad_i, s1))}+{len(pad_bringup(pad_b, s2))})")
    print(f"  scratch md5       : {md5(scratch)}")
    print(f"  gicview cells     : S1={gm['cells']['S1']['addr']} S2={gm['cells']['S2']['addr']} "
          + " ".join(f"C{i}={gm['cells'][f'C{i}']['addr']}" for i in range(GICV_NCELLS)))
    print(f"  gicview gic reads : C0/C1/C2={[hex(x) for x in GIC_THUNK_READS]} "
          f"C3/C4/C5={[hex(x) for x in GIC_BRINGUP_READS]}")
    print(f"  gicview md5       : {md5(gic)}")
    return 0


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="patch_fw_scratch.py", description=__doc__.splitlines()[0])
    ap.add_argument("--fw", default="build/tmp/FIRMWARE.bin", help="input blob (READ-ONLY)")
    ap.add_argument("--barmap", default="opensource/build/register-dumps/barmap_ep0_bar0.bin",
                    help="normal-op BAR0 baseline used for S1/S2 selection")
    ap.add_argument("--out", help="output blob (never the input)")
    ap.add_argument("--variant", choices=("probe", "scratch", "gicview"),
                    help="probe: one non-executed byte flip; scratch: the two instrumentation "
                         "stores; gicview: scratch + six device-side GIC reads into cells C0..C5")
    ap.add_argument("--manifest", help="manifest path (default <out>.manifest.json)")
    ap.add_argument("--selftest", action="store_true", help="run the byte-level selftest")
    args = ap.parse_args(argv)

    try:
        if args.selftest:
            return selftest(args.fw, args.barmap)
        if not (args.out and args.variant):
            ap.error("--out and --variant are required (or use --selftest)")
        if os.path.abspath(args.out) == os.path.abspath(args.fw):
            raise PatchError("refusing to overwrite the input blob in place")
        if not os.path.exists(args.barmap):
            raise PatchError(f"barmap missing: {args.barmap}")

        data = rd(args.fw)
        checks = check_input(data, args.fw)
        barmap = rd(args.barmap)
        refs = build_refs(data)
        out, manifest = (make_probe(data, refs) if args.variant == "probe"
                         else make_scratch(data, barmap, refs) if args.variant == "scratch"
                         else make_gicview(data, barmap, refs))
        manifest.update({
            "tool": "tools/patch_fw_scratch.py",
            "input": {"path": args.fw, "md5": md5(data), "size": len(data), "checks": checks},
            "output": {"path": args.out, "md5": md5(out), "size": len(out)},
            "size_unchanged": len(out) == len(data),
        })

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "wb") as fh:
            fh.write(out)
        mpath = args.manifest or (args.out + ".manifest.json")
        with open(mpath, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")

        if rd(args.fw) != data:
            raise PatchError("the input blob changed during the run")

        print(f"{args.variant}: wrote {args.out} ({len(out)} B, md5 {md5(out)})")
        print(f"manifest: {mpath}")
        return 0
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
