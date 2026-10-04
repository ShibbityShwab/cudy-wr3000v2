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
  gicview  - scratch + six device-side GIC reads deposited into fresh WRAM cells C0..C5.
  gicsend  - gicview + a THIRD trampoline at the firmware's own out[1] message post
             (file 0x86F5A, `str r2,[r3]` with r3 = CA 0x40039014, r2 = 4 = bit 2, the
             "device platform ready" word), which reproduces the store and then reads the
             three GIC words into fresh cells D0/D1/D2:
                             D0 <- CA 0x40161208 (GICD_ISPENDR2  word 2, bit 12 = id 0x4c)
                             D1 <- CA 0x40160118 (GICC HPPIR, 0x3ff = nothing pending)
                             D2 <- CA 0x40161308 (GICD_ISACTIVER2 word 2, delivered/active)
             Because the site runs on the post, the D cells hold the LAST post's sample - a
             few instructions after the store, which is stated and bounded in the manifest.
             The acknowledging GICC IAR CA 0x4016010c is NEVER read by any variant.
  gicpost  - gicsend + a FOURTH trampoline at file 0x87036, the first instruction boundary after
             the conditional enable store (file 0x8702c) that lies OUTSIDE its `itet lo` block -
             the firmware's own `bl #0xbdf50`.  The pad samples CA 0x40161108 back into E0 (the
             ISENABLER2 word 2 POST-write readback: bit 12 set proves the conditional store
             landed), CA 0x40161208 into E1 (ISPENDR2 at the same instant) and re-arms the
             sentinel E2 = 0x50aa7e49; the enable-gate pad additionally deposits the APSR it
             captures (`mrs ip, apsr`) into E3 and leaves the request word 0xe2e2e2e2 in E2 on
             its id-0x4c-gated path, so E0/E1 belong to the same pass as E3.  E3 decodes the very
             flags the store tests (bit 30 = Z, bit 29 = C; LO held iff C = 0 and Z = 0), which is
             the one thing every earlier sample could not see.

S1/S2 (and the gicview/gicsend C*/D* cells) are chosen by rule from barmap_ep0_bar0.bin: a
4-byte aligned firmware runtime address whose 4-byte word is 0x00000000 at BAR0 offset ==
addr AND at the ACP alias BAR0 0x6b8000+addr, outside the four named tables, each cell at
least 8 bytes from the previous one.

The input blob is only ever read; every artifact is written under --out.

usage:
  patch_fw_scratch.py --fw <FIRMWARE.bin> --out <variant.bin>
                      --variant probe|scratch|gicview|gicsend|gicpost
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
GICVIEW_MD5 = "b6b7faa9b2682d959cce6d0fb2bae315"   # frozen gicview-variant output (selftest regression)
GICSEND_MD5 = "326619bed125e65930a0a62bc6abdd47"   # frozen gicsend-variant output (selftest regression)
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

# ---- gicsend: the firmware's own out[1] message post (variant "gicsend") ---------
# The firmware writes the D2H pending bitmap to out[1] (CA 0x40039014) from exactly four
# places in the image (phase38 docs/phase38/open-gaps-static-attempt.md section 1.1, an
# exhaustive address-provenance scan): the ctx init `*out[1] = 0` (file 0x978c), the inline
# "platform ready" pair (file 0x86F5A/0x86F66, bit 2), the generic notify primitive
# `d2h_notify` @ file 0x86170 (`str r3,[r1]` @ 0x861B0, ids 5/6/8) and its IRQ-0x4E flush
# @ file 0x86156.  Of those, the ONLY one that runs in this variant's boot (the port's
# frozen params never post an SR descriptor, so no ring and therefore no id-6 notify) is the
# inline store at file 0x86F5A, inside the ETE bring-up routine @ file 0x86E14.  That store
# is the image's only possible source of the out[1] = 0x00000004 word every takeover logs
# (e.g. "out[1] 0x00000000 -> 0x00000004  bit 2 set (id 2)"), so the site is proven on the
# executed path by the observed register, not assumed.
SEND_SITE = 0x86F5A                     # `str r2,[r3]` (2 B) + `movs r2,#1` (2 B) -> replaced
SEND_CONT = 0x86F5E                     # continue at `add.w r3,r3,#0xc8000`
GICS_NCELLS = 6                        # D0..D2 sample, D3 marker, D4/D5 re-check in a 2nd page
GICS_MARKER = MARKER                   # 0x50AA7E49 - the proven presence proof (the S2+4 idiom)
GIC_SEND_READS = (GICD_ISPENDR2, GICC_HPPIR, GICD_ISACTIVER2)       # -> D0, D1, D2
GIC_SEND_RECHECK = GICD_ISPENDR2       # -> D4 (a second read of the critical word)
NOTE_GICSEND_SITE = (
    "gicsend puts a third `bl` trampoline at file 0x86F5A, replacing the 4 bytes `str r2,[r3]` "
    "(the firmware's out[1] post, r3 = CA 0x40039014, r2 = 4) + `movs r2,#1`. The pad reproduces "
    "the store FIRST (so the post has happened), then reads CA 0x40161208 -> D0 (ISPENDR2 word 2, "
    "bit 12 = source id 0x4c), CA 0x40160118 -> D1 (GICC HPPIR, 0x3ff = nothing pending for the "
    "CPU) and CA 0x40161308 -> D2 (ISACTIVER2 word 2, bit 12 = delivered/active), then restores "
    "r0-r5, reproduces `movs r2,#1` as `movw r2,#1`, restores the saved APSR and returns to "
    "0x86F5E. r0-r5 are saved/restored (r1 holds the 0x4000010c spin pointer and r3 the out[1] CA "
    "for the following instructions), r6/r7/sl are untouched, and lr is restored by the routine's "
    "own epilogue before any use, so the `bl`'s lr clobber is harmless. The original flags are "
    "restored; the replaced `movs r2,#1` would have set N=Z=0, and the next flag consumer in the "
    "routine is the `cmp` at 0x86F7A, which sets its own - so the difference is inert."
)
NOTE_GICSEND_CELLS = (
    "SELECTION RULE FOR D (iteration 2, after the first gicsend boot): the first gicsend attempt "
    "took D0..D2 from the plain walk, which placed them at 0x104004/0x10400C/0x10408C - holes "
    "inside the 0x104000 page (984 of its 1024 words are live in the normal-op barmap, the ETE "
    "ring-table band). In that boot every other cell agreed between its BAR0 and alias views while "
    "those three did not (BAR0 read 0, the ACP alias read the deposited GIC words), i.e. the "
    "deposit was not readable back unambiguously from the region-0 view. gicsend therefore takes "
    "its D cells ONLY from 4 KB pages that are entirely 0x00 at BOTH views in "
    "barmap_ep0_bar0.bin - pages with no live firmware word at all - plus a presence marker and a "
    "second read of the critical word in a second such page (the brief's one re-run allowance; "
    "the named host-side cause is the cell rule, not the device). S1/S2/C0..C5 are the walk's "
    "fixed prefix and are unchanged, so the variants stay directly comparable."
)
NOTE_GICSEND_MARKER = (
    "The marker cell (the S2+4 idiom, 0x50AA7E49) is the presence proof of the send pad: the site "
    "may run a single time and the cells may be read minutes later, so a zero sample is only "
    "meaningful if a constant written by the same pad in the same page is still readable at "
    "capture time. D3 is the marker in the D0..D2 page and D5 a second marker in D4's page; an "
    "intact marker next to a zero sample means 'the register read 0', a missing marker means 'the "
    "deposit was lost and the sample is void'."
)
NOTE_GICSEND_TIMING = (
    "TIMING BOUND (stated, not hidden): the D cells are written a few instructions AFTER the "
    "out[1] store (the pad stores first, then reads). Because the site is the out[1] writer, the "
    "cells hold the LAST post's sample and that value persists until the next post. A D0 with bit "
    "12 clear therefore means 'not pending at the sampled instant', not 'never pending'."
)

S_CELL_LO, S_CELL_HI = 0xE7000, 0xFFF00
S_CELL_ALIAS_HI = 0x1BFFFF             # descriptor 0 (ROM_WRAM) device limit
S_CELL_EXCLUDE = (
    0x118D68 + 0x50,
    0x17D430 + 0xC0,
    0x105F80 + 0xA0,
    0x172130 + 0x10,
)
# ---- gicpost: the POST-WRITE readback of the enable store (variant "gicpost") --------------
# The firmware's enable store is the CONDITIONAL `strlo.w r4,[r3,r2,lsl #2]` at file 0x8702c: it
# lands only when the LO condition holds (C == 0 AND Z == 0).  Every earlier sample is taken
# BEFORE it (the enable-gate pad at file 0x87024 runs first; gicsend samples at the out[1] post,
# much later), so a takeover boot in which the condition is false would look exactly like a boot
# in which the write landed and the wire stayed silent.  gicpost closes that hole:
#   * a second trampoline at file 0x87036.  0x8702c is the conditional store; 0x87030/0x87034 are
#     the `itet lo` block's hs/lo slots, so a `bl` planted there would sit INSIDE an IT block
#     (UNPREDICTABLE).  0x87036 is the first boundary after the store that is outside the block
#     and runs unconditionally - the firmware's own `bl #0xbdf50` - and the pad reproduces that
#     call EXACTLY: it contains no `bl` of its own, so lr still holds 0x8703a (the value the
#     replaced instruction installed, which the callee at file 0xbdf54 passes on), and it ends in
#     `b.w 0xbdf50`, dropping the callee back to the identical instruction (0x8703a).
#   * the enable-gate pad (file 0xc8198) additionally deposits the APSR it captured into E3 and
#     leaves the request word GICP_REQUEST in E2 on the same id-0x4c-gated path.  The post pad
#     consumes that request (match, clear, sample), so E0/E1 describe the SAME id-0x4c pass whose
#     flags E3 records, not whatever the last enable() call happened to be.  E2 therefore
#     separates three states: 0x50aa7e49 = the sample ran; 0xe2e2e2e2 = the request was set and
#     never consumed (the post pad did not run - say so rather than reading the zeros); 0 = no
#     id-0x4c enable pass happened at all.
# The gate pad restores APSR before returning to 0x87028, so the flags at 0x8702c are the ORIGINAL
# `cmp r4,r3` flags (file 0x87014) - the very ones E3 records.  APSR bit 31 = N, 30 = Z, 29 = C,
# 28 = V; LO held iff C == 0 and Z == 0.
POST_SITE = 0x87036          # `bl #0xbdf50` - first boundary after the store, outside the IT block
POST_CALL = 0xBDF50          # the call the replaced instruction makes (reproduced with `b.w`)
POST_CONT = 0x8703A          # `mov r0,r4` - where that call returns (lr = 0x8703a at the site)
GICP_NCELLS = 4              # E0..E3
GICP_READS = (GICD_ISENABLER2, GICD_ISPENDR2)   # -> E0, E1
GICP_MARKER = MARKER         # 0x50aa7e49 - the post pad's presence sentinel -> E2
GICP_REQUEST = 0xE2E2E2E2    # the gate pad's request word -> E2 (consumed by the post pad)
GICP_E_LO = S_CELL_LO        # the sub-boundary band, where BAR0 and the ACP alias agree
GICP_E_HI = 0x104000         # the pinned agreement boundary (0x103ffc agrees, 0x104004 does not)

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


def _zero_page_spans(barmap: bytes) -> list[int]:
    """The 4 KB pages of the ROM_WRAM band that are entirely 0x00 at BOTH the BAR0 and the alias
    view in the barmap baseline - pages with no live firmware word in them at all.  The D cells
    (iteration 2) come only from these, because the first attempt's holes inside a live page did
    not read back at the BAR0 view."""
    ok = _cell_ok(barmap)
    pages = []
    for p in range(S_CELL_LO & ~0xFFF, S_CELL_ALIAS_HI - 0xFFF, 0x1000):
        if all(ok(x) for x in range(p, p + 0x1000, 4)):
            pages.append(p)
    return pages


def select_cells_gicsend(barmap: bytes):
    """The walk's fixed prefix (S1, S2, C0..C5, identical to scratch/gicview) plus six D cells: the
    sample/marker group in the lowest all-zero 4 KB page and the re-check group in the next one."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("gicsend selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < 2:
        raise PatchError("gicsend selection failed: fewer than two all-zero 4 KB pages in the band")
    p1, p2 = pages[0], pages[1]

    def take(page: int, n: int, prev: list[int]) -> list[int]:
        out: list[int] = []
        a = page
        while a + 8 <= page + 0x1000 and len(out) < n:
            last = out[-1] if out else prev[-1]
            if ok(a) and a - last >= 8:
                out.append(a)
            a += 4
        return out

    d = take(p1, 4, prefix)
    if len(d) < 4:
        raise PatchError(f"gicsend selection failed: page {p1:#x} has fewer than four usable cells")
    e = take(p2, 2, d)
    if len(e) < 2:
        raise PatchError(f"gicsend selection failed: page {p2:#x} has fewer than two usable cells")
    cells = prefix + d + e
    sel = {
        "rule": "4-byte aligned runtime addr; 4-byte word == 0x00000000 at BAR0 offset addr and "
                "at alias 0x6b8000+addr; outside the four excluded tables; each cell >= 8 bytes "
                "from the previous one.  S1/S2/C0..C5 = the walk's fixed prefix (identical to the "
                "scratch/gicview variants).  D0..D3 = the first four usable cells of the lowest "
                "4 KB page that is entirely zero at both views; D4..D5 = the first two usable "
                "cells of the next such page",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "d_page_1": hex(p1),
        "d_page_2": hex(p2),
        "note": NOTE_RANGE,
        "fresh_cell_justification": (
            "S1/S2/C0..C5 keep their gicview-variant values (the walk's fixed prefix).  D0..D5 are "
            "chosen from 4 KB pages that are entirely zero in barmap_ep0_bar0.bin at BOTH the BAR0 "
            "and the ACP-alias offsets, i.e. from pages with no live firmware word - the fix for "
            "the first gicsend boot, whose D cells were holes inside the live 0x104000 page and "
            "were not readable back from the BAR0 view.  Each cell is >= 8 bytes from the previous "
            "one and outside the four excluded tables, and D3/D5 are presence markers."
        ),
    }
    return cells, sel


NOTE_GICPOST_E = (
    "E0..E3 live in the sub-boundary band [0xE7000, 0x104000): the BAR0 view and the ACP alias "
    "agree there (the boundary is empirically pinned at 0x104000 - the C5 cell 0x103ffc reads "
    "identically at both views, the round-1 cell 0x104004 did not), so an E value is admissible "
    "from the BAR0 read alone.  The brief's preference for an all-zero 4 KB page below the "
    "boundary is UNSATISFIABLE against barmap_ep0_bar0.bin: the lowest all-zero page is 0x11e000 "
    "(above the boundary), and the entire sub-boundary band holds exactly 13 zero words, nine of "
    "which are already S1/S1+4/S2/S2+4/C0..C5.  The four survivors - 0x103fb8, 0x103fe8, "
    "0x103ff0, 0x103ff8, all in the one sub-boundary page that has any zero word at all "
    "(0x103000, the page the C cells sit in) - are E0..E3, so E2 (the sentinel) and E3 (the APSR) "
    "sit in the same page as E0/E1 as required, and the deposit is readable from the BAR0 view "
    "(the C cells prove that view live at these addresses in the gicview/gicsend boots)."
)


def select_cells_gicpost(barmap: bytes):
    """The gicsend cells (S1/S2/C0..C5 = the walk's prefix, D0..D5 = the two all-zero pages) plus
    the four E cells of the post-write sample group (see NOTE_GICPOST_E)."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("gicpost selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < 2:
        raise PatchError("gicpost selection failed: fewer than two all-zero 4 KB pages in the band")

    def take(page: int, n: int, prev: list[int]) -> list[int]:
        out: list[int] = []
        a = page
        while a + 8 <= page + 0x1000 and len(out) < n:
            last = out[-1] if out else prev[-1]
            if ok(a) and a - last >= 8:
                out.append(a)
            a += 4
        return out

    d = take(pages[0], 4, prefix)
    if len(d) < 4:
        raise PatchError(f"gicpost selection failed: page {pages[0]:#x} has fewer than four usable cells")
    d2 = take(pages[1], 2, d)
    if len(d2) < 2:
        raise PatchError(f"gicpost selection failed: page {pages[1]:#x} has fewer than two usable cells")

    used = set(prefix) | {prefix[0] + 4, prefix[1] + 4}     # S1+4/S2+4 are written slots
    band = [a for a in range(GICP_E_LO, GICP_E_HI, 4) if ok(a)]
    e = [a for a in band if a not in used][:GICP_NCELLS]
    if len(e) < GICP_NCELLS:
        raise PatchError(f"gicpost selection failed: only {len(e)} free sub-boundary cells for E0..E3")

    cells = prefix + d + d2 + e
    sel = {
        "rule": "S1/S2/C0..C5 = the walk's fixed prefix and D0..D5 = the two all-zero 4 KB pages "
                "(identical to the gicsend variant, so the variants stay directly comparable).  "
                "E0..E3 = the free 4-byte words of the sub-boundary band [0xE7000, 0x104000) that "
                "are 0x00000000 at BOTH the BAR0 offset and the alias offset in "
                "barmap_ep0_bar0.bin, outside the four excluded tables and distinct from every "
                "earlier cell and from the S1+4/S2+4 written slots",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "all_zero_pages_below_boundary": [hex(p) for p in pages if p < GICP_E_HI],
        "d_page_1": hex(pages[0]),
        "d_page_2": hex(pages[1]),
        "e_band": [hex(GICP_E_LO), hex(GICP_E_HI)],
        "e_band_zero_words": [hex(a) for a in band],
        "e_band_used_by_earlier_cells": [hex(a) for a in band if a in used],
        "e_pages": sorted({hex(a & ~0xFFF) for a in e}),
        "note": NOTE_RANGE,
        "e_note": NOTE_GICPOST_E,
    }
    return cells, sel


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


def pad_thunk(pad: int, s1: int, gic_cells: list[int] | None = None,
              apsr_cell: int | None = None, req_cell: int | None = None) -> bytes:
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
    if req_cell is not None:                          # gicpost: E2 <- the id-0x4c request word
        body += _store_imm_block(GICP_REQUEST, req_cell)
    if apsr_cell is not None:                         # gicpost: E3 <- the APSR captured below
        body += _store_ip_block(apsr_cell)
    l1 = bne_addr + 2 + len(body)         # +34 (scratch); later when the GIC blocks are added
    tail = b"".join([
        pop(PAD_SAVE),
        movw(3, GIC_CA_BASE & 0xFFFF),    # r3 = 0x40161100 (the replaced ldrlo r3)
        movt(3, GIC_CA_BASE >> 16),
        msr_apsr(12),                     # restore flags for the itet block
    ])
    back = l1 + len(tail)
    return head + b_cond(bne_addr, l1, COND_NE) + body + tail + b_w(back, CONT_THUNK)


def _store_imm_block(value: int, cell: int) -> bytes:
    """movw/movt an immediate into r1 and the cell address into r0, then `str r1,[r0]`.  r0/r1 are
    saved/restored by the pad's push/pop."""
    return b"".join([
        movw(1, value & 0xFFFF),
        movt(1, value >> 16),
        movw(0, cell & 0xFFFF),
        movt(0, cell >> 16),
        str_imm(1, 0, 0),
    ])


def pad_send(pad: int, d_cells: list[int]) -> bytes:
    """The send-site pad. Order matters: the replaced `str r2,[r3]` poster is reproduced FIRST
    (before its own sample), then the three device-side GIC reads are deposited into D0/D1/D2, a
    presence marker into D3, a second read of the critical word into D4 and a second marker into
    D5; then r0-r5 are restored, `movs r2,#1` is reproduced as `movw r2,#1`, the saved flags are
    restored and the pad returns to the instruction after the replaced pair."""
    d0, d1, d2, d3, d4, d5 = d_cells
    head = b"".join([
        mrs_apsr(12),                                   # +0  save condition flags
        push(PAD_SAVE),                                 # +4  24 bytes, keeps SP 8-aligned
        str_imm(2, 3, 0),                               # +6  reproduce `str r2,[r3]` -> the post
        gic_read_store_block(GIC_SEND_READS[0], d0),    # D0  ISPENDR2
        gic_read_store_block(GIC_SEND_READS[1], d1),    # D1  HPPIR
        gic_read_store_block(GIC_SEND_READS[2], d2),    # D2  ISACTIVER2
        _store_imm_block(GICS_MARKER, d3),              # D3  presence marker (same page)
        gic_read_store_block(GIC_SEND_RECHECK, d4),     # D4  ISPENDR2 again (second page)
        _store_imm_block(GICS_MARKER, d5),              # D5  presence marker (second page)
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(2, 1),                       # reproduce `movs r2,#1`
        msr_apsr(12),                     # restore flags for the continuation
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, SEND_CONT)


def _store_ip_block(cell: int) -> bytes:
    """movw/movt the cell address into r0 and `str.w ip,[r0]`.  ip (r12) is where the gate pad
    parks the APSR it captured, and ip is not a low register, so the 32-bit store form is used."""
    return b"".join([
        movw(0, cell & 0xFFFF),
        movt(0, cell >> 16),
        str_imm_w(12, 0, 0),
    ])


def pad_post(pad: int, e_cells: list[int]) -> bytes:
    """The post-write pad (gicpost), entered at file 0x87036.

    0x8702c is the conditional store; 0x87030/0x87034 are the `itet lo` block's hs/lo slots, so a
    `bl` planted there would sit INSIDE an IT block (UNPREDICTABLE).  0x87036 is the first boundary
    after the store that is outside the block and runs unconditionally: the firmware's own
    `bl #0xbdf50`.  The pad therefore has to leave that call's semantics exactly as they were:

      * it must NOT contain any `bl` of its own - the `bl` at 0x87036 installs lr = 0x8703a, the
        callee's own `mov r2, lr` (file 0xbdf54) passes that value on, and the callee returns
        through it, so lr is live data at this point, not scratch;
      * it ends in `b.w 0xbdf50`, a tail branch that leaves lr at 0x8703a and so drops the callee
        back to the identical instruction (0x8703a, `mov r0,r4`) it would have reached unpatched.

    The sample is gated on the request the gate pad left in E2 (GICP_REQUEST): the gate pad only
    writes it on its id-0x4c path, so E0/E1/E2 describe that pass and no earlier or later enable()
    call.  E0 is CA 0x40161108 (ISENABLER2 word 2) read back immediately after the store, E1 is
    CA 0x40161208 (ISPENDR2 word 2) read at the same instant, and E2 is then re-armed with the
    0x50aa7e49 sentinel, which is the presence proof of the sample.  r0-r5 and the condition flags
    are saved and restored.
    """
    e0, e1, e2, _e3 = e_cells
    head = b"".join([
        mrs_apsr(12),                                    # +0  park the condition flags
        push(PAD_SAVE),                                  # +4  24 bytes, SP stays 8-aligned
        movw(1, GICP_REQUEST & 0xFFFF),                  # +6
        movt(1, GICP_REQUEST >> 16),                     # +10  r1 = 0xe2e2e2e2
        movw(0, e2 & 0xFFFF),                            # +14  r0 = &E2
        movt(0, e2 >> 16),                               # +18
        ldr_imm(2, 0, 0),                                # +22  r2 = *E2 (the request word)
        cmp_reg(2, 1),                                   # +24
    ])
    bne_addr = pad + len(head)                           # +26
    body = b"".join([
        movw(2, 0),                                      # r2 = 0
        str_imm(2, 0, 0),                                # *E2 = 0 (consume the request)
        gic_read_store_block(GICP_READS[0], e0),         # E0  ISENABLER2, POST-write readback
        gic_read_store_block(GICP_READS[1], e1),         # E1  ISPENDR2, right after the store
        _store_imm_block(GICP_MARKER, e2),               # E2  sentinel: the sample happened
    ])
    l_skip = bne_addr + 2 + len(body)
    tail = b"".join([
        pop(PAD_SAVE),
        msr_apsr(12),                                    # the flags the replaced bl saw
    ])
    back = l_skip + len(tail)
    return head + b_cond(bne_addr, l_skip, COND_NE) + body + tail + b_w(back, POST_CALL)


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

def patch_sites(data: bytes, pad_i: int, pad_b: int, pad_s: int | None = None,
                pad_p: int | None = None) -> bytes:
    buf = bytearray(data)
    buf[SITE_THUNK:SITE_THUNK + 4] = bl(SITE_THUNK, pad_i)
    buf[BRINGUP_SITE:BRINGUP_SITE + 4] = bl(BRINGUP_SITE, pad_b)
    if pad_s is not None:
        buf[SEND_SITE:SEND_SITE + 4] = bl(SEND_SITE, pad_s)
    if pad_p is not None:
        buf[POST_SITE:POST_SITE + 4] = bl(POST_SITE, pad_p)
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
                  gic_cells: list[int] | None = None,
                  apsr_cell: int | None = None, req_cell: int | None = None) -> dict:
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    thunk = dis(ENABLE_THUNK, 0x4C)
    if not any(s.startswith("strlo") and "r4, [r3, r2, lsl #2]" in s for s in thunk):
        raise PatchError(f"the original ISENABLER write is missing from the patched thunk: {thunk!r}")
    site = dis(SITE_THUNK, 4)
    if not (len(site) == 1 and site[0].startswith("bl ")):
        raise PatchError(f"thunk site 0x{SITE_THUNK:x} did not re-disassemble to a bl: {site!r}")

    p_i = dis(pad_i, len(pad_thunk(pad_i, s1, gic_cells, apsr_cell=apsr_cell, req_cell=req_cell)))
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

    if req_cell is not None:                          # gicpost: the E2 request store
        if not any(s.startswith("movw r1, #0xe2e2") for s in p_i):
            raise PatchError(f"thunk pad missing the gicpost request store (E2): {p_i!r}")
    if apsr_cell is not None:                         # gicpost: the E3 APSR deposit
        if not any(s.startswith("str.w ip, [r0]") for s in p_i):
            raise PatchError(f"thunk pad missing the gicpost APSR deposit (E3): {p_i!r}")

    if gic_cells:
        code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=apsr_cell, req_cell=req_cell)
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


def verify_disasm_gicsend(data: bytes, pad_i: int, pad_b: int, pad_s: int, s1: int, s2: int,
                          gic_cells: list[int], d_cells: list[int],
                          apsr_cell: int | None = None, req_cell: int | None = None) -> dict:
    """gicview verification plus the send-site trampoline: the site must re-disassemble to a bl,
    the pad must reproduce the out[1] post and `movs r2,#1`, and it must carry the three
    device-side GIC read/store blocks into D0/D1/D2 in the documented order."""
    seen = verify_disasm(data, pad_i, pad_b, s1, s2, gic_cells,
                         apsr_cell=apsr_cell, req_cell=req_cell)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    site = [f"{i.mnemonic} {i.op_str}".strip()
            for i in md.disasm(data[SEND_SITE:SEND_SITE + 4], SEND_SITE)]
    if not (len(site) == 1 and site[0].startswith("bl ")):
        raise PatchError(f"send site 0x{SEND_SITE:x} did not re-disassemble to a bl: {site!r}")

    code_s = pad_send(pad_s, d_cells)
    p_s = [f"{i.mnemonic} {i.op_str}".strip()
           for i in md.disasm(data[pad_s:pad_s + len(code_s)], pad_s)]
    if not any(s.startswith("str r2, [r3]") for s in p_s):
        raise PatchError(f"send pad missing the reproduced out[1] post `str r2,[r3]`: {p_s!r}")
    if not any(s.startswith("movw r2, #1") for s in p_s):
        raise PatchError(f"send pad missing the reproduced `movs r2,#1` (as movw): {p_s!r}")
    if not any(s.startswith("push") for s in p_s) or not any(s.startswith("pop") for s in p_s):
        raise PatchError(f"send pad missing the register save/restore: {p_s!r}")
    for read_ca, cell in zip(GIC_SEND_READS + (GIC_SEND_RECHECK,),
                             [d_cells[0], d_cells[1], d_cells[2], d_cells[4]]):
        block = gic_read_store_block(read_ca, cell)
        if block not in code_s or block not in data[pad_s:pad_s + len(code_s)]:
            raise PatchError(f"send pad missing the GIC read/store for CA {read_ca:#x} -> cell {cell:#x}")
    for cell in (d_cells[3], d_cells[5]):
        block = _store_imm_block(GICS_MARKER, cell)
        if block not in code_s or block not in data[pad_s:pad_s + len(code_s)]:
            raise PatchError(f"send pad missing the presence marker 0x{GICS_MARKER:08x} -> cell {cell:#x}")
    n_ldr = sum(1 for s in p_s if s.startswith("ldr r1, [r1]"))
    if n_ldr != len(GIC_SEND_READS) + 1:
        raise PatchError(f"expected {len(GIC_SEND_READS) + 1} send-side GIC loads, "
                         f"disassembly shows {n_ldr}: {p_s!r}")
    if not any(s.startswith("b.w") for s in p_s):
        raise PatchError(f"send pad missing its return branch: {p_s!r}")
    cont = [f"{i.mnemonic} {i.op_str}".strip()
            for i in md.disasm(data[SEND_CONT:SEND_CONT + 4], SEND_CONT)]
    if not (len(cont) == 1 and cont[0].startswith("add.w r3, r3, #0xc8000")):
        raise PatchError(f"send continuation 0x{SEND_CONT:x} is not the expected add.w: {cont!r}")
    seen["send_site"] = site
    seen["send_pad"] = p_s
    return seen


def verify_disasm_gicpost(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int,
                          s1: int, s2: int, gic_cells: list[int], d_cells: list[int],
                          e_cells: list[int]) -> dict:
    """The gicsend verification (with the gicpost thunk-pad additions) plus the post-write pad:
    the site re-disassembles to a bl, the pad carries the request gate, the request clear, the two
    POST-write GIC read/store blocks and the re-armed sentinel, it holds no `bl` (which would
    clobber the live lr) and its tail is the `b.w` that reproduces the replaced call."""
    seen = verify_disasm_gicsend(data, pad_i, pad_b, pad_s, s1, s2, gic_cells, d_cells,
                                 apsr_cell=e_cells[3], req_cell=e_cells[2])
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    if POST_SITE != 0x87036 or data[POST_SITE:POST_SITE + 4] != bl(POST_SITE, pad_p):
        raise PatchError(f"post site {POST_SITE:#x} bytes are not the intended bl")
    site = [f"{i.mnemonic} {i.op_str}".strip()
            for i in md.disasm(data[POST_SITE:POST_SITE + 4], POST_SITE)]
    if not (len(site) == 1 and site[0].startswith("bl ")):
        raise PatchError(f"post site 0x{POST_SITE:x} did not re-disassemble to a bl: {site!r}")

    code_p = pad_post(pad_p, e_cells)
    p_p = [f"{i.mnemonic} {i.op_str}".strip()
           for i in md.disasm(data[pad_p:pad_p + len(code_p)], pad_p)]
    if not any(s.startswith("cmp r2, r1") for s in p_p):
        raise PatchError(f"post pad missing the request gate: {p_p!r}")
    if not any(s.startswith("bne") for s in p_p):
        raise PatchError(f"post pad missing the gate branch: {p_p!r}")
    if not any(s.startswith("ldr r2, [r0]") for s in p_p):
        raise PatchError(f"post pad missing the request load: {p_p!r}")
    if not any(s.startswith("str r2, [r0]") for s in p_p):
        raise PatchError(f"post pad missing the request clear: {p_p!r}")
    for read_ca, cell in zip(GICP_READS, e_cells[:2]):
        block = gic_read_store_block(read_ca, cell)
        if block not in code_p or block not in data[pad_p:pad_p + len(code_p)]:
            raise PatchError(f"post pad missing the GIC read/store for CA {read_ca:#x} -> cell {cell:#x}")
    if _store_imm_block(GICP_MARKER, e_cells[2]) not in code_p:
        raise PatchError("post pad missing the re-armed sentinel")
    if _store_ip_block(e_cells[3]) in code_p:
        raise PatchError("post pad must not write E3 (the gate pad owns it)")
    if push(PAD_SAVE) not in code_p or pop(PAD_SAVE) not in code_p:
        raise PatchError("post pad missing the register save/restore")
    if mrs_apsr(12) not in code_p or msr_apsr(12) not in code_p:
        raise PatchError("post pad missing the flag save/restore")
    if bl(pad_p, POST_CALL) in code_p:
        raise PatchError("post pad must NOT contain a bl: it would clobber the live lr")
    if code_p[-4:] != b_w(pad_p + len(code_p) - 4, POST_CALL):
        raise PatchError(f"post pad tail is not the reproduced `b.w` call: {code_p[-4:].hex()}")
    n_ldr = sum(1 for s in p_p if s.startswith("ldr r1, [r1]"))
    if n_ldr != len(GICP_READS):
        raise PatchError(f"expected {len(GICP_READS)} post-pad GIC loads, disassembly shows {n_ldr}")
    # the sample order: clear the request, then E0, then E1, then re-arm the sentinel
    i_clear = code_p.index(str_imm(2, 0, 0))
    i_e0 = code_p.index(gic_read_store_block(GICP_READS[0], e_cells[0]))
    i_e1 = code_p.index(gic_read_store_block(GICP_READS[1], e_cells[1]))
    i_sent = code_p.index(_store_imm_block(GICP_MARKER, e_cells[2]))
    if not i_clear < i_e0 < i_e1 < i_sent:
        raise PatchError("post pad order is not clear -> E0 -> E1 -> sentinel")
    seen["post_site"] = site
    seen["post_pad"] = p_p
    return seen


def make_gicsend(data: bytes, barmap: bytes, refs: set[int]):
    """gicview + a third trampoline at the firmware's own out[1] post (file 0x86F5A), whose pad
    reproduces the post and then deposits ISPENDR2/HPPIR/ISACTIVER2 into fresh cells D0..D2."""
    cells, sel = select_cells_gicsend(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    dc = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICS_NCELLS]

    need_i = len(pad_thunk(0, s1, gc))
    pad_i, len_i = find_padding(data, refs, need_i, [])
    need_b = len(pad_bringup(0, s2, gc))
    pad_b, len_b = find_padding(data, refs, need_b, [(pad_i, pad_i + len_i)])
    need_s = len(pad_send(0, dc))
    pad_s, len_s = find_padding(data, refs, need_s, [(pad_i, pad_i + len_i), (pad_b, pad_b + len_b)])

    code_i = pad_thunk(pad_i, s1, gc)
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send(pad_s, dc)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s))
    out[pad_i:pad_i + len(code_i)] = code_i
    out[pad_b:pad_b + len(code_b)] = code_b
    out[pad_s:pad_s + len(code_s)] = code_s
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    if out[SITE_THUNK:SITE_THUNK + 4] != bl(SITE_THUNK, pad_i):
        raise PatchError("internal error: the thunk site bytes are not the intended bl")
    if out[BRINGUP_SITE:BRINGUP_SITE + 4] != bl(BRINGUP_SITE, pad_b):
        raise PatchError("internal error: the bring-up site bytes are not the intended bl")
    if out[SEND_SITE:SEND_SITE + 4] != bl(SEND_SITE, pad_s):
        raise PatchError("internal error: the send site bytes are not the intended bl")

    check_original_gic_write(out)
    seen = verify_disasm_gicsend(out, pad_i, pad_b, pad_s, s1, s2, gc, dc)

    cell_records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        cell_records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(dc):
        cell_records[f"D{i}"] = cell_record(barmap, a)

    manifest = {
        "variant": "gicsend",
        "selection": sel,
        "cells": cell_records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICD_ISENABLER2": hex(GICD_ISENABLER2),
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICD_ISACTIVER2": hex(GICD_ISACTIVER2),
            "GICC_base": "0x40160100",
            "GICC_HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging)",
            "note": NOTE_GIC_MAP,
            "send_read_order": {
                "D0": {"ca": hex(GICD_ISPENDR2), "point": "send pad, after the reproduced out[1] post"},
                "D1": {"ca": hex(GICC_HPPIR), "point": "send pad, after the reproduced out[1] post"},
                "D2": {"ca": hex(GICD_ISACTIVER2), "point": "send pad, after the reproduced out[1] post"},
                "D3": {"ca": "none", "point": f"presence marker 0x{GICS_MARKER:08x}, same page as D0..D2"},
                "D4": {"ca": hex(GIC_SEND_RECHECK), "point": "send pad, a second read of the critical word, second all-zero page"},
                "D5": {"ca": "none", "point": f"presence marker 0x{GICS_MARKER:08x}, same page as D4"},
            },
            "cells_note": NOTE_GICSEND_CELLS,
            "marker_note": NOTE_GICSEND_MARKER,
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "runtime_addr": hex(pad_i + BIAS),
                      "run_length": hex(len_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "runtime_addr": hex(pad_b + BIAS),
                        "run_length": hex(len_b), "code_length": len(code_b), "code_hex": code_b.hex()},
            "send": {"file_offset": hex(pad_s), "runtime_addr": hex(pad_s + BIAS),
                     "run_length": hex(len_s), "code_length": len(code_s), "code_hex": code_s.hex()},
        },
        "patches": [
            {"kind": "trampoline-entry", "region": "enable thunk 0x86ff4", "file_offset": hex(SITE_THUNK),
             "before": data[SITE_THUNK:SITE_THUNK + 4].hex(),
             "after": bl(SITE_THUNK, pad_i).hex(), "note": NOTE_GICVIEW_I},
            {"kind": "trampoline-entry", "region": "distributor bring-up 0x6e5c-0x6ed4",
             "file_offset": hex(BRINGUP_SITE), "before": data[BRINGUP_SITE:BRINGUP_SITE + 4].hex(),
             "after": bl(BRINGUP_SITE, pad_b).hex(), "note": NOTE_GICVIEW_II},
            {"kind": "trampoline-entry", "region": "firmware out[1] post 0x86F5A (ETE bring-up 0x86E14)",
             "file_offset": hex(SEND_SITE), "before": data[SEND_SITE:SEND_SITE + 4].hex(),
             "after": bl(SEND_SITE, pad_s).hex(), "note": NOTE_GICSEND_SITE},
        ],
        "send_site": {
            "file_offset": hex(SEND_SITE),
            "runtime_addr": hex(SEND_SITE + BIAS),
            "replaced_bytes": data[SEND_SITE:SEND_SITE + 4].hex(),
            "replaced_instructions": ["str r2, [r3]  (out[1] CA 0x40039014 <- 4 = bit 2)",
                                      "movs r2, #1"],
            "continuation_file_offset": hex(SEND_CONT),
            "why_this_site": (
                "the out[1] (CA 0x40039014) writers in this image are exactly four (phase38 "
                "open-gaps-static-attempt.md section 1.1, address-provenance scan): ctx init "
                "(*out[1]=0, file 0x978c), the inline platform-ready pair (file 0x86F5A/0x86F66, "
                "bit 2), d2h_notify (file 0x861B0, ids 5/6/8) and its IRQ-0x4E flush (file "
                "0x86156).  The brief's frozen params post no SR descriptor, so the id-6 "
                "d2h_notify post cannot occur in this boot; the observed out[1] = 0x00000004 "
                "(bit 2) can only come from the inline store at 0x86F5A, which is therefore "
                "proven on the executed path by the register value itself."
            ),
            "id_6_note": (
                "the id-6 (bit 6 = 0x40) post of the takeover dialogue is the OTHER writer: "
                "d2h_notify @ file 0x86170, store at 0x861B0, called with r1=6 from file 0x86224 "
                "(docs/phase38 section 2.1 site 2).  It is gated on the device-side `armed` flag "
                "(obj+0xb4) and needs a committed ring descriptor, so it is NOT sampled here; "
                "see the interp's bounds."
            ),
            "timing": NOTE_GICSEND_TIMING,
        },
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


def make_gicpost(data: bytes, barmap: bytes, refs: set[int]):
    """gicsend + a fourth trampoline at file 0x87036 (the post-write pad, E0/E1/E2) plus the gate
    pad's E2/E3 deposits: the APSR the conditional store executes with, and the post-write
    readback of the word that store writes."""
    cells, sel = select_cells_gicpost(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    dc = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICS_NCELLS]
    ec = cells[2 + GICV_NCELLS + GICS_NCELLS:2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS]
    if len(ec) != GICP_NCELLS:
        raise PatchError("internal error: E0..E3 were not selected")

    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    pad_i, len_i = find_padding(data, refs, need_i, [])
    need_b = len(pad_bringup(0, s2, gc))
    pad_b, len_b = find_padding(data, refs, need_b, [(pad_i, pad_i + len_i)])
    need_s = len(pad_send(0, dc))
    pad_s, len_s = find_padding(data, refs, need_s, [(pad_i, pad_i + len_i), (pad_b, pad_b + len_b)])
    need_p = len(pad_post(0, ec))
    pad_p, len_p = find_padding(data, refs, need_p, [(pad_i, pad_i + len_i),
                                                     (pad_b, pad_b + len_b), (pad_s, pad_s + len_s)])

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send(pad_s, dc)
    code_p = pad_post(pad_p, ec)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p))
    out[pad_i:pad_i + len(code_i)] = code_i
    out[pad_b:pad_b + len(code_b)] = code_b
    out[pad_s:pad_s + len(code_s)] = code_s
    out[pad_p:pad_p + len(code_p)] = code_p
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    for site, pad in ((SITE_THUNK, pad_i), (BRINGUP_SITE, pad_b), (SEND_SITE, pad_s),
                      (POST_SITE, pad_p)):
        if out[site:site + 4] != bl(site, pad):
            raise PatchError(f"internal error: site {site:#x} bytes are not the intended bl")
    if out[0x8702C:0x87030] != data[0x8702C:0x87030]:
        raise PatchError("internal error: the original ISENABLER store at file 0x8702c was altered")
    if out[0x87030:0x87036] != data[0x87030:0x87036]:
        raise PatchError("internal error: the itet block 0x87030..0x87035 was altered")

    check_original_gic_write(out)
    seen = verify_disasm_gicpost(out, pad_i, pad_b, pad_s, pad_p, s1, s2, gc, dc, ec)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(dc):
        records[f"D{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)

    manifest = {
        "variant": "gicpost",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICD_ISENABLER2": hex(GICD_ISENABLER2),
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICD_ISACTIVER2": hex(GICD_ISACTIVER2),
            "GICC_base": "0x40160100",
            "GICC_HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging)",
            "note": NOTE_GIC_MAP,
            "read_order": {
                "C0": {"ca": hex(GICD_ISENABLER2), "point": "gate pad (file 0x87024), PRE-write"},
                "C1": {"ca": hex(GICD_ISPENDR2), "point": "gate pad, PRE-write"},
                "C2": {"ca": hex(GICC_HPPIR), "point": "gate pad, PRE-write"},
                "C3": {"ca": hex(GICD_ISPENDR2), "point": "bring-up end"},
                "C4": {"ca": hex(GICD_ISACTIVER2), "point": "bring-up end"},
                "C5": {"ca": hex(GICC_HPPIR), "point": "bring-up end"},
                "D0": {"ca": hex(GICD_ISPENDR2), "point": "send pad, after the out[1] post"},
                "D1": {"ca": hex(GICC_HPPIR), "point": "send pad, after the out[1] post"},
                "D2": {"ca": hex(GICD_ISACTIVER2), "point": "send pad, after the out[1] post"},
                "D3": {"ca": "none", "point": f"presence marker 0x{GICS_MARKER:08x} (send pad)"},
                "D4": {"ca": hex(GIC_SEND_RECHECK), "point": "send pad, second read, second all-zero page"},
                "D5": {"ca": "none", "point": f"presence marker 0x{GICS_MARKER:08x} (send pad)"},
                "E0": {"ca": hex(GICD_ISENABLER2), "point": "post-write pad (file 0x87036), AFTER the store"},
                "E1": {"ca": hex(GICD_ISPENDR2), "point": "post-write pad, AFTER the store"},
                "E2": {"ca": "none", "point": f"request 0x{GICP_REQUEST:08x} (gate pad) / sentinel "
                                                       f"0x{GICP_MARKER:08x} (post pad)"},
                "E3": {"ca": "none", "point": "the APSR the gate pad captured (mrs ip,apsr at file "
                                                    "0x87024) and restored before the store at 0x8702c"},
            },
            "cells_note": NOTE_GICSEND_CELLS,
            "marker_note": NOTE_GICSEND_MARKER,
            "e_note": NOTE_GICPOST_E,
        },
        "classification": {
            "instrument": "E0 is the LATCHED ISENABLER2 word 2 read a few instructions after the "
                           "conditional store; E3 is the APSR the same pass executed with.  E2 proves "
                           "the sample belongs to an id-0x4c-gated pass.",
            "E0_bit12_set": "the conditional store LANDED (its LO condition held) - the silence is "
                            "downstream of the write, and the store-skipped root cause is excluded",
            "E0_bit12_clear_E3_lo_false": "THE STORE WAS SKIPPED - the enable never happens in a "
                                          "takeover boot (ROOT CAUSE)",
            "E0_bit12_clear_E3_lo_true": "the store executed but did not take (register anomaly, "
                                         "its own finding)",
            "E3_decode": "APSR bit 31 = N, 30 = Z, 29 = C, 28 = V; LO held iff C == 0 and Z == 0",
            "E2_states": {hex(GICP_MARKER): "the post pad sampled",
                          hex(GICP_REQUEST): "the request was set and never consumed - the post pad "
                                             "did not run, so E0/E1 zeros are void (say so, do "
                                             "not interpret them)",
                          "0x0": "no id-0x4c enable pass"},
            "bounds": "one-shot latched sample, not a timing window; E1 is the pending state at the "
                      "same instant only; the gate is the bitmap 0x1000, which within the thunk's "
                      "valid id range 0x10..0x5f is id 0x4c or id 0x2c (id 0x2c would store to word "
                      "1, CA 0x40161104, which is not read here - the static enable table gives "
                      "both ids the same 05 01 descriptor shape, so the id is inferred from the "
                      "phase47 enable list and the S1+4 destination constant, not proven here)",
        },
        "post_site": {
            "file_offset": hex(POST_SITE),
            "runtime_addr": hex(POST_SITE + BIAS),
            "replaced_bytes": data[POST_SITE:POST_SITE + 4].hex(),
            "replaced_instruction": "bl #0xbdf50",
            "why_this_site": (
                "the first instruction boundary after the conditional store at file 0x8702c that is "
                "outside the `itet lo` block (0x87030 is its hs slot, 0x87034 its lo slot: a bl "
                "there would be unpredictable) and runs unconditionally"
            ),
            "reproduction": (
                "the pad contains no `bl`, so lr still holds 0x8703a - the return address the "
                "replaced instruction itself installed and the value the callee (file 0xbdf50, "
                "`mov r2, lr` at 0xbdf54) passes on; the pad ends in `b.w 0xbdf50`, so the callee "
                "returns to the identical instruction (file 0x8703a) it would have reached unpatched"
            ),
            "continuation_file_offset": hex(POST_CONT),
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "runtime_addr": hex(pad_i + BIAS),
                      "run_length": hex(len_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "runtime_addr": hex(pad_b + BIAS),
                        "run_length": hex(len_b), "code_length": len(code_b), "code_hex": code_b.hex()},
            "send": {"file_offset": hex(pad_s), "runtime_addr": hex(pad_s + BIAS),
                     "run_length": hex(len_s), "code_length": len(code_s), "code_hex": code_s.hex()},
            "post": {"file_offset": hex(pad_p), "runtime_addr": hex(pad_p + BIAS),
                     "run_length": hex(len_p), "code_length": len(code_p), "code_hex": code_p.hex()},
        },
        "patches": [
            {"kind": "trampoline-entry", "region": "enable thunk 0x86ff4", "file_offset": hex(SITE_THUNK),
             "before": data[SITE_THUNK:SITE_THUNK + 4].hex(),
             "after": bl(SITE_THUNK, pad_i).hex(), "note": NOTE_GICVIEW_I},
            {"kind": "trampoline-entry", "region": "distributor bring-up 0x6e5c-0x6ed4",
             "file_offset": hex(BRINGUP_SITE), "before": data[BRINGUP_SITE:BRINGUP_SITE + 4].hex(),
             "after": bl(BRINGUP_SITE, pad_b).hex(), "note": NOTE_GICVIEW_II},
            {"kind": "trampoline-entry", "region": "firmware out[1] post 0x86F5A (ETE bring-up 0x86E14)",
             "file_offset": hex(SEND_SITE), "before": data[SEND_SITE:SEND_SITE + 4].hex(),
             "after": bl(SEND_SITE, pad_s).hex(), "note": NOTE_GICSEND_SITE},
            {"kind": "trampoline-entry", "region": "enable-thunk post-store boundary 0x87036",
             "file_offset": hex(POST_SITE), "before": data[POST_SITE:POST_SITE + 4].hex(),
             "after": bl(POST_SITE, pad_p).hex(),
             "note": "the firmware's own `bl #0xbdf50` at the first post-store boundary outside "
                     "the `itet lo` block; the pad samples ISENABLER2/ISPENDR2 post-write (E0/E1) "
                     "and reproduces the call as a `b.w` with lr untouched"},
        ],
        "preserved": {
            "original_gic_write": {
                "file_offset": "0x8702c",
                "instruction": "strlo.w r4, [r3, r2, lsl #2]",
                "ca": "0x40161100 + (id/32)*4",
                "verified_present": True,
                "bytes_identical": out[0x8702C:0x87030] == data[0x8702C:0x87030],
            },
            "itet_block": {"file_offset": "0x8702a..0x87035",
                           "bytes_identical": out[0x87030:0x87036] == data[0x87030:0x87036]},
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
    one("strw_ip", str_imm_w(12, 0, 0), "str.w ip, [r0]")
    one("str2", str_imm(2, 0, 0), "str r2, [r0]")
    one("movw0", movw(2, 0), "movw r2, #0")
    one("movwreq", movw(1, GICP_REQUEST & 0xFFFF), "movw r1, #0xe2e2")
    one("movtreq", movt(1, GICP_REQUEST >> 16), "movt r1, #0xe2e2")
    one("cmp21", cmp_reg(2, 1), "cmp r2, r1")
    one("bwcall", b_w(0x1000, 0x800000), "b.w #0x800000", addr=0x1000)


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
    assert md5(gic) == GICVIEW_MD5, f"gicview output changed: {md5(gic)} != {GICVIEW_MD5}"
    assert not (set(range(pad_i_g, pad_i_g + 64)) & set(range(pad_b_g, pad_b_g + 64))), "the gicview pads overlap"

    # ---- gicsend: gicview + a third trampoline at the firmware's own out[1] post
    gsen, gsm = make_gicsend(data, barmap, refs)
    assert len(gsen) == len(data), "gicsend changed the size"
    gsen2, gsm2 = make_gicsend(data, barmap, refs)
    assert gsen == gsen2, "gicsend patch is not deterministic"
    assert json.dumps(gsm, sort_keys=True) == json.dumps(gsm2, sort_keys=True), "gicsend manifest not deterministic"

    # S1/S2/C0..C5 must be the gicview cells, so the variants stay directly comparable
    for name in ["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]:
        assert gsm["cells"][name]["addr"] == gm["cells"][name]["addr"], f"gicsend moved cell {name}"
    ds = [int(gsm["cells"][f"D{i}"]["addr"], 16) for i in range(GICS_NCELLS)]
    all_cells = [s1, s2] + gc + ds
    assert len(set(all_cells)) == len(all_cells), "gicsend cells are not all distinct"
    assert all(ds[i + 1] - ds[i] >= 8 for i in range(GICS_NCELLS - 1)), "D cells are not >= 8 bytes apart"
    assert all(gsm["cells"][f"D{i}"]["barmap_value"] == "0x0" for i in range(GICS_NCELLS)), \
        "a D cell baseline is not zero"
    assert all(c not in S_CELL_EXCLUDE for c in ds), "a D cell is inside an excluded table"
    # the D cells come from all-zero 4 KB pages (the iteration-2 rule) - the fix for the first boot
    zp = [int(p, 16) for p in gsm["selection"]["all_zero_pages"]]
    assert len(zp) >= 2, "gicsend did not find two all-zero pages"
    p1s, p2s = int(gsm["selection"]["d_page_1"], 16), int(gsm["selection"]["d_page_2"], 16)
    assert p1s == zp[0] and p2s == zp[1], "gicsend picked unexpected all-zero pages"
    assert all(p1s <= c < p1s + 0x1000 for c in ds[:4]), "D0..D3 are not in page 1"
    assert all(p2s <= c < p2s + 0x1000 for c in ds[4:]), "D4..D5 are not in page 2"
    pagemap = barmap
    for p in (p1s, p2s):
        assert all(word_at(pagemap, x) == 0 and word_at(pagemap, ALIAS_OFF + x) == 0
                   for x in range(p, p + 0x1000, 4)), f"page {p:#x} is not all-zero in the barmap"
    assert gsm["gic_map"]["send_read_order"]["D0"]["ca"] == hex(GICD_ISPENDR2) == "0x40161208"
    assert gsm["gic_map"]["send_read_order"]["D1"]["ca"] == hex(GICC_HPPIR) == "0x40160118"
    assert gsm["gic_map"]["send_read_order"]["D2"]["ca"] == hex(GICD_ISACTIVER2) == "0x40161308"
    assert gsm["gic_map"]["send_read_order"]["D4"]["ca"] == hex(GIC_SEND_RECHECK) == "0x40161208"
    assert gsm["gic_map"]["send_read_order"]["D3"]["ca"] == "none"
    assert gsm["gic_map"]["send_read_order"]["D5"]["ca"] == "none"

    # the site: the replaced bytes are exactly the firmware's out[1] post pair, and the
    # continuation (`add.w r3,r3,#0xc8000`) is untouched (the pad's own selftest asserts it too)
    assert SEND_SITE == 0x86F5A and SEND_CONT == 0x86F5E
    assert data[SEND_SITE:SEND_SITE + 4] == bytes.fromhex("1a600122"), "the send site is not str r2,[r3]+movs r2,#1"
    assert gsm["send_site"]["replaced_bytes"] == data[SEND_SITE:SEND_SITE + 4].hex()

    pad_i_s = int(gsm["padding"]["thunk"]["file_offset"], 16)
    pad_b_s = int(gsm["padding"]["bringup"]["file_offset"], 16)
    pad_d_s = int(gsm["padding"]["send"]["file_offset"], 16)
    code_i_s = pad_thunk(pad_i_s, s1, gc)
    code_b_s = pad_bringup(pad_b_s, s2, gc)
    code_d_s = pad_send(pad_d_s, ds)

    # regression: the two gicview trampolines did not move and did not change a byte
    assert pad_i_s == pad_i_g and pad_b_s == pad_b_g, "gicsend moved a gicview pad"
    assert code_i_s == code_i_g and code_b_s == code_b_g, "gicsend changed a gicview pad"
    assert gsen[pad_i_s:pad_i_s + len(code_i_s)] == gic[pad_i_g:pad_i_g + len(code_i_g)], "gicsend thunk pad differs from gicview"
    assert gsen[pad_b_s:pad_b_s + len(code_b_s)] == gic[pad_b_g:pad_b_g + len(code_b_g)], "gicsend bring-up pad differs from gicview"

    # liveness of the send pad itself: the four reads, the two markers, the reproduced post, the save/restore
    for read_ca, cell in zip(GIC_SEND_READS + (GIC_SEND_RECHECK,), [ds[0], ds[1], ds[2], ds[4]]):
        assert gic_read_store_block(read_ca, cell) in code_d_s, f"send pad missing CA {read_ca:#x}"
    for cell in (ds[3], ds[5]):
        assert _store_imm_block(GICS_MARKER, cell) in code_d_s, f"send pad missing the marker for {cell:#x}"
    assert str_imm(2, 3, 0) in code_d_s, "send pad missing the reproduced out[1] store"
    assert movw(2, 1) in code_d_s, "send pad missing the reproduced movs r2,#1"
    assert push(PAD_SAVE) in code_d_s and pop(PAD_SAVE) in code_d_s, "send pad missing the register save/restore"
    assert b_w(pad_d_s + len(code_d_s) - 4, SEND_CONT) == code_d_s[-4:], "send pad return branch is wrong"

    allowed_s = set(range(SITE_THUNK, SITE_THUNK + 4)) | set(range(BRINGUP_SITE, BRINGUP_SITE + 4))
    allowed_s |= set(range(SEND_SITE, SEND_SITE + 4))
    allowed_s |= set(range(pad_i_s, pad_i_s + len(code_i_s)))
    allowed_s |= set(range(pad_b_s, pad_b_s + len(code_b_s)))
    allowed_s |= set(range(pad_d_s, pad_d_s + len(code_d_s)))
    changed_s = [i for i in range(len(data)) if gsen[i] != data[i]]
    assert changed_s and all(c in allowed_s for c in changed_s), "gicsend changed bytes outside its regions"
    assert not (set(range(pad_i_s, pad_i_s + 64)) & set(range(pad_d_s, pad_d_s + 64))), "the send pad overlaps the thunk pad"
    assert not (set(range(pad_b_s, pad_b_s + 64)) & set(range(pad_d_s, pad_d_s + 64))), "the send pad overlaps the bring-up pad"
    assert gsen[SEND_CONT:SEND_CONT + 0x22] == data[SEND_CONT:SEND_CONT + 0x22], \
        "gicsend altered the byte stream after the send site"
    check_original_gic_write(gsen)
    verify_disasm_gicsend(gsen, pad_i_s, pad_b_s, pad_d_s, s1, s2, gc, ds)

    # gicsend must differ from gicview ONLY at the send site + the send pad
    diff_gv = [i for i in range(len(data)) if gsen[i] != gic[i]]
    assert diff_gv and all((SEND_SITE <= c < SEND_SITE + 4) or (pad_d_s <= c < pad_d_s + len(code_d_s))
                           for c in diff_gv), "gicsend differs from gicview outside the send site/pad"

    assert md5(gsen) == GICSEND_MD5, f"gicsend output changed: {md5(gsen)} != {GICSEND_MD5}"

    # ---- gicpost: gicsend + the post-write pad (E0/E1/E2) and the gate pad's E2/E3 deposits
    gp, gpm = make_gicpost(data, barmap, refs)
    assert len(gp) == len(data), "gicpost changed the size"
    gp2, gpm2 = make_gicpost(data, barmap, refs)
    assert gp == gp2, "gicpost patch is not deterministic"
    assert json.dumps(gpm, sort_keys=True) == json.dumps(gpm2, sort_keys=True), \
        "gicpost manifest is not deterministic"
    for nm in ["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)] + [f"D{i}" for i in range(GICS_NCELLS)]:
        assert gpm["cells"][nm]["addr"] == gsm["cells"][nm]["addr"], f"gicpost moved cell {nm}"
    ec = [int(gpm["cells"][f"E{i}"]["addr"], 16) for i in range(GICP_NCELLS)]
    every = [s1, s2] + gc + ds + ec
    assert len(set(every)) == len(every), "gicpost cells are not all distinct"
    assert all(gpm["cells"][f"E{i}"]["barmap_value"] == "0x0" for i in range(GICP_NCELLS)), \
        "an E cell baseline is not zero at BAR0"
    assert all(gpm["cells"][f"E{i}"]["barmap_alias_value"] == "0x0" for i in range(GICP_NCELLS)), \
        "an E cell baseline is not zero at the alias"
    assert all(c not in S_CELL_EXCLUDE for c in ec), "an E cell is inside an excluded table"
    assert all(c < GICP_E_HI for c in ec), "an E cell sits at or above the aliasing boundary"
    assert len({c & ~0xFFF for c in ec}) == 1, "the E cells are not all in one page"
    assert gpm["selection"]["e_pages"] == [hex(ec[0] & ~0xFFF)], "the e_pages record is wrong"
    assert gpm["selection"]["all_zero_pages_below_boundary"] == [], \
        "the barmap grew a sub-boundary all-zero page - the E selection rule needs revisiting"
    assert len(gpm["selection"]["e_band_zero_words"]) == 13, "the sub-boundary zero-word count moved"

    # the post site is the firmware's own bl, reproduced as a b.w that leaves lr alone
    assert POST_SITE == 0x87036 and data[POST_SITE:POST_SITE + 4] == bytes.fromhex("36f08bff"), \
        "the post site is not bl #0xbdf50"
    pad_i_p = int(gpm["padding"]["thunk"]["file_offset"], 16)
    pad_b_p = int(gpm["padding"]["bringup"]["file_offset"], 16)
    pad_s_p = int(gpm["padding"]["send"]["file_offset"], 16)
    pad_p_p = int(gpm["padding"]["post"]["file_offset"], 16)
    assert gp[POST_SITE:POST_SITE + 4] == bl(POST_SITE, pad_p_p), "the post site is not the intended bl"
    assert gp[0x8702C:0x87030] == data[0x8702C:0x87030], "gicpost altered the original ISENABLER store"
    assert gp[0x87030:0x87036] == data[0x87030:0x87036], "gicpost altered the itet block"
    check_original_gic_write(gp)
    verify_disasm_gicpost(gp, pad_i_p, pad_b_p, pad_s_p, pad_p_p, s1, s2, gc, ds, ec)

    # the gicpost pads: gicsend's pads plus the E deposits; bring-up and send stay byte-identical
    code_i_p = pad_thunk(pad_i_p, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_p_p = pad_post(pad_p_p, ec)
    assert gp[pad_i_p:pad_i_p + len(code_i_p)] == code_i_p, "the gicpost thunk pad is not in the image"
    assert gp[pad_p_p:pad_p_p + len(code_p_p)] == code_p_p, "the gicpost post pad is not in the image"
    assert _store_imm_block(GICP_REQUEST, ec[2]) in code_i_p, "thunk pad missing the E2 request"
    assert _store_ip_block(ec[3]) in code_i_p, "thunk pad missing the E3 APSR deposit"
    assert code_i_p[:12] == bytes.fromhex(gsm["padding"]["thunk"]["code_hex"])[:12], \
        "the gicpost thunk pad head diverged from gicsend"
    assert gpm["padding"]["bringup"]["code_hex"] == gsm["padding"]["bringup"]["code_hex"], \
        "the gicpost bring-up pad differs from gicsend"
    assert gpm["padding"]["send"]["code_hex"] == gsm["padding"]["send"]["code_hex"], \
        "the gicpost send pad differs from gicsend"
    for key in ("thunk", "bringup", "send"):
        assert gpm["padding"][key]["file_offset"] == gsm["padding"][key]["file_offset"], \
            f"gicpost moved the {key} pad"

    # gicpost must differ from gicsend only at the post site and the two pads it touches
    diff_gs = [i for i in range(len(data)) if gp[i] != gsen[i]]
    ok_diff = (set(range(POST_SITE, POST_SITE + 4)) | set(range(pad_p_p, pad_p_p + len(code_p_p)))
               | set(range(pad_i_p, pad_i_p + len(code_i_p))))
    assert diff_gs and all(c in ok_diff for c in diff_gs), \
        "gicpost differs from gicsend outside its own regions"

    # changed bytes confined to the four sites + four pads
    allowed_p = set()
    for site in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE):
        allowed_p |= set(range(site, site + 4))
    for key in ("thunk", "bringup", "send", "post"):
        off = int(gpm["padding"][key]["file_offset"], 16)
        allowed_p |= set(range(off, off + int(gpm["padding"][key]["code_length"])))
    changed_p = [i for i in range(len(data)) if gp[i] != data[i]]
    assert changed_p and all(c in allowed_p for c in changed_p), \
        "gicpost changed bytes outside its regions"
    assert not (set(range(pad_i_p, pad_i_p + 64)) & set(range(pad_p_p, pad_p_p + 64))), \
        "the gicpost post pad overlaps the thunk pad"
    assert gpm["post_site"]["file_offset"] == hex(POST_SITE) == "0x87036"
    assert gpm["classification"]["E3_decode"].startswith("APSR bit 31 = N")

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
    print(f"  gicsend cells     : " + " ".join(f"D{i}={gsm['cells'][f'D{i}']['addr']}" for i in range(GICS_NCELLS))
          + f" (send pad @ file {gsm['padding']['send']['file_offset']}, site {hex(SEND_SITE)})")
    print(f"  gicsend sends     : D0/D1/D2={[hex(x) for x in GIC_SEND_READS]}")
    print(f"  gicsend md5       : {md5(gsen)}")
    print(f"  gicpost cells     : " + " ".join(f"E{i}={gpm['cells'][f'E{i}']['addr']}"
                                               for i in range(GICP_NCELLS))
          + f" (post pad @ file {gpm['padding']['post']['file_offset']}, site {hex(POST_SITE)})")
    print(f"  gicpost post reads: E0/E1={[hex(x) for x in GICP_READS]} E3=APSR from the gate pad")
    print(f"  gicpost md5       : {md5(gp)}")
    return 0


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="patch_fw_scratch.py", description=__doc__.splitlines()[0])
    ap.add_argument("--fw", default="build/tmp/FIRMWARE.bin", help="input blob (READ-ONLY)")
    ap.add_argument("--barmap", default="opensource/build/register-dumps/barmap_ep0_bar0.bin",
                    help="normal-op BAR0 baseline used for S1/S2 selection")
    ap.add_argument("--out", help="output blob (never the input)")
    ap.add_argument("--variant", choices=("probe", "scratch", "gicview", "gicsend", "gicpost"),
                    help="probe: one non-executed byte flip; scratch: the two instrumentation "
                         "stores; gicview: scratch + six device-side GIC reads into cells C0..C5; "
                         "gicsend: gicview + a third trampoline at the firmware's out[1] message "
                         "post (file 0x86F5A) reading ISPENDR2/HPPIR/ISACTIVER2 into cells D0..D2; "
                         "gicpost: gicsend + a fourth trampoline at file 0x87036 (the first "
                         "boundary after the conditional enable store) reading ISENABLER2 back "
                         "POST-write into E0 and ISPENDR2 into E1, with the enable-gate pad's "
                         "APSR deposit in E3")
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
                         else make_gicview(data, barmap, refs) if args.variant == "gicview"
                         else make_gicsend(data, barmap, refs) if args.variant == "gicsend"
                         else make_gicpost(data, barmap, refs))
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
