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
  gicmask  - gicpost + the DELIVERY-CONFIGURATION sample at the firmware's own post: the send-site
             pad ALSO reads eight 4-byte-aligned device registers into fresh WRAM cells F0..F7 -
             the CPU interface's own enable/mask (GICC_CTLR/PMR), the distributor's per-id
             target/priority/config for id 0x4c (ITARGETSR/IPRIORITYR/ICFGR), and the glue's
             mask/raw/masked status (ctrl-rb +0x2e8/+0x2e4/+0x2ec) - and then arms a sentinel F8
             in its first page and F9 in its second.  The enable-gate pad additionally deposits
             the request word GICM_REQUEST into F9 on its id-0x4c-gated path, so F9 is the
             gicpost handshake moved to the send pad and doubles as an ORDERING witness: F9 =
             sentinel means a post ran AFTER the id-0x4c enable pass, F9 = request means the
             enable pass came last, F9 = 0 means no id-0x4c enable pass happened.  Every address
             is re-derived from the image before use (see the gicmask constants below).
  gicking  - gicmask + the H2D RING and the polarity discriminator, plus the GICD_IGROUPR read.  The
             send pad (the firmware's own out[1] post, file 0x86F5A) first drives the glue mask
             (CA 0x400392e8 <= 0x21, bit 0 MASKED + bit 5 held), THEN rings the H2D doorbell
             (CA 0x400392d4 <= 0x1, bit 0 - ring.md's fallback actor, placed immediately before
             the GIC sample), then samples the eight delivery registers (D0..D5/F0..F9, as gicmask)
             - F5/F6/F7 are therefore the MASKED post-ring glue mask/raw/status - then restores the
             vendor-live open mask (0x20) and reads the control group G0..G2 (status with the mask
             open, mask readback, GICD_IGROUPR word 2 for id 0x4c = CA 0x40161088) with the page
             sentinel G3.  One boot carries the three checks the reports specify: the ring, the glue
             raw/status across it, and the polarity discriminator (record model: raw rises while the
             masked status stays 0, then status rises once the mask opens).  NEVER writes
             0x400392f0 (intr-clear); NEVER reads 0x4016010c (acknowledging IAR) or 0x10161000.
  gicunmask - gicpost's S/C/E instrument with the gicking pads as the base, but the send pad rings
             the H2D doorbell with the glue mask OPEN (the documented vendor value 0x20) and samples
             the post-unmask GIC state immediately: H0 = GICD_ISPENDR2 word 2 (THE decisive read),
             H1 = GICC HPPIR, H2 = GICD_ISACTIVER2 word 2, H3 = glue raw, H4 = glue post-mask
             status, plus H5 = ISPENDR2 re-read at the NEXT send-site visit and one presence
             sentinel per used page.  This is the direct follow-up to gicking's open step R2: gicking
             rang the doorbell with the line deliberately MASKED, so its post-ring ISPENDR2 sample
             was confounded; gicunmask decides the ring->GIC step in one boot.  NEVER writes
             0x400392f0; NEVER reads 0x4016010c or 0x10161000.
  trigring - trigger.md section 3's candidate: the send pad performs the ring the FIRMWARE never
             issues, at the firmware's OWN natural post (file 0x86F5A, between the reproduced
             out[1] `*0x40039014 = 4` and the natural D2H notify at 0x86F62), so the firmware's own
             H2D dispatcher (file 0x818AC) is the consumer.  trigger.md found NO firmware write
             site that can ring CA 0x400392d4 (the image holds exactly one doorbell store, the
             dispatcher's own re-arm `str r1,[r2]` with r1 = 8 = bit 3, at file 0x818C4 - not the
             H2D ring), so the task's fallback applies and the pad writes CA 0x400392d4 <= 0x1
             directly - arithmetically the trigger.md sequence `str rX,[r3 + 0x2C0]`, r3 =
             0x40039014, rX = 1 - with the glue mask OPEN (0x20) across the ring.  What makes it
             different from gicunmask: it takes the PRE-ring and POST-ring samples in the SAME
             visit with the mask already open, so the ONLY difference between T0..T3 and T4..T7 is
             the ring.  T0..T3 = ISPENDR2 word 2 / HPPIR / glue raw / glue status PRE-ring;
             T4..T7 = the same four POST-ring; TS1/TS2 = one presence sentinel per used page.  The
             thunk/bring-up/post pads are gicpost's, so S1/S2/C0..C5/E0..E3 keep their addresses.
             NEVER writes 0x400392f0; NEVER writes the masked word 0x21; NEVER reads 0x4016010c or
             0x10161000.
  trignat  - trigger2.md section 3: the natural-post ring with the device-dispatcher consumption
             witness.  Pad A at the firmware's OWN natural post (file 0x86F5A) takes the next-visit
             entry reads of out[0]/out[1] (A_E0/A_E1), reproduces the out[1] post, opens the glue
             mask (0x400392e8 <= 0x20), performs the H2D submission out[0] <= 8 (the store
             `pcie_msg_send` makes - the load-bearing correction to trigger.md section 3: the post
             writes out[1], not the pending bitmap the dispatcher reads), samples A_S0..A_S2
             PRE-ring, RINGS the H2D doorbell (0x400392d4 <= 0x1, once, never 8), samples
             A_S3..A_S8 POST-ring (out[0] / out[1] / ISPENDR2 / HPPIR / glue raw / glue status) and
             arms the page sentinels A_P1/A_P2.  Pad B at the announce routine's exit (file 0x86F7E,
             after the 0xcece handshake wait) reads the device-dispatcher consumption witnesses
             B_D0 (out[0] = 0, where the pad had stored 8) and B_D2 (ISPENDR2 word 2 bit 12 CLEAR =
             the id-0x4c interrupt was taken), plus B_D1/B_D3, and arms B_P3.  The thunk/bring-up/
             post pads are gicpost's, so S1/S2/C0..C5/E0..E3 keep their addresses.  Branch table
             (trigger2.md section 4): TRIGNAT-COMPLETE / RING-PENDING-NOT-TAKEN / GLUE-ONLY /
             NOTHING.  NEVER writes 0x400392f0; NEVER writes 0x21; NEVER reads 0x4016010c or
             0x10161000.
  trigcons - padb.md section 3 option (a): trignat with Pad B MOVED from the announce routine's
             exit (file 0x86F7E, behind the `*(0x4000010C) == 0xcece` handshake wait) to the
             wait's OWN instruction `movw r3,#0xcece` at file 0x86F74 - immediately before the
             loop head 0x86F78, so the pad is guaranteed to RUN (the salvage proved the wait never
             completes this boot, so trignat's Pad B never ran).  Pad B takes the same four
             consumption witnesses B_D0..B_D3 + the B_P3 sentinel, then RE-EMITS the replaced
             `movw r3,#0xcece` and branches to the loop head 0x86F78, so the loop's `cmp r2,r3`
             still sees 0xcece.  Pad A, the thunk/bring-up/post pads and every cell are byte-
             identical to trignat's.  Because the read is now PRE-wait the expected row is
             RING-PENDING-NOT-TAKEN (B_D0 = 8, B_D2 bit 12 SET) - the residual gate is named as the
             CPU-interface take/enable, past the wire.  NEVER writes 0x400392f0; NEVER writes 0x21;
             NEVER reads 0x4016010c or 0x10161000.

S1/S2 (and the gicview/gicsend C*/D* cells) are chosen by rule from barmap_ep0_bar0.bin: a
4-byte aligned firmware runtime address whose 4-byte word is 0x00000000 at BAR0 offset ==
addr AND at the ACP alias BAR0 0x6b8000+addr, outside the four named tables, each cell at
least 8 bytes from the previous one.

The input blob is only ever read; every artifact is written under --out.

usage:
  patch_fw_scratch.py --fw <FIRMWARE.bin> --out <variant.bin>
                      --variant probe|scratch|gicview|gicsend|gicpost|gicmask|gicking|gicunmask|trigring|trignat|trigcons
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
GICPOST_MD5 = "a4e69d74c172d856dd0e336a64482fbd"   # frozen gicpost-variant output (selftest regression)
GICMASK_MD5 = "2d354bd297270d6a64056bf2fc663dc2"   # frozen gicmask-variant output (selftest regression)
GICKING_MD5 = "0f2e431f8e32c040b8ad7e7001f8ab57"   # frozen gicking-variant output (selftest regression)
GICUNMASK_MD5 = "a68d5fed68b3015ab97c63ca7a394c28"  # frozen gicunmask-variant output (selftest regression)
TRIGRING_MD5 = "0769eed122c0506d3afca6b5a8bd8ae9"             # frozen trigring-variant output (selftest regression)
TRIGNAT_MD5 = "845188343f70cff9de29e77aea464021"             # frozen trignat-variant output (selftest regression)
TRIGCONS_MD5 = "5fb51acd68c62699435d2e1fd823d900"             # frozen trigcons-variant output (selftest regression)
INTA_MD5 = "bcf14dbeefe45bcfce8df279c06776bd"                 # frozen inta-variant output (selftest regression)
INTA2_MD5 = "545e77a5b12b4e0da8a6923eea29672c"                # frozen inta2-variant output (selftest regression)
INTA3_MD5 = "eee1f67370b56eca42316f6eeb490c45"              # frozen inta3-variant output (selftest regression)
TAKE1_MD5 = "0c681650de28488ab75fb5755684f0c7"              # frozen take1-variant output (selftest regression)
# ^ take1 = inta3 + the fwprobe.md `vec` canary/CPSR/counter pads + the giccpu.md cell set; the
#   value is pinned by the selftest and re-derived from the two byte-identical regenerations.
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

# ---- gicmask: the DELIVERY-CONFIGURATION sample (variant "gicmask") --------------------------
# The enable is proven taken (gicpost E0 = 0x1001) and the 0x4c line is silent at the enable instant
# and at the firmware's own post while the same ISPENDR2 word carries another line, so the remaining
# question is WHERE the delivery breaks.  This variant samples the DELIVERY CONFIGURATION - the CPU
# interface's own enable/mask, the distributor's per-id target/priority/config, and the glue's
# mask/raw/masked status - device-side, at the firmware's own post (the send-site trampoline, which
# runs at every post).
#
# EVERY ADDRESS WAS RE-DERIVED FROM THE IMAGE BEFORE USE (the gicview map correction is precedent;
# the manifest's gic_map.verification carries the anchoring instruction/literal for each one):
#   F0 -> CA 0x40160100 GICC_CTLR.  The GICC page base is the firmware's own literal at file 0x8309c
#         (`ldr r3,[pc,#0xc]` at 0x8308c), written 1 at 0x8308e (`str r2,[r3]`, r2 = 1): the
#         firmware ENABLES the CPU interface.  IAR 0x4016010c (literal file 0x83010, read by the ISR
#         at file 0x82f04) and EoI 0x40160110 (literal file 0x83020, written at 0x82f52) pin the page
#         at +0x0/+0xC/+0x10 - exactly the GIC-400 CPU interface.
#   F1 -> CA 0x40160104 GICC_PMR.  The firmware's own literal at file 0x83098, written 0xff at
#         0x83054, with 0x40160108 (BPR) = 3 at 0x8305a.  No standalone literal for +0x4 exists, so
#         this one is LAYOUT-DERIVED - but anchored by the three literals above (the layout that
#         makes +0xC IAR and +0x10 EoI is the GIC-400 CPU interface, whose +0x4 is PMR).
#   F2 -> CA 0x4016184C GICD_ITARGETSR word covering ids 0x4c..0x4f (relevant byte = 0x4c, bits
#         7:0).  Base 0x40161800 is the firmware's own literal at file 0x7174 (and 0x8753c); 0x4c is
#         4-byte aligned, so this is an aligned word read (no unaligned device access).
#   F3 -> CA 0x4016144C GICD_IPRIORITYR word covering ids 0x4c..0x4f.  Base 0x40161400 is the
#         firmware's own literal at file 0x7170 (and 0x81a88).
#   F4 -> CA 0x40161C10 GICD_ICFGR word 4 (ids 0x40..0x4f; id 0x4c's 2-bit field = bits 25:24).
#         Base 0x40161c00 is the firmware's own literal at file 0x715c.
#   F5 -> CA 0x400392E8 the glue's HOST_INTR_MASK (ctrl-rb +0x2E8).  **CORRECTION OF THE BRIEF**:
#         "0x3d8" is not an address - it is the MASK CONSTANT the vendor's own pcie_intr_handle ANDs
#         with the glue status word (`ldr r4,[r3,#0x2ec]` at hi5622v100_plat.ko 0x833c then
#         `ands r4, r4, #0x3d8` at 0x8344; 0x3d8 = bits {3,4,6,7,8,9}).  There is NO register at
#         ctrl-rb +0x3d8.  The glue's actual mask register is +0x2E8: the verified sibling header
#         (mp17c pcie_ctrl_rb_regs.h) names it PCIE_CTRL_RB_HOST_INTR_MASK, the vendor's own RMW on
#         it is `ldr r8,[r3,#0x2e8]` / `and r8,r8,#0xfffffc20` / `str r8,[r2,#0x2e8]`
#         (pcie_ete_chn_res), the takeover reset is 0x3ff and the vendor live value is 0x20
#         (reg_all.txt), and phase 45/46/47 key the whole chain on it.  Polarity: bit 0 =
#         host2device_tx_intr_mask, **1 = masked, 0 = open** (`/* mask:1 for mask, 0 for unmask */`),
#         so a SET bit 0 is the "the glue masks the line" branch and a CLEAR bit 0 is the vendor's
#         open state.
#   F6 -> CA 0x400392E4 the glue's HOST_INTR_RAW_STATUS (+0x2E4): bit 0 = host2device_tx raw event,
#         bit 3 = device2host_rx (phase 46 measured bit 0 latching 0->1 on a doorbell write and bit
#         3 latched from the boot dialogue).
#   F7 -> CA 0x400392EC the glue's HOST_INTR_STATUS (+0x2EC, post-mask - the same word the vendor
#         ISR reads under the 0x3d8 mask).
#         The ctrl-rb base 0x40039000 is the firmware's own literal at file 0x86fb4 (and 0xcf2ac);
#         the three offsets are offset-identity from the verified sibling header plus phase 46/47's
#         live measurements (the image holds no literal for 0x400392d4/e4/e8/ec/f0 - they are
#         computed, per phase 47 section 4).
#   NEVER touched: the intr-clear CA 0x400392f0 (write-to-clear, forbidden), the acknowledging IAR
#   CA 0x4016010c (never read by any variant), and the RC misc window 0x10161000.
GICM_READS = (
    (0x40160100, "GICC_CTLR"),
    (0x40160104, "GICC_PMR (layout-derived, anchored by the IAR/EoI literals)"),
    (0x4016184C, "GICD_ITARGETSR ids 0x4c..0x4f"),
    (0x4016144C, "GICD_IPRIORITYR ids 0x4c..0x4f"),
    (0x40161C10, "GICD_ICFGR word 4 (ids 0x40..0x4f)"),
    (0x400392E8, "glue HOST_INTR_MASK (+0x2e8)"),
    (0x400392E4, "glue HOST_INTR_RAW_STATUS (+0x2e4)"),
    (0x400392EC, "glue HOST_INTR_STATUS (+0x2ec)"),
)
GICM_NSAMPLES = 8              # F0..F7 = the eight register samples, in GICM_READS order
GICM_NCELLS = 10               # F0..F7 + F8 (page-1 sentinel) + F9 (page-2 handshake)
GICM_SENTINEL = MARKER         # 0x50aa7e49 - the same presence-proof idiom gicpost uses
GICM_REQUEST = GICP_REQUEST    # 0xe2e2e2e2 - the gate pad's handshake first half
GICM_F_PAGE_1_IDX = 2          # all_zero_pages[2] (the next all-zero page pair after D's)
GICM_F_PAGE_2_IDX = 3          # all_zero_pages[3]
NOTE_GICM_CELLS = (
    "F0..F7 are the eight register samples and F8/F9 the per-page sentinels.  The brief asks for "
    "the sub-boundary band 'where views agree if possible': it is IMPOSSIBLE for eight more cells - "
    "the whole sub-boundary band [0xE7000, 0x104000) holds exactly 13 zero words and nine of them "
    "are already S1/S1+4/S2/S2+4/C0..C5 (the remaining four are the E cells), so gicmask takes its "
    "F cells from the NEXT two all-zero 4 KB pages after the D pair (all_zero_pages[2] and [3]), "
    "under the same rule gicsend used for D: entirely 0x00000000 at BOTH the BAR0 and the ACP-alias "
    "offsets in barmap_ep0_bar0.bin, no live firmware word.  Cells above the 0x104000 boundary are "
    "readable only through the ACP alias (the gicsend aliasing fact), so the capture quotes the "
    "alias for F0..F9 and the interp says so; the in-image cells S1/S2/C0..C5 are untouched and "
    "stay comparable to every earlier iteration.  Each F sample cell is >= 8 bytes from its "
    "neighbours, F8 sits after F0..F3 in page 1 and F9 after F4..F7 in page 2, so each used page "
    "carries a constant written by the same pad after its samples (a zero sample is then a real "
    "register read, not a lost deposit)."
)
NOTE_GICM_HANDSHAKE = (
    "The handshake is gicpost's pattern moved to the send pad: the enable-gate pad leaves the "
    "request word 0xe2e2e2e2 in F9 on its id-0x4c-gated path only, and the send pad writes the "
    "sentinel 0x50aa7e49 into F9 (and into F8) on every post.  No branch is needed: whichever "
    "write is last wins, so the captured F9 is an ORDERING witness - 0x50aa7e49 = a post ran after "
    "the id-0x4c enable pass (the F sample is post-enable), 0xe2e2e2e2 = the enable pass came after "
    "the last post (the sample still reads the registers, but predates that pass), 0x0 = no "
    "id-0x4c enable pass happened in this boot.  Note this handshake proves ORDERING between the "
    "enable pass and the post; it does NOT bind the sample to the enable pass the way gicpost's "
    "post-store pad could (the two pads are in different functions), which is irrelevant here: the "
    "delivery-configuration registers are static post-init state, not a per-pass transient."
)

# ---- gicking: the H2D ring + the polarity discriminator + IGROUPR (variant "gicking") -----------
# Implements, in ONE takeover boot, the three checks the gicking reports specify:
#   (1) the RING per ring.md section 3's fallback actor - a device-side store of value 0x1 (bit 0,
#       host2device_tx) to CA 0x400392d4, placed in the same straight-line send pad immediately
#       BEFORE the GIC sample.  Bit 3 (value 8) is the firmware's own dispatcher re-arm constant,
#       NOT the H2D ring, and is never written (the port's intrsamp rings 1 then 8; only 1 is the
#       host2device event).
#   (2) the glue raw/status sample across the ring: CA 0x400392E4 (raw) / 0x400392EC (status) /
#       0x400392E8 (mask), sampled at the firmware's own post (the send site) - the F5/F6/F7 cells
#       (masked, since the pad holds bit 0 of the mask set across the ring) and the G0 cell (the
#       post-unmask control).
#   (3) the polarity discriminator (polarity.md section 3): the pad sets the glue mask to 0x21
#       (bit 0 MASKED, bit 5 held), rings, reads the trio; then restores 0x20 (open, the vendor
#       live value) and re-reads.  Record-model prediction: raw bit 0 -> 1 while the post-mask
#       status bit 0 stays 0 (F6/F7), then status bit 0 -> 1 once the mask is open (G0).  The
#       inverted model shows status bit 0 -> 1 while still masked (F7); an independent raw-latch
#       model shows both rise.  One boot separates all three.
#   plus the GICD_IGROUPR word-2 read for id 0x4c (CA 0x40161088, bit 12, mask 0x1000 - addr.md):
#   bit 12 = 1 (Group 1) with GICC_CTLR = 0x1 (EnableGrp0 only, F0) is the group-gate root (row A);
#   0 (Group 0) kills that root (row B).
# The doorbell is rung ONCE per send-pad run; it is write-only / self-clearing (every record line
# reads back 0).  The pad restores the glue mask to 0x20 before it returns, leaving the vendor-live
# state.  NEVER written: 0x400392f0 (intr-clear).  NEVER read: 0x4016010c (acknowledging IAR),
# 0x10161000 (RC misc).
GICK_RING_CA = 0x400392D4               # ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])
GICK_RING_VAL = 0x00000001              # bit 0 = host2device_tx (ring.md)
GICK_GLUE_RAW = 0x400392E4              # HOST_INTR_RAW_STATUS (+0x2e4)
GICK_GLUE_MASK = 0x400392E8             # HOST_INTR_MASK (+0x2e8), 1 = masked
GICK_GLUE_STATUS = 0x400392EC           # HOST_INTR_STATUS (+0x2ec), post-mask
GICK_MASK_MASKED = 0x00000021           # bit 0 set (masked) + bit 5 held (the vendor's 0x20 | 0x1)
GICK_MASK_OPEN = 0x00000020             # the vendor live value: bit 0 open, bit 5 set
GICD_IGROUPR2 = 0x40161088              # GICD_IGROUPR word 2 (ids 0x40..0x5f), bit 12 = id 0x4c
GICD_IGROUPR_0X4C = 0x00001000          # the id-0x4c bit in that word (mask)
GICK_NCELLS = 4                         # G0 status(open) / G1 mask(open) / G2 IGROUPR / G3 sentinel
GICK_SENTINEL = MARKER                  # 0x50aa7e49 - the per-page presence proof
GICK_G_PAGE_IDX = 4                     # all_zero_pages[4] = 0x122000 (next page after the F pair)
NOTE_GICK_RING = (
    "The ring is ring.md section 3's device-side fallback actor: CA 0x400392d4 <= 0x1 (bit 0, "
    "host2device_tx), value 1 NOT 8 (bit 3 is the firmware's own dispatcher re-arm constant, not "
    "the H2D ring).  The CA reads back 0 after a write (write-only / self-clearing - both of "
    "ring.md's records show readback 0), so the presence proof of the ring is the glue raw bit 0 "
    "rising (F6), not a readback.  The store sits in the SAME straight-line pad as the GIC sample, "
    "immediately before it (the fallback's prescribed placement), so D0/F0/F5/F6/F7 are the "
    "post-ring samples.  The host-side ring (wifidrv1 intrsamp) is not in the frozen params "
    "(intrsamp=0) and cannot be co-timed with a device-side sample anyway."
)
NOTE_GICK_DISC = (
    "The polarity discriminator (polarity.md section 3) is a controlled knob inside the same pad: "
    "the pad first stores 0x21 into the glue mask CA 0x400392e8 (bit 0 MASKED, bit 5 held), rings, "
    "and the F block reads mask/raw/status with the mask still set (F5 = 0x21 proves the knob "
    "landed; F6 = raw; F7 = status).  It then restores 0x20 (open - the vendor live value, which "
    "wifidrv1's own wr=1 bind also writes to CA 0x400392e8) and reads status again (G0) plus the "
    "mask readback (G1).  Predictions, all read in ONE boot: the record model ('1 = masked', "
    "status = raw & ~mask) gives raw bit0 = 1 while status bit0 = 0 (F6/F7), then status bit0 = 1 "
    "once open (G0); the inverted model gives status bit0 = 1 while still masked (F7); an "
    "independent-raw-latch model gives F7 bit0 = 1 too.  The mask is restored before the pad "
    "returns, so the device is left in the vendor-live state."
)
NOTE_GICK_IGROUPR = (
    "GICD_IGROUPR word 2 for id 0x4c = CA 0x40161088 (bit 12, mask 0x1000), layout-derived "
    "exactly as addr.md section 1: GICD base 0x40161000 (firmware literal file 0x716c) + 0x080 "
    "(the IGROUPR bank) + 4*2, the same id->word/bit style phase32/phase49 verified for the "
    "ISENABLER word (0x40161108).  addr.md notes the image holds NO IGROUPR literal, so this is "
    "doc-anchored, not literal-anchored - the read is the check.  GICv2 semantics: 1 = Group 1, "
    "0 = Group 0.  With GICC_CTLR = 0x1 (F0, EnableGrp0 only) a Group-1 id 0x4c cannot signal to "
    "the CPU (row A = the group-gate root); Group 0 (bit 12 = 0) kills that root (row B)."
)
NOTE_GICK_CELLS = (
    "G0..G3 continue the F pages' rule: the next all-zero 4 KB page after the F pair "
    "(all_zero_pages[4] = 0x122000), entirely 0x00000000 at BOTH the BAR0 and the ACP-alias "
    "offsets in barmap_ep0_bar0.bin, >= 8 bytes apart, outside the four excluded tables and "
    "distinct from every earlier cell.  The brief's preference for the sub-boundary band is "
    "EXHAUSTED (13 zero words: S1/S1+4/S2/S2+4/C0..C5/E0..E3 - the F cells already had to go "
    "above 0x104000), so the G cells are alias-only, exactly like the D/F cells, and are quoted "
    "from the ACP alias; G3 is the page's presence sentinel, written by the same pad after "
    "G0..G2, so a zero G0 is a real register read and not a lost deposit."
)

# ---- gicunmask: the POST-UNMASK ring->GIC sample (variant "gicunmask") ---------------------------
# The direct follow-up to gicking's open step R2.  gicking rang the H2D doorbell CA 0x400392d4 <= 0x1
# while the glue mask 0x400392e8 bit 0 was DELIBERATELY MASKED (0x21), and its post-ring ISPENDR2
# word-2 sample (D0 = 0x20, bit 12 clear) was therefore CONFOUNDED: a line gated by the glue mask is
# expected to leave the distributor's pending bit clear.  gicking's own discriminator control then
# restored the mask to OPEN (0x20) and read the glue status (G0 bit 0 = 1) but never re-read
# ISPENDR2, so the ring->GIC step stayed undecided.  gicunmask closes that hole in ONE boot with the
# mask OPEN across the ring:
#   (a) the pad stores the DOCUMENTED OPEN mask 0x20 into CA 0x400392e8 (bit 0 open, bit 5 held) -
#       the vendor-live value, so no restore is needed;
#   (b) rings the H2D doorbell CA 0x400392d4 <= 0x1 (bit 0, host2device_tx) ONCE, immediately before
#       the GIC sample;
#   (c) samples five registers, THE DECISIVE READ FIRST:
#           H0 <- CA 0x40161208 GICD_ISPENDR2 word 2 (bit 12 = source id 0x4c) - THE decisive read
#           H1 <- CA 0x40160118 GICC HPPIR (0x3ff = nothing pending for the CPU; non-acknowledging)
#           H2 <- CA 0x40161308 GICD_ISACTIVER2 word 2 (bit 12 = delivered/active)
#           H3 <- CA 0x400392e4 the glue's HOST_INTR_RAW_STATUS (bit 0 = the ring latch)
#           H4 <- CA 0x400392ec the glue's HOST_INTR_STATUS (post-mask - proves the line passed)
#   (d) H5 <- CA 0x40161208 read at the NEXT send-site visit.  The pad runs on every out[1] post, so
#       H0..H4 are THIS visit's instant sample and H5 is the value one post-interval later (a delayed
#       delivery lands in H5, not H0).  The H5 read is placed BEFORE this visit's mask write and
#       ring, so on a second visit it reflects the first visit's ring with the mask already open.
#   plus H6/H7, one presence sentinel per used 4 KB page (the 0x50aa7e49 idiom): a zero H sample
#   next to an intact sentinel is a real register read, not a lost deposit.
# The three branches this boot decides (exactly one):
#   H0 bit 12 SET                       -> the ringed event REACHES the GIC (the wire is ALIVE when
#                                          rung; the open question becomes why the natural posts
#                                          never raise it);
#   H0 bit 12 clear + H3 = 0x1 + H4 = 0x1 -> the glue latches AND passes the line (raw and post-mask
#                                          status both set) but the GIC never sees it -> THE
#                                          GLUE->GIC WIRE IS THE DEAD LINK;
#   H0 bit 12 clear + H5 bit 12 SET     -> DELAYED DELIVERY (the pending bit rose by the next post).
# Sanities kept from the gicking/gicpost base: S1/S1+4 and S2/S2+4 and the C0..C5 GIC reads in the
# (byte-identical) thunk/bring-up pads; E0..E3 in the (byte-identical) post-write pad, where E0 is
# the ISENABLER2 word-2 POST-write readback proving the firmware's own id-0x4c enable store landed.
# The ring is rung ONCE per send-pad run and the mask is left at the vendor-live 0x20.  NEVER
# written: 0x400392f0 (intr-clear, write-to-clear).  NEVER read: 0x4016010c (acknowledging IAR),
# 0x10161000 (RC misc; a read there PANICKED the box).
GICU_RING_CA = GICK_RING_CA               # ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])
GICU_RING_VAL = GICK_RING_VAL             # 0x1 = bit 0 host2device_tx
GICU_GLUE_MASK = GICK_GLUE_MASK           # ctrl-rb +0x2e8, bit 0: 1 = masked, 0 = open
GICU_MASK_OPEN = GICK_MASK_OPEN           # 0x20 - the documented open bit-0 value (vendor live)
GICU_GLUE_RAW = GICK_GLUE_RAW             # ctrl-rb +0x2e4 HOST_INTR_RAW_STATUS
GICU_GLUE_STATUS = GICK_GLUE_STATUS       # ctrl-rb +0x2ec HOST_INTR_STATUS (post-mask)
GICU_READS = (GICD_ISPENDR2, GICC_HPPIR, GICD_ISACTIVER2, GICU_GLUE_RAW, GICU_GLUE_STATUS)   # H0..H4
GICU_H5_CA = GICD_ISPENDR2                # H5 - the next-visit re-read of the decisive word
GICU_NCELLS = 8                           # H0..H5 samples + H6/H7 per-page sentinels
GICU_SENTINEL = MARKER                    # 0x50aa7e49 - the presence proof of the send pad
GICU_H_PAGE_1_IDX = GICK_G_PAGE_IDX + 1   # all_zero_pages[5] = 0x123000 (H0..H4 + H6)
GICU_H_PAGE_2_IDX = GICK_G_PAGE_IDX + 2   # all_zero_pages[6] = 0x124000 (H5 + H7)
NOTE_GICU_UNMASK = (
    "The ring is rung with the glue mask OPEN (CA 0x400392e8 <= 0x20, bit 0 = 0 = unmasked, the "
    "documented vendor-live value and the same value wifidrv1's own wr=1 bind writes): the exact "
    "hole gicking left.  The store sits in the same straight-line send pad immediately before the "
    "H0..H4 sample block, so H0/H1/H2/H3/H4 are the post-unmask, post-ring samples; H3 (glue raw) "
    "and H4 (glue post-mask status) are read at the same instant as H0, so a H0 with bit 12 clear "
    "next to H3 = 0x1 and H4 = 0x1 is a genuine 'the glue passed the line and the GIC did not see "
    "it' observation (the same-instant glue control that gicking lacked for the GIC)."
)
NOTE_GICU_H_CELLS = (
    "H0..H5 are the six new samples and H6/H7 one presence sentinel per used 4 KB page.  The brief's "
    "preference for the sub-boundary band is IMPOSSIBLE for eight more cells (the band holds 13 zero "
    "words, all consumed by S1/S1+4/S2/S2+4/C0..C5/E0..E3), so the H cells continue the D/F/G rule: "
    "the next two all-zero 4 KB pages after gicking's G page (all_zero_pages[5] = 0x123000 and "
    "[6] = 0x124000), entirely 0x00000000 at BOTH the BAR0 and the ACP-alias offsets in "
    "barmap_ep0_bar0.bin, 4-byte aligned, >= 8 bytes apart, outside the four excluded tables and "
    "distinct from every earlier cell.  H0..H4 and the page-1 sentinel H6 sit in page 1; H5 and the "
    "page-2 sentinel H7 sit in page 2.  Cells above the 0x104000 aliasing boundary are read through "
    "the ACP alias (the gicsend aliasing fact), so the capture quotes the alias for H0..H7."
)
NOTE_GICU_H5 = (
    "H5 is the 'delayed delivery' witness: the send pad runs at every out[1] post (the same site "
    "gicking/gicmask used), so H5 - read at the START of a visit, before that visit's mask write and "
    "ring - holds the ISPENDR2 word 2 one full post-interval after the PREVIOUS visit's ring.  If the "
    "site is visited more than once, a pending bit that rises only after the ring+delivery latency "
    "shows up in H5 even when H0's instant sample was clear.  CAVEAT (stated, not hidden): if the "
    "site is visited ONLY once, H5 is that single visit's pre-ring read and is void for the delayed "
    "branch - the intact H7 sentinel next to a zero H5 then means 'the register read 0 at the entry "
    "instant', not 'never delivered'."
)

# ---- trigring: the NATURAL-POST ring with PRE/POST samples (variant "trigring") -----------------
# Implements trigger.md section 3 - the single best candidate for the next boot.  trigger.md found,
# by an exhaustive literal + address-provenance scan, that the firmware image contains NO bit-0
# store to CA 0x400392d4 (the H2D doorbell): the only store that touches that CA is the H2D
# dispatcher's own re-arm, `str r1,[r2]` with r1 = 8 = bit 3 (device2host_rx_intr_set), at file
# 0x818C4; and the natural "post" the instruments sampled (routine 0x86E14, post block 0x86F54)
# writes only out[1] (CA 0x40039014 = 4) and the D2H notify (CA 0x40101434 = 1), neither of which
# is the H2D doorbell.  Because NO firmware write site can perform the ring, the task's fallback
# applies and the pad performs the candidate ring itself, as the explicit stand-in for the natural
# trigger:
#   trigger.md section 3: "in the send pad at file 0x86F5A, after reproducing the natural post
#   (*0x40039014 = 4), before the D2H notify, insert str rX,[r3 + 0x2C0] with r3 = 0x40039014 and
#   rX = 1 -> writes CA 0x400392D4 <= 1".
# r3 = 0x40039014 IS the live register at the site (loaded at file 0x86F56, `ldr r3,[pc,#0x64]`),
# so 0x40039014 + 0x2C0 = 0x400392D4: the pad stores the same CA <= 1 the gicking/gicunmask pads
# wrote, now placed INSIDE the natural post so the firmware's own H2D dispatcher (file 0x818AC) is
# the consumer.  Per the task's allowance the CA is written directly (write_ca_block(0x400392d4,
# 1)); that is arithmetically the trigger.md sequence with the live r3.  The glue mask is driven to
# the documented OPEN value 0x20 and left there (the vendor-live state); the masked word 0x21 is
# NEVER written.  NEVER written: 0x400392f0 (intr-clear, write-to-clear).  NEVER read: 0x4016010c
# (acknowledging IAR), 0x10161000 (RC misc; a read there PANICKED the box).
TRIG_RING_CA = GICK_RING_CA            # ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])
TRIG_RING_VAL = GICK_RING_VAL          # 0x1 = bit 0 host2device_tx
TRIG_RING_OFF = 0x2C0                  # trigger.md section 3: 0x40039014 + 0x2C0 = 0x400392d4
TRIG_GLUE_MASK = GICK_GLUE_MASK        # ctrl-rb +0x2e8, bit 0: 1 = masked, 0 = open
TRIG_MASK_OPEN = GICK_MASK_OPEN        # 0x20 - the documented open bit-0 value (vendor live)
TRIG_GLUE_RAW = GICK_GLUE_RAW          # ctrl-rb +0x2e4 HOST_INTR_RAW_STATUS
TRIG_GLUE_STATUS = GICK_GLUE_STATUS    # ctrl-rb +0x2ec HOST_INTR_STATUS (post-mask)
TRIG_READS = (GICD_ISPENDR2, GICC_HPPIR, TRIG_GLUE_RAW, TRIG_GLUE_STATUS)  # T0..T3 pre / T4..T7 post
TRIG_NCELLS = 10                       # T0..T7 samples + TS1/TS2 per-page sentinels
TRIG_SENTINEL = MARKER                 # 0x50aa7e49 - the presence proof of the send pad
TRIG_T_PAGE_1_IDX = GICU_H_PAGE_2_IDX + 1   # all_zero_pages[7] = 0x125000 (T0..T3 + TS1)
TRIG_T_PAGE_2_IDX = GICU_H_PAGE_2_IDX + 2   # all_zero_pages[8] = 0x14e000 (T4..T7 + TS2)
NOTE_TRIG_RING = (
    "The ring is trigger.md section 3's candidate, performed by the pad because the image has no "
    "firmware site that can: CA 0x400392d4 <= 0x1 (bit 0, host2device_tx), value 1 NOT 8 (bit 3 is "
    "the firmware's own dispatcher re-arm constant, at file 0x818C4 - never written).  The store "
    "sits in the SAME straight-line send pad as the samples, at the firmware's OWN natural post "
    "(between the reproduced `*0x40039014 = 4` and the natural D2H notify at 0x86F62, which the "
    "pad's return path still reaches), so the firmware's own H2D dispatcher (file 0x818AC) consumes "
    "it.  The CA reads back 0 after a write (write-only / self-clearing), so the presence proof of "
    "the ring is the glue raw bit 0 rising (T6), not a readback."
)
NOTE_TRIG_PREPOST = (
    "WHAT MAKES trigring DIFFERENT FROM gicunmask (stated explicitly, per the task): gicunmask "
    "sampled only the POST-ring state in one visit (H0..H4) plus an entry read at the NEXT visit "
    "(H5) - and its H5 is taken BEFORE its own mask-open store, so gicunmask's pre/post delta "
    "conflates the mask change with the ring.  trigring takes the PRE-ring and POST-ring samples in "
    "the SAME visit, with the glue mask already OPEN across both, so the ONLY thing between T0..T3 "
    "and T4..T7 is the ring.  A pre sample (T0) with bit 12 clear next to a post sample (T4) with "
    "bit 12 set is the ring->GIC step proven causally tight; a T4 also clear next to T6/T7 set is "
    "the 'glue latched but the GIC did not see it' branch; both clear is a bounded negative."
)
NOTE_TRIG_CELLS = (
    "T0..T7 are the eight pre/post samples; TS1/TS2 are one presence sentinel per used 4 KB page "
    "(the 0x50aa7e49 idiom).  The brief's preference for the sub-boundary band is IMPOSSIBLE "
    "(13 zero words, all consumed by S1/S1+4/S2/S2+4/C0..C5/E0..E3), so the T cells continue the "
    "D/F/G/H rule: the next two all-zero 4 KB pages after gicunmask's H pair (all_zero_pages[7] = "
    "0x125000 and [8] = 0x14e000), entirely 0x00000000 at BOTH the BAR0 and the ACP-alias offsets "
    "in barmap_ep0_bar0.bin, 4-byte aligned, >= 8 bytes apart, outside the four excluded tables "
    "and distinct from every earlier cell.  T0..T3 + TS1 sit in page 1; T4..T7 + TS2 sit in page "
    "2.  Cells above the 0x104000 aliasing boundary are read through the ACP alias (the gicsend "
    "aliasing fact), so the capture quotes the alias for T0..T7/TS1/TS2."
)

# ---- trignat: the NATURAL-POST ring + the DEVICE-DISPATCHER consumption witness (variant "trignat")
# Implements trigger2.md section 3 (the follow-up of trigring).  trigger2.md settled that the natural
# ring actor for the H2D doorbell CA 0x400392d4 (bit 0) is the HOST driver, whose `pcie_msg_send`
# stores the pending bitmap to out[0] (CA 0x40039010) and then ORs bit 0 into the doorbell; the
# firmware's ONLY store to that CA is value 8 (bit 3) - the H2D dispatcher's own re-arm.  The
# consumer of a ring is the DEVICE firmware: `fn_array[0x4C]` -> stub 0x294 -> dispatcher 0x818AC,
# which acks CA 0x400392F0 = 1, reads+clears out[0] (`ldr r5,[r2]` / `str r1,[r2]` with r1 = 0, file
# 0x818BE) and re-arms the doorbell with 8 (file 0x818C4).  trignat has the FIRMWARE perform the
# host's two stores at the firmware's own natural post so the device-internal chain is tested end to
# end with no host/RC confound, and adds the instrument trigring lacked: the consumption witness
# (Pad B's drain read: out[0] read 0 after the dispatch, and ISPENDR2 bit 12 clear because the
# id-0x4c interrupt was taken).
#
# LOAD-BEARING CORRECTION TO trigger.md section 3 (trigger2.md section 0): that post writes out[1]
# (`*0x40039014 = 4`), NOT the pending bitmap the dispatcher reads, so Pad A must ALSO store
# out[0] <= 8 (the store `pcie_msg_send` makes) - without it 0x818AC reads out[0] = 0, calls no
# handler and leaves no consumption witness.  bit 3 is the H2D id whose device handler
# `pcie_msg_init` registers (THE-GATE-MAP.md) and the id the vendor host submits for the SR path
# (`pcie_msg_send(chip,3)`).
#
# Two pads (the patch_fw_scratch idiom: mrs_apsr(12) / push(PAD_SAVE) / write_ca_block /
# gic_read_store_block / _store_imm_block / pop(PAD_SAVE) / msr_apsr(12) / b_w):
#   Pad A at file 0x86F5A (the firmware's OWN natural post - the trigring send site):
#     entry reads of out[0]/out[1] (A_E0/A_E1, the gicunmask H5 next-visit idiom; the fallback
#     consumption read) -> reproduce the natural post (`str r2,[r3]`, out[1] <= 4) -> glue mask
#     OPEN (0x20) -> the H2D submission out[0] <= 8 -> pre-ring reads A_S0 (out[0] sanity = 8),
#     A_S1 (ISPENDR2 word 2), A_S2 (HPPIR = 0x3ff) -> THE RING (CA 0x400392d4 <= 1, once, NEVER 8)
#     -> post-ring reads A_S3 (ISPENDR2 w2 - bit 12 SET expected), A_S4 (HPPIR = 0x4c),
#     A_S5 (out[0] latency datum, expected 8 = not yet consumed), A_S6 (out[1] = 4), A_S7 (glue
#     raw), A_S8 (glue status) -> the page sentinels A_P1/A_P2 -> reproduce `movs r2,#1` as
#     `movw r2,#1`, restore flags, `b.w 0x86F5E` (the natural D2H notify at 0x86F66 still runs).
#   Pad B at file 0x86F7E (the announce routine's exit, AFTER the 0xcece handshake wait):
#     B_D0 = out[0] (CA 0x40039010) - EXPECTED 0 if 0x818AC ran and consumed the `8`; B_D1 = out[1];
#     B_D2 = ISPENDR2 word 2 - expected bit 12 CLEAR (the id-0x4c interrupt taken); B_D3 = HPPIR;
#     B_P3 = the page sentinel; then it reproduces the replaced `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`
#     and `b.w 0x86F82`.  (The `bl` installs lr = 0x86F82, but the reproduced pop.w restores the
#     routine's own lr from the stack, so the clobber is harmless.)
# Cells: the gicpost sanities (S1/S2/C0..C5 and E0..E3 - IDENTICAL addresses) plus the trignat
# cells from the next two all-zero 4 KB pages after trigring's T pair (all_zero_pages[9] =
# 0x14f000 and [10] = 0x150000): page 9 carries A_S0..A_S3, A_P1, A_E0, A_E1 (7); page 10 carries
# A_S4..A_S8, A_P2, B_D0..B_D3, B_P3 (11).  NEVER written: 0x400392f0 (intr-clear, write-to-clear)
# and the masked glue word 0x21 (the mask stays OPEN).  NEVER read: 0x4016010c (acknowledging IAR),
# 0x10161000 (RC misc; a read there PANICKED the box).
TRIGNAT_RING_CA = GICK_RING_CA            # ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])
TRIGNAT_RING_VAL = GICK_RING_VAL          # 0x1 = bit 0 host2device_tx
TRIGNAT_GLUE_MASK = GICK_GLUE_MASK        # ctrl-rb +0x2e8, bit 0: 1 = masked, 0 = open
TRIGNAT_MASK_OPEN = GICK_MASK_OPEN        # 0x20 - the documented open bit-0 value (vendor live)
TRIGNAT_GLUE_RAW = GICK_GLUE_RAW          # ctrl-rb +0x2e4 HOST_INTR_RAW_STATUS
TRIGNAT_GLUE_STATUS = GICK_GLUE_STATUS    # ctrl-rb +0x2ec HOST_INTR_STATUS (post-mask)
TRIGNAT_OUT0_CA = 0x40039010              # out[0] = the H2D pending bitmap 0x818AC consumes
TRIGNAT_OUT1_CA = 0x40039014              # out[1] = the D2H pending bitmap the natural post writes
TRIGNAT_SUBMIT_VAL = 0x00000008           # bit 3 = the H2D id pcie_msg_init registers (pcie_msg_send(chip,3))
TRIGNAT_PRE_READS = (TRIGNAT_OUT0_CA, GICD_ISPENDR2, GICC_HPPIR)                 # A_S0, A_S1, A_S2
TRIGNAT_POST_READS = (GICD_ISPENDR2, GICC_HPPIR, TRIGNAT_OUT0_CA, TRIGNAT_OUT1_CA,
                      TRIGNAT_GLUE_RAW, TRIGNAT_GLUE_STATUS)                     # A_S3..A_S8
TRIGNAT_A_NSAMPLES = 9                    # A_S0..A_S8 (3 pre-ring + 6 post-ring)
TRIGNAT_A_NENTRY = 2                      # A_E0, A_E1 (next-visit entry reads of out[0]/out[1])
TRIGNAT_A_NSENTINELS = 2                  # A_P1 (page 9), A_P2 (page 10)
TRIGNAT_A_NCELLS = 13                     # A_S0..A_S8 + A_P1 + A_E0/A_E1 + A_P2
TRIGNAT_A_PAGE9_NCELLS = 7                # A_S0..A_S3 + A_P1 + A_E0/A_E1 (all_zero_pages[9])
TRIGNAT_A_PAGE10_NCELLS = 6               # A_S4..A_S8 + A_P2 (all_zero_pages[10])
TRIGNAT_B_READS = (TRIGNAT_OUT0_CA, TRIGNAT_OUT1_CA, GICD_ISPENDR2, GICC_HPPIR)  # B_D0..B_D3
TRIGNAT_B_NSAMPLES = 4
TRIGNAT_B_NSENTINELS = 1                  # B_P3 (page 10)
TRIGNAT_B_NCELLS = 5
TRIGNAT_SENTINEL = MARKER                 # 0x50aa7e49 - the per-page presence proof
TRIGNAT_A_PAGE_IDX = TRIG_T_PAGE_2_IDX + 1   # all_zero_pages[9]  = 0x14f000 (Pad A page 1)
TRIGNAT_B_PAGE_IDX = TRIG_T_PAGE_2_IDX + 2   # all_zero_pages[10] = 0x150000 (Pad A page 2 + Pad B)
TRIGNAT_SITE_A = SEND_SITE                # 0x86f5a - Pad A replaces `str r2,[r3]`+`movs r2,#1`
TRIGNAT_CONT_A = SEND_CONT                # 0x86f5e
TRIGNAT_SITE_B = 0x86F7E                  # Pad B replaces `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`
TRIGNAT_CONT_B = 0x86F82                  # continue at `ldr r0,[pc,#0x3c]`
TRIGNAT_DRAIN_POP = bytes.fromhex("bde8f843")   # the replaced `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`
NOTE_TRIGNAT_A = (
    "Pad A is entered at the firmware's OWN natural post (file 0x86F5A, r2 = 4 and r3 = CA "
    "0x40039014 from 0x86F54/0x86F56).  It FIRST takes the two entry reads A_E0 (out[0]) / A_E1 "
    "(out[1]) BEFORE reproducing the post - the only placement that makes the section-4 'expected "
    "0 / 4 after a prior visit' true: A_E1 = 4 iff a prior visit already stored out[1], and "
    "A_E0 = 0 iff the prior visit's out[0] = 8 was consumed by the dispatcher.  It then reproduces "
    "the natural post (`str r2,[r3]` -> out[1] <= 4), drives the glue mask to the documented OPEN "
    "value 0x20, performs the H2D submission out[0] <= 8 (the store `pcie_msg_send` makes, the "
    "load-bearing correction to trigger.md section 3 - without it 0x818AC reads out[0] = 0 and "
    "calls no handler), takes the pre-ring reads A_S0/A_S1/A_S2, RINGS the doorbell "
    "(CA 0x400392d4 <= 0x1, once, never 8 = the dispatcher's re-arm constant), takes the post-ring "
    "reads A_S3..A_S8 (A_S5 is the latency datum: 8 = the ISR did not preempt the pad; 0 = it "
    "did), arms the page sentinels A_P1/A_P2, reproduces `movs r2,#1` as `movw r2,#1`, restores "
    "the saved flags and returns to 0x86F5E - so the natural D2H notify at 0x86F66 runs after the "
    "ring.  r0-r5 (r3 = the out[1] CA, r1 = the 0x4000010c spin pointer at file 0x86F78, r5 = the "
    "0xbe0 base) are saved/restored by push/pop PAD_SAVE."
)
NOTE_TRIGNAT_B = (
    "Pad B is entered at file 0x86F7E, the announce routine's exit AFTER the `*(0x4000010C) == "
    "0xcece` handshake wait (0x86F74..0x86F7C) - i.e. at the first point where a consumed ring can "
    "be observed.  It reads B_D0 = out[0] (EXPECTED 0, where Pad A stored 8 - the device-dispatcher "
    "consumption witness: 0x818AC reads out[0] into r5 then clears it with r1 = 0), B_D1 = out[1], "
    "B_D2 = ISPENDR2 word 2 (expected bit 12 CLEAR = the id-0x4c interrupt was taken / "
    "acknowledged), B_D3 = HPPIR, and arms the sentinel B_P3, then reproduces the replaced "
    "`pop.w {r3,r4,r5,r6,r7,r8,sb,lr}` and branches to 0x86F82.  The `bl` at the site installs "
    "lr = 0x86F82, but the reproduced pop.w restores the routine's own lr from the stack before any "
    "use, so the clobber is inert.  Pad B sits behind the 0xcece handshake loop, so if the sentinel "
    "is missing the row-4 'PAD-DID-NOT-RUN' fallback is the A_E0/A_E1 entry reads (the first visit "
    "is ambiguous: A_E0 = 0 on the first visit too)."
)
NOTE_TRIGNAT_CELLS = (
    "The trignat cells continue the D/F/G/H/T rule: the next two all-zero 4 KB pages after "
    "trigring's T pair (all_zero_pages[9] = 0x14f000 and [10] = 0x150000), entirely 0x00000000 at "
    "BOTH the BAR0 and the ACP-alias offsets in barmap_ep0_bar0.bin, 4-byte aligned, >= 8 bytes "
    "apart, outside the four excluded tables and distinct from every earlier cell (the S1/S2/C0..C5 "
    "and E0..E3 sanities keep their gicpost addresses).  Page 9 carries A_S0..A_S3, the sentinel "
    "A_P1 and the entry reads A_E0/A_E1; page 10 carries A_S4..A_S8, the sentinel A_P2, and Pad "
    "B's B_D0..B_D3 + B_P3.  Cells above the 0x104000 aliasing boundary are read through the ACP "
    "alias (the gicsend aliasing fact), so the capture quotes the alias for the trignat cells."
)
NOTE_TRIGNAT_BRANCHES = (
    "settled branch table (trigger2.md section 4): TRIGNAT-COMPLETE = A_S3 bit 12 SET, A_S4 = "
    "0x4C, B_D0 = 0 and B_D2 bit 12 CLEAR (with B_P3 = sentinel) - the firmware's own post -> ring "
    "-> device GIC -> device dispatcher CONSUMED out[0]; RING-PENDING-NOT-TAKEN = A_S3 bit 12 SET, "
    "A_S4 = 0x4C and (B_D0 = 8 or B_D2 bit 12 SET) - the ringed event reaches the GIC but the "
    "id-0x4c interrupt is never taken; GLUE-ONLY = A_S3 bit 12 CLEAR and (A_S7 or A_S8 bit 0 = 1); "
    "NOTHING = A_S3 bit 12 CLEAR and A_S7/A_S8 bit 0 = 0 with sentinels present.  A_S5 = 8 with "
    "row 1 holding means the ISR did not preempt Pad A and Pad B caught the consumption; A_S5 = 0 "
    "means the ISR preempted the pad mid-way."
)

# ---- trigcons: the pad-B MOVE past the 0xcece gate (variant "trigcons")
# Implements padb.md section 3 option (a) - the chosen build-node fix.  trignat's Pad B sits at the
# announce routine's EXIT (file 0x86F7E), behind the `*(0x4000010C) == 0xcece` handshake wait
# (0x86F74..0x86F7C); nothing in this image (or any held `.ko`) writes 0xcece, so the loop never
# exits and Pad B never ran (the salvage's B_P3 ABSENT, row "-").  trigcons MOVES the pad onto the
# wait's own instruction: the site is now file 0x86F74, the `movw r3,#0xcece` (stock bytes
# 4cf6ce63), and the continuation is the loop head 0x86F78 (`ldr r2,[r1]`, r1 = CA 0x4000010c).
# The pad takes the SAME B_D0..B_D3 samples + the B_P3 sentinel and then re-emits
# `movw r3,#0xcece` (the instruction it replaced) before branching to 0x86F78, so the loop's
# `cmp r2,r3` still compares against 0xcece.  Pad A, the thunk/bring-up/post pads and every cell
# keep trignat's addresses (the drain pad's length is unchanged), so S1/S2/C0..C5/E0..E3 and A_*
# stay directly comparable.  Because the read is now PRE-wait, the expected row is
# RING-PENDING-NOT-TAKEN (B_D0 = 8, B_D2 bit 12 SET) - the residual gate named as the CPU-interface
# take/enable; only the (c) host write can reach the post-handshake instant.  NEVER writes
# 0x400392f0; NEVER writes 0x21; NEVER reads 0x4016010c or 0x10161000.
TRIGCONS_SITE_B = 0x86F74                  # Pad B's moved site: the announce gate `movw r3,#0xcece`
TRIGCONS_CONT_B = 0x86F78                  # continuation: the spin loop head `ldr r2,[r1]`
TRIGCONS_SITE_B_BYTES = bytes.fromhex("4cf6ce63")   # the replaced `movw r3,#0xcece` (stock 0x86F74)
NOTE_TRIGCONS_A = NOTE_TRIGNAT_A           # Pad A is byte-identical to trignat's
NOTE_TRIGCONS_B = (
    "Pad B is MOVED from trignat's announce-exit site (file 0x86F7E, behind the 0xcece wait that "
    "never completes this boot) to the wait's OWN `movw r3,#0xcece` at file 0x86F74 - the "
    "instruction immediately before the only blocking instruction, so the pad is guaranteed to "
    "run.  It takes the same four samples B_D0 (out[0], CA 0x40039010), B_D1 (out[1]), B_D2 "
    "(ISPENDR2 word 2, CA 0x40161208), B_D3 (GICC HPPIR) and arms B_P3, then RE-EMITS the replaced "
    "`movw r3,#0xcece` (so the loop's `cmp r2,r3` at 0x86F7A still compares against 0xcece) and "
    "branches to the loop head 0x86F78.  The read is PRE-wait: the expected outcome is "
    "RING-PENDING-NOT-TAKEN (B_D0 = 8, B_D2 bit 12 SET), naming the CPU-interface take/enable as "
    "the residual gate past the wire.  r1 (the CA 0x4000010c spin pointer) and r5 (the 0xbe0 "
    "message object) are preserved by PAD_SAVE; only r3 is re-set, AFTER the pop (row order: "
    "pop(PAD_SAVE), movw r3,#0xcece, msr_apsr(12), b.w 0x86F78).  The replaced site's own lr "
    "clobber is inert: the pad never returns through lr - it ends in a `b.w` to 0x86F78."
)
NOTE_TRIGCONS_BRANCHES = (
    "Pad B now runs BEFORE the 0xcece wait, so the branch table differs from trignat's: "
    "TRIGCONS-COMPLETE = A_S3 bit 12 SET, A_S4 = 0x4C, B_D0 = 0 and B_D2 bit 12 CLEAR (with B_P3 = "
    "sentinel) - the ringed event reached the GIC AND the id-0x4c interrupt was taken/consumed "
    "across the tiny Pad A -> Pad B window; RING-PENDING-NOT-TAKEN (the EXPECTED row for this "
    "placement, padb.md section 2a) = A_S3 bit 12 SET, A_S4 = 0x4C and (B_D0 = 8 or B_D2 bit 12 "
    "SET) - the wire/GIC step landed but the CPU-side take did not, naming the residual gate; "
    "GLUE-ONLY = A_S3 bit 12 CLEAR and (A_S7 or A_S8 bit 0 = 1); NOTHING = A_S3 bit 12 CLEAR with "
    "A_S7/A_S8 bit 0 = 0 and the sentinels present.  A_S5 = 8 with a pending row means the ISR did "
    "not preempt Pad A; A_S5 = 0 means it did."
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


def cmp_reg_t2(rn: int, rm: int) -> bytes:
    """CMP (register) T2: `010000 1010 Rm Rn` - the encoding the firmware's own announce loop uses
    at file 0x86f7a (stock 9a42 = `cmp r2,r3`).  Semantically identical to cmp_reg() (T1); the loop
    pair is re-emitted byte-for-byte with this form."""
    return struct.pack("<H", 0x4280 | ((rm & 7) << 3) | (rn & 7))


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


def alloc_pads(data: bytes, refs: set[int], needs: list[tuple[str, int]]) -> dict[str, tuple[int, int]]:
    """Variant-local padding allocation for gicmask: first-fit, longest-need first, over the
    non-referenced 0x00 runs - and, unlike find_padding, it may place SEVERAL pads inside ONE run
    (each pad is a straight-line trampoline that ends in a branch, so nothing falls through into
    the next one).  gicmask needs four pads of 334/160/102/94 bytes and the image holds exactly one
    run big enough for the 334-byte one, so the three smaller pads must share it.

    Returns name -> (file_offset, the run's length); deterministic (the run list is sorted by
    length then address, and the needs are placed in descending size order)."""
    free = [[st, st + ln] for st, ln in padding_runs(data, refs, [])]
    out: dict[str, tuple[int, int]] = {}
    for name, need in sorted(needs, key=lambda t: -t[1]):
        need += need & 1
        placed = None
        for span in free:
            if span[1] - span[0] >= need:
                placed = span
                break
        if placed is None:
            raise PatchError(f"no non-referenced 0x00 padding space left for the {name} pad "
                             f"({need} bytes)")
        out[name] = (placed[0], placed[1] - placed[0])
        placed[0] += need
    return out


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


def select_cells_gicmask(barmap: bytes):
    """The gicpost cells (S1/S2/C0..C5 = the walk prefix, D0..D5 = the two all-zero pages, E0..E3 =
    the sub-boundary band) plus the ten F cells: F0..F3 and the sentinel F8 from the first five
    usable cells of all_zero_pages[2], F4..F7 and the handshake F9 from the first five of
    all_zero_pages[3].  Deterministic; every cell zero at both views, outside the exclusions and
    distinct from every earlier cell."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("gicmask selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < 4:
        raise PatchError("gicmask selection failed: fewer than four all-zero 4 KB pages in the band")

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
        raise PatchError(f"gicmask selection failed: page {pages[0]:#x} has fewer than four usable cells")
    d2 = take(pages[1], 2, d)
    if len(d2) < 2:
        raise PatchError(f"gicmask selection failed: page {pages[1]:#x} has fewer than two usable cells")

    used = set(prefix) | {prefix[0] + 4, prefix[1] + 4}
    band = [a for a in range(GICP_E_LO, GICP_E_HI, 4) if ok(a)]
    e = [a for a in band if a not in used][:GICP_NCELLS]
    if len(e) < GICP_NCELLS:
        raise PatchError(f"gicmask selection failed: only {len(e)} free sub-boundary cells for E0..E3")

    p1, p2 = pages[GICM_F_PAGE_1_IDX], pages[GICM_F_PAGE_2_IDX]
    f1 = take(p1, 5, d2)
    if len(f1) < 5:
        raise PatchError(f"gicmask selection failed: page {p1:#x} has fewer than five usable cells")
    f2 = take(p2, 5, f1)
    if len(f2) < 5:
        raise PatchError(f"gicmask selection failed: page {p2:#x} has fewer than five usable cells")

    cells = prefix + d + d2 + e + f1[:4] + f2[:4] + [f1[4], f2[4]]
    sel = {
        "rule": "S1/S2/C0..C5 = the walk's fixed prefix and D0..D5 = the two all-zero 4 KB pages "
                "and E0..E3 = the free sub-boundary zero words (all IDENTICAL to the gicpost "
                "variant, so the iterations stay directly comparable).  F0..F3 + F8 = the first "
                "five usable cells of all_zero_pages[2]; F4..F7 + F9 = the first five of "
                "all_zero_pages[3] - same rule as D (4-byte aligned, 0x00000000 at BOTH the BAR0 "
                "and the alias offset in barmap_ep0_bar0.bin, outside the four excluded tables, "
                ">= 8 bytes from the previous cell, distinct from every earlier cell)",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "all_zero_pages_below_boundary": [hex(p) for p in pages if p < GICP_E_HI],
        "d_page_1": hex(pages[0]),
        "d_page_2": hex(pages[1]),
        "f_page_1": hex(p1),
        "f_page_2": hex(p2),
        "f_page_1_idx": GICM_F_PAGE_1_IDX,
        "f_page_2_idx": GICM_F_PAGE_2_IDX,
        "e_band": [hex(GICP_E_LO), hex(GICP_E_HI)],
        "e_band_zero_words": [hex(a) for a in band],
        "e_band_used_by_earlier_cells": [hex(a) for a in band if a in used],
        "e_pages": sorted({hex(a & ~0xFFF) for a in e}),
        "f_pages": sorted({hex(a & ~0xFFF) for a in f1 + f2}),
        "f_samples_page_1": [hex(a) for a in f1[:4]],
        "f_samples_page_2": [hex(a) for a in f2[:4]],
        "f_sentinels": [hex(f1[4]), hex(f2[4])],
        "note": NOTE_RANGE,
        "e_note": NOTE_GICPOST_E,
        "f_note": NOTE_GICM_CELLS,
    }
    return cells, sel


def select_cells_gicking(barmap: bytes):
    """The gicmask cells (S1/S2/C0..C5, D0..D5, E0..E3, F0..F9 - IDENTICAL, so every iteration stays
    directly comparable) plus the four G cells of the ring/discriminator group: G0..G2 and the page
    sentinel G3 from the first four usable cells of all_zero_pages[4] (the next all-zero 4 KB page
    after the F pair).  Deterministic; every cell zero at both views, outside the exclusions and
    distinct from every earlier cell."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("gicking selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < GICK_G_PAGE_IDX + 1:
        raise PatchError("gicking selection failed: fewer than five all-zero 4 KB pages in the band")

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
        raise PatchError(f"gicking selection failed: page {pages[0]:#x} has fewer than four usable cells")
    d2 = take(pages[1], 2, d)
    if len(d2) < 2:
        raise PatchError(f"gicking selection failed: page {pages[1]:#x} has fewer than two usable cells")

    used = set(prefix) | {prefix[0] + 4, prefix[1] + 4}
    band = [a for a in range(GICP_E_LO, GICP_E_HI, 4) if ok(a)]
    e = [a for a in band if a not in used][:GICP_NCELLS]
    if len(e) < GICP_NCELLS:
        raise PatchError(f"gicking selection failed: only {len(e)} free sub-boundary cells for E0..E3")

    p1, p2 = pages[GICM_F_PAGE_1_IDX], pages[GICM_F_PAGE_2_IDX]
    f1 = take(p1, 5, d2)
    if len(f1) < 5:
        raise PatchError(f"gicking selection failed: page {p1:#x} has fewer than five usable cells")
    f2 = take(p2, 5, f1)
    if len(f2) < 5:
        raise PatchError(f"gicking selection failed: page {p2:#x} has fewer than five usable cells")

    gp = pages[GICK_G_PAGE_IDX]
    gg = take(gp, GICK_NCELLS, f2)
    if len(gg) < GICK_NCELLS:
        raise PatchError(f"gicking selection failed: page {gp:#x} has fewer than {GICK_NCELLS} "
                         "usable cells for G0..G3")

    cells = prefix + d + d2 + e + f1[:4] + f2[:4] + [f1[4], f2[4]] + gg
    sel = {
        "rule": "S1/S2/C0..C5 = the walk's fixed prefix, D0..D5 = the two all-zero 4 KB pages and "
                "E0..E3 = the free sub-boundary zero words and F0..F9 = the next all-zero pair "
                "(all IDENTICAL to the gicmask variant).  G0..G2 + G3 = the first four usable cells "
                "of all_zero_pages[4] (the next all-zero 4 KB page after the F pair) - same rule as "
                "D/F: 4-byte aligned, 0x00000000 at BOTH the BAR0 and the alias offset in "
                "barmap_ep0_bar0.bin, outside the four excluded tables, >= 8 bytes from the "
                "previous cell, distinct from every earlier cell",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "all_zero_pages_below_boundary": [hex(p) for p in pages if p < GICP_E_HI],
        "d_page_1": hex(pages[0]),
        "d_page_2": hex(pages[1]),
        "f_page_1": hex(p1),
        "f_page_2": hex(p2),
        "g_page": hex(gp),
        "g_page_idx": GICK_G_PAGE_IDX,
        "g_cells": [hex(c) for c in gg],
        "g_samples": [hex(c) for c in gg[:3]],
        "g_sentinel": hex(gg[3]),
        "e_band": [hex(GICP_E_LO), hex(GICP_E_HI)],
        "e_band_zero_words": [hex(a) for a in band],
        "e_band_used_by_earlier_cells": [hex(a) for a in band if a in used],
        "e_pages": sorted({hex(a & ~0xFFF) for a in e}),
        "f_pages": sorted({hex(a & ~0xFFF) for a in f1 + f2}),
        "f_samples_page_1": [hex(a) for a in f1[:4]],
        "f_samples_page_2": [hex(a) for a in f2[:4]],
        "f_sentinels": [hex(f1[4]), hex(f2[4])],
        "note": NOTE_RANGE,
        "e_note": NOTE_GICPOST_E,
        "f_note": NOTE_GICM_CELLS,
        "g_note": NOTE_GICK_CELLS,
    }
    return cells, sel


def select_cells_gicunmask(barmap: bytes):
    """The gicpost cells (S1/S2/C0..C5 and E0..E3 - IDENTICAL addresses, so the sanities stay
    directly comparable to every earlier iteration) plus the six H samples and the two H page
    sentinels from the next two all-zero 4 KB pages after gicking's G page.  Deterministic; every
    cell zero at both views, outside the exclusions, distinct from every earlier cell."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("gicunmask selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < GICU_H_PAGE_2_IDX + 1:
        raise PatchError(f"gicunmask selection failed: fewer than {GICU_H_PAGE_2_IDX + 1} all-zero "
                         "4 KB pages in the band")

    def take(page: int, n: int, prev: list[int]) -> list[int]:
        out: list[int] = []
        a = page
        while a + 8 <= page + 0x1000 and len(out) < n:
            last = out[-1] if out else prev[-1]
            if ok(a) and a - last >= 8:
                out.append(a)
            a += 4
        return out

    used = set(prefix) | {prefix[0] + 4, prefix[1] + 4}
    band = [a for a in range(GICP_E_LO, GICP_E_HI, 4) if ok(a)]
    e = [a for a in band if a not in used][:GICP_NCELLS]
    if len(e) < GICP_NCELLS:
        raise PatchError(f"gicunmask selection failed: only {len(e)} free sub-boundary cells for E0..E3")

    p1, p2 = pages[GICU_H_PAGE_1_IDX], pages[GICU_H_PAGE_2_IDX]
    h1 = take(p1, 6, prefix)                     # H0..H4 + H6 (page 1)
    if len(h1) < 6:
        raise PatchError(f"gicunmask selection failed: page {p1:#x} has fewer than six usable cells")
    h2 = take(p2, 2, h1)                         # H5 + H7 (page 2)
    if len(h2) < 2:
        raise PatchError(f"gicunmask selection failed: page {p2:#x} has fewer than two usable cells")

    h = h1[:5] + [h2[0]] + [h1[5]] + [h2[1]]     # H0..H4, H5, H6 (page-1 sentinel), H7 (page-2)
    cells = prefix + e + h
    sel = {
        "rule": "S1/S2/C0..C5 = the walk's fixed prefix and E0..E3 = the free sub-boundary zero "
                "words (IDENTICAL to gicking/gicpost).  H0..H4 + H6 = the first six usable cells of "
                "all_zero_pages[5], H5 + H7 = the first two of all_zero_pages[6] - the same rule as "
                "D/F/G: 4-byte aligned, 0x00000000 at BOTH the BAR0 and the alias offset in "
                "barmap_ep0_bar0.bin, outside the four excluded tables, >= 8 bytes from the "
                "previous cell, distinct from every earlier cell",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "all_zero_pages_below_boundary": [hex(p) for p in pages if p < GICP_E_HI],
        "h_page_1": hex(p1),
        "h_page_2": hex(p2),
        "h_page_1_idx": GICU_H_PAGE_1_IDX,
        "h_page_2_idx": GICU_H_PAGE_2_IDX,
        "h_samples_page_1": [hex(a) for a in h1[:5]],
        "h_samples_page_2": [hex(a) for a in h2[:1]],
        "h_sentinels": [hex(h1[5]), hex(h2[1])],
        "e_band": [hex(GICP_E_LO), hex(GICP_E_HI)],
        "e_band_zero_words": [hex(a) for a in band],
        "e_band_used_by_earlier_cells": [hex(a) for a in band if a in used],
        "e_pages": sorted({hex(a & ~0xFFF) for a in e}),
        "note": NOTE_RANGE,
        "e_note": NOTE_GICPOST_E,
        "h_note": NOTE_GICU_H_CELLS,
    }
    return cells, sel


def select_cells_trigring(barmap: bytes):
    """The gicpost cells (S1/S2/C0..C5 and E0..E3 - IDENTICAL addresses, so the sanities stay
    directly comparable to every earlier iteration) plus the ten T cells: the four PRE-ring samples,
    the four POST-ring samples (the same CAs in the same order) and one sentinel per used page, all
    from the next two all-zero 4 KB pages after gicunmask's H pair.  Deterministic; every cell zero
    at both views, outside the exclusions, distinct from every earlier cell."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("trigring selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < TRIG_T_PAGE_2_IDX + 1:
        raise PatchError(f"trigring selection failed: fewer than {TRIG_T_PAGE_2_IDX + 1} all-zero "
                         "4 KB pages in the band")

    def take(page: int, n: int, prev: list[int]) -> list[int]:
        out: list[int] = []
        a = page
        while a + 8 <= page + 0x1000 and len(out) < n:
            last = out[-1] if out else prev[-1]
            if ok(a) and a - last >= 8:
                out.append(a)
            a += 4
        return out

    used = set(prefix) | {prefix[0] + 4, prefix[1] + 4}
    band = [a for a in range(GICP_E_LO, GICP_E_HI, 4) if ok(a)]
    e = [a for a in band if a not in used][:GICP_NCELLS]
    if len(e) < GICP_NCELLS:
        raise PatchError(f"trigring selection failed: only {len(e)} free sub-boundary cells for E0..E3")

    p1, p2 = pages[TRIG_T_PAGE_1_IDX], pages[TRIG_T_PAGE_2_IDX]
    t1 = take(p1, 5, prefix)                     # T0..T3 + TS1 (page 1)
    if len(t1) < 5:
        raise PatchError(f"trigring selection failed: page {p1:#x} has fewer than five usable cells")
    t2 = take(p2, 5, t1)                         # T4..T7 + TS2 (page 2)
    if len(t2) < 5:
        raise PatchError(f"trigring selection failed: page {p2:#x} has fewer than five usable cells")

    t = t1[:4] + t2[:4] + [t1[4]] + [t2[4]]      # T0..T3, T4..T7, TS1 (page-1), TS2 (page-2)
    cells = prefix + e + t
    sel = {
        "rule": "S1/S2/C0..C5 = the walk's fixed prefix and E0..E3 = the free sub-boundary zero "
                "words (IDENTICAL to gicking/gicpost/gicunmask).  T0..T3 + TS1 = the first five "
                "usable cells of all_zero_pages[7], T4..T7 + TS2 = the first five of "
                "all_zero_pages[8] - the same rule as D/F/G/H: 4-byte aligned, 0x00000000 at BOTH "
                "the BAR0 and the alias offset in barmap_ep0_bar0.bin, outside the four excluded "
                "tables, >= 8 bytes from the previous cell, distinct from every earlier cell",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "all_zero_pages_below_boundary": [hex(p) for p in pages if p < GICP_E_HI],
        "t_page_1": hex(p1),
        "t_page_2": hex(p2),
        "t_page_1_idx": TRIG_T_PAGE_1_IDX,
        "t_page_2_idx": TRIG_T_PAGE_2_IDX,
        "t_pre_samples": [hex(a) for a in t1[:4]],
        "t_post_samples": [hex(a) for a in t2[:4]],
        "t_sentinels": [hex(t1[4]), hex(t2[4])],
        "e_band": [hex(GICP_E_LO), hex(GICP_E_HI)],
        "e_band_zero_words": [hex(a) for a in band],
        "e_band_used_by_earlier_cells": [hex(a) for a in band if a in used],
        "e_pages": sorted({hex(a & ~0xFFF) for a in e}),
        "note": NOTE_RANGE,
        "e_note": NOTE_GICPOST_E,
        "t_note": NOTE_TRIG_CELLS,
    }
    return cells, sel


def select_cells_trignat(barmap: bytes):
    """The gicpost cells (S1/S2/C0..C5 and E0..E3 - IDENTICAL addresses, so the sanities stay
    directly comparable to every earlier iteration) plus the thirteen A cells and the five B cells
    from the next two all-zero 4 KB pages after trigring's T pair.  Deterministic; every cell zero
    at both views, outside the exclusions, distinct from every earlier cell."""
    check_barmap(barmap)
    ok = _cell_ok(barmap)
    primary = [a for a in range(S_CELL_LO, S_CELL_HI, 4) if ok(a)]
    prefix = walk_cells(barmap, 2 + GICV_NCELLS, ok=ok)
    if len(prefix) < 2 + GICV_NCELLS:
        raise PatchError("trignat selection failed: fewer than eight usable cells for S1/S2/C0..C5")
    pages = _zero_page_spans(barmap)
    if len(pages) < TRIGNAT_B_PAGE_IDX + 1:
        raise PatchError(f"trignat selection failed: fewer than {TRIGNAT_B_PAGE_IDX + 1} all-zero "
                         "4 KB pages in the band")

    def take(page: int, n: int, prev: list[int]) -> list[int]:
        out: list[int] = []
        a = page
        while a + 8 <= page + 0x1000 and len(out) < n:
            last = out[-1] if out else prev[-1]
            if ok(a) and a - last >= 8:
                out.append(a)
            a += 4
        return out

    used = set(prefix) | {prefix[0] + 4, prefix[1] + 4}
    band = [a for a in range(GICP_E_LO, GICP_E_HI, 4) if ok(a)]
    e = [a for a in band if a not in used][:GICP_NCELLS]
    if len(e) < GICP_NCELLS:
        raise PatchError(f"trignat selection failed: only {len(e)} free sub-boundary cells for E0..E3")

    p1, p2 = pages[TRIGNAT_A_PAGE_IDX], pages[TRIGNAT_B_PAGE_IDX]
    a1 = take(p1, TRIGNAT_A_PAGE9_NCELLS, prefix)        # A_S0..A_S3, A_P1, A_E0, A_E1 (page 9)
    if len(a1) < TRIGNAT_A_PAGE9_NCELLS:
        raise PatchError(f"trignat selection failed: page {p1:#x} has fewer than "
                         f"{TRIGNAT_A_PAGE9_NCELLS} usable cells")
    a2 = take(p2, TRIGNAT_A_PAGE10_NCELLS + TRIGNAT_B_NCELLS, a1)   # A_S4..A_S8, A_P2, then B cells
    if len(a2) < TRIGNAT_A_PAGE10_NCELLS + TRIGNAT_B_NCELLS:
        raise PatchError(f"trignat selection failed: page {p2:#x} has fewer than "
                         f"{TRIGNAT_A_PAGE10_NCELLS + TRIGNAT_B_NCELLS} usable cells")

    cells = prefix + e + a1 + a2
    sel = {
        "rule": "S1/S2/C0..C5 = the walk's fixed prefix and E0..E3 = the free sub-boundary zero "
                "words (IDENTICAL to gicking/gicpost/gicunmask/trigring).  A_S0..A_S3 + A_P1 + "
                "A_E0/A_E1 = the first seven usable cells of all_zero_pages[9]; A_S4..A_S8 + A_P2 = "
                "the next six, and B_D0..B_D3 + B_P3 = the following five, of all_zero_pages[10] - "
                "the same rule as D/F/G/H/T: 4-byte aligned, 0x00000000 at BOTH the BAR0 and the "
                "alias offset in barmap_ep0_bar0.bin, outside the four excluded tables, >= 8 bytes "
                "from the previous cell, distinct from every earlier cell",
        "spec_range": [hex(S_CELL_LO), hex(S_CELL_HI)],
        "spec_range_zero_words": len(primary),
        "range_used": [hex(S_CELL_LO), hex(S_CELL_ALIAS_HI)],
        "excludes": [hex(x) for x in S_CELL_EXCLUDE],
        "cells_used": [hex(c) for c in cells],
        "all_zero_pages": [hex(p) for p in pages],
        "all_zero_pages_below_boundary": [hex(p) for p in pages if p < GICP_E_HI],
        "a_page": hex(p1),
        "b_page": hex(p2),
        "a_page_idx": TRIGNAT_A_PAGE_IDX,
        "b_page_idx": TRIGNAT_B_PAGE_IDX,
        "a_samples": [hex(a) for a in a1[:4] + a2[:5]],
        "a_entry_reads": [hex(a) for a in a1[5:7]],
        "a_sentinels": [hex(a1[4]), hex(a2[5])],
        "b_samples": [hex(a) for a in a2[6:10]],
        "b_sentinels": [hex(a2[10])],
        "e_band": [hex(GICP_E_LO), hex(GICP_E_HI)],
        "e_band_zero_words": [hex(a) for a in band],
        "e_band_used_by_earlier_cells": [hex(a) for a in band if a in used],
        "e_pages": sorted({hex(a & ~0xFFF) for a in e}),
        "note": NOTE_RANGE,
        "e_note": NOTE_GICPOST_E,
        "a_note": NOTE_TRIGNAT_CELLS,
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


def write_ca_block(ca: int, value: int) -> bytes:
    """A device-side store of a constant to a mapped CA: movw/movt the CA into r1, movw the
    constant into r0, then `str r0,[r1]`.  r0/r1 are saved by the pad's push.  Used by the gicking
    variant to ring the H2D doorbell (CA 0x400392d4 <= 1) and to drive the glue mask
    (CA 0x400392e8 <= 0x21, then <= 0x20).  NEVER used on the intr-clear CA 0x400392f0."""
    return b"".join([
        movw(1, ca & 0xFFFF),
        movt(1, ca >> 16),
        movw(0, value & 0xFFFF),
        str_imm(0, 1, 0),
    ])


def pad_thunk(pad: int, s1: int, gic_cells: list[int] | None = None,
              apsr_cell: int | None = None, req_cell: int | None = None,
              f_req_cell: int | None = None) -> bytes:
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
    if f_req_cell is not None:                        # gicmask: F9 <- the send-pad handshake request
        body += _store_imm_block(GICM_REQUEST, f_req_cell)
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


def pad_send(pad: int, d_cells: list[int], f_cells: list[int] | None = None,
             g_cells: list[int] | None = None) -> bytes:
    """The send-site pad. Order matters: the replaced `str r2,[r3]` poster is reproduced FIRST
    (before its own sample), then the three device-side GIC reads are deposited into D0/D1/D2, a
    presence marker into D3, a second read of the critical word into D4 and a second marker into
    D5; then r0-r5 are restored, `movs r2,#1` is reproduced as `movw r2,#1`, the saved flags are
    restored and the pad returns to the instruction after the replaced pair.

    gicmask passes f_cells (F0..F9): after the D block the pad reads the eight delivery-configuration
    registers into F0..F7, arms the sentinel F8 at the end of the first F page's samples (F0..F3),
    then reads F4..F7 and arms F9 at the end of the second page.  F8/F9 are written after their
    page's samples with no branch between, so an intact sentinel makes a zero sample a real
    register read.

    gicking passes g_cells (G0..G3): the pad stores the masked glue word (0x21) into CA 0x400392e8,
    rings the H2D doorbell (CA 0x400392d4 <= 0x1) BEFORE the D/F sample blocks (so D0/F0/F5/F6/F7
    are the post-ring samples and F5 = 0x21 proves the controlled knob landed), then after the F
    block restores the open vendor mask (0x20) and reads the control group - status with the mask
    open (G0), the mask readback (G1), the GICD_IGROUPR word 2 for id 0x4c (G2, CA 0x40161088), and
    the page sentinel G3.  The mask is left at its vendor-live value 0x20."""
    d0, d1, d2, d3, d4, d5 = d_cells
    head = b"".join([
        mrs_apsr(12),                                   # +0  save condition flags
        push(PAD_SAVE),                                 # +4  24 bytes, keeps SP 8-aligned
        str_imm(2, 3, 0),                               # +6  reproduce `str r2,[r3]` -> the post
    ])
    if g_cells:                                         # gicking: mask the line, THEN ring
        head += b"".join([
            write_ca_block(GICK_GLUE_MASK, GICK_MASK_MASKED),   # bit 0 = masked (the knob)
            write_ca_block(GICK_RING_CA, GICK_RING_VAL),        # the H2D doorbell (bit 0 = 1)
        ])
    head += b"".join([
        gic_read_store_block(GIC_SEND_READS[0], d0),    # D0  ISPENDR2 (post-ring)
        gic_read_store_block(GIC_SEND_READS[1], d1),    # D1  HPPIR
        gic_read_store_block(GIC_SEND_READS[2], d2),    # D2  ISACTIVER2
        _store_imm_block(GICS_MARKER, d3),              # D3  presence marker (same page)
        gic_read_store_block(GIC_SEND_RECHECK, d4),     # D4  ISPENDR2 again (second page)
        _store_imm_block(GICS_MARKER, d5),              # D5  presence marker (second page)
    ])
    if f_cells:                                         # gicmask: the delivery-configuration sample
        for i in range(4):
            head += gic_read_store_block(GICM_READS[i][0], f_cells[i])          # F0..F3
        head += _store_imm_block(GICM_SENTINEL, f_cells[8])                     # F8 (page 1)
        for i in range(4, GICM_NSAMPLES):
            head += gic_read_store_block(GICM_READS[i][0], f_cells[i])          # F4..F7
        head += _store_imm_block(GICM_SENTINEL, f_cells[9])                     # F9 (page 2)
    if g_cells:                                         # gicking: restore the open mask, then control
        g0, g1, g2, g3 = g_cells
        head += b"".join([
            write_ca_block(GICK_GLUE_MASK, GICK_MASK_OPEN),     # restore the vendor-live open mask
            gic_read_store_block(GICK_GLUE_STATUS, g0),         # G0 status with the mask open (control)
            gic_read_store_block(GICK_GLUE_MASK, g1),           # G1 mask readback (0x20)
            gic_read_store_block(GICD_IGROUPR2, g2),            # G2 IGROUPR word 2 (id 0x4c bit 12)
            _store_imm_block(GICK_SENTINEL, g3),                # G3 page sentinel (after G0..G2)
        ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(2, 1),                       # reproduce `movs r2,#1`
        msr_apsr(12),                     # restore flags for the continuation
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, SEND_CONT)


def pad_send_h(pad: int, h_cells: list[int]) -> bytes:
    """The gicunmask send-site pad (entered at the firmware's own out[1] post, file 0x86F5A).

    Straight line: reproduce the replaced `str r2,[r3]` post FIRST (so the post has happened), then
    read H5 (the ISPENDR2 word-2 entry sample - the NEXT-visit witness), then drive the glue mask
    OPEN (CA 0x400392e8 <= 0x20), then RING the H2D doorbell (CA 0x400392d4 <= 0x1, once), then
    sample H0..H4 (ISPENDR2 / HPPIR / ISACTIVER2 / glue raw / glue post-mask status) and arm the two
    per-page sentinels H6/H7.  H0 is taken a few instructions after the ring - the decisive read.
    r0-r5 are saved/restored, `movs r2,#1` is reproduced as `movw r2,#1`, the saved flags are
    restored and the pad returns to the instruction after the replaced pair.  Nothing else is
    written: never 0x400392f0 (intr-clear), never read 0x4016010c (IAR) or 0x10161000."""
    h0, h1c, h2, h3, h4, h5, hs1, hs2 = h_cells
    head = b"".join([
        mrs_apsr(12),                                   # +0  save condition flags
        push(PAD_SAVE),                                 # +4  24 bytes, keeps SP 8-aligned
        str_imm(2, 3, 0),                               # +6  reproduce `str r2,[r3]` -> the post
        gic_read_store_block(GICD_ISPENDR2, h5),        # H5  entry read (next-visit witness, pre-ring)
        write_ca_block(GICU_GLUE_MASK, GICU_MASK_OPEN),  # (a) open the glue mask (0x20)
        write_ca_block(GICU_RING_CA, GICU_RING_VAL),     # (b) ring the H2D doorbell (0x400392d4 <= 1)
    ])
    body = b"".join([
        gic_read_store_block(GICD_ISPENDR2, h0),        # H0  THE decisive read (ISPENDR2 word 2)
        gic_read_store_block(GICC_HPPIR, h1c),          # H1  GICC HPPIR (non-acknowledging)
        gic_read_store_block(GICD_ISACTIVER2, h2),      # H2  ISACTIVER2 word 2
        gic_read_store_block(GICU_GLUE_RAW, h3),        # H3  glue HOST_INTR_RAW_STATUS
        gic_read_store_block(GICU_GLUE_STATUS, h4),     # H4  glue HOST_INTR_STATUS (post-mask)
        _store_imm_block(GICU_SENTINEL, hs1),           # H6  page-1 sentinel (after H0..H4)
        _store_imm_block(GICU_SENTINEL, hs2),           # H7  page-2 sentinel (after H5)
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(2, 1),                       # reproduce `movs r2,#1`
        msr_apsr(12),                     # restore flags for the continuation
    ])
    back = pad + len(head) + len(body) + len(tail)
    return head + body + tail + b_w(back, SEND_CONT)


def pad_send_trig(pad: int, t_cells: list[int]) -> bytes:
    """The trigring send-site pad (entered at the firmware's own out[1] post, file 0x86F5A).

    Straight line: reproduce the replaced `str r2,[r3]` post FIRST (so the natural post has
    happened), drive the glue mask OPEN (CA 0x400392e8 <= 0x20 - BEFORE both samples, so the only
    thing between the pre and post groups is the ring), then take the PRE-ring samples T0..T3
    (ISPENDR2 word 2 / HPPIR / glue raw / glue status) and the page-1 sentinel TS1, then RING the
    H2D doorbell (CA 0x400392d4 <= 0x1, once - trigger.md section 3's candidate, the value of
    `str rX,[r3 + 0x2C0]` with r3 = 0x40039014 and rX = 1), then take the POST-ring samples T4..T7
    (the same four registers in the same order) and the page-2 sentinel TS2.  r0-r5 are
    saved/restored, `movs r2,#1` is reproduced as `movw r2,#1`, the saved flags are restored and
    the pad returns to the instruction after the replaced pair - so the natural D2H notify at
    0x86F62 runs after the ring, exactly as trigger.md section 3 prescribes.  Nothing else is
    written: never 0x400392f0 (intr-clear), never the masked word 0x21 (the mask stays open);
    never read 0x4016010c (acknowledging IAR) or 0x10161000."""
    t0, t1, t2, t3, t4, t5, t6, t7, ts1, ts2 = t_cells
    head = b"".join([
        mrs_apsr(12),                                    # +0  save condition flags
        push(PAD_SAVE),                                  # +4  24 bytes, keeps SP 8-aligned
        str_imm(2, 3, 0),                                # +6  reproduce `str r2,[r3]` -> the post
        write_ca_block(TRIG_GLUE_MASK, TRIG_MASK_OPEN),  # glue mask OPEN (0x20), before both samples
    ])
    body = b"".join([
        gic_read_store_block(TRIG_READS[0], t0),         # T0  ISPENDR2 word 2 PRE-ring
        gic_read_store_block(TRIG_READS[1], t1),         # T1  HPPIR            PRE-ring
        gic_read_store_block(TRIG_READS[2], t2),         # T2  glue raw         PRE-ring
        gic_read_store_block(TRIG_READS[3], t3),         # T3  glue status      PRE-ring
        _store_imm_block(TRIG_SENTINEL, ts1),            # TS1 page-1 sentinel (after T0..T3)
        write_ca_block(TRIG_RING_CA, TRIG_RING_VAL),     # RING CA 0x400392d4 <= 0x1 (once)
        gic_read_store_block(TRIG_READS[0], t4),         # T4  ISPENDR2 word 2 POST-ring
        gic_read_store_block(TRIG_READS[1], t5),         # T5  HPPIR            POST-ring
        gic_read_store_block(TRIG_READS[2], t6),         # T6  glue raw         POST-ring
        gic_read_store_block(TRIG_READS[3], t7),         # T7  glue status      POST-ring
        _store_imm_block(TRIG_SENTINEL, ts2),            # TS2 page-2 sentinel (after T4..T7)
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(2, 1),                                      # reproduce `movs r2,#1`
        msr_apsr(12),                                    # restore flags for the continuation
    ])
    back = pad + len(head) + len(body) + len(tail)
    return head + body + tail + b_w(back, SEND_CONT)


def pad_send_trignat(pad: int, a_cells: list[int]) -> bytes:
    """The trignat Pad A (entered at the firmware's own natural out[1] post, file 0x86F5A).

    Straight line: the next-visit entry reads A_E0/A_E1 of out[0]/out[1] FIRST (before the post is
    reproduced - the only placement that makes '0 / 4 after a prior visit' true), then reproduce the
    replaced `str r2,[r3]` post, drive the glue mask OPEN (CA 0x400392e8 <= 0x20), perform the H2D
    submission (CA 0x40039010 <= 8, the store `pcie_msg_send` makes), take the pre-ring reads
    A_S0/A_S1/A_S2, RING the H2D doorbell (CA 0x400392d4 <= 0x1, once), take the post-ring reads
    A_S3..A_S8 and arm the page sentinels A_P1/A_P2.  Then r0-r5 are restored, `movs r2,#1` is
    reproduced as `movw r2,#1`, the saved flags are restored and the pad returns to 0x86F5E - so
    the natural D2H notify still runs.  NOTHING else is written: never 0x400392f0 (intr-clear),
    never the masked word 0x21 (the mask stays open); never read 0x4016010c (acknowledging IAR) or
    0x10161000."""
    a_s0_3, a_p1, a_e, a_s4_8, a_p2 = a_cells[0:4], a_cells[4], a_cells[5:7], a_cells[7:12], a_cells[12]
    head = b"".join([
        mrs_apsr(12),                                            # +0  save the condition flags
        push(PAD_SAVE),                                          # +4  24 bytes, SP stays 8-aligned
        gic_read_store_block(TRIGNAT_OUT0_CA, a_e[0]),           # A_E0 entry read of out[0]
        gic_read_store_block(TRIGNAT_OUT1_CA, a_e[1]),           # A_E1 entry read of out[1]
        str_imm(2, 3, 0),                                        # A1  reproduce `str r2,[r3]`
        write_ca_block(TRIGNAT_GLUE_MASK, TRIGNAT_MASK_OPEN),    # A2  glue mask OPEN (0x20)
        write_ca_block(TRIGNAT_OUT0_CA, TRIGNAT_SUBMIT_VAL),     # A3  H2D submission out[0] <= 8
    ])
    body = b"".join([
        gic_read_store_block(TRIGNAT_PRE_READS[0], a_s0_3[0]),   # A_S0 out[0] pre-ring sanity
        gic_read_store_block(TRIGNAT_PRE_READS[1], a_s0_3[1]),   # A_S1 ISPENDR2 w2 pre-ring
        gic_read_store_block(TRIGNAT_PRE_READS[2], a_s0_3[2]),   # A_S2 HPPIR pre-ring
        write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL),       # A7  THE RING (once, never 8)
        gic_read_store_block(TRIGNAT_POST_READS[0], a_s0_3[3]),  # A_S3 ISPENDR2 w2 post-ring
        gic_read_store_block(TRIGNAT_POST_READS[1], a_s4_8[0]),  # A_S4 HPPIR post-ring
        gic_read_store_block(TRIGNAT_POST_READS[2], a_s4_8[1]),  # A_S5 out[0] latency datum
        gic_read_store_block(TRIGNAT_POST_READS[3], a_s4_8[2]),  # A_S6 out[1] (the reproduced post)
        gic_read_store_block(TRIGNAT_POST_READS[4], a_s4_8[3]),  # A_S7 glue raw
        gic_read_store_block(TRIGNAT_POST_READS[5], a_s4_8[4]),  # A_S8 glue status
        _store_imm_block(TRIGNAT_SENTINEL, a_p1),                # A_P1 page-9 sentinel
        _store_imm_block(TRIGNAT_SENTINEL, a_p2),                # A_P2 page-10 sentinel
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(2, 1),                                              # reproduce `movs r2,#1`
        msr_apsr(12),                                            # restore flags for the continuation
    ])
    back = pad + len(head) + len(body) + len(tail)
    return head + body + tail + b_w(back, TRIGNAT_CONT_A)


def pad_drain_trignat(pad: int, b_cells: list[int]) -> bytes:
    """The trignat Pad B (entered at file 0x86F7E, the announce routine's exit after the 0xcece
    handshake wait).  It reads the four drain witnesses B_D0..B_D3 (out[0] - expected 0 after the
    dispatcher consumed the 8; out[1]; ISPENDR2 word 2 - expected bit 12 clear; HPPIR) and arms the
    sentinel B_P3, then reproduces the replaced `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}` and branches to
    0x86F82.  r0-r5 and the flags are saved/restored.  The reproduced pop.w restores the routine's
    own lr from the stack, so the `bl`'s lr clobber is inert."""
    b_d, b_p = b_cells[0:4], b_cells[4]
    head = b"".join([
        mrs_apsr(12),                                            # +0  save the condition flags
        push(PAD_SAVE),                                          # +4  24 bytes, SP stays 8-aligned
        gic_read_store_block(TRIGNAT_B_READS[0], b_d[0]),        # B_D0 out[0] (0 after consumption)
        gic_read_store_block(TRIGNAT_B_READS[1], b_d[1]),        # B_D1 out[1]
        gic_read_store_block(TRIGNAT_B_READS[2], b_d[2]),        # B_D2 ISPENDR2 w2 (bit 12 = taken)
        gic_read_store_block(TRIGNAT_B_READS[3], b_d[3]),        # B_D3 HPPIR
        _store_imm_block(TRIGNAT_SENTINEL, b_p),                 # B_P3 page-10 sentinel (Pad B)
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        msr_apsr(12),                                            # restore flags
        TRIGNAT_DRAIN_POP,                                       # reproduce pop.w {r3..sb,lr}
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, TRIGNAT_CONT_B)


def pad_drain_trigcons(pad: int, b_cells: list[int]) -> bytes:
    """The trigcons Pad B (padb.md section 3 option (a)): the SAME four consumption witnesses
    B_D0..B_D3 + the B_P3 sentinel as trignat, but MOVED to file 0x86F74, the announce wait's own
    `movw r3,#0xcece` - immediately before the loop head 0x86F78, so it is guaranteed to run even
    though nothing completes the 0xcece handshake this boot.  The tail restores r0-r5, RE-EMITS the
    replaced `movw r3,#0xcece` (AFTER the pop, so it survives PAD_SAVE), restores the saved flags
    and branches to 0x86F78 (`ldr r2,[r1]`, the loop head).  r0-r5 (r1 = the CA 0x4000010c spin
    pointer, r5 = the 0xbe0 message object) are saved/restored; only r3 is re-set.  The `bl` at the
    site installs lr = 0x86F78, but the pad ends in a `b.w` to the same address and never returns
    through lr, so the clobber is inert."""
    b_d, b_p = b_cells[0:4], b_cells[4]
    head = b"".join([
        mrs_apsr(12),                                            # +0  save the condition flags
        push(PAD_SAVE),                                          # +4  24 bytes, SP stays 8-aligned
        gic_read_store_block(TRIGNAT_B_READS[0], b_d[0]),        # B_D0 out[0] (8 = still pending)
        gic_read_store_block(TRIGNAT_B_READS[1], b_d[1]),        # B_D1 out[1]
        gic_read_store_block(TRIGNAT_B_READS[2], b_d[2]),        # B_D2 ISPENDR2 w2 (bit 12 = taken)
        gic_read_store_block(TRIGNAT_B_READS[3], b_d[3]),        # B_D3 HPPIR
        _store_imm_block(TRIGNAT_SENTINEL, b_p),                 # B_P3 page-10 sentinel (Pad B)
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(3, 0xcece),                                         # reproduce `movw r3,#0xcece`
        msr_apsr(12),                                            # restore the saved flags
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, TRIGCONS_CONT_B)


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
                pad_p: int | None = None, pad_d: int | None = None,
                drain_site: int | None = None, loop_pad: int | None = None,
                loop_site: int | None = None) -> bytes:
    buf = bytearray(data)
    buf[SITE_THUNK:SITE_THUNK + 4] = bl(SITE_THUNK, pad_i)
    buf[BRINGUP_SITE:BRINGUP_SITE + 4] = bl(BRINGUP_SITE, pad_b)
    if pad_s is not None:
        buf[SEND_SITE:SEND_SITE + 4] = bl(SEND_SITE, pad_s)
    if pad_p is not None:
        buf[POST_SITE:POST_SITE + 4] = bl(POST_SITE, pad_p)
    if pad_d is not None:
        site = TRIGNAT_SITE_B if drain_site is None else drain_site
        buf[site:site + 4] = bl(site, pad_d)
    if loop_pad is not None:
        site = INTA_SITE_L if loop_site is None else loop_site
        buf[site:site + 4] = bl(site, loop_pad)
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
                          apsr_cell: int | None = None, req_cell: int | None = None,
                          f_cells: list[int] | None = None,
                          g_cells: list[int] | None = None) -> dict:
    """gicview verification plus the send-site trampoline: the site must re-disassemble to a bl,
    the pad must reproduce the out[1] post and `movs r2,#1`, and it must carry the three
    device-side GIC read/store blocks into D0/D1/D2 in the documented order.  gicmask passes
    f_cells so the pad is disassembled as it exists: its F block sits between the D block and the
    tail, so a pad built without f_cells would be truncated before the `movs r2,#1` reproduction.
    gicking passes g_cells for the same reason (its ring/discriminator block sits between the D/F
    blocks and the tail)."""
    seen = verify_disasm(data, pad_i, pad_b, s1, s2, gic_cells,
                         apsr_cell=apsr_cell, req_cell=req_cell)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    site = [f"{i.mnemonic} {i.op_str}".strip()
            for i in md.disasm(data[SEND_SITE:SEND_SITE + 4], SEND_SITE)]
    if not (len(site) == 1 and site[0].startswith("bl ")):
        raise PatchError(f"send site 0x{SEND_SITE:x} did not re-disassemble to a bl: {site!r}")

    code_s = pad_send(pad_s, d_cells, f_cells, g_cells)
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
    n_expect = len(GIC_SEND_READS) + 1 + (GICM_NSAMPLES if f_cells else 0) + (3 if g_cells else 0)
    if n_ldr != n_expect:
        raise PatchError(f"expected {n_expect} send-side GIC loads, "
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
                          e_cells: list[int], f_cells: list[int] | None = None,
                          g_cells: list[int] | None = None) -> dict:
    """The gicsend verification (with the gicpost thunk-pad additions) plus the post-write pad:
    the site re-disassembles to a bl, the pad carries the request gate, the request clear, the two
    POST-write GIC read/store blocks and the re-armed sentinel, it holds no `bl` (which would
    clobber the live lr) and its tail is the `b.w` that reproduces the replaced call."""
    seen = verify_disasm_gicsend(data, pad_i, pad_b, pad_s, s1, s2, gic_cells, d_cells,
                                 apsr_cell=e_cells[3], req_cell=e_cells[2], f_cells=f_cells,
                                 g_cells=g_cells)
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


def verify_disasm_gicmask(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int,
                          s1: int, s2: int, gic_cells: list[int], d_cells: list[int],
                          e_cells: list[int], f_cells: list[int],
                          g_cells: list[int] | None = None) -> dict:
    """The gicpost verification PLUS the gicmask additions: the enable-gate pad must carry the F9
    request store, the send pad must carry the eight delivery-configuration read/store blocks (in
    GICM_READS order, F0..F3 before F8, F4..F7 before F9) and the two sentinels, and every F cell
    must be distinct from the earlier ones.  gicking passes g_cells so the send pad is
    disassembled as it exists (with the ring/discriminator block)."""
    if len(f_cells) != GICM_NCELLS:
        raise PatchError(f"gicmask expected {GICM_NCELLS} F cells, got {len(f_cells)}")
    every = [s1, s2] + gic_cells + d_cells + e_cells + f_cells
    if len(set(every)) != len(every):
        raise PatchError("gicmask cells are not all distinct")
    seen = verify_disasm_gicpost(data, pad_i, pad_b, pad_s, pad_p, s1, s2, gic_cells, d_cells,
                                 e_cells, f_cells=f_cells, g_cells=g_cells)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2],
                       f_req_cell=f_cells[9])
    if not any(s.startswith("movw r1, #0xe2e2") for s in seen["thunk_pad"]):
        raise PatchError("gicmask: the gate pad lost the request store")
    if _store_imm_block(GICM_REQUEST, f_cells[9]) not in code_i:
        raise PatchError("gicmask: the gate pad is missing the F9 handshake request")

    code_s = pad_send(pad_s, d_cells, f_cells, g_cells)
    p_s = [f"{i.mnemonic} {i.op_str}".strip()
           for i in md.disasm(data[pad_s:pad_s + len(code_s)], pad_s)]
    if not any(s.startswith("str r2, [r3]") for s in p_s):
        raise PatchError(f"gicmask send pad missing the reproduced out[1] post: {p_s!r}")
    for i, (read_ca, name) in enumerate(GICM_READS):
        block = gic_read_store_block(read_ca, f_cells[i])
        if block not in code_s or block not in data[pad_s:pad_s + len(code_s)]:
            raise PatchError(f"gicmask send pad missing the {name} read CA {read_ca:#x} -> F{i} "
                             f"({f_cells[i]:#x})")
    for slot in (8, 9):
        if _store_imm_block(GICM_SENTINEL, f_cells[slot]) not in code_s:
            raise PatchError(f"gicmask send pad missing the sentinel for F{slot} ({f_cells[slot]:#x})")
    if push(PAD_SAVE) not in code_s or pop(PAD_SAVE) not in code_s:
        raise PatchError("gicmask send pad missing the register save/restore")
    n_ldr = sum(1 for s in p_s if s.startswith("ldr r1, [r1]"))
    n_g = 3 if g_cells else 0
    if n_ldr != len(GIC_SEND_READS) + 1 + GICM_NSAMPLES + n_g:
        raise PatchError(f"gicmask expected {len(GIC_SEND_READS) + 1 + GICM_NSAMPLES + n_g} "
                         f"send-pad loads, disassembly shows {n_ldr}")
    # the F order: F0..F3, then F8, then F4..F7, then F9
    idx = []
    for i in range(4):
        idx.append(code_s.index(gic_read_store_block(GICM_READS[i][0], f_cells[i])))
    idx.append(code_s.index(_store_imm_block(GICM_SENTINEL, f_cells[8])))
    for i in range(4, GICM_NSAMPLES):
        idx.append(code_s.index(gic_read_store_block(GICM_READS[i][0], f_cells[i])))
    idx.append(code_s.index(_store_imm_block(GICM_SENTINEL, f_cells[9])))
    if idx != sorted(idx) or len(set(idx)) != len(idx):
        raise PatchError("gicmask send pad F order is not F0..F3 -> F8 -> F4..F7 -> F9")
    seen["send_pad"] = p_s
    seen["thunk_pad"] = [f"{i.mnemonic} {i.op_str}".strip()
                         for i in md.disasm(data[pad_i:pad_i + len(code_i)], pad_i)]
    return seen


def verify_disasm_gicking(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int,
                          s1: int, s2: int, gic_cells: list[int], d_cells: list[int],
                          e_cells: list[int], f_cells: list[int], g_cells: list[int]) -> dict:
    """The gicmask verification (with the send pad disassembled including its gicking block) PLUS
    the ring checks: the send pad must carry the two glue-mask stores, the H2D ring store, the three
    G reads and the G sentinel, in the order mask-masked -> ring -> D/F samples -> mask-open -> G;
    the doorbell must be rung exactly once; and no gicking pad may address the forbidden CAs
    0x400392f0 (intr-clear) or 0x4016010c (acknowledging IAR)."""
    if len(g_cells) != GICK_NCELLS:
        raise PatchError(f"gicking expected {GICK_NCELLS} G cells, got {len(g_cells)}")
    every = [s1, s2] + gic_cells + d_cells + e_cells + f_cells + g_cells
    if len(set(every)) != len(every):
        raise PatchError("gicking cells are not all distinct")
    seen = verify_disasm_gicmask(data, pad_i, pad_b, pad_s, pad_p, s1, s2, gic_cells, d_cells,
                                 e_cells, f_cells, g_cells=g_cells)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    code_s = pad_send(pad_s, d_cells, f_cells, g_cells)
    p_s = [f"{i.mnemonic} {i.op_str}".strip()
           for i in md.disasm(data[pad_s:pad_s + len(code_s)], pad_s)]

    blk_mask_set = write_ca_block(GICK_GLUE_MASK, GICK_MASK_MASKED)
    blk_ring = write_ca_block(GICK_RING_CA, GICK_RING_VAL)
    blk_mask_open = write_ca_block(GICK_GLUE_MASK, GICK_MASK_OPEN)
    for name, blk in (("mask-masked", blk_mask_set), ("ring", blk_ring),
                      ("mask-open", blk_mask_open)):
        if blk not in code_s or blk not in data[pad_s:pad_s + len(code_s)]:
            raise PatchError(f"gicking send pad missing the {name} store: {p_s!r}")
    for read_ca, cell, nm in ((GICK_GLUE_STATUS, g_cells[0], "G0 status(open)"),
                              (GICK_GLUE_MASK, g_cells[1], "G1 mask(open)"),
                              (GICD_IGROUPR2, g_cells[2], "G2 IGROUPR2")):
        blk = gic_read_store_block(read_ca, cell)
        if blk not in code_s or blk not in data[pad_s:pad_s + len(code_s)]:
            raise PatchError(f"gicking send pad missing {nm}: CA {read_ca:#x} -> {cell:#x}")
    if _store_imm_block(GICK_SENTINEL, g_cells[3]) not in code_s:
        raise PatchError("gicking send pad missing the G3 page sentinel")
    order = [
        code_s.index(blk_mask_set),
        code_s.index(blk_ring),
        code_s.index(gic_read_store_block(GIC_SEND_READS[0], d_cells[0])),
        code_s.index(gic_read_store_block(GICM_READS[0][0], f_cells[0])),
        code_s.index(gic_read_store_block(GICM_READS[5][0], f_cells[5])),
        code_s.index(blk_mask_open),
        code_s.index(gic_read_store_block(GICK_GLUE_STATUS, g_cells[0])),
        code_s.index(gic_read_store_block(GICD_IGROUPR2, g_cells[2])),
        code_s.index(_store_imm_block(GICK_SENTINEL, g_cells[3])),
    ]
    if order != sorted(order) or len(set(order)) != len(order):
        raise PatchError("gicking send pad order is not mask-masked -> ring -> D/F -> mask-open -> G")
    if code_s.count(blk_ring) != 1:
        raise PatchError("gicking send pad must ring the doorbell exactly once")
    for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0)):
        if bad in code_s:
            raise PatchError(f"gicking send pad addresses a forbidden CA: {bad.hex()}")
    seen["send_pad"] = p_s
    seen["gicking"] = {
        "ring_ca": hex(GICK_RING_CA),
        "ring_value": hex(GICK_RING_VAL),
        "mask_masked": hex(GICK_MASK_MASKED),
        "mask_open": hex(GICK_MASK_OPEN),
        "igroupr_ca": hex(GICD_IGROUPR2),
        "igroupr_bit": hex(GICD_IGROUPR_0X4C),
        "disc_cells": {"F5_mask": hex(f_cells[5]), "F6_raw": hex(f_cells[6]),
                       "F7_status": hex(f_cells[7]), "G0_status_open": hex(g_cells[0]),
                       "G1_mask_open": hex(g_cells[1])},
        "igroupr_cell": hex(g_cells[2]),
        "sentinel_cell": hex(g_cells[3]),
    }
    return seen


def verify_disasm_gicunmask(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int,
                            s1: int, s2: int, gic_cells: list[int], e_cells: list[int],
                            h_cells: list[int]) -> dict:
    """Byte-equality of the four pads against their reconstruction PLUS the send pad's block order:
    H5 entry read -> mask-open store -> ring store -> H0..H4 reads -> H6/H7 sentinels.  The ring must
    appear exactly once, H0 must be the FIRST sample after the ring, and no pad may address a
    forbidden CA (0x400392f0 write, 0x4016010c read, 0x10161000 read/write)."""
    if len(h_cells) != GICU_NCELLS:
        raise PatchError(f"gicunmask expected {GICU_NCELLS} H cells, got {len(h_cells)}")
    every = [s1, s2] + gic_cells + e_cells + h_cells
    if len(set(every)) != len(every):
        raise PatchError("gicunmask cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2])
    code_b = pad_bringup(pad_b, s2, gic_cells)
    code_s = pad_send_h(pad_s, h_cells)
    code_p = pad_post(pad_p, e_cells)
    for name, off, code in (("thunk", pad_i, code_i), ("bringup", pad_b, code_b),
                            ("send", pad_s, code_s), ("post", pad_p, code_p)):
        if data[off:off + len(code)] != code:
            raise PatchError(f"the gicunmask {name} pad at {off:#x} is not the intended bytes")

    blk_mask_open = write_ca_block(GICU_GLUE_MASK, GICU_MASK_OPEN)
    blk_ring = write_ca_block(GICU_RING_CA, GICU_RING_VAL)
    for nm, blk in (("mask-open", blk_mask_open), ("ring", blk_ring)):
        if blk not in code_s:
            raise PatchError(f"the gicunmask send pad is missing the {nm} store")
    if code_s.count(blk_ring) != 1:
        raise PatchError("the gicunmask send pad must ring the doorbell exactly once")

    for ca, cell, nm in ((GICD_ISPENDR2, h_cells[0], "H0 ISPENDR2"),
                         (GICC_HPPIR, h_cells[1], "H1 HPPIR"),
                         (GICD_ISACTIVER2, h_cells[2], "H2 ISACTIVER2"),
                         (GICU_GLUE_RAW, h_cells[3], "H3 glue raw"),
                         (GICU_GLUE_STATUS, h_cells[4], "H4 glue status"),
                         (GICD_ISPENDR2, h_cells[5], "H5 ISPENDR2 (entry)")):
        if gic_read_store_block(ca, cell) not in code_s:
            raise PatchError(f"the gicunmask send pad is missing {nm}: CA {ca:#x} -> {cell:#x}")
    for cell, nm in ((h_cells[6], "H6"), (h_cells[7], "H7")):
        if _store_imm_block(GICU_SENTINEL, cell) not in code_s:
            raise PatchError(f"the gicunmask send pad is missing the {nm} page sentinel")

    order = [
        code_s.index(gic_read_store_block(GICD_ISPENDR2, h_cells[5])),      # H5 entry
        code_s.index(blk_mask_open),                                          # mask open
        code_s.index(blk_ring),                                               # ring
        code_s.index(gic_read_store_block(GICD_ISPENDR2, h_cells[0])),        # H0 decisive
        code_s.index(gic_read_store_block(GICC_HPPIR, h_cells[1])),
        code_s.index(gic_read_store_block(GICD_ISACTIVER2, h_cells[2])),
        code_s.index(gic_read_store_block(GICU_GLUE_RAW, h_cells[3])),
        code_s.index(gic_read_store_block(GICU_GLUE_STATUS, h_cells[4])),
        code_s.index(_store_imm_block(GICU_SENTINEL, h_cells[6])),
        code_s.index(_store_imm_block(GICU_SENTINEL, h_cells[7])),
    ]
    if order != sorted(order) or len(set(order)) != len(order):
        raise PatchError("the gicunmask send pad order is not "
                         "H5 -> mask-open -> ring -> H0..H4 -> H6/H7")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s), ("post", code_p)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"the gicunmask {name} pad addresses a forbidden CA: {bad.hex()}")

    seen = {
        "thunk_pad": dis(pad_i, len(code_i)),
        "bringup_pad": dis(pad_b, len(code_b)),
        "send_pad": dis(pad_s, len(code_s)),
        "post_pad": dis(pad_p, len(code_p)),
        "gicunmask": {
            "ring_ca": hex(GICU_RING_CA), "ring_value": hex(GICU_RING_VAL),
            "mask_open": hex(GICU_MASK_OPEN),
            "h_reads": [hex(x) for x in GICU_READS],
            "h5_ca": hex(GICU_H5_CA),
            "h_cells": [hex(c) for c in h_cells],
            "sentinels": [hex(h_cells[6]), hex(h_cells[7])],
            "send_pad_len": len(code_s),
        },
    }
    return seen


def verify_disasm_trigring(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int,
                           s1: int, s2: int, gic_cells: list[int], e_cells: list[int],
                           t_cells: list[int]) -> dict:
    """Byte-equality of the four pads against their reconstruction PLUS the send pad's block order:
    post-reproduce -> mask-open -> T0..T3 (PRE) -> TS1 -> ring -> T4..T7 (POST) -> TS2.  The ring must
    appear exactly once and sit between the pre and post groups, the mask word 0x21 must NOT be
    written, and no pad may address a forbidden CA (0x400392f0 write, 0x4016010c read, 0x10161000
    read/write)."""
    if len(t_cells) != TRIG_NCELLS:
        raise PatchError(f"trigring expected {TRIG_NCELLS} T cells, got {len(t_cells)}")
    every = [s1, s2] + gic_cells + e_cells + t_cells
    if len(set(every)) != len(every):
        raise PatchError("trigring cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2])
    code_b = pad_bringup(pad_b, s2, gic_cells)
    code_s = pad_send_trig(pad_s, t_cells)
    code_p = pad_post(pad_p, e_cells)
    for name, off, code in (("thunk", pad_i, code_i), ("bringup", pad_b, code_b),
                            ("send", pad_s, code_s), ("post", pad_p, code_p)):
        if data[off:off + len(code)] != code:
            raise PatchError(f"the trigring {name} pad at {off:#x} is not the intended bytes")

    blk_mask_open = write_ca_block(TRIG_GLUE_MASK, TRIG_MASK_OPEN)
    blk_ring = write_ca_block(TRIG_RING_CA, TRIG_RING_VAL)
    for nm, blk in (("mask-open", blk_mask_open), ("ring", blk_ring)):
        if blk not in code_s:
            raise PatchError(f"the trigring send pad is missing the {nm} store")
    if code_s.count(blk_ring) != 1:
        raise PatchError("the trigring send pad must ring the doorbell exactly once")
    if write_ca_block(TRIG_GLUE_MASK, GICK_MASK_MASKED) in code_s:
        raise PatchError("the trigring send pad must NOT write the masked word 0x21")

    pre = [gic_read_store_block(TRIG_READS[i], t_cells[i]) for i in range(4)]
    post = [gic_read_store_block(TRIG_READS[i], t_cells[4 + i]) for i in range(4)]
    for nm, blk in [(f"T{i}", pre[i]) for i in range(4)] + [(f"T{4 + i}", post[i]) for i in range(4)]:
        if blk not in code_s:
            raise PatchError(f"the trigring send pad is missing the {nm} read")
    for cell, nm in ((t_cells[8], "TS1"), (t_cells[9], "TS2")):
        if _store_imm_block(TRIG_SENTINEL, cell) not in code_s:
            raise PatchError(f"the trigring send pad is missing the {nm} page sentinel")

    order = [code_s.index(str_imm(2, 3, 0))] + [code_s.index(blk_mask_open)] \
        + [code_s.index(b) for b in pre] + [code_s.index(_store_imm_block(TRIG_SENTINEL, t_cells[8]))] \
        + [code_s.index(blk_ring)] + [code_s.index(b) for b in post] \
        + [code_s.index(_store_imm_block(TRIG_SENTINEL, t_cells[9]))]
    if order != sorted(order) or len(set(order)) != len(order):
        raise PatchError("the trigring send pad order is not post-reproduce -> mask-open -> T0..T3 -> "
                         "TS1 -> ring -> T4..T7 -> TS2")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s), ("post", code_p)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"the trigring {name} pad addresses a forbidden CA: {bad.hex()}")

    seen = {
        "thunk_pad": dis(pad_i, len(code_i)),
        "bringup_pad": dis(pad_b, len(code_b)),
        "send_pad": dis(pad_s, len(code_s)),
        "post_pad": dis(pad_p, len(code_p)),
        "trigring": {
            "ring_ca": hex(TRIG_RING_CA), "ring_value": hex(TRIG_RING_VAL),
            "ring_offset_from_out1": hex(TRIG_RING_OFF),
            "mask_open": hex(TRIG_MASK_OPEN),
            "pre_reads": [hex(x) for x in TRIG_READS],
            "post_reads": [hex(x) for x in TRIG_READS],
            "t_cells": [hex(c) for c in t_cells],
            "sentinels": [hex(t_cells[8]), hex(t_cells[9])],
            "send_pad_len": len(code_s),
        },
    }
    return seen


def verify_disasm_trignat(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int, pad_d: int,
                          s1: int, s2: int, gic_cells: list[int], e_cells: list[int],
                          a_cells: list[int], b_cells: list[int]) -> dict:
    """Byte-equality of the five pads against their reconstruction PLUS the Pad A / Pad B block
    orders: Pad A = entry reads A_E0/A_E1 -> post-reproduce -> mask-open -> submit -> A_S0..A_S2 ->
    ring -> A_S3..A_S8 -> A_P1 -> A_P2; Pad B = B_D0..B_D3 -> B_P3 -> reproduce pop.w.  The ring
    must appear exactly once in Pad A and nowhere in Pad B, the masked word 0x21 must NOT be written,
    the dispatcher-consumption submit (out[0] <= 8) must be present, and no pad may address a
    forbidden CA (0x400392f0 write, 0x4016010c read, 0x10161000 read/write)."""
    if len(a_cells) != TRIGNAT_A_NCELLS:
        raise PatchError(f"trignat expected {TRIGNAT_A_NCELLS} A cells, got {len(a_cells)}")
    if len(b_cells) != TRIGNAT_B_NCELLS:
        raise PatchError(f"trignat expected {TRIGNAT_B_NCELLS} B cells, got {len(b_cells)}")
    every = [s1, s2] + gic_cells + e_cells + a_cells + b_cells
    if len(set(every)) != len(every):
        raise PatchError("trignat cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2])
    code_b = pad_bringup(pad_b, s2, gic_cells)
    code_s = pad_send_trignat(pad_s, a_cells)
    code_p = pad_post(pad_p, e_cells)
    code_d = pad_drain_trignat(pad_d, b_cells)
    for name, off, code in (("thunk", pad_i, code_i), ("bringup", pad_b, code_b),
                            ("send", pad_s, code_s), ("post", pad_p, code_p),
                            ("drain", pad_d, code_d)):
        if data[off:off + len(code)] != code:
            raise PatchError(f"the trignat {name} pad at {off:#x} is not the intended bytes")

    blk_mask_open = write_ca_block(TRIGNAT_GLUE_MASK, TRIGNAT_MASK_OPEN)
    blk_submit = write_ca_block(TRIGNAT_OUT0_CA, TRIGNAT_SUBMIT_VAL)
    blk_ring = write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL)
    for nm, blk in (("mask-open", blk_mask_open), ("H2D submission", blk_submit), ("ring", blk_ring)):
        if blk not in code_s:
            raise PatchError(f"the trignat Pad A is missing the {nm} store")
    if code_s.count(blk_ring) != 1:
        raise PatchError("the trignat Pad A must ring the doorbell exactly once")
    if write_ca_block(TRIGNAT_GLUE_MASK, GICK_MASK_MASKED) in code_s:
        raise PatchError("the trignat Pad A must NOT write the masked word 0x21")

    for ca, cell, nm in ((TRIGNAT_OUT0_CA, a_cells[5], "A_E0 out[0] entry"),
                         (TRIGNAT_OUT1_CA, a_cells[6], "A_E1 out[1] entry"),
                         (TRIGNAT_OUT0_CA, a_cells[0], "A_S0 out[0]"),
                         (GICD_ISPENDR2, a_cells[1], "A_S1 ISPENDR2"),
                         (GICC_HPPIR, a_cells[2], "A_S2 HPPIR"),
                         (GICD_ISPENDR2, a_cells[3], "A_S3 ISPENDR2"),
                         (GICC_HPPIR, a_cells[7], "A_S4 HPPIR"),
                         (TRIGNAT_OUT0_CA, a_cells[8], "A_S5 out[0]"),
                         (TRIGNAT_OUT1_CA, a_cells[9], "A_S6 out[1]"),
                         (TRIGNAT_GLUE_RAW, a_cells[10], "A_S7 glue raw"),
                         (TRIGNAT_GLUE_STATUS, a_cells[11], "A_S8 glue status")):
        if gic_read_store_block(ca, cell) not in code_s:
            raise PatchError(f"the trignat Pad A is missing {nm}: CA {ca:#x} -> {cell:#x}")
    for cell, nm in ((a_cells[4], "A_P1"), (a_cells[12], "A_P2")):
        if _store_imm_block(TRIGNAT_SENTINEL, cell) not in code_s:
            raise PatchError(f"the trignat Pad A is missing the {nm} page sentinel")

    order = [code_s.index(gic_read_store_block(TRIGNAT_OUT0_CA, a_cells[5])),          # A_E0
             code_s.index(gic_read_store_block(TRIGNAT_OUT1_CA, a_cells[6])),          # A_E1
             code_s.index(str_imm(2, 3, 0)),                                           # post reproduce
             code_s.index(blk_mask_open),                                              # mask open
             code_s.index(blk_submit),                                                 # submit
             code_s.index(gic_read_store_block(GICD_ISPENDR2, a_cells[1])),            # A_S1
             code_s.index(blk_ring),                                                   # ring
             code_s.index(gic_read_store_block(GICD_ISPENDR2, a_cells[3])),            # A_S3
             code_s.index(_store_imm_block(TRIGNAT_SENTINEL, a_cells[4])),             # A_P1
             code_s.index(_store_imm_block(TRIGNAT_SENTINEL, a_cells[12]))]            # A_P2
    if order != sorted(order) or len(set(order)) != len(order):
        raise PatchError("the trignat Pad A order is not entry-reads -> post -> mask-open -> submit "
                         "-> A_S0..A_S2 -> ring -> A_S3..A_S8 -> A_P1 -> A_P2")

    for ca, cell, nm in ((TRIGNAT_OUT0_CA, b_cells[0], "B_D0 out[0]"),
                         (TRIGNAT_OUT1_CA, b_cells[1], "B_D1 out[1]"),
                         (GICD_ISPENDR2, b_cells[2], "B_D2 ISPENDR2"),
                         (GICC_HPPIR, b_cells[3], "B_D3 HPPIR")):
        if gic_read_store_block(ca, cell) not in code_d:
            raise PatchError(f"the trignat Pad B is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_imm_block(TRIGNAT_SENTINEL, b_cells[4]) not in code_d:
        raise PatchError("the trignat Pad B is missing the B_P3 page sentinel")
    if TRIGNAT_DRAIN_POP not in code_d:
        raise PatchError("the trignat Pad B must reproduce the replaced `pop.w {r3..sb,lr}`")
    if blk_ring in code_d:
        raise PatchError("the trignat Pad B must not ring the doorbell")
    order_d = [code_d.index(gic_read_store_block(TRIGNAT_B_READS[i], b_cells[i])) for i in range(4)]
    order_d.append(code_d.index(_store_imm_block(TRIGNAT_SENTINEL, b_cells[4])))
    order_d.append(code_d.index(TRIGNAT_DRAIN_POP))
    if order_d != sorted(order_d) or len(set(order_d)) != len(order_d):
        raise PatchError("the trignat Pad B order is not B_D0..B_D3 -> B_P3 -> reproduce pop.w")

    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"the trignat {name} pad addresses a forbidden CA: {bad.hex()}")

    seen = {
        "thunk_pad": dis(pad_i, len(code_i)),
        "bringup_pad": dis(pad_b, len(code_b)),
        "send_pad": dis(pad_s, len(code_s)),
        "post_pad": dis(pad_p, len(code_p)),
        "drain_pad": dis(pad_d, len(code_d)),
        "trignat": {
            "site_a": hex(TRIGNAT_SITE_A), "cont_a": hex(TRIGNAT_CONT_A),
            "site_b": hex(TRIGNAT_SITE_B), "cont_b": hex(TRIGNAT_CONT_B),
            "ring_ca": hex(TRIGNAT_RING_CA), "ring_value": hex(TRIGNAT_RING_VAL),
            "submit_ca": hex(TRIGNAT_OUT0_CA), "submit_value": hex(TRIGNAT_SUBMIT_VAL),
            "out1_ca": hex(TRIGNAT_OUT1_CA),
            "mask_open": hex(TRIGNAT_MASK_OPEN),
            "pre_reads": [hex(x) for x in TRIGNAT_PRE_READS],
            "post_reads": [hex(x) for x in TRIGNAT_POST_READS],
            "b_reads": [hex(x) for x in TRIGNAT_B_READS],
            "a_cells": [hex(c) for c in a_cells],
            "b_cells": [hex(c) for c in b_cells],
            "send_pad_len": len(code_s), "drain_pad_len": len(code_d),
        },
    }
    return seen


def verify_disasm_trigcons(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int,
                           pad_d: int, s1: int, s2: int, gic_cells: list[int],
                           e_cells: list[int], a_cells: list[int], b_cells: list[int]) -> dict:
    """Byte-equality of the five pads against their reconstruction PLUS the Pad A / Pad B block
    orders: Pad A (byte-identical to trignat's) = entry reads A_E0/A_E1 -> post-reproduce ->
    mask-open -> submit -> A_S0..A_S2 -> ring -> A_S3..A_S8 -> A_P1 -> A_P2; Pad B (MOVED, padb.md
    section 3 option (a)) = B_D0..B_D3 -> B_P3 -> pop(PAD_SAVE) -> reproduce `movw r3,#0xcece` and
    branch to the loop head 0x86F78 - it must NOT reproduce the old announce-exit `pop.w`.  The
    ring appears exactly once in Pad A and nowhere in Pad B, the masked word 0x21 must NOT be
    written, the dispatcher-consumption submit (out[0] <= 8) must be present, and no pad may
    address a forbidden CA (0x400392f0 write, 0x4016010c read, 0x10161000 read/write)."""
    if len(a_cells) != TRIGNAT_A_NCELLS:
        raise PatchError(f"trigcons expected {TRIGNAT_A_NCELLS} A cells, got {len(a_cells)}")
    if len(b_cells) != TRIGNAT_B_NCELLS:
        raise PatchError(f"trigcons expected {TRIGNAT_B_NCELLS} B cells, got {len(b_cells)}")
    every = [s1, s2] + gic_cells + e_cells + a_cells + b_cells
    if len(set(every)) != len(every):
        raise PatchError("trigcons cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2])
    code_b = pad_bringup(pad_b, s2, gic_cells)
    code_s = pad_send_trignat(pad_s, a_cells)
    code_p = pad_post(pad_p, e_cells)
    code_d = pad_drain_trigcons(pad_d, b_cells)
    for name, off, code in (("thunk", pad_i, code_i), ("bringup", pad_b, code_b),
                            ("send", pad_s, code_s), ("post", pad_p, code_p),
                            ("drain", pad_d, code_d)):
        if data[off:off + len(code)] != code:
            raise PatchError(f"the trigcons {name} pad at {off:#x} is not the intended bytes")

    blk_mask_open = write_ca_block(TRIGNAT_GLUE_MASK, TRIGNAT_MASK_OPEN)
    blk_submit = write_ca_block(TRIGNAT_OUT0_CA, TRIGNAT_SUBMIT_VAL)
    blk_ring = write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL)
    for nm, blk in (("mask-open", blk_mask_open), ("H2D submission", blk_submit), ("ring", blk_ring)):
        if blk not in code_s:
            raise PatchError(f"the trigcons Pad A is missing the {nm} store")
    if code_s.count(blk_ring) != 1:
        raise PatchError("the trigcons Pad A must ring the doorbell exactly once")
    if write_ca_block(TRIGNAT_GLUE_MASK, GICK_MASK_MASKED) in code_s:
        raise PatchError("the trigcons Pad A must NOT write the masked word 0x21")

    for ca, cell, nm in ((TRIGNAT_OUT0_CA, a_cells[5], "A_E0 out[0] entry"),
                         (TRIGNAT_OUT1_CA, a_cells[6], "A_E1 out[1] entry"),
                         (TRIGNAT_OUT0_CA, a_cells[0], "A_S0 out[0]"),
                         (GICD_ISPENDR2, a_cells[1], "A_S1 ISPENDR2"),
                         (GICC_HPPIR, a_cells[2], "A_S2 HPPIR"),
                         (GICD_ISPENDR2, a_cells[3], "A_S3 ISPENDR2"),
                         (GICC_HPPIR, a_cells[7], "A_S4 HPPIR"),
                         (TRIGNAT_OUT0_CA, a_cells[8], "A_S5 out[0]"),
                         (TRIGNAT_OUT1_CA, a_cells[9], "A_S6 out[1]"),
                         (TRIGNAT_GLUE_RAW, a_cells[10], "A_S7 glue raw"),
                         (TRIGNAT_GLUE_STATUS, a_cells[11], "A_S8 glue status")):
        if gic_read_store_block(ca, cell) not in code_s:
            raise PatchError(f"the trigcons Pad A is missing {nm}: CA {ca:#x} -> {cell:#x}")
    for cell, nm in ((a_cells[4], "A_P1"), (a_cells[12], "A_P2")):
        if _store_imm_block(TRIGNAT_SENTINEL, cell) not in code_s:
            raise PatchError(f"the trigcons Pad A is missing the {nm} page sentinel")

    order = [code_s.index(gic_read_store_block(TRIGNAT_OUT0_CA, a_cells[5])),          # A_E0
             code_s.index(gic_read_store_block(TRIGNAT_OUT1_CA, a_cells[6])),          # A_E1
             code_s.index(str_imm(2, 3, 0)),                                           # post reproduce
             code_s.index(blk_mask_open),                                              # mask open
             code_s.index(blk_submit),                                                 # submit
             code_s.index(gic_read_store_block(GICD_ISPENDR2, a_cells[1])),            # A_S1
             code_s.index(blk_ring),                                                   # ring
             code_s.index(gic_read_store_block(GICD_ISPENDR2, a_cells[3])),            # A_S3
             code_s.index(_store_imm_block(TRIGNAT_SENTINEL, a_cells[4])),             # A_P1
             code_s.index(_store_imm_block(TRIGNAT_SENTINEL, a_cells[12]))]            # A_P2
    if order != sorted(order) or len(set(order)) != len(order):
        raise PatchError("the trigcons Pad A order is not entry-reads -> post -> mask-open -> submit "
                         "-> A_S0..A_S2 -> ring -> A_S3..A_S8 -> A_P1 -> A_P2")

    for ca, cell, nm in ((TRIGNAT_OUT0_CA, b_cells[0], "B_D0 out[0]"),
                         (TRIGNAT_OUT1_CA, b_cells[1], "B_D1 out[1]"),
                         (GICD_ISPENDR2, b_cells[2], "B_D2 ISPENDR2"),
                         (GICC_HPPIR, b_cells[3], "B_D3 HPPIR")):
        if gic_read_store_block(ca, cell) not in code_d:
            raise PatchError(f"the trigcons Pad B is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_imm_block(TRIGNAT_SENTINEL, b_cells[4]) not in code_d:
        raise PatchError("the trigcons Pad B is missing the B_P3 page sentinel")
    if movw(3, 0xcece) not in code_d:
        raise PatchError("the trigcons Pad B must re-emit the replaced `movw r3,#0xcece`")
    if TRIGNAT_DRAIN_POP in code_d:
        raise PatchError("the trigcons Pad B must NOT reproduce the old announce-exit pop.w")
    if b_w(pad_d + len(code_d) - 4, TRIGCONS_CONT_B) != code_d[-4:]:
        raise PatchError("the trigcons Pad B return is not a b.w to the loop head 0x86F78")
    if blk_ring in code_d:
        raise PatchError("the trigcons Pad B must not ring the doorbell")
    order_d = [code_d.index(gic_read_store_block(TRIGNAT_B_READS[i], b_cells[i])) for i in range(4)]
    order_d.append(code_d.index(_store_imm_block(TRIGNAT_SENTINEL, b_cells[4])))
    order_d.append(code_d.index(pop(PAD_SAVE)))
    order_d.append(code_d.index(movw(3, 0xcece)))
    if order_d != sorted(order_d) or len(set(order_d)) != len(order_d):
        raise PatchError("the trigcons Pad B order is not B_D0..B_D3 -> B_P3 -> pop -> "
                         "reproduce `movw r3,#0xcece`")

    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"the trigcons {name} pad addresses a forbidden CA: {bad.hex()}")

    seen = {
        "thunk_pad": dis(pad_i, len(code_i)),
        "bringup_pad": dis(pad_b, len(code_b)),
        "send_pad": dis(pad_s, len(code_s)),
        "post_pad": dis(pad_p, len(code_p)),
        "drain_pad": dis(pad_d, len(code_d)),
        "trigcons": {
            "site_a": hex(TRIGNAT_SITE_A), "cont_a": hex(TRIGNAT_CONT_A),
            "site_b": hex(TRIGCONS_SITE_B), "cont_b": hex(TRIGCONS_CONT_B),
            "old_site_b": hex(TRIGNAT_SITE_B),
            "site_b_replaced": TRIGCONS_SITE_B_BYTES.hex(),
            "ring_ca": hex(TRIGNAT_RING_CA), "ring_value": hex(TRIGNAT_RING_VAL),
            "submit_ca": hex(TRIGNAT_OUT0_CA), "submit_value": hex(TRIGNAT_SUBMIT_VAL),
            "out1_ca": hex(TRIGNAT_OUT1_CA),
            "mask_open": hex(TRIGNAT_MASK_OPEN),
            "pre_reads": [hex(x) for x in TRIGNAT_PRE_READS],
            "post_reads": [hex(x) for x in TRIGNAT_POST_READS],
            "b_reads": [hex(x) for x in TRIGNAT_B_READS],
            "a_cells": [hex(c) for c in a_cells],
            "b_cells": [hex(c) for c in b_cells],
            "send_pad_len": len(code_s), "drain_pad_len": len(code_d),
        },
    }
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


def make_gicmask(data: bytes, barmap: bytes, refs: set[int]):
    """gicpost + the DELIVERY-CONFIGURATION sample: the send pad (file 0x86F5A, the firmware's own
    out[1] post) additionally reads the eight registers of GICM_READS - the CPU interface's
    CTLR/PMR, the distributor's per-id ITARGETSR/IPRIORITYR/ICFGR for id 0x4c, and the glue's
    mask/raw/masked status - into fresh WRAM cells F0..F7, then arms the per-page sentinels F8/F9;
    the enable-gate pad deposits the handshake request into F9 (the gicpost pattern, moved to the
    send pad, which additionally makes F9 an ordering witness)."""
    cells, sel = select_cells_gicmask(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    dc = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICS_NCELLS]
    ec = cells[2 + GICV_NCELLS + GICS_NCELLS:2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS]
    fc = cells[2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS:]
    if len(ec) != GICP_NCELLS or len(fc) != GICM_NCELLS:
        raise PatchError("internal error: gicmask cells were not selected")

    # The send pad is by far the largest (the D block + the eight F reads + the two sentinels) and
    # the largest 0x00 run in the loaded image is 636 bytes, so it is allocated FIRST; the other
    # three pads then take the smaller runs.  (This moves the pads relative to gicpost - the pad
    # CODE is unchanged where it is unchanged, only its address; the frozen gicsend/gicpost blobs
    # are asserted byte-identical in the selftest.)
    need_s = len(pad_send(0, dc, fc))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2], f_req_cell=fc[9]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2], f_req_cell=fc[9])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send(pad_s, dc, fc)
    code_p = pad_post(pad_p, ec)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p)):
        out[off:off + len(code)] = code
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
    seen = verify_disasm_gicmask(out, pad_i, pad_b, pad_s, pad_p, s1, s2, gc, dc, ec, fc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(dc):
        records[f"D{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(fc):
        records[f"F{i}"] = cell_record(barmap, a)

    read_map = {}
    for i, (ca, name) in enumerate(GICM_READS):
        read_map[f"F{i}"] = {"ca": hex(ca), "register": name, "point": "send pad (file 0x86F5A), after the reproduced out[1] post"}
    read_map["F8"] = {"ca": "none", "register": f"sentinel 0x{GICM_SENTINEL:08x}, page 1, after F0..F3"}
    read_map["F9"] = {"ca": "none",
                      "register": f"handshake: request 0x{GICM_REQUEST:08x} (gate pad, id-0x4c path) / "
                                  f"sentinel 0x{GICM_SENTINEL:08x} (send pad, after F4..F7)"}

    manifest = {
        "variant": "gicmask",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICC_base": "0x40160100",
            "never_read": "0x4016010c (GICC IAR - acknowledging) and 0x10161000 (RC misc, a read panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, write-to-clear)",
            "f_read_order": read_map,
            "verification": {
                "method": "every CA re-derived from the image on disk (capstone 5.0.7, Thumb) plus the "
                            "verified vendor-module/sibling quotes in the record; the diag script that "
                            "produced these facts is build/tmp/wifidrv1-art/gm_verify*.py",
                "GICD_base_0x40161000": "firmware literal file 0x716c, loaded into r7 at file 0x6e88 "
                                         "(`ldr r7,[pc,#0x2e0]`), written at file 0x6ed4 (`str.w sl,[r7]`)",
                "GICD_ISENABLER_0x40161100": "firmware literal file 0x87044, loaded at 0x87026 "
                                              "(`ldrlo r3,[pc,#0x1c]`), written at 0x8702c",
                "GICC_page_0x40160100": "firmware literal file 0x8309c (`ldr r3,[pc,#0xc]` at 0x8308c, "
                                        "`str r2,[r3]` with r2 = 1 at 0x8308e = the firmware ENABLES the CPU "
                                        "interface); IAR 0x4016010c = literal file 0x83010 (read at 0x82f04), "
                                        "EoI 0x40160110 = literal file 0x83020 (written at 0x82f52) - the "
                                        "GIC-400 CPU-interface layout at +0x0/+0xC/+0x10",
                "GICC_PMR_0x40160104": "firmware literal file 0x83098, written 0xff at 0x83054 (with BPR "
                                       "0x40160108 = 3 at 0x8305a) - LAYOUT-DERIVED (+0x4 of the page above)",
                "GICD_IPRIORITYR_0x40161400": "firmware literal file 0x7170 (and 0x81a88); id 0x4c is "
                                              "4-byte aligned so F3's word read is aligned",
                "GICD_ITARGETSR_0x40161800": "firmware literal file 0x7174 (and 0x8753c)",
                "GICD_ICFGR_0x40161c00": "firmware literal file 0x715c; word 4 covers ids 0x40..0x4f, "
                                         "id 0x4c's 2-bit field = bits 25:24",
                "GICD_ISPENDR_0x40161200": "phase32's clear pair literal 0x40161280 (ICENABLER 0x40161180 "
                                           "= firmware literal file 0x86e0c, +0x100 mirror) puts the pending "
                                           "block at +0x200; word 2 = 0x40161208",
                "glue_base_0x40039000": "firmware literal file 0x86fb4 (and 0xcf2ac)",
                "glue_mask_0x400392e8": "ctrl-rb +0x2E8 = PCIE_CTRL_RB_HOST_INTR_MASK in the verified "
                                        "sibling header (mp17c pcie_ctrl_rb_regs.h); the vendor's own RMW on "
                                        "it is `ldr r8,[r3,#0x2e8]`/`and r8,r8,#0xfffffc20`/`str r8,[r2,#0x2e8]` "
                                        "(pcie_ete_chn_res); takeover reset 0x3ff, vendor live 0x20 (reg_all.txt)",
                "glue_raw_0x400392e4": "ctrl-rb +0x2E4 = HOST_INTR_RAW_STATUS (sibling header); phase 46 "
                                       "measured bit 0 latching 0->1 on a doorbell write",
                "glue_status_0x400392ec": "ctrl-rb +0x2EC = HOST_INTR_STATUS (sibling header); the vendor "
                                          "ISR reads exactly this offset (`ldr r4,[r3,#0x2ec]` at "
                                          "hi5622v100_plat.ko 0x833c, masked with 0x3d8 at 0x8344)",
                "brief_correction_0x3d8": "the brief's 'glue mask 0x3d8' is NOT an address.  0x3d8 is the "
                                          "MASK CONSTANT the vendor's pcie_intr_handle ANDs with the glue "
                                          "status word (`ands r4, r4, #0x3d8` at hi5622v100_plat.ko 0x8344, "
                                          "immediately after `ldr r4,[r3,#0x2ec]` at 0x833c; 0x3d8 = bits "
                                          "{3,4,6,7,8,9}).  There is no register at ctrl-rb +0x3d8, so F5 "
                                          "uses the glue's real mask register +0x2E8 instead, verified from "
                                          "the sibling header, the vendor's own RMW and the live values.",
            },
            "f5_polarity": "HOST_INTR_MASK bit 0 = host2device_tx_intr_mask: 1 = MASKED, 0 = OPEN "
                           "(`/* mask:1 for mask, 0 for unmask */`, phase 45).  A SET bit 0 is the "
                           "'the glue masks the line' branch; the vendor's own live value 0x20 has bit 0 clear.",
            "cells_note": NOTE_GICM_CELLS,
            "handshake_note": NOTE_GICM_HANDSHAKE,
        },
        "classification": {
            "instrument": "F0..F7 are the DEVICE-side delivery configuration read at the firmware's "
                           "own post; F8/F9 are post-sample sentinels (F9 doubles as the handshake cell).",
            "F0_GICC_CTLR": "bit 0 (EnableGrp0) SET = the CPU interface is enabled (the firmware's own "
                            "write at file 0x8308e makes it 1); CLEAR = THE CPU INTERFACE IS DISABLED - "
                            "candidate root cause (nothing enabled the GICC in this takeover boot)",
            "F1_GICC_PMR": "the priority mask; the firmware writes 0xff (all priorities pass).  A low PMR "
                           "(e.g. 0x00 or below the line's priority) would block delivery at the CPU interface",
            "F2_ITARGETSR": "byte 0 = id 0x4c's target CPU mask; 0 = NO TARGET CPU - candidate root "
                            "cause.  On a uniprocessor GIC-400 this register may be RAZ/WI, so a zero "
                            "here is reported with that caveat rather than as a proven fault",
            "F3_IPRIORITYR": "byte 0 = id 0x4c's priority (0x00 = highest); only meaningful against PMR",
            "F4_ICFGR": "bits 25:24 = id 0x4c's config: 0b01 = edge (default for SPIs), 0b10 = level. "
                        "A level-configured line with its source still asserted, or an edge line whose "
                        "edge never arrives, are the two readings",
            "F5_glue_mask": "bit 0 SET = the glue MASKS the H2D line (candidate root, since the vendor's "
                            "live value 0x20 leaves it clear); CLEAR = the mask is open",
            "F6_glue_raw": "bit 0 SET = the H2D event reached the ctrl-rb interrupt stage (the glue DOES "
                           "latch the line); CLEAR = at the sampled post the line never reached the glue "
                           "(an upstream finding - and the expected reading in a boot that rings no "
                           "doorbell).  bit 3 = the D2H direction (latched 1 by the boot dialogue in "
                           "phase 46)",
            "F7_glue_status": "the post-mask word the vendor ISR reads under 0x3d8; bit 0 = 1 only when F6 "
                              "bit 0 is set AND F5 bit 0 is clear",
            "F9_handshake": {
                hex(GICM_SENTINEL): "the send pad ran AFTER the id-0x4c enable pass (the F sample is "
                                    "post-enable)",
                hex(GICM_REQUEST): "the enable pass came after the last post - the F sample predates it",
                "0x0": "no id-0x4c enable pass happened in this boot",
            },
            "unmatchable": "0xffffffff anywhere = not decoded: report it as its own finding, never read it "
                           "as an architectural value",
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
             "note": "the firmware's own `bl #0xbdf50` at the first post-store boundary outside the "
                     "`itet lo` block (gicpost); the pad contains no `bl` and ends `b.w 0xbdf50`"},
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


def make_gicking(data: bytes, barmap: bytes, refs: set[int]):
    """gicmask + the H2D RING, the polarity discriminator and the GICD_IGROUPR read (NOTE_GICK_*).

    The send pad (the firmware's own out[1] post, file 0x86F5A) first stores the masked glue word
    0x21 into CA 0x400392e8, rings the H2D doorbell (CA 0x400392d4 <= 0x1, bit 0 - ring.md's
    fallback actor, immediately before the GIC sample), then takes the D/F samples (post-ring; F5 =
    the masked readback, F6 = raw, F7 = post-mask status) and finally restores the vendor-live open
    mask 0x20 and reads the control group G0..G2 (status with the mask open, mask readback,
    GICD_IGROUPR word 2 for id 0x4c) plus the page sentinel G3."""
    cells, sel = select_cells_gicking(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    dc = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICS_NCELLS]
    ec = cells[2 + GICV_NCELLS + GICS_NCELLS:2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS]
    fc = cells[2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS:
              2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS + GICM_NCELLS]
    gg = cells[2 + GICV_NCELLS + GICS_NCELLS + GICP_NCELLS + GICM_NCELLS:]
    if len(ec) != GICP_NCELLS or len(fc) != GICM_NCELLS or len(gg) != GICK_NCELLS:
        raise PatchError("internal error: gicking cells were not selected")

    need_s = len(pad_send(0, dc, fc, gg))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2], f_req_cell=fc[9]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2], f_req_cell=fc[9])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send(pad_s, dc, fc, gg)
    code_p = pad_post(pad_p, ec)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p)):
        out[off:off + len(code)] = code
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

    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s), ("post", code_p)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0)):
            if bad in code:
                raise PatchError(f"internal error: the gicking {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    seen = verify_disasm_gicking(out, pad_i, pad_b, pad_s, pad_p, s1, s2, gc, dc, ec, fc, gg)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(dc):
        records[f"D{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(fc):
        records[f"F{i}"] = cell_record(barmap, a)
    for i, a in enumerate(gg):
        records[f"G{i}"] = cell_record(barmap, a)

    read_map = {}
    for i, (ca, gname) in enumerate(GICM_READS):
        read_map[f"F{i}"] = {"ca": hex(ca), "register": gname,
                              "point": "send pad, after the ring (post-ring)"}
    read_map["F8"] = {"ca": "none",
                      "register": f"sentinel 0x{GICM_SENTINEL:08x}, page 1, after F0..F3"}
    read_map["F9"] = {"ca": "none",
                      "register": f"handshake: request 0x{GICM_REQUEST:08x} (gate pad, id-0x4c "
                                  f"path) / sentinel 0x{GICM_SENTINEL:08x} (send pad, after F4..F7)"}
    g_map = {
        "G0": {"ca": hex(GICK_GLUE_STATUS), "register": "glue HOST_INTR_STATUS (+0x2ec), mask OPEN",
               "point": "send pad, after the mask is restored to 0x20 (the discriminator control)"},
        "G1": {"ca": hex(GICK_GLUE_MASK), "register": "glue HOST_INTR_MASK (+0x2e8) readback",
               "point": "send pad, mask restored (0x20)"},
        "G2": {"ca": hex(GICD_IGROUPR2),
               "register": "GICD_IGROUPR word 2 (bit 12 = id 0x4c)",
               "point": "send pad, the group-gate check (addr.md)"},
        "G3": {"ca": "none", "register": f"sentinel 0x{GICK_SENTINEL:08x}, the G page",
               "point": "after G0..G2"},
    }

    manifest = {
        "variant": "gicking",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICC_base": "0x40160100",
            "GICD_IGROUPR2": hex(GICD_IGROUPR2),
            "GICD_IGROUPR_0X4C_bit": hex(GICD_IGROUPR_0X4C),
            "never_read": "0x4016010c (GICC IAR - acknowledging; a read acknowledges) and "
                          "0x10161000 (RC misc, a read panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, write-to-clear)",
            "ring": {"ca": hex(GICK_RING_CA), "value": hex(GICK_RING_VAL),
                     "register": "ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])",
                     "note": NOTE_GICK_RING},
            "glue": {"raw": hex(GICK_GLUE_RAW), "mask": hex(GICK_GLUE_MASK),
                     "status": hex(GICK_GLUE_STATUS),
                     "mask_masked": hex(GICK_MASK_MASKED), "mask_open": hex(GICK_MASK_OPEN),
                     "note": NOTE_GICK_DISC},
            "f_read_order": read_map,
            "g_read_order": g_map,
            "igroupr_note": NOTE_GICK_IGROUPR,
            "verification": {
                "method": "every CA re-derived from the image on disk (capstone, Thumb) plus the "
                            "verified vendor-module/sibling quotes in the record; the ring and "
                            "discriminator CAs are the ctrl-rb glue offsets of phase 45/46/47 and "
                            "the ring value is ring.md section 0; the IGROUPR CA is addr.md "
                            "section 1 (GICD base 0x40161000 + 0x080 + 4*2)",
                "GICD_base_0x40161000": "firmware literal file 0x716c, loaded into r7 at file 0x6e88, "
                                         "written 1 at file 0x6ed4",
                "GICD_ISENABLER_0x40161100": "firmware literal file 0x87044, loaded at 0x87026, written "
                                              "at 0x8702c",
                "GICD_IGROUPR2_0x40161088": "GICD base + 0x080 (the IGROUPR bank) + 4*2; the image "
                                             "holds NO IGROUPR literal (addr.md section 1d), so this "
                                             "is doc-anchored exactly as phase32/phase49 anchored "
                                             "the ISENABLER word 0x40161108",
                "GICC_page_0x40160100": "firmware literal file 0x8309c (written 1 at 0x8308e); IAR "
                                        "0x4016010c = literal file 0x83010, EoI 0x40160110 = literal "
                                        "file 0x83020",
                "glue_base_0x40039000": "firmware literal file 0x86fb4 (and 0xcf2ac); the ctrl-rb "
                                        "+0x2d4/+0x2e4/+0x2e8/+0x2ec offsets are the sibling header's "
                                        "HOST2DEVICE_INTR_SET / HOST_INTR_RAW_STATUS / HOST_INTR_MASK "
                                        "/ HOST_INTR_STATUS, measured live in phase 46/47",
                "ring_value_0x1": "ring.md section 0: bit 0 = host2device_tx doorbell; bit 3 (0x8) is "
                                  "the firmware dispatcher's own re-arm constant, NOT the H2D ring",
            },
            "f5_polarity": "HOST_INTR_MASK bit 0 = host2device_tx_intr_mask: 1 = MASKED, 0 = OPEN.  "
                           "gicking drives it explicitly (0x21 masked, then 0x20 open) so the "
                           "polarity is witnessed in-run: F5/F6/F7 are the masked samples, G0/G1 the "
                           "open ones.",
            "cells_note": NOTE_GICK_CELLS,
            "handshake_note": NOTE_GICM_HANDSHAKE,
        },
        "classification": {
            "instrument": "The send pad rings the H2D doorbell (CA 0x400392d4 <= 0x1) and then "
                           "samples: F0 GICC_CTLR, F5/F6/F7 the glue mask/raw/status (post-ring, "
                           "MASKED at 0x21), D0 ISPENDR2 word 2, D1 HPPIR, D2 ISACTIVER2; then it "
                           "restores the open mask and reads G0 (status open) / G1 (mask open) / G2 "
                           "(GICD_IGROUPR word 2 for id 0x4c).  G3 is the page sentinel.",
            "check1_ring": "F6 bit 0 = 1 means the ring reached the ctrl-rb raw latch (the doorbell "
                            "is write-only; its readback is 0 by construction).  F6 bit 0 = 0 with an "
                            "intact F8/F9/G3 sentinel means the ring did not latch at the glue.",
            "check2_glue": "F5 = the mask readback (0x21 proves the controlled knob landed), F6 = "
                            "raw, F7 = post-mask status; G0 = status with the mask open, G1 = the "
                            "restored mask readback.",
            "check3_igroupr": {
                "G2_bit12_set_0x1000": "id 0x4c is Group 1; with GICC_CTLR = 0x1 (F0, EnableGrp0 "
                                       "only) the line CANNOT signal to the CPU - the group gate "
                                       "is a real root cause (addr.md row A)",
                "G2_bit12_clear": "id 0x4c is Group 0 - that group is enabled at the CPU interface "
                                   "(F0 bit 0), so the group gate DIES and the remaining root is "
                                   "the event assertion (addr.md row B)",
                "G2_unreadable": "0xffffffff / a value that does not decode = report as its own "
                                  "finding, never read as an architectural value",
            },
            "polarity_discriminator": {
                "record_model_1_is_masked": "F6 bit 0 = 1 while F7 bit 0 = 0 (raw rises, the masked "
                                            "post-mask status stays clear) and then G0 bit 0 = 1 "
                                            "once the mask is open - the record's model, "
                                            "re-derived in-run",
                "inverted_model": "F7 bit 0 = 1 with the mask still set at 0x21 (the passing line "
                                   "follows the SET mask bit)",
                "independent_raw_latch": "F7 bit 0 = 1 as well (the mask does not gate the status "
                                          "word at all)",
                "prediction_note": "F5/F6/F7 are the MASKED samples and G0/G1 the OPEN ones; the "
                                   "three models are separated by the F6-vs-F7-vs-G0 triple in this "
                                   "single boot (polarity.md section 3)",
            },
            "bounds": "one-shot latched samples, not a timing window; the ring is rung once per "
                      "send-pad run; F1..F4 (PMR/ITARGETSR/IPRIORITYR/ICFGR) are the gicmask "
                      "delivery-configuration reads and are unchanged; the mask is restored to the "
                      "vendor-live 0x20 before the pad returns.",
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
             "after": bl(SEND_SITE, pad_s).hex(),
             "note": "the send pad reproduces the out[1] post, then RINGS the H2D doorbell "
                     "(CA 0x400392d4 <= 0x1) and samples the glue + GIC (see NOTE_GICK_RING / "
                     "NOTE_GICK_DISC); the gicmask D/F sample blocks are kept and are now the "
                     "post-ring samples"},
            {"kind": "trampoline-entry", "region": "enable-thunk post-store boundary 0x87036",
             "file_offset": hex(POST_SITE), "before": data[POST_SITE:POST_SITE + 4].hex(),
             "after": bl(POST_SITE, pad_p).hex(),
             "note": "the firmware's own `bl #0xbdf50`; the pad samples ISENABLER2/ISPENDR2 "
                     "post-write (E0/E1) and reproduces the call as a `b.w` with lr untouched"},
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


def make_gicunmask(data: bytes, barmap: bytes, refs: set[int]):
    """gicking's open step R2 as a variant: the send pad rings the H2D doorbell with the glue mask
    OPEN and samples ISPENDR2/HPPIR/ISACTIVER2/glue-raw/glue-status immediately (H0..H4), re-reads
    ISPENDR2 at the next post (H5) and arms one sentinel per used page (H6/H7).  The thunk/bring-up/
    post pads are byte-identical to gicpost's, so S1/S2/C0..C5/E0..E3 keep their earlier addresses
    and the ISENABLER/E0 sanity still proves the id-0x4c enable store landed."""
    cells, sel = select_cells_gicunmask(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    hc = cells[2 + GICV_NCELLS + GICP_NCELLS:2 + GICV_NCELLS + GICP_NCELLS + GICU_NCELLS]
    if len(ec) != GICP_NCELLS or len(hc) != GICU_NCELLS:
        raise PatchError("internal error: gicunmask cells were not selected")

    need_s = len(pad_send_h(0, hc))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send_h(pad_s, hc)
    code_p = pad_post(pad_p, ec)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p)):
        out[off:off + len(code)] = code
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
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s), ("post", code_p)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0)):
            if bad in code:
                raise PatchError(f"internal error: the gicunmask {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    seen = verify_disasm_gicunmask(out, pad_i, pad_b, pad_s, pad_p, s1, s2, gc, ec, hc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(hc):
        records[f"H{i}"] = cell_record(barmap, a)

    h_read_map = {}
    for i, ca in enumerate(GICU_READS):
        h_read_map[f"H{i}"] = {"ca": hex(ca),
                               "register": ("GICD_ISPENDR2 word 2 (bit 12 = id 0x4c) - THE decisive "
                                            "read" if i == 0 else
                                            "GICC HPPIR (0x3ff = nothing pending; non-acknowledging)"
                                            if i == 1 else
                                            "GICD_ISACTIVER2 word 2 (bit 12 = delivered/active)"
                                            if i == 2 else
                                            "glue HOST_INTR_RAW_STATUS (+0x2e4)" if i == 3 else
                                            "glue HOST_INTR_STATUS (+0x2ec, post-mask)"),
                               "point": "send pad, immediately after the ring (mask OPEN)"}
    h_read_map["H5"] = {"ca": hex(GICU_H5_CA),
                        "register": "GICD_ISPENDR2 word 2 re-read at the NEXT send-site visit",
                        "point": "send pad entry, before this visit's mask write and ring"}
    h_read_map["H6"] = {"ca": "none", "register": f"sentinel 0x{GICU_SENTINEL:08x}, page 1 (H0..H4)",
                        "point": "send pad, after H0..H4"}
    h_read_map["H7"] = {"ca": "none", "register": f"sentinel 0x{GICU_SENTINEL:08x}, page 2 (H5)",
                        "point": "send pad, after H6"}

    manifest = {
        "variant": "gicunmask",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICC_base": "0x40160100",
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICD_ISACTIVER2": hex(GICD_ISACTIVER2),
            "GICC_HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging; a read acknowledges) and "
                          "0x10161000 (RC misc, a read panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, write-to-clear)",
            "ring": {"ca": hex(GICU_RING_CA), "value": hex(GICU_RING_VAL),
                     "register": "ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])",
                     "note": NOTE_GICU_UNMASK},
            "glue": {"raw": hex(GICU_GLUE_RAW), "mask": hex(GICU_GLUE_MASK),
                     "status": hex(GICU_GLUE_STATUS), "mask_open": hex(GICU_MASK_OPEN),
                     "note": "the mask is driven to the documented OPEN value 0x20 (bit 0 = 0, "
                             "bit 5 held) and left there - the vendor-live state; no restore needed."},
            "h_read_order": h_read_map,
            "h5_note": NOTE_GICU_H5,
            "cells_note": NOTE_GICU_H_CELLS,
            "verification": {
                "method": "every CA re-derived from the image on disk (capstone, Thumb) plus the "
                            "verified vendor-module/sibling quotes in the record; the ring and the "
                            "glue offsets are the ctrl-rb glue offsets of phase 45/46/47 and the "
                            "ring value is ring.md section 0",
                "GICD_ISPENDR2_0x40161208": "GICD base 0x40161000 (firmware literal file 0x716c, "
                                             "loaded at 0x6e88, written at 0x6ed4) + 0x200 + 4*2; "
                                             "the same id->word/bit step that lands the ISENABLER "
                                             "word at 0x40161108 (literal file 0x87044)",
                "GICD_ISACTIVER2_0x40161308": "GICD base + 0x300 + 4*2 (phase32's clear pair "
                                               "0x40161180/0x40161280 pins the +0x80/+0x200 banks)",
                "GICC_page_0x40160100": "firmware literal file 0x8309c (written 1 at 0x8308e); IAR "
                                        "0x4016010c = literal file 0x83010, EoI 0x40160110 = "
                                        "literal file 0x83020 -> HPPIR = base+0x18 = 0x40160118",
                "glue_base_0x40039000": "firmware literal file 0x86fb4 (and 0xcf2ac); the ctrl-rb "
                                        "+0x2d4/+0x2e4/+0x2e8/+0x2ec offsets are the sibling "
                                        "header's HOST2DEVICE_INTR_SET / HOST_INTR_RAW_STATUS / "
                                        "HOST_INTR_MASK / HOST_INTR_STATUS, measured live in "
                                        "phase 46/47",
                "mask_polarity": "HOST_INTR_MASK bit 0: 1 = masked, 0 = open - re-derived in-run by "
                                 "the gicking discriminator (F6 bit0 = 1 while F7 bit0 = 0 masked, "
                                 "then G0 bit0 = 1 once open); gicunmask drives the OPEN value 0x20",
                "ring_value_0x1": "ring.md section 0: bit 0 = host2device_tx doorbell; bit 3 (0x8) "
                                  "is the firmware dispatcher's own re-arm constant, NOT the H2D ring",
            },
        },
        "classification": {
            "instrument": "The send pad opens the glue mask (CA 0x400392e8 <= 0x20), rings the H2D "
                           "doorbell (CA 0x400392d4 <= 0x1, once) and samples H0 = ISPENDR2 word 2 "
                           "(bit 12 = source id 0x4c), H1 = HPPIR, H2 = ISACTIVER2 word 2, H3 = glue "
                           "raw, H4 = glue post-mask status; H5 re-reads ISPENDR2 at the next post; "
                           "H6/H7 are the per-page presence sentinels.",
            "branch_H0_bit12_set": "the ringed event REACHES the GIC - H0 bit 12 SET means the "
                                    "distributor's pending bit for id 0x4c rose on the ringed line "
                                    "while the glue mask was OPEN, so the wire is ALIVE when rung; "
                                    "the open question then becomes why the natural posts never "
                                    "raise it.",
            "branch_H0_clear_H3_H4_set": "the glue latches AND passes the line (H3 raw bit 0 = 1 and "
                                          "H4 post-mask status bit 0 = 1 at the same instant as H0) "
                                          "but the GIC never sees it (H0 bit 12 clear) -> THE "
                                          "GLUE->GIC WIRE IS THE DEAD LINK.",
            "branch_H0_clear_H5_set": "DELAYED DELIVERY - H0 bit 12 clear but H5 bit 12 SET means the "
                                       "pending bit rose by the next post, so the instant sample, "
                                       "not the wire, was the issue (delivery latency).",
            "branch_H0_clear_H3_H4_clear": "the ring did not even reach the glue status (H3 and H4 "
                                            "clear) - that contradicts gicking's own F6 = 0x1 and "
                                            "would be its own finding.",
            "branch_H0_H5_clear": "not delivered within the sampled instant and one post interval - "
                                  "a bounded negative, not a proof (the samples are instant, not a "
                                  "timing window).",
            "h5_void_if_single_visit": "if the send site is visited only once in this boot, H5 is the "
                                        "single visit's pre-ring read and is VOID for the delayed "
                                        "branch; the intact H7 sentinel next to a zero H5 says so.",
            "sanities": "S1/S1+4/S2/S2+4/C0..C5 and E0..E3 are byte-identical to gicpost's pads; "
                        "E0 = 0x1001 (ISENABLER2 word-2 POST-write, bit 12 set) proves the firmware's "
                        "own id-0x4c enable store landed in this boot.",
            "bounds": "one-shot latched samples, not a timing window; the ring is rung once per "
                      "send-pad run; the mask is driven to and left at the vendor-live 0x20.",
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
             "after": bl(SEND_SITE, pad_s).hex(),
             "note": "the gicunmask send pad reproduces the out[1] post, reads H5 (entry), drives the "
                     "glue mask OPEN (0x400392e8 <= 0x20), RINGS the H2D doorbell "
                     "(0x400392d4 <= 0x1) and samples H0..H4 (see NOTE_GICU_UNMASK)"},
            {"kind": "trampoline-entry", "region": "enable-thunk post-store boundary 0x87036",
             "file_offset": hex(POST_SITE), "before": data[POST_SITE:POST_SITE + 4].hex(),
             "after": bl(POST_SITE, pad_p).hex(),
             "note": "the firmware's own `bl #0xbdf50`; the pad samples ISENABLER2/ISPENDR2 "
                     "post-write (E0/E1) and reproduces the call as a `b.w` with lr untouched"},
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


def make_trigring(data: bytes, barmap: bytes, refs: set[int]):
    """trigger.md section 3's candidate ring at the firmware's own natural post, with the PRE-ring
    and POST-ring samples taken in the SAME visit (T0..T3 then T4..T7) and one sentinel per used
    page (TS1/TS2).  The thunk/bring-up/post pads are byte-identical to gicpost's, so S1/S2/C0..C5
    and E0..E3 keep their earlier addresses and E0 = 0x1001 (the ISENABLER2 word-2 POST-write
    readback) still proves the firmware's own id-0x4c enable store landed."""
    cells, sel = select_cells_trigring(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    tc = cells[2 + GICV_NCELLS + GICP_NCELLS:2 + GICV_NCELLS + GICP_NCELLS + TRIG_NCELLS]
    if len(ec) != GICP_NCELLS or len(tc) != TRIG_NCELLS:
        raise PatchError("internal error: trigring cells were not selected")

    need_s = len(pad_send_trig(0, tc))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send_trig(pad_s, tc)
    code_p = pad_post(pad_p, ec)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p)):
        out[off:off + len(code)] = code
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
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s), ("post", code_p)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0)):
            if bad in code:
                raise PatchError(f"internal error: the trigring {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    seen = verify_disasm_trigring(out, pad_i, pad_b, pad_s, pad_p, s1, s2, gc, ec, tc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(tc):
        records[f"T{i}"] = cell_record(barmap, a)

    t_read_map = {}
    for i, ca in enumerate(TRIG_READS):
        reg = ("GICD_ISPENDR2 word 2 (bit 12 = id 0x4c)" if i == 0 else
               "GICC HPPIR (0x3ff = nothing pending; non-acknowledging)" if i == 1 else
               "glue HOST_INTR_RAW_STATUS (+0x2e4)" if i == 2 else
               "glue HOST_INTR_STATUS (+0x2ec, post-mask)")
        t_read_map[f"T{i}"] = {"ca": hex(ca), "register": reg,
                               "point": "send pad, PRE-ring (mask OPEN, after the reproduced post)"}
        t_read_map[f"T{4 + i}"] = {"ca": hex(ca), "register": reg,
                                   "point": "send pad, POST-ring (the same instant block, after CA "
                                            "0x400392d4 <= 0x1)"}
    t_read_map["T8"] = {"ca": "none", "register": f"sentinel 0x{TRIG_SENTINEL:08x}, page 1 (T0..T3)",
                        "point": "send pad, after T0..T3, before the ring"}
    t_read_map["T9"] = {"ca": "none", "register": f"sentinel 0x{TRIG_SENTINEL:08x}, page 2 (T4..T7)",
                        "point": "send pad, after T4..T7 (last instruction before the return)"}

    manifest = {
        "variant": "trigring",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICC_base": "0x40160100",
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICC_HPPIR": hex(GICC_HPPIR),
            "GICD_ISACTIVER2": hex(GICD_ISACTIVER2),
            "never_read": "0x4016010c (GICC IAR - acknowledging; a read acknowledges) and "
                          "0x10161000 (RC misc, a read panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, write-to-clear) and the masked glue "
                             "word 0x21 (the mask stays OPEN across the ring)",
            "ring": {"ca": hex(TRIG_RING_CA), "value": hex(TRIG_RING_VAL),
                     "register": "ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2])",
                     "trigger_md_candidate": "trigger.md section 3: `str rX,[r3 + 0x2C0]` with "
                                            f"r3 = 0x40039014 and rX = 1 -> {hex(TRIG_RING_CA)} <= 1 "
                                            f"(offset {hex(TRIG_RING_OFF)}); written directly per "
                                            "the task's allowance at the firmware's own natural post",
                     "note": NOTE_TRIG_RING},
            "glue": {"raw": hex(TRIG_GLUE_RAW), "mask": hex(TRIG_GLUE_MASK),
                     "status": hex(TRIG_GLUE_STATUS), "mask_open": hex(TRIG_MASK_OPEN),
                     "note": "the mask is driven to the documented OPEN value 0x20 (bit 0 = 0, "
                             "bit 5 held) BEFORE both samples and left there - the vendor-live state; "
                             "the masked word 0x21 is never written."},
            "t_read_order": t_read_map,
            "prepost_note": NOTE_TRIG_PREPOST,
            "cells_note": NOTE_TRIG_CELLS,
            "verification": {
                "method": "every CA re-derived from the image on disk (capstone, Thumb) plus the "
                            "verified vendor-module/sibling quotes in the record; the ring and the "
                            "glue offsets are the ctrl-rb glue offsets of phase 45/46/47 and the "
                            "ring value is ring.md section 0; the site is the firmware's own out[1] "
                            "post (phase38's exhaustive address-provenance scan)",
                "GICD_ISPENDR2_0x40161208": "GICD base 0x40161000 (firmware literal file 0x716c, "
                                             "loaded at 0x6e88, written at 0x6ed4) + 0x200 + 4*2; "
                                             "the same id->word/bit step that lands the ISENABLER "
                                             "word at 0x40161108 (literal file 0x87044)",
                "GICC_page_0x40160100": "firmware literal file 0x8309c (written 1 at 0x8308e); IAR "
                                        "0x4016010c = literal file 0x83010, EoI 0x40160110 = "
                                        "literal file 0x83020 -> HPPIR = base+0x18 = 0x40160118",
                "glue_base_0x40039000": "firmware literal file 0x86fb4 (and 0xcf2ac); the ctrl-rb "
                                        "+0x2d4/+0x2e4/+0x2e8/+0x2ec offsets are the sibling "
                                        "header's HOST2DEVICE_INTR_SET / HOST_INTR_RAW_STATUS / "
                                        "HOST_INTR_MASK / HOST_INTR_STATUS, measured live in "
                                        "phase 46/47; 0x40039014 (out[1]) is the literal at file "
                                        "0x86fbc and 0x40039014 + 0x2c0 = 0x400392d4 (trigger.md 3)",
                "ring_value_0x1": "ring.md section 0: bit 0 = host2device_tx doorbell; bit 3 (0x8) "
                                  "is the firmware dispatcher's own re-arm constant (file 0x818c4) "
                                  "and is NEVER written by this variant",
                "no_firmware_ring_site": "trigger.md section 1: the image holds NO bit-0 store to "
                                         "0x400392d4 (0 literal hits; the only store, file 0x818c4, "
                                         "writes 8 = bit 3) - hence the pad stand-in the task "
                                         "prescribes",
            },
        },
        "classification": {
            "instrument": "The send pad reproduces the firmware's own out[1] post, opens the glue "
                           "mask (0x400392e8 <= 0x20), samples T0..T3 (ISPENDR2 word 2, HPPIR, glue "
                           "raw, glue status) PRE-ring, rings the H2D doorbell (0x400392d4 <= 0x1, "
                           "once - trigger.md 3's candidate), samples T4..T7 POST-ring and arms the "
                           "page sentinels TS1/TS2.  The natural D2H notify at 0x86F62 runs after the "
                           "ring (the pad returns to 0x86F5E).",
            "branch_T4_bit12_set": "the ringed event REACHES the GIC: the post-ring sample's "
                                    "ISPENDR2 word 2 has bit 12 set while the pre-ring sample did "
                                    "not - the ring->GIC step proven with the mask open in the "
                                    "SAME visit (the delta gicunmask could not isolate).",
            "branch_T4_clear_T6_T7_set": "the glue latches AND passes the line (T6 glue raw bit 0 = 1 "
                                          "and T7 post-mask status bit 0 = 1 at the same instant) "
                                          "but the GIC never sees it (T4 bit 12 clear) -> THE "
                                          "GLUE->GIC WIRE IS THE DEAD LINK.",
            "branch_T0_set": "the pending bit was ALREADY set before the ring (a pre-existing "
                              "latch, e.g. the boot dialogue) - the post sample is then not "
                              "attributable to this ring alone.",
            "branch_both_clear": "not delivered within the sampled instant - a bounded negative, "
                                  "not a proof (the samples are instant, not a timing window).",
            "sanities": "S1/S1+4/S2/S2+4/C0..C5 and E0..E3 are byte-identical to gicpost's pads; "
                        "E0 = 0x1001 (ISENABLER2 word-2 POST-write, bit 12 set) proves the firmware's "
                        "own id-0x4c enable store landed in this boot.",
            "host_side": "The capture hook ALSO runs the hostisr.md section 2 read-only host "
                         "witness (grep -E '^(207|209):' /proc/interrupts, the full /proc/interrupts, "
                         "the /sys irq files, lspci config-space reads, and dmesg grep -Ei "
                         "'omo-drv1|IRQ|irq'), so the HOST-side witness lands in capture-cmd.txt "
                         "next to the device-side T cells: /proc/interrupts showing virq 207/209 "
                         "with an omo-drv1 action and a nonzero counter is the ISR FIRED verdict of "
                         "hostisr.md section 3.",
            "bounds": "one-shot latched samples, not a timing window; the ring is rung once per "
                      "send-pad run; the mask is driven to and left at the vendor-live 0x20.",
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
             "after": bl(SEND_SITE, pad_s).hex(),
             "note": "the trigring send pad reproduces the out[1] post, opens the glue mask "
                     "(0x400392e8 <= 0x20), takes the PRE-ring T0..T3, RINGS the H2D doorbell "
                     "(0x400392d4 <= 0x1) and takes the POST-ring T4..T7 (see NOTE_TRIG_RING)"},
            {"kind": "trampoline-entry", "region": "enable-thunk post-store boundary 0x87036",
             "file_offset": hex(POST_SITE), "before": data[POST_SITE:POST_SITE + 4].hex(),
             "after": bl(POST_SITE, pad_p).hex(),
             "note": "the firmware's own `bl #0xbdf50`; the pad samples ISENABLER2/ISPENDR2 "
                     "post-write (E0/E1) and reproduces the call as a `b.w` with lr untouched"},
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


def make_trignat(data: bytes, barmap: bytes, refs: set[int]):
    """trigger2.md section 3's variant: the firmware's OWN natural post performs the host's two
    stores (out[1] <= 4 reproduced, then the H2D submission out[0] <= 8 and the ring CA 0x400392d4
    <= 1) so the device-internal H2D chain is tested with no host/RC confound, and a second pad at
    the announce routine's exit (file 0x86F7E, after the 0xcece handshake wait) reads the
    device-dispatcher consumption witnesses B_D0 (out[0] = 0) / B_D2 (ISPENDR2 bit 12 clear).  The
    thunk/bring-up/post pads are byte-identical to gicpost's, so S1/S2/C0..C5 and E0..E3 keep their
    earlier addresses and E0 = 0x1001 (the ISENABLER2 word-2 POST-write readback) still proves the
    firmware's own id-0x4c enable store landed."""
    cells, sel = select_cells_trignat(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    off_a = 2 + GICV_NCELLS + GICP_NCELLS
    ac = cells[off_a:off_a + TRIGNAT_A_NCELLS]
    bc = cells[off_a + TRIGNAT_A_NCELLS:off_a + TRIGNAT_A_NCELLS + TRIGNAT_B_NCELLS]
    if len(ec) != GICP_NCELLS or len(ac) != TRIGNAT_A_NCELLS or len(bc) != TRIGNAT_B_NCELLS:
        raise PatchError("internal error: trignat cells were not selected")

    need_s = len(pad_send_trignat(0, ac))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    need_d = len(pad_drain_trignat(0, bc))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p), ("drain", need_d)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]
    (pad_d, len_d) = pads["drain"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send_trignat(pad_s, ac)
    code_p = pad_post(pad_p, ec)
    code_d = pad_drain_trignat(pad_d, bc)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p, pad_d))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p),
                      (pad_d, code_d)):
        out[off:off + len(code)] = code
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    for site, pad in ((SITE_THUNK, pad_i), (BRINGUP_SITE, pad_b), (SEND_SITE, pad_s),
                      (POST_SITE, pad_p), (TRIGNAT_SITE_B, pad_d)):
        if out[site:site + 4] != bl(site, pad):
            raise PatchError(f"internal error: site {site:#x} bytes are not the intended bl")
    if out[0x8702C:0x87030] != data[0x8702C:0x87030]:
        raise PatchError("internal error: the original ISENABLER store at file 0x8702c was altered")
    if out[0x87030:0x87036] != data[0x87030:0x87036]:
        raise PatchError("internal error: the itet block 0x87030..0x87035 was altered")
    if data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] != bytes.fromhex("1a600122"):
        raise PatchError("the trignat Pad A site is not `str r2,[r3]`+`movs r2,#1`")
    if data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] != TRIGNAT_DRAIN_POP:
        raise PatchError("the trignat Pad B site is not `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0)):
            if bad in code:
                raise PatchError(f"internal error: the trignat {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    seen = verify_disasm_trignat(out, pad_i, pad_b, pad_s, pad_p, pad_d, s1, s2, gc, ec, ac, bc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ac[:4]):
        records[f"A_S{i}"] = cell_record(barmap, a)
    records["A_P1"] = cell_record(barmap, ac[4])
    records["A_E0"] = cell_record(barmap, ac[5])
    records["A_E1"] = cell_record(barmap, ac[6])
    for i, a in enumerate(ac[7:12]):
        records[f"A_S{4 + i}"] = cell_record(barmap, a)
    records["A_P2"] = cell_record(barmap, ac[12])
    for i, a in enumerate(bc[:4]):
        records[f"B_D{i}"] = cell_record(barmap, a)
    records["B_P3"] = cell_record(barmap, bc[4])

    a_read_map = {
        "A_E0": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0] H2D pending bitmap",
                 "point": "Pad A entry, BEFORE the post is reproduced (next-visit consumption read)"},
        "A_E1": {"ca": hex(TRIGNAT_OUT1_CA), "register": "out[1] D2H pending bitmap",
                 "point": "Pad A entry, BEFORE the post is reproduced (next-visit read; 4 = a prior post ran)"},
        "A_S0": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0]",
                 "point": "Pad A, after the submission, PRE-ring (expected 8)"},
        "A_S1": {"ca": hex(GICD_ISPENDR2), "register": "GICD_ISPENDR2 word 2 (bit 12 = id 0x4c)",
                 "point": "Pad A, PRE-ring (expected bit 12 clear)"},
        "A_S2": {"ca": hex(GICC_HPPIR), "register": "GICC HPPIR (0x3ff = nothing pending)",
                 "point": "Pad A, PRE-ring"},
        "A_S3": {"ca": hex(GICD_ISPENDR2), "register": "GICD_ISPENDR2 word 2",
                 "point": "Pad A, POST-ring (expected bit 12 SET)"},
        "A_S4": {"ca": hex(GICC_HPPIR), "register": "GICC HPPIR",
                 "point": "Pad A, POST-ring (expected 0x4c)"},
        "A_S5": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0] - the latency datum",
                 "point": "Pad A, POST-ring (8 = not yet consumed; 0 = the ISR preempted the pad)"},
        "A_S6": {"ca": hex(TRIGNAT_OUT1_CA), "register": "out[1] (the reproduced natural post)",
                 "point": "Pad A, POST-ring (expected 4)"},
        "A_S7": {"ca": hex(TRIGNAT_GLUE_RAW), "register": "glue HOST_INTR_RAW_STATUS (+0x2e4)",
                 "point": "Pad A, POST-ring (bit 0 latch)"},
        "A_S8": {"ca": hex(TRIGNAT_GLUE_STATUS), "register": "glue HOST_INTR_STATUS (+0x2ec, post-mask)",
                 "point": "Pad A, POST-ring (bit 0 passes)"},
        "A_P1": {"ca": "none", "register": f"sentinel 0x{TRIGNAT_SENTINEL:08x}, page 9",
                 "point": "Pad A, after A_S0..A_S8"},
        "A_P2": {"ca": "none", "register": f"sentinel 0x{TRIGNAT_SENTINEL:08x}, page 10",
                 "point": "Pad A, after A_S0..A_S8"},
    }
    b_read_map = {
        "B_D0": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0] H2D pending bitmap",
                 "point": "Pad B, after the 0xcece handshake - expected 0 (the dispatcher consumed the 8)"},
        "B_D1": {"ca": hex(TRIGNAT_OUT1_CA), "register": "out[1] D2H pending bitmap / handler effect",
                 "point": "Pad B"},
        "B_D2": {"ca": hex(GICD_ISPENDR2), "register": "GICD_ISPENDR2 word 2",
                 "point": "Pad B - expected bit 12 CLEAR (the id-0x4c interrupt was taken)"},
        "B_D3": {"ca": hex(GICC_HPPIR), "register": "GICC HPPIR", "point": "Pad B"},
        "B_P3": {"ca": "none", "register": f"sentinel 0x{TRIGNAT_SENTINEL:08x}, page 10 (Pad B)",
                 "point": "Pad B, after B_D0..B_D3"},
    }

    manifest = {
        "variant": "trignat",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICC_base": "0x40160100",
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICD_ISENABLER2": hex(GICD_ISENABLER2),
            "GICC_HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging; a read acknowledges) and "
                          "0x10161000 (RC misc, a read panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, write-to-clear) and the masked glue "
                             "word 0x21 (the mask stays OPEN)",
            "ring": {"ca": hex(TRIGNAT_RING_CA), "value": hex(TRIGNAT_RING_VAL),
                     "register": "ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2]); value 1 = bit 0 "
                                 "host2device_tx, NEVER 8 (the dispatcher's own re-arm constant, "
                                 "file 0x818c4)",
                     "note": NOTE_TRIGNAT_A},
            "submit": {"ca": hex(TRIGNAT_OUT0_CA), "value": hex(TRIGNAT_SUBMIT_VAL),
                       "register": "out[0] - the H2D pending bitmap 0x818AC reads then clears",
                       "note": "the load-bearing correction to trigger.md section 3: that post writes "
                               "out[1] (0x40039014), not this word, so Pad A also stores out[0] <= 8 "
                               "- the store `pcie_msg_send` makes (`.ko` file 0x1619c); without it "
                               "0x818AC reads out[0] = 0 and dispatches no handler"},
            "out1": {"ca": hex(TRIGNAT_OUT1_CA),
                     "register": "out[1] - the natural post's D2H pending bitmap (reproduced <= 4)"},
            "glue": {"raw": hex(TRIGNAT_GLUE_RAW), "mask": hex(TRIGNAT_GLUE_MASK),
                     "status": hex(TRIGNAT_GLUE_STATUS), "mask_open": hex(TRIGNAT_MASK_OPEN)},
            "dispatcher": {"entry": "fn_array[0x4C] -> stub 0x294 -> file 0x818AC",
                           "ack": "CA 0x400392f0 <= 1 (file 0x818b8) - written by the FIRMWARE only",
                           "consume": "ldr r5,[r2] / str r1,[r2] with r1 = 0 (file 0x818bc/0x818be): "
                                      "reads then CLEARS out[0] (CA 0x40039010)",
                           "rearm": "CA 0x400392d4 <= 8 (file 0x818c4) - the dispatcher's own re-arm, "
                                    "NEVER written by this variant"},
            "a_read_order": a_read_map,
            "b_read_order": b_read_map,
            "pad_a_note": NOTE_TRIGNAT_A,
            "pad_b_note": NOTE_TRIGNAT_B,
            "cells_note": NOTE_TRIGNAT_CELLS,
            "verification": {
                "method": "every CA re-derived from the image on disk (capstone, Thumb) plus the "
                            "verified vendor-module quotes in the record",
                "post_site_0x86f5a": "stock bytes 1a600122 = `str r2,[r3]` (r2 = 4 set at 0x86f54, "
                                     "r3 = literal file 0x86fbc = 0x40039014) + `movs r2,#1`; the "
                                     "continuation 0x86f5e is `add.w r3,r3,#0xc8000`",
                "drain_site_0x86f7e": "stock bytes bde8f843 = `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`, the "
                                      "exit of the announce routine after the `*(0x4000010C) == "
                                      "0xcece` wait (0x86f74..0x86f7c); continuation 0x86f82 = "
                                      "`ldr r0,[pc,#0x3c]`",
                "out0_0x40039010": "literal file 0x97e0; out[0] = ctx+0x04, the word 0x818ac reads "
                                   "then clears",
                "out1_0x40039014": "literal file 0x86fbc (and 0x97dc) - the natural post's target",
                "ring_value_0x1": "ring.md section 0 / trigger2.md section 1: `pcie_msg_send` ORs "
                                  "bit 0 into comm+0x34 (= CA 0x400392d4, `.ko` file 0x161b0); bit 3 "
                                  "(0x8) is the dispatcher's re-arm (file 0x818c4), NEVER written",
                "GICD_ISPENDR2_0x40161208": "GICD base 0x40161000 (firmware literal file 0x716c) + "
                                             "0x200 + 4*2",
                "GICC_page_0x40160100": "firmware literal file 0x8309c; IAR 0x4016010c = literal "
                                        "file 0x83010, EoI 0x40160110 = literal 0x83020 -> HPPIR = "
                                        "base+0x18",
                "glue_base_0x40039000": "firmware literal file 0x86fb4 (and 0xcf2ac); the ctrl-rb "
                                        "+0x2d4/+0x2e4/+0x2e8/+0x2ec offsets are the sibling header's "
                                        "HOST2DEVICE_INTR_SET / HOST_INTR_RAW_STATUS / HOST_INTR_MASK "
                                        "/ HOST_INTR_STATUS, measured live in phase 46/47",
            },
        },
        "classification": {
            "instrument": "Pad A (the firmware's OWN natural post, file 0x86F5A) entry-reads "
                           "out[0]/out[1], reproduces the natural out[1] <= 4, opens the glue mask "
                           "(0x400392e8 <= 0x20), performs the H2D submission out[0] <= 8, samples "
                           "A_S0..A_S2 PRE-ring, RINGS the doorbell (0x400392d4 <= 0x1, once), samples "
                           "A_S3..A_S8 POST-ring, arms A_P1/A_P2 and returns to 0x86F5E so the natural "
                           "D2H notify still runs.  Pad B (file 0x86F7E, after the 0xcece handshake "
                           "wait) reads the consumption witnesses B_D0 (out[0] = 0) / B_D2 (ISPENDR2 "
                           "bit 12 clear) and arms B_P3.",
            "branch_TRIGNAT_COMPLETE": "A_S3 bit 12 SET, A_S4 = 0x4C, B_D0 = 0, B_D2 bit 12 CLEAR "
                                        "(with B_P3 = sentinel) -> the firmware's own post -> ring -> "
                                        "device GIC -> the DEVICE DISPATCHER CONSUMED out[0]; the core "
                                        "question is answered YES device-side.",
            "branch_RING_PENDING_NOT_TAKEN": "A_S3 bit 12 SET, A_S4 = 0x4C and (B_D0 = 8 or B_D2 bit 12 "
                                              "SET) -> the ringed event REACHES the GIC (pending) but "
                                              "the id-0x4c interrupt is never taken, so 0x818AC never "
                                              "runs; the gate is the CPU-side IRQ take/enable.",
            "branch_GLUE_ONLY": "A_S3 bit 12 CLEAR and (A_S7 bit 0 = 1 or A_S8 bit 0 = 1) -> the glue "
                                 "latched/passed but the GIC did not see it.",
            "branch_NOTHING": "A_S3 bit 12 CLEAR and A_S7/A_S8 bit 0 = 0 with sentinels present -> the "
                               "ring did not land (or did not reach the glue) - a bounded negative, "
                               "not a proof.",
            "pad_did_not_run": "A_P1/A_P2/B_P3 sentinel missing -> the record is void for the affected "
                                "cells; Pad B is behind the 0xcece handshake loop, so fall back to "
                                "A_E0/A_E1 (the single-visit ambiguity: A_E0 = 0 on the first visit too).",
            "latency_datum": "A_S5 = 8 with TRIGNAT-COMPLETE holding means the ISR did not preempt "
                              "Pad A and Pad B is what caught the consumption; A_S5 = 0 means the ISR "
                              "preempted the pad mid-way.",
            "branches_note": NOTE_TRIGNAT_BRANCHES,
            "host_side": "The capture hook ALSO runs the hostisr.md section 2 read-only host witness, "
                          "so /proc/interrupts 207:/209: with an omo-drv1 action and a nonzero counter "
                          "lands in capture-cmd.txt next to the device-side cells (only meaningful "
                          "once the wifidrv1.c IRQ port change rides CI).",
            "sanities": "S1/S1+4/S2/S2+4/C0..C5 and E0..E3 are byte-identical to gicpost's pads; "
                         "E0 = 0x1001 (ISENABLER2 word-2 POST-write, bit 12 set) proves the firmware's "
                         "own id-0x4c enable store landed in this boot.",
            "bounds": "one-shot latched samples, not a timing window; the ring is rung once per Pad A "
                      "run; the mask is driven to and left at the vendor-live 0x20.",
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "runtime_addr": hex(pad_i + BIAS),
                      "run_length": hex(len_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "runtime_addr": hex(pad_b + BIAS),
                        "run_length": hex(len_b), "code_length": len(code_b), "code_hex": code_b.hex()},
            "send_a": {"file_offset": hex(pad_s), "runtime_addr": hex(pad_s + BIAS),
                       "run_length": hex(len_s), "code_length": len(code_s), "code_hex": code_s.hex()},
            "post": {"file_offset": hex(pad_p), "runtime_addr": hex(pad_p + BIAS),
                     "run_length": hex(len_p), "code_length": len(code_p), "code_hex": code_p.hex()},
            "drain_b": {"file_offset": hex(pad_d), "runtime_addr": hex(pad_d + BIAS),
                        "run_length": hex(len_d), "code_length": len(code_d), "code_hex": code_d.hex()},
        },
        "sites": {
            "send_a": {"file_offset": hex(TRIGNAT_SITE_A), "cont": hex(TRIGNAT_CONT_A),
                       "replaced_bytes": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
                       "replaced": "str r2,[r3] (out[1] <= 4) + movs r2,#1",
                       "after": bl(TRIGNAT_SITE_A, pad_s).hex()},
            "drain_b": {"file_offset": hex(TRIGNAT_SITE_B), "cont": hex(TRIGNAT_CONT_B),
                        "replaced_bytes": data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4].hex(),
                        "replaced": "pop.w {r3,r4,r5,r6,r7,r8,sb,lr}",
                        "after": bl(TRIGNAT_SITE_B, pad_d).hex()},
        },
        "patches": [
            {"kind": "trampoline-entry", "region": "enable thunk 0x86ff4", "file_offset": hex(SITE_THUNK),
             "before": data[SITE_THUNK:SITE_THUNK + 4].hex(),
             "after": bl(SITE_THUNK, pad_i).hex(), "note": NOTE_GICVIEW_I},
            {"kind": "trampoline-entry", "region": "distributor bring-up 0x6e5c-0x6ed4",
             "file_offset": hex(BRINGUP_SITE), "before": data[BRINGUP_SITE:BRINGUP_SITE + 4].hex(),
             "after": bl(BRINGUP_SITE, pad_b).hex(), "note": NOTE_GICVIEW_II},
            {"kind": "trampoline-entry", "region": "firmware out[1] post 0x86F5A (ETE bring-up 0x86E14)",
             "file_offset": hex(TRIGNAT_SITE_A), "before": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
             "after": bl(TRIGNAT_SITE_A, pad_s).hex(), "note": NOTE_TRIGNAT_A},
            {"kind": "trampoline-entry", "region": "announce routine exit 0x86F7E (after the 0xcece wait)",
             "file_offset": hex(TRIGNAT_SITE_B), "before": data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4].hex(),
             "after": bl(TRIGNAT_SITE_B, pad_d).hex(), "note": NOTE_TRIGNAT_B},
            {"kind": "trampoline-entry", "region": "enable-thunk post-store boundary 0x87036",
             "file_offset": hex(POST_SITE), "before": data[POST_SITE:POST_SITE + 4].hex(),
             "after": bl(POST_SITE, pad_p).hex(),
             "note": "the firmware's own `bl #0xbdf50`; the pad samples ISENABLER2/ISPENDR2 "
                     "post-write (E0/E1) and reproduces the call as a `b.w` with lr untouched"},
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
            "natural_post_continuation": {"file_offset": "0x86f5e..0x86f7e",
                                           "bytes_identical": out[0x86F5E:0x86F7E] == data[0x86F5E:0x86F7E]},
            "announce_exit_continuation": {"file_offset": "0x86f82..",
                                            "bytes_identical": out[0x86F82:0x86F92] == data[0x86F82:0x86F92]},
        },
        "disasm": seen,
    }
    return out, manifest


def make_trigcons(data: bytes, barmap: bytes, refs: set[int]):
    """padb.md section 3 option (a): trignat's instrument with Pad B MOVED past the 0xcece gate.
    Pad A (the firmware's OWN natural post, file 0x86F5A) is byte-identical to trignat's - it
    reproduces the out[1] <= 4 post, opens the glue mask, performs the H2D submission out[0] <= 8
    and rings CA 0x400392d4 <= 1 - and the thunk/bring-up/post pads keep their cells, so S1/S2/
    C0..C5/E0..E3 and the A_* samples stay directly comparable to trignat's.  Pad B now sits at
    file 0x86F74 (the announce wait's own `movw r3,#0xcece`, stock bytes 4cf6ce63), takes the same
    B_D0..B_D3 + B_P3 samples, re-emits `movw r3,#0xcece` and branches to the loop head 0x86F78 -
    so it runs even though nothing writes 0xcece, at the price of the PRE-wait instant (expected
    row RING-PENDING-NOT-TAKEN).  The OLD announce-exit site 0x86F7E stays stock `pop.w`."""
    cells, sel = select_cells_trignat(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    off_a = 2 + GICV_NCELLS + GICP_NCELLS
    ac = cells[off_a:off_a + TRIGNAT_A_NCELLS]
    bc = cells[off_a + TRIGNAT_A_NCELLS:off_a + TRIGNAT_A_NCELLS + TRIGNAT_B_NCELLS]
    if len(ec) != GICP_NCELLS or len(ac) != TRIGNAT_A_NCELLS or len(bc) != TRIGNAT_B_NCELLS:
        raise PatchError("internal error: trigcons cells were not selected")

    need_s = len(pad_send_trignat(0, ac))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    need_d = len(pad_drain_trigcons(0, bc))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p), ("drain", need_d)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]
    (pad_d, len_d) = pads["drain"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send_trignat(pad_s, ac)
    code_p = pad_post(pad_p, ec)
    code_d = pad_drain_trigcons(pad_d, bc)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p, pad_d,
                                drain_site=TRIGCONS_SITE_B))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p),
                      (pad_d, code_d)):
        out[off:off + len(code)] = code
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    for site, pad in ((SITE_THUNK, pad_i), (BRINGUP_SITE, pad_b), (SEND_SITE, pad_s),
                      (POST_SITE, pad_p), (TRIGCONS_SITE_B, pad_d)):
        if out[site:site + 4] != bl(site, pad):
            raise PatchError(f"internal error: site {site:#x} bytes are not the intended bl")
    if out[0x8702C:0x87030] != data[0x8702C:0x87030]:
        raise PatchError("internal error: the original ISENABLER store at file 0x8702c was altered")
    if out[0x87030:0x87036] != data[0x87030:0x87036]:
        raise PatchError("internal error: the itet block 0x87030..0x87035 was altered")
    if data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] != bytes.fromhex("1a600122"):
        raise PatchError("the trigcons Pad A site is not `str r2,[r3]`+`movs r2,#1`")
    if data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] != TRIGCONS_SITE_B_BYTES:
        raise PatchError("the trigcons Pad B site is not `movw r3,#0xcece` (4cf6ce63)")
    if movw(3, 0xcece) != TRIGCONS_SITE_B_BYTES:
        raise PatchError("internal error: the encoder does not re-emit `movw r3,#0xcece`")
    if data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] != TRIGNAT_DRAIN_POP:
        raise PatchError("the stock old announce-exit site is not `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`")
    if out[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] != data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4]:
        raise PatchError("internal error: trigcons altered the old announce-exit site 0x86F7E")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"internal error: the trigcons {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    seen = verify_disasm_trigcons(out, pad_i, pad_b, pad_s, pad_p, pad_d, s1, s2, gc, ec, ac, bc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ac[:4]):
        records[f"A_S{i}"] = cell_record(barmap, a)
    records["A_P1"] = cell_record(barmap, ac[4])
    records["A_E0"] = cell_record(barmap, ac[5])
    records["A_E1"] = cell_record(barmap, ac[6])
    for i, a in enumerate(ac[7:12]):
        records[f"A_S{4 + i}"] = cell_record(barmap, a)
    records["A_P2"] = cell_record(barmap, ac[12])
    for i, a in enumerate(bc[:4]):
        records[f"B_D{i}"] = cell_record(barmap, a)
    records["B_P3"] = cell_record(barmap, bc[4])

    a_read_map = {
        "A_E0": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0] H2D pending bitmap",
                 "point": "Pad A entry, BEFORE the post is reproduced (next-visit consumption read)"},
        "A_E1": {"ca": hex(TRIGNAT_OUT1_CA), "register": "out[1] D2H pending bitmap",
                 "point": "Pad A entry, BEFORE the post is reproduced (next-visit read; 4 = a prior post ran)"},
        "A_S0": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0]",
                 "point": "Pad A, after the submission, PRE-ring (expected 8)"},
        "A_S1": {"ca": hex(GICD_ISPENDR2), "register": "GICD_ISPENDR2 word 2 (bit 12 = id 0x4c)",
                 "point": "Pad A, PRE-ring (expected bit 12 clear)"},
        "A_S2": {"ca": hex(GICC_HPPIR), "register": "GICC HPPIR (0x3ff = nothing pending)",
                 "point": "Pad A, PRE-ring"},
        "A_S3": {"ca": hex(GICD_ISPENDR2), "register": "GICD_ISPENDR2 word 2",
                 "point": "Pad A, POST-ring (expected bit 12 SET)"},
        "A_S4": {"ca": hex(GICC_HPPIR), "register": "GICC HPPIR",
                 "point": "Pad A, POST-ring (expected 0x4c)"},
        "A_S5": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0] - the latency datum",
                 "point": "Pad A, POST-ring (8 = not yet consumed; 0 = the ISR preempted the pad)"},
        "A_S6": {"ca": hex(TRIGNAT_OUT1_CA), "register": "out[1] (the reproduced natural post)",
                 "point": "Pad A, POST-ring (expected 4)"},
        "A_S7": {"ca": hex(TRIGNAT_GLUE_RAW), "register": "glue HOST_INTR_RAW_STATUS (+0x2e4)",
                 "point": "Pad A, POST-ring (bit 0 latch)"},
        "A_S8": {"ca": hex(TRIGNAT_GLUE_STATUS), "register": "glue HOST_INTR_STATUS (+0x2ec, post-mask)",
                 "point": "Pad A, POST-ring (bit 0 passes)"},
        "A_P1": {"ca": "none", "register": f"sentinel 0x{TRIGNAT_SENTINEL:08x}, page 9",
                 "point": "Pad A, after A_S0..A_S8"},
        "A_P2": {"ca": "none", "register": f"sentinel 0x{TRIGNAT_SENTINEL:08x}, page 10",
                 "point": "Pad A, after A_S0..A_S8"},
    }
    b_read_map = {
        "B_D0": {"ca": hex(TRIGNAT_OUT0_CA), "register": "out[0] H2D pending bitmap",
                 "point": "Pad B (MOVED to 0x86F74, PRE-wait): expected 8 = still pending"},
        "B_D1": {"ca": hex(TRIGNAT_OUT1_CA), "register": "out[1] D2H pending bitmap / handler effect",
                 "point": "Pad B (MOVED, PRE-wait)"},
        "B_D2": {"ca": hex(GICD_ISPENDR2), "register": "GICD_ISPENDR2 word 2",
                 "point": "Pad B (MOVED, PRE-wait): expected bit 12 SET (the id-0x4c interrupt not yet taken)"},
        "B_D3": {"ca": hex(GICC_HPPIR), "register": "GICC HPPIR", "point": "Pad B (MOVED, PRE-wait)"},
        "B_P3": {"ca": "none", "register": f"sentinel 0x{TRIGNAT_SENTINEL:08x}, page 10 (Pad B)",
                 "point": "Pad B, after B_D0..B_D3"},
    }

    manifest = {
        "variant": "trigcons",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000",
            "GICC_base": "0x40160100",
            "GICD_ISPENDR2": hex(GICD_ISPENDR2),
            "GICD_ISENABLER2": hex(GICD_ISENABLER2),
            "GICC_HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging; a read acknowledges) and "
                          "0x10161000 (RC misc, a read panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, write-to-clear) and the masked glue "
                             "word 0x21 (the mask stays OPEN)",
            "ring": {"ca": hex(TRIGNAT_RING_CA), "value": hex(TRIGNAT_RING_VAL),
                     "register": "ctrl-rb +0x2d4 = HOST2DEVICE_INTR_SET (out[2]); value 1 = bit 0 "
                                 "host2device_tx, NEVER 8 (the dispatcher's own re-arm constant, "
                                 "file 0x818c4)",
                     "note": NOTE_TRIGCONS_A},
            "submit": {"ca": hex(TRIGNAT_OUT0_CA), "value": hex(TRIGNAT_SUBMIT_VAL),
                       "register": "out[0] - the H2D pending bitmap 0x818AC reads then clears",
                       "note": "the load-bearing correction to trigger.md section 3: that post writes "
                               "out[1] (0x40039014), not this word, so Pad A also stores out[0] <= 8 "
                               "- the store `pcie_msg_send` makes (`.ko` file 0x1619c); without it "
                               "0x818AC reads out[0] = 0 and dispatches no handler"},
            "out1": {"ca": hex(TRIGNAT_OUT1_CA),
                     "register": "out[1] - the natural post's D2H pending bitmap (reproduced <= 4)"},
            "gate": {"ca": "0x4000010c", "wait_value": "0x0000cece",
                     "site": hex(TRIGCONS_SITE_B), "cont": hex(TRIGCONS_CONT_B),
                     "old_site": hex(TRIGNAT_SITE_B),
                     "note": "padb.md section 1: the announce routine waits on *(CA 0x4000010c) == "
                             "0x0000cece (movw r3,#0xcece at 0x86F74; the same value is awaited in "
                             "the cpsid-i helper 0x820F8).  NOTHING in the image writes it, so the "
                             "loop never exits; trigcons moves Pad B onto the wait's own movw so "
                             "the B cells have a producer.  (This CA is 0x4000010c, NOT the "
                             "forbidden 0x4016010c.)"},
            "glue": {"raw": hex(TRIGNAT_GLUE_RAW), "mask": hex(TRIGNAT_GLUE_MASK),
                     "status": hex(TRIGNAT_GLUE_STATUS), "mask_open": hex(TRIGNAT_MASK_OPEN)},
            "dispatcher": {"entry": "fn_array[0x4C] -> stub 0x294 -> file 0x818AC",
                           "ack": "CA 0x400392f0 <= 1 (file 0x818b8) - written by the FIRMWARE only",
                           "consume": "ldr r5,[r2] / str r1,[r2] with r1 = 0 (file 0x818bc/0x818be): "
                                      "reads then CLEARS out[0] (CA 0x40039010)",
                           "rearm": "CA 0x400392d4 <= 8 (file 0x818c4) - the dispatcher's own re-arm, "
                                    "NEVER written by this variant"},
            "a_read_order": a_read_map,
            "b_read_order": b_read_map,
            "pad_a_note": NOTE_TRIGCONS_A,
            "pad_b_note": NOTE_TRIGCONS_B,
            "cells_note": NOTE_TRIGNAT_CELLS,
            "verification": {
                "method": "every CA re-derived from the image on disk (capstone, Thumb) plus the "
                            "verified vendor-module quotes in the record",
                "post_site_0x86f5a": "stock bytes 1a600122 = `str r2,[r3]` (r2 = 4 set at 0x86f54, "
                                     "r3 = literal file 0x86fbc = 0x40039014) + `movs r2,#1`; the "
                                     "continuation 0x86f5e is `add.w r3,r3,#0xc8000`",
                "drain_site_0x86f74": "stock bytes 4cf6ce63 = `movw r3,#0xcece`, the announce wait's "
                                      "own instruction (padb.md section 1); the continuation "
                                      "0x86f78 = `ldr r2,[r1]` (r1 = literal file 0x86fa0 = "
                                      "0x4000010c), the spin loop head",
                "old_drain_site_0x86f7e": "stock bytes bde8f843 = `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`, "
                                          "the announce routine's exit; UNTOUCHED by trigcons",
                "out0_0x40039010": "literal file 0x97e0; out[0] = ctx+0x04, the word 0x818ac reads "
                                   "then clears",
                "out1_0x40039014": "literal file 0x86fbc (and 0x97dc) - the natural post's target",
                "gate_0x4000010c": "literal file 0x86fa0 (and 0x82110 for the cpsid-i helper); "
                                   "ZERO occurrences of 0xcece as a literal in the image",
                "ring_value_0x1": "ring.md section 0 / trigger2.md section 1: `pcie_msg_send` ORs "
                                  "bit 0 into comm+0x34 (= CA 0x400392d4, `.ko` file 0x161b0); bit 3 "
                                  "(0x8) is the dispatcher's re-arm (file 0x818c4), NEVER written",
                "GICD_ISPENDR2_0x40161208": "GICD base 0x40161000 (firmware literal file 0x716c) + "
                                             "0x200 + 4*2",
                "GICC_page_0x40160100": "firmware literal file 0x8309c; IAR 0x4016010c = literal "
                                        "file 0x83010, EoI 0x40160110 = literal 0x83020 -> HPPIR = "
                                        "base+0x18",
                "glue_base_0x40039000": "firmware literal file 0x86fb4 (and 0xcf2ac); the ctrl-rb "
                                        "+0x2d4/+0x2e4/+0x2e8/+0x2ec offsets are the sibling header's "
                                        "HOST2DEVICE_INTR_SET / HOST_INTR_RAW_STATUS / HOST_INTR_MASK "
                                        "/ HOST_INTR_STATUS, measured live in phase 46/47",
            },
        },
        "classification": {
            "instrument": "Pad A (the firmware's OWN natural post, file 0x86F5A) entry-reads "
                           "out[0]/out[1], reproduces the natural out[1] <= 4, opens the glue mask "
                           "(0x400392e8 <= 0x20), performs the H2D submission out[0] <= 8, samples "
                           "A_S0..A_S2 PRE-ring, RINGS the doorbell (0x400392d4 <= 0x1, once), samples "
                           "A_S3..A_S8 POST-ring, arms A_P1/A_P2 and returns to 0x86F5E so the natural "
                           "D2H notify still runs.  Pad B is MOVED (padb.md section 3 option (a)) to "
                           "0x86F74, the announce wait's own `movw r3,#0xcece`, so it runs ahead of "
                           "the never-exiting 0xcece loop: it reads B_D0..B_D3, arms B_P3, re-emits "
                           "`movw r3,#0xcece` and branches to the loop head 0x86F78.  The old "
                           "announce-exit site 0x86F7E stays stock.",
            "branch_TRIGCONS_COMPLETE": "A_S3 bit 12 SET, A_S4 = 0x4C, B_D0 = 0, B_D2 bit 12 CLEAR "
                                        "(with B_P3 = sentinel) -> the ringed event reached the GIC "
                                        "AND the id-0x4c interrupt was taken/consumed across the tiny "
                                        "Pad A -> Pad B window.",
            "branch_RING_PENDING_NOT_TAKEN": "A_S3 bit 12 SET, A_S4 = 0x4C and (B_D0 = 8 or B_D2 bit 12 "
                                              "SET) -> the ringed event REACHES the GIC (pending) but "
                                              "the id-0x4c interrupt is never taken; the gate is the "
                                              "CPU-side IRQ take/enable.  THE EXPECTED ROW for this "
                                              "pre-wait placement (padb.md section 2a).",
            "branch_GLUE_ONLY": "A_S3 bit 12 CLEAR and (A_S7 bit 0 = 1 or A_S8 bit 0 = 1) -> the glue "
                                 "latched/passed but the GIC did not see it.",
            "branch_NOTHING": "A_S3 bit 12 CLEAR and A_S7/A_S8 bit 0 = 0 with sentinels present -> the "
                               "ring did not land (or did not reach the glue) - a bounded negative, "
                               "not a proof.",
            "pad_did_not_run": "A_P1/A_P2/B_P3 sentinel missing -> the record is void for the affected "
                                "cells.  Unlike trignat, Pad B is NOT behind the 0xcece wait, so a "
                                "missing B_P3 would be a patch defect, not the runtime gate.",
            "latency_datum": "A_S5 = 8 with a pending row means the ISR did not preempt Pad A and only "
                              "the (c) host write can reach the post-handshake instant; A_S5 = 0 means "
                              "the ISR preempted the pad mid-way.",
            "branches_note": NOTE_TRIGCONS_BRANCHES,
            "host_side": "The capture hook ALSO runs the hostisr.md section 2 read-only host witness, "
                          "so /proc/interrupts 207:/209: with an omo-drv1 action and a nonzero counter "
                          "lands in capture-cmd.txt next to the device-side cells (only meaningful "
                          "once the wifidrv1.c IRQ port change rides CI).",
            "sanities": "S1/S1+4/S2/S2+4/C0..C5 and E0..E3 are byte-identical to gicpost's pads; "
                         "E0 = 0x1001 (ISENABLER2 word-2 POST-write, bit 12 set) proves the firmware's "
                         "own id-0x4c enable store landed in this boot.  Pad A and the A_* cells are "
                         "byte-identical to trignat's.",
            "bounds": "one-shot latched samples, not a timing window; the ring is rung once per Pad A "
                      "run; the mask is driven to and left at the vendor-live 0x20.  Pad B forfeits "
                      "the post-handshake instant (padb.md section 2a/4): option (c)'s host write of "
                      "0x0000cece to BAR0+0x3b810c is the companion that restores it.",
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "runtime_addr": hex(pad_i + BIAS),
                      "run_length": hex(len_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "runtime_addr": hex(pad_b + BIAS),
                        "run_length": hex(len_b), "code_length": len(code_b), "code_hex": code_b.hex()},
            "send_a": {"file_offset": hex(pad_s), "runtime_addr": hex(pad_s + BIAS),
                       "run_length": hex(len_s), "code_length": len(code_s), "code_hex": code_s.hex()},
            "post": {"file_offset": hex(pad_p), "runtime_addr": hex(pad_p + BIAS),
                     "run_length": hex(len_p), "code_length": len(code_p), "code_hex": code_p.hex()},
            "drain_b": {"file_offset": hex(pad_d), "runtime_addr": hex(pad_d + BIAS),
                        "run_length": hex(len_d), "code_length": len(code_d), "code_hex": code_d.hex()},
        },
        "sites": {
            "send_a": {"file_offset": hex(TRIGNAT_SITE_A), "cont": hex(TRIGNAT_CONT_A),
                       "replaced_bytes": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
                       "replaced": "str r2,[r3] (out[1] <= 4) + movs r2,#1",
                       "after": bl(TRIGNAT_SITE_A, pad_s).hex()},
            "drain_b": {"file_offset": hex(TRIGCONS_SITE_B), "cont": hex(TRIGCONS_CONT_B),
                        "replaced_bytes": data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4].hex(),
                        "replaced": "movw r3,#0xcece (the announce wait's gate constant)",
                        "after": bl(TRIGCONS_SITE_B, pad_d).hex()},
            "old_drain_b": {"file_offset": hex(TRIGNAT_SITE_B),
                            "bytes": data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4].hex(),
                            "unchanged": out[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] ==
                                         data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4]},
        },
        "patches": [
            {"kind": "trampoline-entry", "region": "enable thunk 0x86ff4", "file_offset": hex(SITE_THUNK),
             "before": data[SITE_THUNK:SITE_THUNK + 4].hex(),
             "after": bl(SITE_THUNK, pad_i).hex(), "note": NOTE_GICVIEW_I},
            {"kind": "trampoline-entry", "region": "distributor bring-up 0x6e5c-0x6ed4",
             "file_offset": hex(BRINGUP_SITE), "before": data[BRINGUP_SITE:BRINGUP_SITE + 4].hex(),
             "after": bl(BRINGUP_SITE, pad_b).hex(), "note": NOTE_GICVIEW_II},
            {"kind": "trampoline-entry", "region": "firmware out[1] post 0x86F5A (ETE bring-up 0x86E14)",
             "file_offset": hex(TRIGNAT_SITE_A), "before": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
             "after": bl(TRIGNAT_SITE_A, pad_s).hex(), "note": NOTE_TRIGCONS_A},
            {"kind": "trampoline-entry", "region": "announce 0xcece gate 0x86F74 (MOVED; padb.md option (a))",
             "file_offset": hex(TRIGCONS_SITE_B), "before": data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4].hex(),
             "after": bl(TRIGCONS_SITE_B, pad_d).hex(), "note": NOTE_TRIGCONS_B},
            {"kind": "trampoline-entry", "region": "enable-thunk post-store boundary 0x87036",
             "file_offset": hex(POST_SITE), "before": data[POST_SITE:POST_SITE + 4].hex(),
             "after": bl(POST_SITE, pad_p).hex(),
             "note": "the firmware's own `bl #0xbdf50`; the pad samples ISENABLER2/ISPENDR2 "
                     "post-write (E0/E1) and reproduces the call as a `b.w` with lr untouched"},
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
            "natural_post_continuation": {"file_offset": "0x86f5e..0x86f74",
                                           "bytes_identical": out[0x86F5E:0x86F74] == data[0x86F5E:0x86F74]},
            "announce_loop_body": {"file_offset": "0x86f78..0x86f7e",
                                   "bytes_identical": out[0x86F78:0x86F7E] == data[0x86F78:0x86F7E]},
            "old_announce_exit_continuation": {"file_offset": "0x86f7e..",
                                               "bytes_identical": out[0x86F7E:0x86F92] == data[0x86F7E:0x86F92]},
        },
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
    assert md5(gp) == GICPOST_MD5, f"gicpost output changed: {md5(gp)} != {GICPOST_MD5}"

    # ---- gicmask: gicpost + the delivery-configuration sample at the send pad (F0..F9)
    gmk, gkm = make_gicmask(data, barmap, refs)
    assert len(gmk) == len(data), "gicmask changed the size"
    gmk2, gkm2 = make_gicmask(data, barmap, refs)
    assert gmk == gmk2, "gicmask patch is not deterministic"
    assert json.dumps(gkm, sort_keys=True) == json.dumps(gkm2, sort_keys=True), \
        "gicmask manifest is not deterministic"
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"D{i}" for i in range(GICS_NCELLS)] + [f"E{i}" for i in range(GICP_NCELLS)]):
        assert gkm["cells"][nm]["addr"] == gpm["cells"][nm]["addr"], f"gicmask moved cell {nm}"
    fmc = [int(gkm["cells"][f"F{i}"]["addr"], 16) for i in range(GICM_NCELLS)]
    every_m = [s1, s2] + gc + ds + ec + fmc
    assert len(set(every_m)) == len(every_m), "gicmask cells are not all distinct"
    assert all(gkm["cells"][f"F{i}"]["barmap_value"] == "0x0" for i in range(GICM_NCELLS)), \
        "an F cell baseline is not zero at BAR0"
    assert all(gkm["cells"][f"F{i}"]["barmap_alias_value"] == "0x0" for i in range(GICM_NCELLS)), \
        "an F cell baseline is not zero at the alias"
    assert all(c not in S_CELL_EXCLUDE for c in fmc), "an F cell is inside an excluded table"
    assert all(fmc[i + 1] - fmc[i] >= 8 for i in range(3)), "F0..F3 are not >= 8 bytes apart"
    assert all(fmc[i + 1] - fmc[i] >= 8 for i in range(4, 7)), "F4..F7 are not >= 8 bytes apart"
    assert fmc[8] - fmc[3] >= 8 and fmc[9] - fmc[7] >= 8, \
        "the F sentinels are not >= 8 bytes from their page's samples"
    pages_g = [int(p, 16) for p in gkm["selection"]["all_zero_pages"]]
    f1p = int(gkm["selection"]["f_page_1"], 16)
    f2p = int(gkm["selection"]["f_page_2"], 16)
    assert f1p == pages_g[GICM_F_PAGE_1_IDX] and f2p == pages_g[GICM_F_PAGE_2_IDX], \
        "gicmask picked unexpected F pages"
    assert all(f1p <= c < f1p + 0x1000 for c in fmc[:4] + [fmc[8]]), "F0..F3/F8 are not in page 1"
    assert all(f2p <= c < f2p + 0x1000 for c in fmc[4:8] + [fmc[9]]), "F4..F7/F9 are not in page 2"
    assert fmc[8] == f1p + 0x20 and fmc[9] == f2p + 0x20, \
        "the F sentinels are not the fifth cells of their pages"
    for p in (f1p, f2p):
        assert all(word_at(barmap, x) == 0 and word_at(barmap, ALIAS_OFF + x) == 0
                   for x in range(p, p + 0x1000, 4)), f"F page {p:#x} is not all-zero in the barmap"
    assert [r[0] for r in GICM_READS] == [0x40160100, 0x40160104, 0x4016184C, 0x4016144C,
                                          0x40161C10, 0x400392E8, 0x400392E4, 0x400392EC]

    pad_i_m = int(gkm["padding"]["thunk"]["file_offset"], 16)
    pad_b_m = int(gkm["padding"]["bringup"]["file_offset"], 16)
    pad_s_m = int(gkm["padding"]["send"]["file_offset"], 16)
    pad_p_m = int(gkm["padding"]["post"]["file_offset"], 16)
    code_i_m = pad_thunk(pad_i_m, s1, gc, apsr_cell=ec[3], req_cell=ec[2], f_req_cell=fmc[9])
    code_b_m = pad_bringup(pad_b_m, s2, gc)
    code_s_m = pad_send(pad_s_m, ds, fmc)
    code_p_m = pad_post(pad_p_m, ec)
    assert _store_imm_block(GICM_REQUEST, fmc[9]) in code_i_m, "the gate pad lost the F9 request"
    assert _store_ip_block(ec[3]) in code_i_m, "the gate pad lost the E3 APSR deposit"
    for i, (ca_m, nm_m) in enumerate(GICM_READS):
        assert gic_read_store_block(ca_m, fmc[i]) in code_s_m, f"send pad missing {nm_m} -> F{i}"
    assert _store_imm_block(GICM_SENTINEL, fmc[8]) in code_s_m, "send pad missing the F8 sentinel"
    assert _store_imm_block(GICM_SENTINEL, fmc[9]) in code_s_m, "send pad missing the F9 sentinel"
    for off_m, code_m in ((pad_i_m, code_i_m), (pad_b_m, code_b_m), (pad_s_m, code_s_m),
                          (pad_p_m, code_p_m)):
        assert gmk[off_m:off_m + len(code_m)] == code_m, f"the gicmask pad at {off_m:#x} is not in the image"
    idx_m = [code_s_m.index(gic_read_store_block(GICM_READS[i][0], fmc[i])) for i in range(4)]
    idx_m.append(code_s_m.index(_store_imm_block(GICM_SENTINEL, fmc[8])))
    idx_m += [code_s_m.index(gic_read_store_block(GICM_READS[i][0], fmc[i]))
              for i in range(4, GICM_NSAMPLES)]
    idx_m.append(code_s_m.index(_store_imm_block(GICM_SENTINEL, fmc[9])))
    assert idx_m == sorted(idx_m) and len(set(idx_m)) == len(idx_m), \
        "the send pad F order is not F0..F3 -> F8 -> F4..F7 -> F9"
    pads_m = [(pad_i_m, len(code_i_m)), (pad_b_m, len(code_b_m)), (pad_s_m, len(code_s_m)),
              (pad_p_m, len(code_p_m))]
    for a_i in range(len(pads_m)):
        for b_i in range(a_i + 1, len(pads_m)):
            s_a, l_a = pads_m[a_i]
            s_b, l_b = pads_m[b_i]
            assert s_a + l_a <= s_b or s_b + l_b <= s_a, "two gicmask pads overlap"
    allowed_m = set()
    for site_m in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE):
        allowed_m |= set(range(site_m, site_m + 4))
    for key_m in ("thunk", "bringup", "send", "post"):
        off_m = int(gkm["padding"][key_m]["file_offset"], 16)
        allowed_m |= set(range(off_m, off_m + int(gkm["padding"][key_m]["code_length"])))
    changed_m = [i for i in range(len(data)) if gmk[i] != data[i]]
    assert changed_m and all(c in allowed_m for c in changed_m), \
        "gicmask changed bytes outside its regions"
    assert gmk[0x8702C:0x87030] == data[0x8702C:0x87030], "gicmask altered the ISENABLER store"
    assert gmk[0x87030:0x87036] == data[0x87030:0x87036], "gicmask altered the itet block"
    check_original_gic_write(gmk)
    verify_disasm_gicmask(gmk, pad_i_m, pad_b_m, pad_s_m, pad_p_m, s1, s2, gc, ds, ec, fmc)
    assert gkm["gic_map"]["verification"]["brief_correction_0x3d8"].startswith("the brief's")
    assert gkm["gic_map"]["f_read_order"]["F5"]["ca"] == "0x400392e8"
    assert gkm["gic_map"]["f_read_order"]["F2"]["ca"] == "0x4016184c"
    assert md5(gmk) == GICMASK_MD5, f"gicmask output changed: {md5(gmk)} != {GICMASK_MD5}"

    # ---- gicking: gicmask + the H2D ring + the polarity discriminator + the IGROUPR read
    gkb, gkn = make_gicking(data, barmap, refs)
    assert len(gkb) == len(data), "gicking changed the size"
    gkb2, gkn2 = make_gicking(data, barmap, refs)
    assert gkb == gkb2, "gicking patch is not deterministic"
    assert json.dumps(gkn, sort_keys=True) == json.dumps(gkn2, sort_keys=True), \
        "gicking manifest is not deterministic"

    # every earlier cell keeps its gicmask address (the iterations stay directly comparable)
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"D{i}" for i in range(GICS_NCELLS)] + [f"E{i}" for i in range(GICP_NCELLS)]
               + [f"F{i}" for i in range(GICM_NCELLS)]):
        assert gkn["cells"][nm]["addr"] == gkm["cells"][nm]["addr"], f"gicking moved cell {nm}"

    gkc = [int(gkn["cells"][f"G{i}"]["addr"], 16) for i in range(GICK_NCELLS)]
    every_k = [s1, s2] + gc + ds + ec + fmc + gkc
    assert len(set(every_k)) == len(every_k), "gicking cells are not all distinct"
    assert all(gkn["cells"][f"G{i}"]["barmap_value"] == "0x0" for i in range(GICK_NCELLS)), \
        "a G cell baseline is not zero at BAR0"
    assert all(gkn["cells"][f"G{i}"]["barmap_alias_value"] == "0x0" for i in range(GICK_NCELLS)), \
        "a G cell baseline is not zero at the alias"
    assert all(c not in S_CELL_EXCLUDE for c in gkc), "a G cell is inside an excluded table"
    assert all(gkc[i + 1] - gkc[i] >= 8 for i in range(GICK_NCELLS - 1)), \
        "the G cells are not >= 8 bytes apart"
    ggp = int(gkn["selection"]["g_page"], 16)
    assert ggp == int(gkn["selection"]["all_zero_pages"][GICK_G_PAGE_IDX], 16), \
        "gicking picked an unexpected G page"
    assert all(ggp <= c < ggp + 0x1000 for c in gkc), "the G cells are not in the G page"
    assert all(word_at(barmap, x) == 0 and word_at(barmap, ALIAS_OFF + x) == 0
               for x in range(ggp, ggp + 0x1000, 4)), f"G page {ggp:#x} is not all-zero in the barmap"
    assert gkn["gic_map"]["ring"]["ca"] == hex(GICK_RING_CA) == "0x400392d4"
    assert gkn["gic_map"]["ring"]["value"] == "0x1"
    assert gkn["gic_map"]["GICD_IGROUPR2"] == hex(GICD_IGROUPR2) == "0x40161088"
    assert gkn["gic_map"]["glue"]["mask_masked"] == "0x21"
    assert gkn["gic_map"]["glue"]["mask_open"] == "0x20"

    pad_i_k = int(gkn["padding"]["thunk"]["file_offset"], 16)
    pad_b_k = int(gkn["padding"]["bringup"]["file_offset"], 16)
    pad_s_k = int(gkn["padding"]["send"]["file_offset"], 16)
    pad_p_k = int(gkn["padding"]["post"]["file_offset"], 16)
    code_i_k = pad_thunk(pad_i_k, s1, gc, apsr_cell=ec[3], req_cell=ec[2], f_req_cell=fmc[9])
    code_b_k = pad_bringup(pad_b_k, s2, gc)
    code_s_k = pad_send(pad_s_k, ds, fmc, gkc)
    code_p_k = pad_post(pad_p_k, ec)
    for off_k, code_k in ((pad_i_k, code_i_k), (pad_b_k, code_b_k), (pad_s_k, code_s_k),
                          (pad_p_k, code_p_k)):
        assert gkb[off_k:off_k + len(code_k)] == code_k, \
            f"the gicking pad at {off_k:#x} is not in the image"
    for site_k, pad_k in ((SITE_THUNK, pad_i_k), (BRINGUP_SITE, pad_b_k), (SEND_SITE, pad_s_k),
                          (POST_SITE, pad_p_k)):
        assert gkb[site_k:site_k + 4] == bl(site_k, pad_k), f"site {site_k:#x} is not the intended bl"

    # the ring/discriminator/IGROUPR gates are present and in order
    blk_set = write_ca_block(GICK_GLUE_MASK, GICK_MASK_MASKED)
    blk_ring = write_ca_block(GICK_RING_CA, GICK_RING_VAL)
    blk_open = write_ca_block(GICK_GLUE_MASK, GICK_MASK_OPEN)
    assert blk_set in code_s_k and blk_ring in code_s_k and blk_open in code_s_k, \
        "the gicking send pad lost a ring/mask store"
    assert code_s_k.count(blk_ring) == 1, "the gicking send pad must ring exactly once"
    assert gic_read_store_block(GICD_IGROUPR2, gkc[2]) in code_s_k, "the IGROUPR read is missing"
    assert _store_imm_block(GICK_SENTINEL, gkc[3]) in code_s_k, "the G3 sentinel is missing"
    order_k = [code_s_k.index(blk_set), code_s_k.index(blk_ring),
               code_s_k.index(gic_read_store_block(GIC_SEND_READS[0], ds[0])),
               code_s_k.index(gic_read_store_block(GICM_READS[0][0], fmc[0])),
               code_s_k.index(gic_read_store_block(GICM_READS[5][0], fmc[5])),
               code_s_k.index(blk_open),
               code_s_k.index(gic_read_store_block(GICK_GLUE_STATUS, gkc[0])),
               code_s_k.index(gic_read_store_block(GICD_IGROUPR2, gkc[2])),
               code_s_k.index(_store_imm_block(GICK_SENTINEL, gkc[3]))]
    assert order_k == sorted(order_k) and len(set(order_k)) == len(order_k), \
        "the gicking send pad order is not mask-masked -> ring -> D/F -> mask-open -> G"

    # no gicking pad may address a forbidden CA (intr-clear, acknowledging IAR, RC misc)
    for bad_k in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                  write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
        assert bad_k not in code_i_k and bad_k not in code_b_k and bad_k not in code_s_k \
            and bad_k not in code_p_k, "a gicking pad addresses a forbidden CA"

    pads_k = [(pad_i_k, len(code_i_k)), (pad_b_k, len(code_b_k)), (pad_s_k, len(code_s_k)),
              (pad_p_k, len(code_p_k))]
    for a_i in range(len(pads_k)):
        for b_i in range(a_i + 1, len(pads_k)):
            s_a, l_a = pads_k[a_i]
            s_b, l_b = pads_k[b_i]
            assert s_a + l_a <= s_b or s_b + l_b <= s_a, "two gicking pads overlap"
    allowed_k = set()
    for site_k in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE):
        allowed_k |= set(range(site_k, site_k + 4))
    for key_k in ("thunk", "bringup", "send", "post"):
        off_k = int(gkn["padding"][key_k]["file_offset"], 16)
        allowed_k |= set(range(off_k, off_k + int(gkn["padding"][key_k]["code_length"])))
    changed_k = [i for i in range(len(data)) if gkb[i] != data[i]]
    assert changed_k and all(c in allowed_k for c in changed_k), \
        "gicking changed bytes outside its regions"
    assert gkb[0x8702C:0x87030] == data[0x8702C:0x87030], "gicking altered the ISENABLER store"
    assert gkb[0x87030:0x87036] == data[0x87030:0x87036], "gicking altered the itet block"
    check_original_gic_write(gkb)
    verify_disasm_gicking(gkb, pad_i_k, pad_b_k, pad_s_k, pad_p_k, s1, s2, gc, ds, ec, fmc, gkc)

    # gicking must differ from gicmask ONLY at the four sites and the four pads (same sites, so
    # only the bl displacements and the pad bodies move)
    diff_gmk = [i for i in range(len(data)) if gkb[i] != gmk[i]]
    assert diff_gmk and all(c in allowed_k for c in diff_gmk), \
        "gicking differs from gicmask outside the sites/pads"
    assert md5(gkb) == GICKING_MD5, f"gicking output changed: {md5(gkb)} != {GICKING_MD5}"

    # ---- gicunmask: gicking's open step R2 - the POST-UNMASK ring->GIC sample (H0..H7)
    gub, gum = make_gicunmask(data, barmap, refs)
    assert len(gub) == len(data), "gicunmask changed the size"
    gub2, gum2 = make_gicunmask(data, barmap, refs)
    assert gub == gub2, "gicunmask patch is not deterministic"
    assert json.dumps(gum, sort_keys=True) == json.dumps(gum2, sort_keys=True), \
        "gicunmask manifest is not deterministic"
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)]):
        assert gum["cells"][nm]["addr"] == gpm["cells"][nm]["addr"], f"gicunmask moved cell {nm}"
    hcu = [int(gum["cells"][f"H{i}"]["addr"], 16) for i in range(GICU_NCELLS)]
    every_u = [s1, s2] + gc + ec + hcu
    assert len(set(every_u)) == len(every_u), "gicunmask cells are not all distinct"
    assert all(c not in S_CELL_EXCLUDE for c in hcu), "an H cell is inside an excluded table"
    assert all(gum["cells"][f"H{i}"]["barmap_value"] == "0x0" for i in range(GICU_NCELLS)), \
        "an H cell baseline is not zero at BAR0"
    assert all(gum["cells"][f"H{i}"]["barmap_alias_value"] == "0x0" for i in range(GICU_NCELLS)), \
        "an H cell baseline is not zero at the alias"
    assert all(hcu[i + 1] - hcu[i] >= 8 for i in range(4)) and hcu[6] - hcu[4] >= 8 \
        and hcu[7] - hcu[5] >= 8, "the H sample cells are not >= 8 bytes apart"
    pages_u = [int(p, 16) for p in gum["selection"]["all_zero_pages"]]
    hu1 = int(gum["selection"]["h_page_1"], 16)
    hu2 = int(gum["selection"]["h_page_2"], 16)
    assert hu1 == pages_u[GICU_H_PAGE_1_IDX] and hu2 == pages_u[GICU_H_PAGE_2_IDX], \
        "gicunmask picked unexpected H pages"
    assert all(hu1 <= c < hu1 + 0x1000 for c in hcu[:5] + [hcu[6]]), "H0..H4/H6 are not in page 1"
    assert all(hu2 <= c < hu2 + 0x1000 for c in (hcu[5], hcu[7])), "H5/H7 are not in page 2"
    assert hcu[6] == hu1 + 0x28 and hcu[7] == hu2 + 0x8, "the H sentinels are not the 6th/2nd cells"
    for p in (hu1, hu2):
        assert all(word_at(barmap, x) == 0 and word_at(barmap, ALIAS_OFF + x) == 0
                   for x in range(p, p + 0x1000, 4)), f"H page {p:#x} is not all-zero in the barmap"
    assert [r for r in GICU_READS] == [0x40161208, 0x40160118, 0x40161308, 0x400392E4, 0x400392EC]
    assert gum["gic_map"]["ring"]["ca"] == hex(GICU_RING_CA) == "0x400392d4"
    assert gum["gic_map"]["ring"]["value"] == "0x1"
    assert gum["gic_map"]["glue"]["mask_open"] == "0x20"
    assert gum["gic_map"]["h_read_order"]["H0"]["ca"] == "0x40161208"
    assert gum["gic_map"]["h_read_order"]["H5"]["ca"] == "0x40161208"
    assert gum["gic_map"]["h_read_order"]["H6"]["ca"] == "none"
    assert gum["gic_map"]["h_read_order"]["H7"]["ca"] == "none"
    assert "branch_H0_bit12_set" in gum["classification"]
    assert "branch_H0_clear_H3_H4_set" in gum["classification"]
    assert "branch_H0_clear_H5_set" in gum["classification"]

    pad_i_u = int(gum["padding"]["thunk"]["file_offset"], 16)
    pad_b_u = int(gum["padding"]["bringup"]["file_offset"], 16)
    pad_s_u = int(gum["padding"]["send"]["file_offset"], 16)
    pad_p_u = int(gum["padding"]["post"]["file_offset"], 16)
    code_i_u = pad_thunk(pad_i_u, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b_u = pad_bringup(pad_b_u, s2, gc)
    code_s_u = pad_send_h(pad_s_u, hcu)
    code_p_u = pad_post(pad_p_u, ec)
    for off_u, code_u in ((pad_i_u, code_i_u), (pad_b_u, code_b_u), (pad_s_u, code_s_u),
                          (pad_p_u, code_p_u)):
        assert gub[off_u:off_u + len(code_u)] == code_u, \
            f"the gicunmask pad at {off_u:#x} is not in the image"
    for site_u, pad_u in ((SITE_THUNK, pad_i_u), (BRINGUP_SITE, pad_b_u), (SEND_SITE, pad_s_u),
                          (POST_SITE, pad_p_u)):
        assert gub[site_u:site_u + 4] == bl(site_u, pad_u), f"site {site_u:#x} is not the intended bl"
    blk_open_u = write_ca_block(GICU_GLUE_MASK, GICU_MASK_OPEN)
    blk_ring_u = write_ca_block(GICU_RING_CA, GICU_RING_VAL)
    assert blk_open_u in code_s_u and blk_ring_u in code_s_u, "the gicunmask send pad lost a store"
    assert code_s_u.count(blk_ring_u) == 1, "the gicunmask send pad must ring exactly once"
    assert write_ca_block(GICK_GLUE_MASK, GICK_MASK_MASKED) not in code_s_u, \
        "gicunmask must NOT write the masked 0x21 word (the mask is open across the ring)"
    for i, ca_u in enumerate(GICU_READS):
        assert gic_read_store_block(ca_u, hcu[i]) in code_s_u, f"send pad missing H{i} ({ca_u:#x})"
    assert gic_read_store_block(GICD_ISPENDR2, hcu[5]) in code_s_u, "send pad missing the H5 entry read"
    assert _store_imm_block(GICU_SENTINEL, hcu[6]) in code_s_u, "send pad missing the H6 sentinel"
    assert _store_imm_block(GICU_SENTINEL, hcu[7]) in code_s_u, "send pad missing the H7 sentinel"
    order_u = [code_s_u.index(gic_read_store_block(GICD_ISPENDR2, hcu[5])),
               code_s_u.index(blk_open_u),
               code_s_u.index(blk_ring_u),
               code_s_u.index(gic_read_store_block(GICD_ISPENDR2, hcu[0])),
               code_s_u.index(gic_read_store_block(GICU_GLUE_STATUS, hcu[4])),
               code_s_u.index(_store_imm_block(GICU_SENTINEL, hcu[6])),
               code_s_u.index(_store_imm_block(GICU_SENTINEL, hcu[7]))]
    assert order_u == sorted(order_u) and len(set(order_u)) == len(order_u), \
        "the gicunmask send pad order is not H5 -> mask-open -> ring -> H0..H4 -> sentinels"
    for bad_u in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                  write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
        assert bad_u not in code_i_u and bad_u not in code_b_u and bad_u not in code_s_u \
            and bad_u not in code_p_u, "a gicunmask pad addresses a forbidden CA"
    pads_u = [(pad_i_u, len(code_i_u)), (pad_b_u, len(code_b_u)), (pad_s_u, len(code_s_u)),
              (pad_p_u, len(code_p_u))]
    for a_u in range(len(pads_u)):
        for b_u in range(a_u + 1, len(pads_u)):
            s_a_u, l_a_u = pads_u[a_u]
            s_b_u, l_b_u = pads_u[b_u]
            assert s_a_u + l_a_u <= s_b_u or s_b_u + l_b_u <= s_a_u, "two gicunmask pads overlap"
    allowed_u = set()
    for site_u in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE):
        allowed_u |= set(range(site_u, site_u + 4))
    for key_u in ("thunk", "bringup", "send", "post"):
        off_u = int(gum["padding"][key_u]["file_offset"], 16)
        allowed_u |= set(range(off_u, off_u + int(gum["padding"][key_u]["code_length"])))
    changed_u = [i for i in range(len(data)) if gub[i] != data[i]]
    assert changed_u and all(c in allowed_u for c in changed_u), \
        "gicunmask changed bytes outside its regions"
    assert gub[0x8702C:0x87030] == data[0x8702C:0x87030], "gicunmask altered the ISENABLER store"
    assert gub[0x87030:0x87036] == data[0x87030:0x87036], "gicunmask altered the itet block"
    check_original_gic_write(gub)
    verify_disasm_gicunmask(gub, pad_i_u, pad_b_u, pad_s_u, pad_p_u, s1, s2, gc, ec, hcu)
    assert md5(gub) == GICUNMASK_MD5, f"gicunmask output changed: {md5(gub)} != {GICUNMASK_MD5}"

    # the thunk/bring-up/post pads must be the SAME instruction program as gicpost's (the S/C/E
    # sanities are unchanged); only the branch displacements differ because the pads may land at
    # different file offsets, so compare the branch-target-normalized instruction streams
    mdz = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def norm_stream(off_u, code_u):
        out_u = []
        for ins_u in mdz.disasm(code_u, off_u):
            out_u.append(ins_u.mnemonic + (" <br>" if ins_u.mnemonic.startswith("b") else
                                           f" {ins_u.op_str}"))
        return out_u

    pad_i_p = int(gpm["padding"]["thunk"]["file_offset"], 16)
    pad_b_p = int(gpm["padding"]["bringup"]["file_offset"], 16)
    pad_p_p = int(gpm["padding"]["post"]["file_offset"], 16)
    for key_u, off_u, code_u, off_p, code_p in (
            ("thunk", pad_i_u, code_i_u, pad_i_p,
             pad_thunk(pad_i_p, s1, gc, apsr_cell=ec[3], req_cell=ec[2])),
            ("bringup", pad_b_u, code_b_u, pad_b_p, pad_bringup(pad_b_p, s2, gc)),
            ("post", pad_p_u, code_p_u, pad_p_p, pad_post(pad_p_p, ec))):
        assert len(code_u) == len(code_p), f"the gicunmask {key_u} pad length differs from gicpost"
        assert norm_stream(off_u, code_u) == norm_stream(off_p, code_p), \
            f"the gicunmask {key_u} pad is not the same instruction program as gicpost's"
    # the send pad must differ from gicpost's (it carries gicunmask's own open+ring+H sequence)
    assert gum["padding"]["send"]["code_hex"] != gpm["padding"]["send"]["code_hex"]

    # ---- trigring: trigger.md section 3's candidate at the natural post, PRE/POST samples (T0..T9)
    gtr, gtm = make_trigring(data, barmap, refs)
    assert len(gtr) == len(data), "trigring changed the size"
    gtr2, gtm2 = make_trigring(data, barmap, refs)
    assert gtr == gtr2, "trigring patch is not deterministic"
    assert json.dumps(gtm, sort_keys=True) == json.dumps(gtm2, sort_keys=True), \
        "trigring manifest is not deterministic"
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)]):
        assert gtm["cells"][nm]["addr"] == gpm["cells"][nm]["addr"], f"trigring moved cell {nm}"
    tct = [int(gtm["cells"][f"T{i}"]["addr"], 16) for i in range(TRIG_NCELLS)]
    every_t = [s1, s2] + gc + ec + tct
    assert len(set(every_t)) == len(every_t), "trigring cells are not all distinct"
    assert all(c not in S_CELL_EXCLUDE for c in tct), "a T cell is inside an excluded table"
    assert all(gtm["cells"][f"T{i}"]["barmap_value"] == "0x0" for i in range(TRIG_NCELLS)), \
        "a T cell baseline is not zero at BAR0"
    assert all(gtm["cells"][f"T{i}"]["barmap_alias_value"] == "0x0" for i in range(TRIG_NCELLS)), \
        "a T cell baseline is not zero at the alias"
    assert all(tct[i + 1] - tct[i] >= 8 for i in range(3)), "T0..T3 are not >= 8 bytes apart"
    assert all(tct[4 + i + 1] - tct[4 + i] >= 8 for i in range(3)), "T4..T7 are not >= 8 bytes apart"
    assert tct[8] - tct[3] >= 8 and tct[9] - tct[7] >= 8, \
        "the T sentinels are not >= 8 bytes from their page's samples"
    pages_t = [int(p, 16) for p in gtm["selection"]["all_zero_pages"]]
    t1p = int(gtm["selection"]["t_page_1"], 16)
    t2p = int(gtm["selection"]["t_page_2"], 16)
    assert t1p == pages_t[TRIG_T_PAGE_1_IDX] and t2p == pages_t[TRIG_T_PAGE_2_IDX], \
        "trigring picked unexpected T pages"
    assert all(t1p <= c < t1p + 0x1000 for c in tct[:4] + [tct[8]]), "T0..T3/TS1 are not in page 1"
    assert all(t2p <= c < t2p + 0x1000 for c in tct[4:8] + [tct[9]]), "T4..T7/TS2 are not in page 2"
    assert tct[8] == t1p + 0x20 and tct[9] == t2p + 0x20, \
        "the T sentinels are not the fifth cells of their pages"
    for p in (t1p, t2p):
        assert all(word_at(barmap, x) == 0 and word_at(barmap, ALIAS_OFF + x) == 0
                   for x in range(p, p + 0x1000, 4)), f"T page {p:#x} is not all-zero in the barmap"
    assert [r for r in TRIG_READS] == [0x40161208, 0x40160118, 0x400392E4, 0x400392EC]
    assert gtm["gic_map"]["ring"]["ca"] == hex(TRIG_RING_CA) == "0x400392d4"
    assert gtm["gic_map"]["ring"]["value"] == "0x1"
    assert gtm["gic_map"]["glue"]["mask_open"] == "0x20"
    assert TRIG_RING_OFF == 0x2C0 and GIC_SEND_READS[0] == GICD_ISPENDR2
    assert int("0x40039014", 16) + TRIG_RING_OFF == TRIG_RING_CA, \
        "the trigring ring is not trigger.md's r3+0x2C0 == 0x400392d4"
    assert "branch_T4_bit12_set" in gtm["classification"]
    assert "branch_T4_clear_T6_T7_set" in gtm["classification"]
    assert "host_side" in gtm["classification"]
    assert gtm["gic_map"]["t_read_order"]["T0"]["ca"] == "0x40161208"
    assert gtm["gic_map"]["t_read_order"]["T4"]["ca"] == "0x40161208"
    assert gtm["gic_map"]["t_read_order"]["T8"]["ca"] == "none"
    assert gtm["gic_map"]["t_read_order"]["T9"]["ca"] == "none"

    pad_i_t = int(gtm["padding"]["thunk"]["file_offset"], 16)
    pad_b_t = int(gtm["padding"]["bringup"]["file_offset"], 16)
    pad_s_t = int(gtm["padding"]["send"]["file_offset"], 16)
    pad_p_t = int(gtm["padding"]["post"]["file_offset"], 16)
    code_i_t = pad_thunk(pad_i_t, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b_t = pad_bringup(pad_b_t, s2, gc)
    code_s_t = pad_send_trig(pad_s_t, tct)
    code_p_t = pad_post(pad_p_t, ec)
    for off_t, code_t in ((pad_i_t, code_i_t), (pad_b_t, code_b_t), (pad_s_t, code_s_t),
                          (pad_p_t, code_p_t)):
        assert gtr[off_t:off_t + len(code_t)] == code_t, \
            f"the trigring pad at {off_t:#x} is not in the image"
    for site_t, pad_t in ((SITE_THUNK, pad_i_t), (BRINGUP_SITE, pad_b_t), (SEND_SITE, pad_s_t),
                          (POST_SITE, pad_p_t)):
        assert gtr[site_t:site_t + 4] == bl(site_t, pad_t), f"site {site_t:#x} is not the intended bl"
    blk_open_t = write_ca_block(TRIG_GLUE_MASK, TRIG_MASK_OPEN)
    blk_ring_t = write_ca_block(TRIG_RING_CA, TRIG_RING_VAL)
    assert blk_open_t in code_s_t and blk_ring_t in code_s_t, "the trigring send pad lost a store"
    assert code_s_t.count(blk_ring_t) == 1, "the trigring send pad must ring exactly once"
    assert write_ca_block(GICK_GLUE_MASK, GICK_MASK_MASKED) not in code_s_t, \
        "trigring must NOT write the masked 0x21 word (the mask is open across the ring)"
    for i in range(4):
        assert gic_read_store_block(TRIG_READS[i], tct[i]) in code_s_t, f"send pad missing PRE T{i}"
        assert gic_read_store_block(TRIG_READS[i], tct[4 + i]) in code_s_t, \
            f"send pad missing POST T{4 + i}"
    assert _store_imm_block(TRIG_SENTINEL, tct[8]) in code_s_t, "send pad missing the TS1 sentinel"
    assert _store_imm_block(TRIG_SENTINEL, tct[9]) in code_s_t, "send pad missing the TS2 sentinel"
    order_t = [code_s_t.index(str_imm(2, 3, 0)), code_s_t.index(blk_open_t)] \
        + [code_s_t.index(gic_read_store_block(TRIG_READS[i], tct[i])) for i in range(4)] \
        + [code_s_t.index(_store_imm_block(TRIG_SENTINEL, tct[8])), code_s_t.index(blk_ring_t)] \
        + [code_s_t.index(gic_read_store_block(TRIG_READS[i], tct[4 + i])) for i in range(4)] \
        + [code_s_t.index(_store_imm_block(TRIG_SENTINEL, tct[9]))]
    assert order_t == sorted(order_t) and len(set(order_t)) == len(order_t), \
        "the trigring send pad order is not post-reproduce -> mask-open -> T0..T3 -> TS1 -> ring -> "
    for bad_t in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                  write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
        assert bad_t not in code_i_t and bad_t not in code_b_t and bad_t not in code_s_t \
            and bad_t not in code_p_t, "a trigring pad addresses a forbidden CA"
    pads_t = [(pad_i_t, len(code_i_t)), (pad_b_t, len(code_b_t)), (pad_s_t, len(code_s_t)),
              (pad_p_t, len(code_p_t))]
    for a_t in range(len(pads_t)):
        for b_t in range(a_t + 1, len(pads_t)):
            s_a_t, l_a_t = pads_t[a_t]
            s_b_t, l_b_t = pads_t[b_t]
            assert s_a_t + l_a_t <= s_b_t or s_b_t + l_b_t <= s_a_t, "two trigring pads overlap"
    allowed_t = set()
    for site_t in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE):
        allowed_t |= set(range(site_t, site_t + 4))
    for key_t in ("thunk", "bringup", "send", "post"):
        off_t = int(gtm["padding"][key_t]["file_offset"], 16)
        allowed_t |= set(range(off_t, off_t + int(gtm["padding"][key_t]["code_length"])))
    changed_t = [i for i in range(len(data)) if gtr[i] != data[i]]
    assert changed_t and all(c in allowed_t for c in changed_t), \
        "trigring changed bytes outside its regions"
    assert gtr[0x8702C:0x87030] == data[0x8702C:0x87030], "trigring altered the ISENABLER store"
    assert gtr[0x87030:0x87036] == data[0x87030:0x87036], "trigring altered the itet block"
    check_original_gic_write(gtr)
    verify_disasm_trigring(gtr, pad_i_t, pad_b_t, pad_s_t, pad_p_t, s1, s2, gc, ec, tct)
    # the thunk/bring-up/post pads must be the SAME instruction program as gicpost's (the S/C/E
    # sanities are unchanged); only the branch displacements differ
    for key_t, off_t, code_t, off_p, code_p in (
            ("thunk", pad_i_t, code_i_t, pad_i_p,
             pad_thunk(pad_i_p, s1, gc, apsr_cell=ec[3], req_cell=ec[2])),
            ("bringup", pad_b_t, code_b_t, pad_b_p, pad_bringup(pad_b_p, s2, gc)),
            ("post", pad_p_t, code_p_t, pad_p_p, pad_post(pad_p_p, ec))):
        assert len(code_t) == len(code_p), f"the trigring {key_t} pad length differs from gicpost"
        assert norm_stream(off_t, code_t) == norm_stream(off_p, code_p), \
            f"the trigring {key_t} pad is not the same instruction program as gicpost's"
    assert gtm["padding"]["send"]["code_hex"] != gum["padding"]["send"]["code_hex"]
    assert md5(gtr) == TRIGRING_MD5, f"trigring output changed: {md5(gtr)} != {TRIGRING_MD5}"

    # ---- trignat: the natural-post ring + the device-dispatcher consumption witness
    gtn, gtnm = make_trignat(data, barmap, refs)
    assert len(gtn) == len(data), "trignat changed the size"
    gtn2, gtnm2 = make_trignat(data, barmap, refs)
    assert gtn == gtn2, "trignat patch is not deterministic"
    assert json.dumps(gtnm, sort_keys=True) == json.dumps(gtnm2, sort_keys=True), \
        "trignat manifest is not deterministic"
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)]):
        assert gtnm["cells"][nm]["addr"] == gpm["cells"][nm]["addr"], f"trignat moved cell {nm}"

    a_names = [f"A_S{i}" for i in range(4)] + ["A_P1", "A_E0", "A_E1"] \
        + [f"A_S{i}" for i in range(4, 9)] + ["A_P2"]
    b_names = [f"B_D{i}" for i in range(4)] + ["B_P3"]
    assert len(a_names) == TRIGNAT_A_NCELLS and len(b_names) == TRIGNAT_B_NCELLS
    acn = [int(gtnm["cells"][nm]["addr"], 16) for nm in a_names]
    bcn = [int(gtnm["cells"][nm]["addr"], 16) for nm in b_names]
    every_n = [s1, s2] + gc + ec + acn + bcn
    assert len(set(every_n)) == len(every_n), "trignat cells are not all distinct"
    for nm in a_names + b_names:
        assert gtnm["cells"][nm]["barmap_value"] == "0x0", f"{nm} baseline is not zero at BAR0"
        assert gtnm["cells"][nm]["barmap_alias_value"] == "0x0", \
            f"{nm} baseline is not zero at the alias"
    assert all(c not in S_CELL_EXCLUDE for c in acn + bcn), \
        "a trignat cell is inside an excluded table"
    assert all(acn[i + 1] - acn[i] >= 8 for i in range(6)), "A_S0..A_P1..A_E1 are not >= 8 apart"
    p10_cells = acn[7:13] + bcn
    assert all(p10_cells[i + 1] - p10_cells[i] >= 8 for i in range(len(p10_cells) - 1)), \
        "the page-10 trignat cells are not >= 8 bytes apart"
    pages_n = [int(p, 16) for p in gtnm["selection"]["all_zero_pages"]]
    ap_n = int(gtnm["selection"]["a_page"], 16)
    bp_n = int(gtnm["selection"]["b_page"], 16)
    assert ap_n == pages_n[TRIGNAT_A_PAGE_IDX] and bp_n == pages_n[TRIGNAT_B_PAGE_IDX], \
        "trignat picked unexpected A/B pages"
    assert ap_n == 0x14F000 and bp_n == 0x150000, "trignat pages are not 0x14f000/0x150000"
    assert all(ap_n <= c < ap_n + 0x1000 for c in acn[:7]), "the page-9 A cells are not in page 9"
    assert all(bp_n <= c < bp_n + 0x1000 for c in acn[7:13] + bcn), \
        "the page-10 A/B cells are not in page 10"
    assert acn[4] == ap_n + 0x20 and acn[12] == bp_n + 0x28 and bcn[4] == bp_n + 0x50, \
        "the trignat sentinels are not the expected cells of their pages"
    for p in (ap_n, bp_n):
        assert all(word_at(barmap, x) == 0 and word_at(barmap, ALIAS_OFF + x) == 0
                   for x in range(p, p + 0x1000, 4)), f"trignat page {p:#x} is not all-zero"

    # the two sites: Pad A replaces the natural post pair, Pad B the announce routine's pop.w
    assert TRIGNAT_SITE_A == SEND_SITE == 0x86F5A and TRIGNAT_CONT_A == SEND_CONT == 0x86F5E
    assert data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] == bytes.fromhex("1a600122"), \
        "the Pad A site is not str r2,[r3]+movs r2,#1"
    assert TRIGNAT_SITE_B == 0x86F7E and TRIGNAT_CONT_B == 0x86F82
    assert TRIGNAT_DRAIN_POP == bytes.fromhex("bde8f843") == data[0x86F7E:0x86F82], \
        "the Pad B site is not pop.w {r3,r4,r5,r6,r7,r8,sb,lr}"
    assert gtnm["sites"]["send_a"]["replaced_bytes"] == "1a600122"
    assert gtnm["sites"]["drain_b"]["replaced_bytes"] == "bde8f843"

    pad_i_n = int(gtnm["padding"]["thunk"]["file_offset"], 16)
    pad_b_n = int(gtnm["padding"]["bringup"]["file_offset"], 16)
    pad_s_n = int(gtnm["padding"]["send_a"]["file_offset"], 16)
    pad_p_n = int(gtnm["padding"]["post"]["file_offset"], 16)
    pad_d_n = int(gtnm["padding"]["drain_b"]["file_offset"], 16)
    code_i_n = pad_thunk(pad_i_n, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b_n = pad_bringup(pad_b_n, s2, gc)
    code_s_n = pad_send_trignat(pad_s_n, acn)
    code_p_n = pad_post(pad_p_n, ec)
    code_d_n = pad_drain_trignat(pad_d_n, bcn)
    for off_n, code_n in ((pad_i_n, code_i_n), (pad_b_n, code_b_n), (pad_s_n, code_s_n),
                          (pad_p_n, code_p_n), (pad_d_n, code_d_n)):
        assert gtn[off_n:off_n + len(code_n)] == code_n, \
            f"the trignat pad at {off_n:#x} is not in the image"
    for site_n, pad_n in ((SITE_THUNK, pad_i_n), (BRINGUP_SITE, pad_b_n), (SEND_SITE, pad_s_n),
                          (POST_SITE, pad_p_n), (TRIGNAT_SITE_B, pad_d_n)):
        assert gtn[site_n:site_n + 4] == bl(site_n, pad_n), \
            f"site {site_n:#x} is not the intended bl"

    blk_open_n = write_ca_block(TRIGNAT_GLUE_MASK, TRIGNAT_MASK_OPEN)
    blk_submit_n = write_ca_block(TRIGNAT_OUT0_CA, TRIGNAT_SUBMIT_VAL)
    blk_ring_n = write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL)
    assert blk_open_n in code_s_n and blk_submit_n in code_s_n and blk_ring_n in code_s_n, \
        "the trignat Pad A lost a mask/submit/ring store"
    assert code_s_n.count(blk_ring_n) == 1, "the trignat Pad A must ring exactly once"
    assert blk_ring_n not in code_d_n, "the trignat Pad B must not ring"
    assert write_ca_block(TRIGNAT_GLUE_MASK, GICK_MASK_MASKED) not in code_s_n, \
        "trignat must NOT write the masked 0x21 word"
    for i, ca_n in enumerate(TRIGNAT_PRE_READS):
        assert gic_read_store_block(ca_n, acn[i]) in code_s_n, f"Pad A missing A_S{i} ({ca_n:#x})"
    a_samples_n = acn[0:4] + acn[7:12]
    assert len(a_samples_n) == TRIGNAT_A_NSAMPLES
    for i, ca_n in enumerate(TRIGNAT_POST_READS):
        assert gic_read_store_block(ca_n, a_samples_n[3 + i]) in code_s_n, \
            f"Pad A missing A_S{3 + i} ({ca_n:#x})"
    assert gic_read_store_block(TRIGNAT_OUT0_CA, acn[5]) in code_s_n, "Pad A missing the A_E0 entry read"
    assert gic_read_store_block(TRIGNAT_OUT1_CA, acn[6]) in code_s_n, "Pad A missing the A_E1 entry read"
    assert _store_imm_block(TRIGNAT_SENTINEL, acn[4]) in code_s_n, "Pad A missing the A_P1 sentinel"
    assert _store_imm_block(TRIGNAT_SENTINEL, acn[12]) in code_s_n, "Pad A missing the A_P2 sentinel"
    for i, ca_n in enumerate(TRIGNAT_B_READS):
        assert gic_read_store_block(ca_n, bcn[i]) in code_d_n, f"Pad B missing B_D{i} ({ca_n:#x})"
    assert _store_imm_block(TRIGNAT_SENTINEL, bcn[4]) in code_d_n, "Pad B missing the B_P3 sentinel"
    assert TRIGNAT_DRAIN_POP in code_d_n, "Pad B must reproduce the replaced pop.w"
    assert str_imm(2, 3, 0) in code_s_n, "Pad A missing the reproduced out[1] store"
    assert movw(2, 1) in code_s_n, "Pad A missing the reproduced movs r2,#1"
    for code_n in (code_s_n, code_d_n):
        assert push(PAD_SAVE) in code_n and pop(PAD_SAVE) in code_n, "a trignat pad lost the save/restore"
    assert b_w(pad_s_n + len(code_s_n) - 4, TRIGNAT_CONT_A) == code_s_n[-4:], "Pad A return is wrong"
    assert b_w(pad_d_n + len(code_d_n) - 4, TRIGNAT_CONT_B) == code_d_n[-4:], "Pad B return is wrong"

    order_n = [code_s_n.index(gic_read_store_block(TRIGNAT_OUT0_CA, acn[5])),   # A_E0
               code_s_n.index(gic_read_store_block(TRIGNAT_OUT1_CA, acn[6])),   # A_E1
               code_s_n.index(str_imm(2, 3, 0)),                                # post reproduce
               code_s_n.index(blk_open_n),                                     # mask open
               code_s_n.index(blk_submit_n),                                   # submit
               code_s_n.index(gic_read_store_block(TRIGNAT_OUT0_CA, acn[0])),   # A_S0
               code_s_n.index(blk_ring_n),                                     # ring
               code_s_n.index(gic_read_store_block(GICD_ISPENDR2, acn[3])),     # A_S3
               code_s_n.index(_store_imm_block(TRIGNAT_SENTINEL, acn[4])),      # A_P1
               code_s_n.index(_store_imm_block(TRIGNAT_SENTINEL, acn[12]))]     # A_P2
    assert order_n == sorted(order_n) and len(set(order_n)) == len(order_n), \
        "the trignat Pad A order is not entry -> post -> mask -> submit -> pre -> ring -> post -> P1/P2"
    order_d_n = [code_d_n.index(gic_read_store_block(TRIGNAT_B_READS[i], bcn[i])) for i in range(4)]
    order_d_n.append(code_d_n.index(_store_imm_block(TRIGNAT_SENTINEL, bcn[4])))
    order_d_n.append(code_d_n.index(TRIGNAT_DRAIN_POP))
    assert order_d_n == sorted(order_d_n) and len(set(order_d_n)) == len(order_d_n), \
        "the trignat Pad B order is not B_D0..B_D3 -> B_P3 -> reproduce pop.w"
    for bad_n in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                  write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
        for code_n in (code_i_n, code_b_n, code_s_n, code_p_n, code_d_n):
            assert bad_n not in code_n, "a trignat pad addresses a forbidden CA"

    pads_n = [(pad_i_n, len(code_i_n)), (pad_b_n, len(code_b_n)), (pad_s_n, len(code_s_n)),
              (pad_p_n, len(code_p_n)), (pad_d_n, len(code_d_n))]
    for a_n in range(len(pads_n)):
        for b_n in range(a_n + 1, len(pads_n)):
            s_a_n, l_a_n = pads_n[a_n]
            s_b_n, l_b_n = pads_n[b_n]
            assert s_a_n + l_a_n <= s_b_n or s_b_n + l_b_n <= s_a_n, "two trignat pads overlap"
    allowed_n = set()
    for site_n in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE, TRIGNAT_SITE_B):
        allowed_n |= set(range(site_n, site_n + 4))
    for key_n in ("thunk", "bringup", "send_a", "post", "drain_b"):
        off_n = int(gtnm["padding"][key_n]["file_offset"], 16)
        allowed_n |= set(range(off_n, off_n + int(gtnm["padding"][key_n]["code_length"])))
    changed_n = [i for i in range(len(data)) if gtn[i] != data[i]]
    assert changed_n and all(c in allowed_n for c in changed_n), \
        "trignat changed bytes outside its regions"
    assert gtn[0x8702C:0x87030] == data[0x8702C:0x87030], "trignat altered the ISENABLER store"
    assert gtn[0x87030:0x87036] == data[0x87030:0x87036], "trignat altered the itet block"
    assert gtn[SEND_CONT:SEND_CONT + 0x20] == data[SEND_CONT:SEND_CONT + 0x20], \
        "trignat altered the byte stream between the two sites"
    assert gtn[0x86F82:0x86F92] == data[0x86F82:0x86F92], \
        "trignat altered the byte stream after the drain site"
    check_original_gic_write(gtn)
    verify_disasm_trignat(gtn, pad_i_n, pad_b_n, pad_s_n, pad_p_n, pad_d_n, s1, s2, gc, ec, acn, bcn)
    for key_n, off_n, code_n, off_p2, code_p2 in (
            ("thunk", pad_i_n, code_i_n, pad_i_p,
             pad_thunk(pad_i_p, s1, gc, apsr_cell=ec[3], req_cell=ec[2])),
            ("bringup", pad_b_n, code_b_n, pad_b_p, pad_bringup(pad_b_p, s2, gc)),
            ("post", pad_p_n, code_p_n, pad_p_p, pad_post(pad_p_p, ec))):
        assert len(code_n) == len(code_p2), f"the trignat {key_n} pad length differs from gicpost"
        assert norm_stream(off_n, code_n) == norm_stream(off_p2, code_p2), \
            f"the trignat {key_n} pad is not the same instruction program as gicpost's"
    assert gtnm["classification"]["branch_TRIGNAT_COMPLETE"].startswith("A_S3 bit 12 SET")
    assert "branch_RING_PENDING_NOT_TAKEN" in gtnm["classification"]
    assert "branch_GLUE_ONLY" in gtnm["classification"]
    assert "branch_NOTHING" in gtnm["classification"]
    assert gtnm["gic_map"]["ring"]["ca"] == hex(TRIGNAT_RING_CA) == "0x400392d4"
    assert gtnm["gic_map"]["ring"]["value"] == "0x1"
    assert gtnm["gic_map"]["submit"]["ca"] == "0x40039010" and gtnm["gic_map"]["submit"]["value"] == "0x8"
    assert gtnm["gic_map"]["out1"]["ca"] == "0x40039014"
    assert gtnm["gic_map"]["dispatcher"]["consume"].startswith("ldr r5,[r2]")
    assert gtnm["gic_map"]["a_read_order"]["A_S3"]["ca"] == "0x40161208"
    assert gtnm["gic_map"]["a_read_order"]["A_S4"]["ca"] == "0x40160118"
    assert gtnm["gic_map"]["b_read_order"]["B_D0"]["ca"] == "0x40039010"
    assert gtnm["gic_map"]["b_read_order"]["B_D2"]["ca"] == "0x40161208"
    assert gtnm["gic_map"]["b_read_order"]["B_P3"]["ca"] == "none"
    assert md5(gtn) == TRIGNAT_MD5, f"trignat output changed: {md5(gtn)} != {TRIGNAT_MD5}"

    # ---- trigcons: the Pad-B MOVE past the 0xcece gate (padb.md section 3 option (a))
    gcn, gcnm = make_trigcons(data, barmap, refs)
    assert len(gcn) == len(data), "trigcons changed the size"
    gcn2, gcnm2 = make_trigcons(data, barmap, refs)
    assert gcn == gcn2, "trigcons patch is not deterministic"
    assert json.dumps(gcnm, sort_keys=True) == json.dumps(gcnm2, sort_keys=True), \
        "trigcons manifest is not deterministic"
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)] + a_names + b_names):
        assert gcnm["cells"][nm]["addr"] == gtnm["cells"][nm]["addr"], f"trigcons moved cell {nm}"
    acn_c = [int(gcnm["cells"][nm]["addr"], 16) for nm in a_names]
    bcn_c = [int(gcnm["cells"][nm]["addr"], 16) for nm in b_names]
    assert acn_c == acn and bcn_c == bcn, "trigcons changed the A/B cell addresses"

    pad_i_c = int(gcnm["padding"]["thunk"]["file_offset"], 16)
    pad_b_c = int(gcnm["padding"]["bringup"]["file_offset"], 16)
    pad_s_c = int(gcnm["padding"]["send_a"]["file_offset"], 16)
    pad_p_c = int(gcnm["padding"]["post"]["file_offset"], 16)
    pad_d_c = int(gcnm["padding"]["drain_b"]["file_offset"], 16)
    # Pad A + the thunk/bring-up/post pads are byte-identical to trignat's (same addresses too)
    for key_c, off_c, code_p3 in (("thunk", pad_i_c, code_i_n), ("bringup", pad_b_c, code_b_n),
                                  ("send_a", pad_s_c, code_s_n), ("post", pad_p_c, code_p_n)):
        assert off_c == int(gtnm["padding"][key_c]["file_offset"], 16), \
            f"trigcons moved the {key_c} pad"
        assert gcn[off_c:off_c + len(code_p3)] == code_p3, f"the trigcons {key_c} pad changed"
    assert pad_d_c == pad_d_n, "trigcons moved the drain pad"
    code_d_c = pad_drain_trigcons(pad_d_c, bcn)
    assert gcn[pad_d_c:pad_d_c + len(code_d_c)] == code_d_c, "the trigcons drain pad is not in the image"

    # the MOVED site: 0x86F74 (`movw r3,#0xcece`) -> bl; the OLD site 0x86F7E stays STOCK
    assert TRIGCONS_SITE_B == 0x86F74 and TRIGCONS_CONT_B == 0x86F78
    assert TRIGCONS_SITE_B_BYTES == bytes.fromhex("4cf6ce63") == data[0x86F74:0x86F78], \
        "the trigcons site is not `movw r3,#0xcece`"
    assert movw(3, 0xcece) == TRIGCONS_SITE_B_BYTES, "the encoder does not re-emit `movw r3,#0xcece`"
    assert data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] == TRIGNAT_DRAIN_POP, \
        "the stock old announce-exit site is not pop.w"
    assert gcn[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] == bl(TRIGCONS_SITE_B, pad_d_c), \
        "the trigcons drain site is not the intended bl"
    assert gcn[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] == data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4], \
        "trigcons altered the old announce-exit site 0x86F7E (must stay stock)"
    assert gcnm["sites"]["drain_b"]["file_offset"] == hex(TRIGCONS_SITE_B)
    assert gcnm["sites"]["drain_b"]["cont"] == hex(TRIGCONS_CONT_B) == "0x86f78"
    assert gcnm["sites"]["drain_b"]["replaced_bytes"] == "4cf6ce63"
    assert gcnm["sites"]["old_drain_b"]["unchanged"] is True

    # Pad B: re-emits the replaced movw, does NOT reproduce the old pop.w, returns to the loop head
    assert movw(3, 0xcece) in code_d_c, "trigcons Pad B lost the reproduced `movw r3,#0xcece`"
    assert TRIGNAT_DRAIN_POP not in code_d_c, "trigcons Pad B must not reproduce the old pop.w"
    assert b_w(pad_d_c + len(code_d_c) - 4, TRIGCONS_CONT_B) == code_d_c[-4:], \
        "trigcons Pad B does not return to the loop head 0x86F78"
    assert blk_ring_n not in code_d_c, "trigcons Pad B must not ring"
    for i, ca_n in enumerate(TRIGNAT_B_READS):
        assert gic_read_store_block(ca_n, bcn_c[i]) in code_d_c, f"trigcons Pad B missing B_D{i}"
    assert _store_imm_block(TRIGNAT_SENTINEL, bcn_c[4]) in code_d_c, "trigcons Pad B missing B_P3"
    for code_n in (code_d_c,):
        for bad_n in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                      write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            assert bad_n not in code_n, "the trigcons drain pad addresses a forbidden CA"

    allowed_c = set()
    for site_c in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE, TRIGCONS_SITE_B):
        allowed_c |= set(range(site_c, site_c + 4))
    for key_c in ("thunk", "bringup", "send_a", "post", "drain_b"):
        off_c = int(gcnm["padding"][key_c]["file_offset"], 16)
        allowed_c |= set(range(off_c, off_c + int(gcnm["padding"][key_c]["code_length"])))
    changed_c = [i for i in range(len(data)) if gcn[i] != data[i]]
    assert changed_c and all(c in allowed_c for c in changed_c), \
        "trigcons changed bytes outside its regions"
    assert gcn[0x8702C:0x87030] == data[0x8702C:0x87030], "trigcons altered the ISENABLER store"
    assert gcn[0x87030:0x87036] == data[0x87030:0x87036], "trigcons altered the itet block"
    assert gcn[SEND_CONT:TRIGCONS_SITE_B] == data[SEND_CONT:TRIGCONS_SITE_B], \
        "trigcons altered the byte stream between the two sites"
    assert gcn[TRIGCONS_CONT_B:TRIGNAT_SITE_B + 4] == data[TRIGCONS_CONT_B:TRIGNAT_SITE_B + 4], \
        "trigcons altered the announce loop body 0x86F78..0x86F82"
    assert gcn[TRIGNAT_SITE_B:0x86F92] == data[TRIGNAT_SITE_B:0x86F92], \
        "trigcons altered the byte stream after the old drain site"
    check_original_gic_write(gcn)
    verify_disasm_trigcons(gcn, pad_i_c, pad_b_c, pad_s_c, pad_p_c, pad_d_c, s1, s2, gc, ec, acn_c, bcn_c)
    assert gcnm["classification"]["branch_TRIGCONS_COMPLETE"].startswith("A_S3 bit 12 SET")
    assert "branch_RING_PENDING_NOT_TAKEN" in gcnm["classification"]
    assert "branch_GLUE_ONLY" in gcnm["classification"]
    assert "branch_NOTHING" in gcnm["classification"]
    assert gcnm["gic_map"]["ring"]["ca"] == hex(TRIGNAT_RING_CA) == "0x400392d4"
    assert gcnm["gic_map"]["gate"]["ca"] == "0x4000010c"
    assert gcnm["gic_map"]["gate"]["wait_value"] == "0x0000cece"
    assert gcnm["gic_map"]["dispatcher"]["consume"].startswith("ldr r5,[r2]")
    assert gcnm["gic_map"]["b_read_order"]["B_D2"]["ca"] == "0x40161208"
    assert gcnm["preserved"]["announce_loop_body"]["bytes_identical"] is True
    assert gcnm["preserved"]["old_announce_exit_continuation"]["bytes_identical"] is True
    assert md5(gcn) == TRIGCONS_MD5, f"trigcons output changed: {md5(gcn)} != {TRIGCONS_MD5}"

    # ---- inta: the DEVCPU drain + delayed cells (devcpu.md sections 4.1/4.2)
    gi, gim = make_inta(data, barmap, refs)
    assert len(gi) == len(data), "inta changed the size"
    gi2, gim2 = make_inta(data, barmap, refs)
    assert gi == gi2, "inta patch is not deterministic"
    assert json.dumps(gim, sort_keys=True) == json.dumps(gim2, sort_keys=True), \
        "inta manifest is not deterministic"
    # every trigcons cell keeps its address (the sanities stay directly comparable)
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)] + a_names + b_names):
        assert gim["cells"][nm]["addr"] == gcnm["cells"][nm]["addr"], f"inta moved cell {nm}"
    pages = _zero_page_spans(barmap)
    p_b2, p_l = pages[INTA_B2_PAGE_IDX], pages[INTA_L_PAGE_IDX]
    b2c_i = [int(gim["cells"][nm]["addr"], 16) for nm in ("B_D4", "B_D5", "B_D6", "B_D7", "B_P4")]
    assert b2c_i == [p_b2 + 8 * i for i in range(INTA_B2_NCELLS)], \
        f"the inta B2 cells are not the page-11 walk: {[hex(c) for c in b2c_i]}"
    l_names_i = ["L1_ISP", "L1_ACT", "L1_HPP", "L1_OU0", "L1_PSR",
                 "L2_ISP", "L2_ACT", "L2_HPP", "L2_OU0", "L2_PSR", "L_CNT", "L_SNT"]
    lc_i = [int(gim["cells"][nm]["addr"], 16) for nm in l_names_i]
    assert lc_i == [p_l + 8 * i for i in range(INTA_L_NCELLS)], \
        f"the inta Pad L cells are not the page-12 walk: {[hex(c) for c in lc_i]}"
    for nm in ("B_D4", "B_P4", "L1_PSR", "L2_PSR", "L_CNT", "L_SNT"):
        assert gim["cells"][nm]["barmap_value"] == "0x0" \
            and gim["cells"][nm]["barmap_alias_value"] == "0x0", f"inta cell {nm} is not zero"
    assert gim["selection"]["inta_b2_page"] == hex(p_b2) and gim["selection"]["inta_l_page"] == hex(p_l)

    pad_i_i = int(gim["padding"]["thunk"]["file_offset"], 16)
    pad_b_i = int(gim["padding"]["bringup"]["file_offset"], 16)
    pad_s_i = int(gim["padding"]["send_a"]["file_offset"], 16)
    pad_p_i = int(gim["padding"]["post"]["file_offset"], 16)
    pad_d_i = int(gim["padding"]["drain_b2"]["file_offset"], 16)
    pad_m_i = int(gim["padding"]["drain_extra"]["file_offset"], 16)
    pad_l_i = int(gim["padding"]["loop_l"]["file_offset"], 16)
    # the thunk/bring-up/send/post pads are the trigcons programs (same instruction stream; the
    # branch operands differ only because the pads moved to fresh addresses)
    for key_i in ("thunk", "bringup", "send_a", "post"):
        off_i = int(gim["padding"][key_i]["file_offset"], 16)
        n_i = int(gim["padding"][key_i]["code_length"])
        off_c4 = int(gcnm["padding"][key_i]["file_offset"], 16)
        assert norm_stream(off_i, gi[off_i:off_i + n_i]) == \
            norm_stream(off_c4, gcn[off_c4:off_c4 + n_i]), \
            f"the inta {key_i} pad is not the same program as trigcons's"
    # Pad B2 = trigcons's drain program with only its tail branch retargeted to the companion
    code_d_i = pad_drain_inta(pad_d_i, bcn, pad_m_i)
    assert gi[pad_d_i:pad_d_i + len(code_d_i)] == code_d_i, "the inta Pad B2 is not in the image"
    assert movw(3, 0xcece) in code_d_i and b_w(pad_d_i + len(code_d_i) - 4, pad_m_i) == code_d_i[-4:]
    code_m_i = pad_drain_extra_inta(pad_m_i, b2c_i)
    code_l_i = pad_loop_inta(pad_l_i, lc_i)
    assert gi[pad_m_i:pad_m_i + len(code_m_i)] == code_m_i, "the inta companion pad is not in the image"
    assert gi[pad_l_i:pad_l_i + len(code_l_i)] == code_l_i, "the inta Pad L is not in the image"
    # the sites: 0x86F74 -> Pad B2, 0x86F78 -> Pad L, the old exit 0x86F7E stays STOCK
    assert gi[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] == bl(TRIGCONS_SITE_B, pad_d_i)
    assert gi[INTA_SITE_L:INTA_SITE_L + 4] == bl(INTA_SITE_L, pad_l_i)
    assert gi[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] == data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4], \
        "inta altered the old announce-exit site 0x86F7E"
    assert INTA_SITE_L_BYTES == bytes.fromhex("0a689a42") == data[INTA_SITE_L:INTA_SITE_L + 4]
    assert gim["sites"]["loop_l"]["replaced_bytes"] == "0a689a42"
    assert gim["sites"]["old_drain_b"]["unchanged"] is True
    assert gim["preserved"]["original_gic_write"]["bytes_identical"] is True
    assert gim["preserved"]["itet_block"]["bytes_identical"] is True

    allowed_i = set()
    for site_i in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE, TRIGCONS_SITE_B, INTA_SITE_L):
        allowed_i |= set(range(site_i, site_i + 4))
    for key_i in ("thunk", "bringup", "send_a", "post", "drain_b2", "drain_extra", "loop_l"):
        off_i = int(gim["padding"][key_i]["file_offset"], 16)
        allowed_i |= set(range(off_i, off_i + int(gim["padding"][key_i]["code_length"])))
    changed_i = [i for i in range(len(data)) if gi[i] != data[i]]
    assert changed_i and all(c in allowed_i for c in changed_i), \
        "inta changed bytes outside its regions"
    assert gi[0x8702C:0x87030] == data[0x8702C:0x87030], "inta altered the ISENABLER store"
    assert gi[0x87030:0x87036] == data[0x87030:0x87036], "inta altered the itet block"
    assert gi[TRIGCONS_CONT_B:INTA_SITE_L] == data[TRIGCONS_CONT_B:INTA_SITE_L], \
        "inta altered the byte stream between 0x86F78 and the old exit"
    assert gi[TRIGNAT_SITE_B:0x86F92] == data[TRIGNAT_SITE_B:0x86F92], \
        "inta altered the byte stream after the old drain site"
    assert gim["classification"]["ROW_1_or_2"].startswith("devcpu.md section 5")
    assert gim["gic_map"]["ISACTIVER2"] == hex(GICD_ISACTIVER2) == "0x40161308"
    assert gim["gic_map"]["GICC_CTLR"] == hex(INTA_GICC_CTLR) == "0x40160100"
    assert gim["gic_map"]["GICC_PMR"] == hex(INTA_GICC_PMR) == "0x40160104"
    assert gim["sites"]["loop_l"]["cont"] == hex(INTA_CONT_L) == "0x86f7c"
    assert md5(gi) == INTA_MD5, f"inta output changed: {md5(gi)} != {INTA_MD5}"

    # ---- inta2: the POST-EXIT take sample (take2.md sections 2/3)
    g2, g2m = make_inta2(data, barmap, refs)
    assert len(g2) == len(data), "inta2 changed the size"
    g2b, g2mb = make_inta2(data, barmap, refs)
    assert g2 == g2b, "inta2 patch is not deterministic"
    assert json.dumps(g2m, sort_keys=True) == json.dumps(g2mb, sort_keys=True), \
        "inta2 manifest is not deterministic"
    # every KEPT cell keeps its inta address; the dropped Pad-L cells are gone
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)] + a_names + b_names
               + ["B_D4", "B_D5", "B_D6", "B_D7", "B_P4"]):
        assert g2m["cells"][nm]["addr"] == gim["cells"][nm]["addr"], f"inta2 moved cell {nm}"
    for nm in ("L1_ISP", "L1_ACT", "L_CNT", "L_SNT", "L2_PSR"):
        assert nm not in g2m["cells"], f"inta2 kept the dropped Pad-L cell {nm}"
    pages = _zero_page_spans(barmap)
    p_f2, p_n2 = pages[INTA2_F_PAGE_IDX], pages[INTA2_N_PAGE_IDX]
    assert (p_f2, p_n2) == (0x155000, 0x157000), \
        f"the inta2 pages are not take2's [13]/[14]: {hex(p_f2)}/{hex(p_n2)}"
    fc2 = [int(g2m["cells"][nm]["addr"], 16) for nm in INTA2_F_NAMES]
    assert fc2 == [p_f2 + 8 * i for i in range(INTA2_F_NCELLS)], \
        f"the inta2 F cells are not the page-13 walk: {[hex(c) for c in fc2]}"
    nc2 = [int(g2m["cells"][nm]["addr"], 16) for nm in INTA2_N_NAMES]
    assert nc2 == [p_n2 + 8 * i for i in range(INTA2_N_NCELLS)], \
        f"the inta2 N cells are not the page-14 walk: {[hex(c) for c in nc2]}"
    for nm in INTA2_F_NAMES + INTA2_N_NAMES:
        assert g2m["cells"][nm]["barmap_value"] == "0x0" \
            and g2m["cells"][nm]["barmap_alias_value"] == "0x0", f"inta2 cell {nm} is not zero"
    assert g2m["selection"]["inta2_f_page"] == hex(p_f2) \
        and g2m["selection"]["inta2_n_page"] == hex(p_n2)
    # the pads
    pad_d2 = int(g2m["padding"]["drain_b2"]["file_offset"], 16)
    pad_m2 = int(g2m["padding"]["drain_extra"]["file_offset"], 16)
    pad_f2 = int(g2m["padding"]["fallthrough_f"]["file_offset"], 16)
    pad_s2 = int(g2m["padding"]["send_n"]["file_offset"], 16)
    acn2 = [int(g2m["cells"][nm]["addr"], 16) for nm in a_names] + nc2
    bcn2 = [int(g2m["cells"][nm]["addr"], 16) for nm in b_names]
    code_s2 = pad_send_inta2(pad_s2, acn2)
    code_f2 = pad_fallthrough_inta2(pad_f2, fc2)
    code_d2 = pad_drain_inta(pad_d2, bcn2, pad_m2)
    code_m2 = pad_drain_extra_inta(pad_m2, [int(g2m["cells"][nm]["addr"], 16)
                                            for nm in ("B_D4", "B_D5", "B_D6", "B_D7", "B_P4")])
    assert g2[pad_s2:pad_s2 + len(code_s2)] == code_s2, "the inta2 Pad A(N) is not in the image"
    assert g2[pad_f2:pad_f2 + len(code_f2)] == code_f2, "the inta2 Site F pad is not in the image"
    assert g2[pad_d2:pad_d2 + len(code_d2)] == code_d2, "the inta2 Pad B2 is not in the image"
    assert g2[pad_m2:pad_m2 + len(code_m2)] == code_m2, "the inta2 drain companion is not in the image"
    # Pad B2 + companion are byte-identical to inta's programs (the pre-exit baseline is unchanged)
    assert code_d2 == pad_drain_inta(pad_d2, bcn2, pad_m2)
    assert movw(3, 0xcece) in code_d2 and b_w(pad_d2 + len(code_d2) - 4, pad_m2) == code_d2[-4:]
    assert TRIGNAT_DRAIN_POP in code_f2 and b_w(pad_f2 + len(code_f2) - 4, INTA2_CONT_F) == code_f2[-4:]
    for ca2, c2, nm2 in ((GICD_ISACTIVER2, fc2[0], "F_ACT"), (GICD_ISPENDR2, fc2[1], "F_ISP"),
                         (GICC_HPPIR, fc2[2], "F_HPP"), (TRIGNAT_OUT0_CA, fc2[3], "F_OU0"),
                         (GICD_ISACTIVER2, nc2[0], "N_ACT"), (GICD_ISPENDR2, nc2[1], "N_ISP"),
                         (GICC_HPPIR, nc2[2], "N_HPP"), (TRIGNAT_OUT0_CA, nc2[3], "N_OU0")):
        code = code_f2 if nm2.startswith("F_") else code_s2
        assert gic_read_store_block(ca2, c2) in code, f"inta2 is missing {nm2}: {ca2:#x} -> {c2:#x}"
    assert _store_cpsr_block(fc2[4]) in code_f2 and _store_imm_block(INTA_SENTINEL, fc2[5]) in code_f2
    assert _store_cpsr_block(nc2[4]) in code_s2 and _store_imm_block(INTA_SENTINEL, nc2[5]) in code_s2
    # the sites: 0x86F5A -> Pad A(N), 0x86F74 -> Pad B2, 0x86F7E -> Site F, 0x86F78 STOCK
    assert g2[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] == bl(TRIGNAT_SITE_A, pad_s2)
    assert g2[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] == bl(TRIGCONS_SITE_B, pad_d2)
    assert g2[INTA2_SITE_F:INTA2_SITE_F + 4] == bl(INTA2_SITE_F, pad_f2)
    assert g2[INTA_SITE_L:INTA_SITE_L + 4] == data[INTA_SITE_L:INTA_SITE_L + 4] == INTA_LOOP_PAIR, \
        "inta2 altered the dropped Pad-L site 0x86F78"
    assert g2[0x86F7C:0x86F7E] == data[0x86F7C:0x86F7E], "inta2 altered the loop's `bne 0x86f78`"
    assert data[INTA2_SITE_F:INTA2_SITE_F + 4] == TRIGNAT_DRAIN_POP, \
        "the inta2 Site F original bytes are not the stock pop.w (bde8f843)"
    assert g2m["sites"]["loop_head_stock"]["unchanged"] is True
    assert g2m["sites"]["fallthrough_f"]["replaced_bytes"] == TRIGNAT_DRAIN_POP.hex() == "bde8f843"
    assert g2m["sites"]["send_n"]["replaced_bytes"] == "1a600122"
    assert g2m["preserved"]["announce_loop_head"]["bytes_identical"] is True
    assert g2m["preserved"]["original_gic_write"]["bytes_identical"] is True
    assert g2m["preserved"]["itet_block"]["bytes_identical"] is True
    allowed_2 = set()
    for site_2 in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE, TRIGCONS_SITE_B, INTA2_SITE_F):
        allowed_2 |= set(range(site_2, site_2 + 4))
    for key_2 in ("thunk", "bringup", "send_n", "post", "drain_b2", "drain_extra", "fallthrough_f"):
        off_2 = int(g2m["padding"][key_2]["file_offset"], 16)
        allowed_2 |= set(range(off_2, off_2 + int(g2m["padding"][key_2]["code_length"])))
    changed_2 = [i for i in range(len(data)) if g2[i] != data[i]]
    assert changed_2 and all(c in allowed_2 for c in changed_2), \
        "inta2 changed bytes outside its regions"
    assert g2[0x8702C:0x87030] == data[0x8702C:0x87030], "inta2 altered the ISENABLER store"
    assert g2[0x87030:0x87036] == data[0x87030:0x87036], "inta2 altered the itet block"
    assert g2[0x86F78:0x86F7E] == data[0x86F78:0x86F7E], "inta2 altered the dropped Pad-L region"
    assert g2[INTA2_CONT_F:0x86F92] == data[INTA2_CONT_F:0x86F92], \
        "inta2 altered the Site-F continuation"
    assert g2m["gic_map"]["ISACTIVER2"] == hex(GICD_ISACTIVER2) == "0x40161308"
    assert g2m["gic_map"]["ISPENDR2"] == hex(GICD_ISPENDR2) == "0x40161208"
    assert g2m["gic_map"]["HPPIR"] == hex(GICC_HPPIR) == "0x40160118"
    assert g2m["inta2"]["site_f"] == hex(INTA2_SITE_F) == "0x86f7e"
    assert g2m["inta2"]["cont_f"] == hex(INTA2_CONT_F) == "0x86f82"
    assert g2m["inta2"]["site_l_stock"] == "0a689a42"
    assert g2m["classification"]["ROW_1"].startswith("take2.md section 4")
    assert md5(g2) == INTA2_MD5, f"inta2 output changed: {md5(g2)} != {INTA2_MD5}"

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

    # ---- inta3: the inta2 take with the N cells on the RETENTION-VERIFIED page (witness2.md FLAW 2)
    g3, g3m = make_inta3(data, barmap, refs)
    assert len(g3) == len(data), "inta3 changed the size"
    g3b, g3mb = make_inta3(data, barmap, refs)
    assert g3 == g3b, "inta3 patch is not deterministic"
    assert json.dumps(g3m, sort_keys=True) == json.dumps(g3mb, sort_keys=True), \
        "inta3 manifest is not deterministic"
    # every kept cell keeps its inta2 address
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)] + a_names + b_names
               + ["B_D4", "B_D5", "B_D6", "B_D7", "B_P4"] + list(INTA2_F_NAMES)):
        assert g3m["cells"][nm]["addr"] == g2m["cells"][nm]["addr"], f"inta3 moved cell {nm}"
    # THE FIX: the six N cells are on page 10, the verified-retaining band, at the first free slots
    assert pages[INTA3_N_PAGE_IDX] == pages[TRIGNAT_B_PAGE_IDX] == 0x150000, \
        "inta3's N page is not page 10"
    assert INTA3_N_PAGE_IDX != INTA2_N_PAGE_IDX and pages[INTA2_N_PAGE_IDX] == 0x157000, \
        "inta2's non-retaining page 14 is not 0x157000"
    nc3 = [int(g3m["cells"][nm]["addr"], 16) for nm in INTA2_N_NAMES]
    assert nc3 == [INTA3_N_FIRST + 8 * i for i in range(INTA3_N_NCELLS)], \
        f"the inta3 N cells are not the page-10 walk: {[hex(c) for c in nc3]}"
    assert all((c & ~0xFFF) == pages[TRIGNAT_B_PAGE_IDX] for c in nc3), \
        "an inta3 N cell left page 10"
    assert all(nc3[i + 1] - nc3[i] >= 8 for i in range(len(nc3) - 1)), \
        "the inta3 N cells are not >= 8 bytes apart"
    assert all(g3m["cells"][nm]["barmap_value"] == "0x0"
               and g3m["cells"][nm]["barmap_alias_value"] == "0x0" for nm in INTA2_N_NAMES), \
        "an inta3 N cell is not zero in barmap at both views"
    assert g3m["selection"]["inta3_n_page"] == "0x150000" \
        and g3m["selection"]["inta3_n_page_idx"] == INTA3_N_PAGE_IDX \
        and g3m["selection"]["inta3_n_cells"] == [hex(c) for c in nc3], \
        "the inta3 selection does not name the page-10 N cells"
    assert g3m["selection"]["inta3_f_page"] == hex(pages[INTA2_F_PAGE_IDX]) == "0x155000", \
        "inta3 did not keep Site F on page 13"
    # the pads have inta2's shapes; the ONLY byte changes vs inta2 are the six N-cell movw immediates
    ac3 = [int(g3m["cells"][nm]["addr"], 16) for nm in a_names] + nc3
    assert len(ac3) == INTA2_A_NCELLS, "the inta3 Pad A cell count changed"
    pad_s3 = int(g3m["padding"]["send_n"]["file_offset"], 16)
    pad_f3 = int(g3m["padding"]["fallthrough_f"]["file_offset"], 16)
    fc3 = [int(g3m["cells"][nm]["addr"], 16) for nm in INTA2_F_NAMES]
    code_s3 = pad_send_inta2(pad_s3, ac3)
    code_f3 = pad_fallthrough_inta2(pad_f3, fc3)
    assert g3[pad_s3:pad_s3 + len(code_s3)] == code_s3, "the inta3 Pad A(N) is not in the image"
    assert g3[pad_f3:pad_f3 + len(code_f3)] == code_f3, "the inta3 Site F pad is not in the image"
    assert g3[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] == bl(TRIGNAT_SITE_A, pad_s3), \
        "the inta3 Pad A site is not the intended bl"
    assert g3[INTA2_SITE_F:INTA2_SITE_F + 4] == bl(INTA2_SITE_F, pad_f3), \
        "the inta3 Site F site is not the intended bl"
    assert g3[INTA_SITE_L:INTA_SITE_L + 4] == data[INTA_SITE_L:INTA_SITE_L + 4], \
        "inta3 altered the dropped Pad-L site 0x86F78"
    pad_d3 = int(g3m["padding"]["drain_b2"]["file_offset"], 16)
    pad_m3 = int(g3m["padding"]["drain_extra"]["file_offset"], 16)
    code_d3 = pad_drain_inta(pad_d3, [int(g3m["cells"][nm]["addr"], 16) for nm in b_names], pad_m3)
    code_m3 = pad_drain_extra_inta(pad_m3, [int(g3m["cells"][nm]["addr"], 16)
                                            for nm in ("B_D4", "B_D5", "B_D6", "B_D7", "B_P4")])
    assert g3[pad_d3:pad_d3 + len(code_d3)] == code_d3, "the inta3 Pad B2 is not in the image"
    assert g3[pad_m3:pad_m3 + len(code_m3)] == code_m3, "the inta3 drain companion is not in the image"
    assert g3[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] == bl(TRIGCONS_SITE_B, pad_d3), \
        "the inta3 Pad B2 site is not the intended bl"
    assert g3[TRIGCONS_CONT_B:TRIGCONS_CONT_B + 4] == data[TRIGCONS_CONT_B:TRIGCONS_CONT_B + 4], \
        "inta3 altered the stock loop head 0x86F78"
    allowed_3 = set()
    for site_3 in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE, TRIGCONS_SITE_B, INTA2_SITE_F):
        allowed_3 |= set(range(site_3, site_3 + 4))
    for key_3 in ("thunk", "bringup", "send_n", "post", "drain_b2", "drain_extra",
                  "fallthrough_f"):
        off_3 = int(g3m["padding"][key_3]["file_offset"], 16)
        allowed_3 |= set(range(off_3, off_3 + int(g3m["padding"][key_3]["code_length"])))
    changed_3 = [i for i in range(len(data)) if g3[i] != data[i]]
    assert changed_3 and all(c in allowed_3 for c in changed_3), \
        "inta3 changed bytes outside its regions"
    diff_23 = [i for i in range(len(data)) if g2[i] != g3[i]]
    assert diff_23, "inta3 is byte-identical to inta2 - the N cells did not move"
    assert all(pad_s3 <= i < pad_s3 + len(code_s3) for i in diff_23), \
        f"inta3 differs from inta2 outside the Pad A(N) program: {[hex(i) for i in diff_23[:8]]}"
    for name_3, code_3 in (("send_n", code_s3), ("fallthrough_f", code_f3)):
        for bad_3 in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                      write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            assert bad_3 not in code_3, f"the inta3 {name_3} pad addresses a forbidden CA"
    assert g3[0x8702C:0x87030] == data[0x8702C:0x87030], \
        "inta3 altered the original ISENABLER store"
    assert md5(g3) == INTA3_MD5, f"inta3 output changed: {md5(g3)} != {INTA3_MD5}"

    # ---- take1: the IRQ-vector canary + the two CPSR milestones + the giccpu cells
    # (fwprobe.md sections 2-5 + giccpu.md sections 4/5)
    g4, g4m = make_take1(data, barmap, refs)
    assert len(g4) == len(data), "take1 changed the size"
    g4b, g4mb = make_take1(data, barmap, refs)
    assert g4 == g4b, "take1 patch is not deterministic"
    assert json.dumps(g4m, sort_keys=True) == json.dumps(g4mb, sort_keys=True), \
        "take1 manifest is not deterministic"
    # every inherited cell keeps its inta3 address
    for nm in (["S1", "S2"] + [f"C{i}" for i in range(GICV_NCELLS)]
               + [f"E{i}" for i in range(GICP_NCELLS)] + a_names + b_names
               + ["B_D4", "B_D5", "B_D6", "B_D7", "B_P4"] + list(INTA2_F_NAMES)
               + list(INTA2_N_NAMES)):
        assert g4m["cells"][nm]["addr"] == g3m["cells"][nm]["addr"], f"take1 moved cell {nm}"
    # the ten NEW cells: page 10, fwprobe's V/M addresses, the contiguous giccpu words, all zero
    v4 = [int(g4m["cells"][nm]["addr"], 16) for nm in TAKE1_V_NAMES]
    c4 = [int(g4m["cells"][nm]["addr"], 16) for nm in TAKE1_CP_NAMES]
    assert v4 == [0x1500A4, 0x1500A8, 0x1500AC, 0x1500B0, 0x1500B4], \
        f"the take1 V/M cells are not fwprobe's addresses: {[hex(c) for c in v4]}"
    assert c4 == [0x1500B8, 0x1500BC, 0x1500C0, 0x1500C4, 0x1500C8], \
        f"the take1 giccpu cells are not the contiguous free words: {[hex(c) for c in c4]}"
    assert all((c & ~0xFFF) == 0x150000 for c in v4 + c4), "a take1 new cell left page 10"
    assert all(g4m["cells"][nm]["barmap_value"] == "0x0"
               and g4m["cells"][nm]["barmap_alias_value"] == "0x0"
               for nm in TAKE1_V_NAMES + TAKE1_CP_NAMES), \
        "a take1 new cell is not zero in barmap at both views"
    inherited4 = set(int(g4m["cells"][nm]["addr"], 16) for nm in g4m["cells"]
                     if nm not in TAKE1_V_NAMES + TAKE1_CP_NAMES)
    assert not (set(v4 + c4) & inherited4), "a take1 new cell collides with an inherited cell"
    assert g4m["aliases"] == {"C_PSR": "B_D5", "F_CTLR": "B_D6", "F_PMR": "B_D7"}, \
        "the take1 alias map changed"
    assert g4m["take1"]["gicc_reads"] == [hex(TAKE1_GICC_RPR), hex(GICC_HPPIR),
                                            hex(TAKE1_GICC_ABPR), hex(TAKE1_GICC_BPR)]
    assert "0x40160120" in g4m["gic_map"]["never_read"], "the AIAR exclusion is not recorded"
    # the three new pads are fwprobe.md section 4's bytes (m2 only in the tail displacement)
    assert g4m["padding"]["vec"]["code_hex"] == \
        "2de9f34d4af2a440caf2a44040f2a401c0f215010860eff30080486040f2ac02c0f2150213685b1c1360baf77ebd", \
        "the take1 vec pad is not fwprobe's bytes"
    assert g4m["padding"]["m1"]["code_hex"] == \
        "0fb4eff3008040f2b001c0f2150108600fbca84772b6baf72bbd", \
        "the take1 m1 pad is not fwprobe's bytes"
    assert g4m["padding"]["m2"]["code_hex"][:-4] == \
        "03b4eff3008040f2b401c0f21501086003bceff30082baf7", \
        "the take1 m2 pad is not fwprobe's program (only the tail displacement may differ)"
    assert g4m["sites"]["vec"]["after"] == "45f06bba" \
        and g4m["sites"]["m1"]["after"] == "45f0c8fa", \
        "the take1 vec/m1 site branches are not fwprobe's (45f06bba / 45f0c8fa)"
    assert g4m["sites"]["vec"]["replaced_bytes"] == "2de9f34d"
    assert g4m["sites"]["m1"]["replaced_bytes"] == "a84772b6"
    assert g4m["sites"]["m2"]["replaced_bytes"] == "eff30082"
    v_site = int(g4m["sites"]["vec"]["file_offset"], 16)
    m1_site = int(g4m["sites"]["m1"]["file_offset"], 16)
    m2_site = int(g4m["sites"]["m2"]["file_offset"], 16)
    pad_v4 = int(g4m["padding"]["vec"]["file_offset"], 16)
    pad_14 = int(g4m["padding"]["m1"]["file_offset"], 16)
    pad_24 = int(g4m["padding"]["m2"]["file_offset"], 16)
    pad_g4 = int(g4m["padding"]["giccpu"]["file_offset"], 16)
    assert g4[v_site:v_site + 4] == b_w(v_site, pad_v4), "the take1 V_SITE is not the b.w"
    assert g4[m1_site:m1_site + 4] == bl(m1_site, pad_14), "the take1 M1_SITE is not the bl"
    assert g4[m2_site:m2_site + 4] == bl(m2_site, pad_24), "the take1 M2_SITE is not the bl"
    # the giccpu chain: drain companion -> giccpu pad -> loop head
    code_g4 = pad_giccpu_take1(pad_g4, c4, TRIGCONS_CONT_B)
    code_14 = pad_m1_take1(pad_14, v4[3], TAKE1_M1_CONT)
    code_24 = pad_m2_take1(pad_24, v4[4], TAKE1_M2_CONT)
    code_v4 = pad_vec_take1(pad_v4, v4, TAKE1_V_CONT)
    code_m4 = pad_drain_extra_inta(int(g4m["padding"]["drain_extra"]["file_offset"], 16),
                                   [int(g4m["cells"][nm]["addr"], 16)
                                    for nm in ("B_D4", "B_D5", "B_D6", "B_D7", "B_P4")],
                                   next_pad=pad_g4)
    assert g4[pad_g4:pad_g4 + len(code_g4)] == code_g4, "the take1 giccpu pad is not in the image"
    assert g4[pad_v4:pad_v4 + len(code_v4)] == code_v4, "the take1 vec pad is not in the image"
    assert g4[pad_14:pad_14 + len(code_14)] == code_14, "the take1 m1 pad is not in the image"
    assert g4[pad_24:pad_24 + len(code_24)] == code_24, "the take1 m2 pad is not in the image"
    assert b_w(pad_g4 + len(code_g4) - 4, TRIGCONS_CONT_B) == code_g4[-4:], \
        "the take1 giccpu pad does not return to the loop head"
    assert code_m4[-4:] == b_w(int(g4m["padding"]["drain_extra"]["file_offset"], 16)
                               + len(code_m4) - 4, pad_g4), \
        "the take1 drain companion does not branch to the giccpu pad"
    for ca4, cell4, nm4 in ((TAKE1_GICC_RPR, c4[0], "C_GRP0"), (GICC_HPPIR, c4[1], "C_GRP1"),
                            (TAKE1_GICC_ABPR, c4[2], "C_GRP2"), (TAKE1_GICC_BPR, c4[3], "F_BPR")):
        assert gic_read_store_block(ca4, cell4) in code_g4, f"take1 is missing {nm4}"
    assert _store_imm_block(INTA_SENTINEL, c4[4]) in code_g4, "take1 is missing the C_SNT sentinel"
    # the untouched bodies and the allowed-change set
    assert g4[TAKE1_V_CONT:TAKE1_M1_SITE] == data[TAKE1_V_CONT:TAKE1_M1_SITE], \
        "take1 altered the ISR body before M1_SITE"
    assert g4[TAKE1_M1_CONT:0x82F78] == data[TAKE1_M1_CONT:0x82F78], \
        "take1 altered the ISR body after M1_SITE"
    assert g4[0x826E0:TAKE1_M2_SITE] == data[0x826E0:TAKE1_M2_SITE], \
        "take1 altered the release body before the guard"
    assert g4[TAKE1_M2_CONT:0x82730] == data[TAKE1_M2_CONT:0x82730], \
        "take1 altered the release spin after the guard"
    assert g4[INTA_SITE_L:INTA_SITE_L + 4] == data[INTA_SITE_L:INTA_SITE_L + 4], \
        "take1 altered the dropped Pad-L site 0x86F78"
    allowed_4 = set()
    for site_4 in (SITE_THUNK, BRINGUP_SITE, SEND_SITE, POST_SITE, TRIGCONS_SITE_B, INTA2_SITE_F,
                   TAKE1_V_SITE, TAKE1_M1_SITE, TAKE1_M2_SITE):
        allowed_4 |= set(range(site_4, site_4 + 4))
    for key_4 in ("thunk", "bringup", "send_n", "post", "drain_b2", "drain_extra", "giccpu",
                  "fallthrough_f", "vec", "m1", "m2"):
        off_4 = int(g4m["padding"][key_4]["file_offset"], 16)
        allowed_4 |= set(range(off_4, off_4 + int(g4m["padding"][key_4]["code_length"])))
    changed_4 = [i for i in range(len(data)) if g4[i] != data[i]]
    assert changed_4 and all(c in allowed_4 for c in changed_4), \
        "take1 changed bytes outside its regions"
    for name_4, code_4 in (("vec", code_v4), ("m1", code_14), ("m2", code_24), ("giccpu", code_g4)):
        for bad_4 in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                      write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0),
                      gic_read_store_block(0x40160120, 0)):
            assert bad_4 not in code_4, f"the take1 {name_4} pad addresses a forbidden CA"
    assert g4[0x8702C:0x87030] == data[0x8702C:0x87030], "take1 altered the ISENABLER store"
    assert g4[0x87030:0x87036] == data[0x87030:0x87036], "take1 altered the itet block"
    assert g4m["classification"]["ROW_1"].startswith("fwprobe.md section 6.1")
    assert g4m["preserved"]["isr_body_around_m1"]["bytes_identical"] is True
    assert g4m["preserved"]["release_body_around_m2"]["bytes_identical"] is True
    assert md5(g4) == TAKE1_MD5, f"take1 output changed: {md5(g4)} != {TAKE1_MD5}"

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
    print(f"  gicmask cells     : " + " ".join(f"F{i}={gkm['cells'][f'F{i}']['addr']}"
                                                for i in range(GICM_NCELLS))
          + f" (send pad @ file {gkm['padding']['send']['file_offset']}, site {hex(SEND_SITE)})")
    print(f"  gicmask reads     : " + ", ".join(f"F{i}={GICM_READS[i][0]:#x}" for i in range(GICM_NSAMPLES))
          + f" F8/F9=sentinel 0x{GICM_SENTINEL:08x} (F9 also the handshake request)")
    print(f"  gicmask md5       : {md5(gmk)}")
    print(f"  gicking cells     : " + " ".join(f"G{i}={gkn['cells'][f'G{i}']['addr']}"
                                               for i in range(GICK_NCELLS))
          + f" (send pad @ file {gkn['padding']['send']['file_offset']}, site {hex(SEND_SITE)})")
    print(f"  gicking ring      : CA {gkn['gic_map']['ring']['ca']} <= {gkn['gic_map']['ring']['value']} "
          f"+ mask {gkn['gic_map']['glue']['mask_masked']} -> {gkn['gic_map']['glue']['mask_open']} "
          f"+ IGROUPR {gkn['gic_map']['GICD_IGROUPR2']} -> F5/F6/F7={gkn['cells']['F5']['addr']}/"
          f"{gkn['cells']['F6']['addr']}/{gkn['cells']['F7']['addr']} G0/G1/G2="
          + "/".join(gkn['cells'][f'G{i}']['addr'] for i in range(3)))
    print(f"  gicking md5       : {md5(gkb)}")
    print(f"  gicunmask cells   : " + " ".join(f"H{i}={gum['cells'][f'H{i}']['addr']}"
                                                for i in range(GICU_NCELLS))
          + f" (send pad @ file {gum['padding']['send']['file_offset']}, site {hex(SEND_SITE)})")
    print(f"  gicunmask reads   : H0..H4={[hex(x) for x in GICU_READS]} H5={hex(GICU_H5_CA)}"
          f" mask-open={hex(GICU_MASK_OPEN)} ring={hex(GICU_RING_VAL)}@{hex(GICU_RING_CA)}")
    print(f"  gicunmask md5     : {md5(gub)}")
    print(f"  trigring cells    : " + " ".join(f"T{i}={gtm['cells'][f'T{i}']['addr']}"
                                                for i in range(TRIG_NCELLS))
          + f" (send pad @ file {gtm['padding']['send']['file_offset']}, site {hex(SEND_SITE)})")
    print(f"  trigring reads    : PRE T0..T3 / POST T4..T7 both {[hex(x) for x in TRIG_READS]}"
          f" mask-open={hex(TRIG_MASK_OPEN)} ring={hex(TRIG_RING_VAL)}@{hex(TRIG_RING_CA)}"
          f" (= out[1] 0x40039014 + {hex(TRIG_RING_OFF)})")
    print(f"  trigring md5      : {md5(gtr)}")
    print(f"  trignat cells     : " + " ".join(f"{n}={gtnm['cells'][n]['addr']}"
                                               for n in (["A_S0", "A_S1", "A_S2", "A_S3", "A_P1",
                                                          "A_E0", "A_E1", "A_S4", "A_S5", "A_S6", "A_S7",
                                                          "A_S8", "A_P2"]
                                                         + ["B_D0", "B_D1", "B_D2", "B_D3", "B_P3"]))
          + f" (Pad A @ file {gtnm['padding']['send_a']['file_offset']}, site {hex(TRIGNAT_SITE_A)}; "
            f"Pad B @ file {gtnm['padding']['drain_b']['file_offset']}, site {hex(TRIGNAT_SITE_B)})")
    print(f"  trignat ring      : mask-open={hex(TRIGNAT_MASK_OPEN)} submit({hex(TRIGNAT_OUT0_CA)})<="
          f"{hex(TRIGNAT_SUBMIT_VAL)} ring={hex(TRIGNAT_RING_VAL)}@{hex(TRIGNAT_RING_CA)}"
          f" PRE A_S0..A_S2={[hex(x) for x in TRIGNAT_PRE_READS]}"
          f" POST A_S3..A_S8={[hex(x) for x in TRIGNAT_POST_READS]}"
          f" B={[hex(x) for x in TRIGNAT_B_READS]}")
    print(f"  trignat md5       : {md5(gtn)}")
    print(f"  trigcons cells    : " + " ".join(f"{n}={gcnm['cells'][n]['addr']}"
                                               for n in (["A_S0", "A_S1", "A_S2", "A_S3", "A_P1",
                                                          "A_E0", "A_E1", "A_S4", "A_S5", "A_S6", "A_S7",
                                                          "A_S8", "A_P2"]
                                                         + ["B_D0", "B_D1", "B_D2", "B_D3", "B_P3"]))
          + f" (Pad A @ file {gcnm['padding']['send_a']['file_offset']}, site {hex(TRIGNAT_SITE_A)}; "
            f"Pad B MOVED @ file {gcnm['padding']['drain_b']['file_offset']}, site {hex(TRIGCONS_SITE_B)} "
            f"cont {hex(TRIGCONS_CONT_B)}; old site {hex(TRIGNAT_SITE_B)} STOCK)")
    print(f"  trigcons gate     : CA {gcnm['gic_map']['gate']['ca']} == {gcnm['gic_map']['gate']['wait_value']}; "
          f"Pad B re-emits movw r3,#0xcece ({TRIGCONS_SITE_B_BYTES.hex()}) and b.w {hex(TRIGCONS_CONT_B)}"
          f" (expect RING-PENDING-NOT-TAKEN)")
    print(f"  trigcons md5      : {md5(gcn)}")
    print(f"  inta cells        : B_D4={gim['cells']['B_D4']['addr']} B_D5={gim['cells']['B_D5']['addr']} "
          f"B_D6={gim['cells']['B_D6']['addr']} B_D7={gim['cells']['B_D7']['addr']} "
          f"B_P4={gim['cells']['B_P4']['addr']} L1_ISP={gim['cells']['L1_ISP']['addr']} "
          f"L2_ISP={gim['cells']['L2_ISP']['addr']} L_CNT={gim['cells']['L_CNT']['addr']} "
          f"L_SNT={gim['cells']['L_SNT']['addr']}")
    print(f"  inta pads         : Pad B2 @ file {gim['padding']['drain_b2']['file_offset']}, "
          f"companion @ {gim['padding']['drain_extra']['file_offset']} "
          f"(B_D4 ISACTIVER2 0x40161308 / B_D5 CPSR / B_D6 0x40160100 / B_D7 0x40160104 + B_P4); "
          f"Pad L @ file {gim['padding']['loop_l']['file_offset']}, site 0x86f78 cont 0x86f7c")
    print(f"  inta md5          : {md5(gi)}")
    print(f"  inta2 cells       : F_ACT={g2m['cells']['F_ACT']['addr']} F_ISP={g2m['cells']['F_ISP']['addr']} "
          f"F_HPP={g2m['cells']['F_HPP']['addr']} F_OU0={g2m['cells']['F_OU0']['addr']} "
          f"F_PSR={g2m['cells']['F_PSR']['addr']} F_SNT={g2m['cells']['F_SNT']['addr']} "
          f"N_ACT={g2m['cells']['N_ACT']['addr']} N_SNT={g2m['cells']['N_SNT']['addr']}")
    print(f"  inta2 pads        : Pad A(N) @ file {g2m['padding']['send_n']['file_offset']}, "
          f"site {hex(TRIGNAT_SITE_A)}; Pad B2 @ {g2m['padding']['drain_b2']['file_offset']} + "
          f"companion {g2m['padding']['drain_extra']['file_offset']}; Site F @ "
          f"{g2m['padding']['fallthrough_f']['file_offset']}, site {hex(INTA2_SITE_F)} "
          f"cont {hex(INTA2_CONT_F)}; 0x86f78 STOCK (Pad L dropped)")
    print(f"  inta2 md5         : {md5(g2)}")
    print(f"  inta3 cells       : " + " ".join(f"{n}={g3m['cells'][n]['addr']}" for n in INTA2_N_NAMES)
          + f" (page 10 = {g3m['selection']['inta3_n_page']} - the retention-VERIFIED band; "
            f"inta2's page 14 = {hex(pages[INTA2_N_PAGE_IDX])} did not retain)")
    print(f"  inta3 pads        : Pad A(N) @ file {g3m['padding']['send_n']['file_offset']}, site "
          f"{hex(TRIGNAT_SITE_A)}; Site F @ {g3m['padding']['fallthrough_f']['file_offset']}, site "
          f"{hex(INTA2_SITE_F)} cont {hex(INTA2_CONT_F)}; only {len(diff_23)} bytes differ from "
          f"inta2 (the six N-cell movw immediates)")
    print(f"  inta3 md5         : {md5(g3)}")
    print(f"  take1 cells       : " + " ".join(f"{n}={g4m['cells'][n]['addr']}"
                                                for n in TAKE1_V_NAMES + TAKE1_CP_NAMES)
          + " (aliases C_PSR=B_D5 F_CTLR=B_D6 F_PMR=B_D7)")
    print(f"  take1 sites       : V 0x82efc (2de9f34d) -> vec pad "
          f"{g4m['padding']['vec']['file_offset']}; M1 0x82f4a (a84772b6) -> "
          f"{g4m['padding']['m1']['file_offset']}; M2 0x8270a (eff30082) -> "
          f"{g4m['padding']['m2']['file_offset']}; giccpu pad "
          f"{g4m['padding']['giccpu']['file_offset']} chained after the drain companion")
    print(f"  take1 md5         : {md5(g4)}")
    return 0


# ---------------------------------------------------------------- main

def _take_cells(page: int, n: int, ok, prev: list[int]) -> list[int]:
    """The selection walk's page rule: from the page base upward, take `n` 4-byte-aligned cells
    that are ok() and >= 8 bytes from the previous accepted cell."""
    out: list[int] = []
    a = page
    while a + 8 <= page + 0x1000 and len(out) < n:
        last = out[-1] if out else prev[-1]
        if ok(a) and a - last >= 8:
            out.append(a)
        a += 4
    return out


# ---- inta: the DEVCPU drain + delayed cells (devcpu.md sections 4.1/4.2, variant "inta")
# devcpu.md names the variant "devcpu"; the task's chosen name here is "inta".  It is trigcons
# (Pad A = the firmware's own natural post at 0x86F5A; Pad B at 0x86F74 = the announce wait's own
# `movw r3,#0xcece`) PLUS:
#   * Pad B2 = trigcons's Pad B EXTENDED with the drain cells B_D4 (ISACTIVER2 word 2),
#     B_D5 (the full CPSR), B_D6 (GICC_CTLR) and B_D7 (GICC_PMR), plus the page-11 sentinel B_P4;
#   * Pad L = a NEW pad at file 0x86F78, the announce wait's own spin head (`ldr r2,[r1]` +
#     `cmp r2,r3`, stock 0a689a42) - the ONLY site re-visited while the CPU is parked: it counts its
#     iterations in L_CNT, samples the GIC/CPSR set L1_* once (iteration 1) and once per 2^24
#     iterations (L2_*), then re-emits the replaced pair and branches to 0x86F7C.
# The B2 cells keep trigcons's B_D0..B_D3 + B_P3 addresses; B_D4..B_P4 sit on all_zero_pages[11] =
# 0x153000 and Pad L's cells on all_zero_pages[12] = 0x154000.  NEVER writes 0x400392f0 or the
# masked word 0x21; NEVER reads the IAR 0x4016010c or 0x10161000 (the gate register 0x4000010c is a
# DIFFERENT address); every added GIC read (ISPENDR2/ISACTIVER2/HPPIR) is non-acknowledging.
INTA_B2_PAGE_IDX = TRIGNAT_B_PAGE_IDX + 1     # all_zero_pages[11] = 0x153000 (B_D4..B_D7, B_P4)
INTA_L_PAGE_IDX = TRIGNAT_B_PAGE_IDX + 2      # all_zero_pages[12] = 0x154000 (Pad L cells)
INTA_GICC_CTLR = 0x40160100                   # GICC_CTLR (firmware literal file 0x8309c)
INTA_GICC_PMR = 0x40160104                    # GICC_PMR (firmware literal file 0x83098)
INTA_B2_NSAMPLES = 4                          # B_D4 (ISACTIVER2), B_D5 (CPSR), B_D6 (CTLR), B_D7 (PMR)
INTA_B2_NCELLS = 5                            # + the B_P4 sentinel
INTA_L_NSAMPLES = 10                          # L1_ISP..L1_PSR, L2_ISP..L2_PSR
INTA_L_NCELLS = 12                            # + L_CNT + L_SNT
INTA_L_READS = (GICD_ISPENDR2, GICD_ISACTIVER2, GICC_HPPIR, TRIGNAT_OUT0_CA)  # 4 reads + the CPSR
INTA_SITE_L = 0x86F78                         # Pad L's site: the 0xcece spin head
INTA_CONT_L = 0x86F7C                         # continuation: the loop's own `bne 0x86F78`
INTA_LOOP_PAIR = ldr_imm(2, 1, 0) + cmp_reg_t2(2, 3)   # the replaced `ldr r2,[r1]` + `cmp r2,r3`
INTA_SITE_L_BYTES = INTA_LOOP_PAIR                     # == the stock bytes 0a689a42
INTA_SENTINEL = MARKER                        # 0x50aa7e49 - the page-12 presence proof
COND_EQ = 0

NOTE_INTA_B2 = (
    "Pad B2 (devcpu.md section 4.1) is trigcons's Pad B at file 0x86F74 - the announce wait's own "
    "`movw r3,#0xcece`, guaranteed to run before the never-exiting 0xcece loop - EXTENDED with the "
    "drain cells: B_D4 (CA 0x40161308 ISACTIVER2 word 2; bit 12 SET = the CPU read the IAR, i.e. "
    "the id-0x4c interrupt is ACTIVE), B_D5 (the full CPSR via `mrs r0,<PSR>` = F3EF 8000, the form "
    "the firmware's own I-bit test at 0x8706a proves reads the whole CPSR - bit 7 = I), B_D6 (CA "
    "0x40160100 GICC_CTLR, expect bit 0 = 1) and B_D7 (CA 0x40160104 GICC_PMR, expect >= 0x50), "
    "plus the page-11 sentinel B_P4.  It keeps the B_D0..B_D3 + B_P3 cells on page 10 at trigcons's "
    "exact addresses and then re-emits `movw r3,#0xcece` and branches to 0x86F78 (the loop head, "
    "now Pad L's site).  r0-r5 are saved/restored; only r3 is re-set, AFTER the pop."
)
NOTE_INTA_L = (
    "Pad L (devcpu.md section 4.2) is the DELAYED sample: the 0xcece spin head at file 0x86F78 "
    "(`ldr r2,[r1]` + `cmp r2,r3`, stock 0a689a42) is replaced with a `bl` to the pad, so the pad "
    "runs on the FIRST revisit (immediately after Pad B2) and on EVERY loop iteration thereafter.  "
    "It increments a persistent counter (L_CNT) and gates its samples with `cmp r3,#1` (iteration "
    "1, the L1 block, which also arms the page-12 sentinel L_SNT) and `lsls r2,r3,#8 ; cmp r2,#0"
    " ; bne tail` (a nonzero multiple of 2^24 iterations, the L2 block).  Both blocks read "
    "ISPENDR2 (CA 0x40161208; bit 12 = pending), ISACTIVER2 (CA 0x40161308; bit 12 = active), "
    "HPPIR (CA 0x40160118) and out[0] (CA 0x40039010) and store the CPSR.  The tail restores "
    "r0-r5, re-emits the replaced `ldr r2,[r1]` and `cmp r2,r3` and branches to 0x86F7C (`bne "
    "0x86F78`); r3 is restored by the pop, so it still holds 0xcece for the re-emitted `cmp`.  No "
    "pad ever returns through lr (they all end in `b.w`), so the `bl`'s lr clobber is inert.  Cost "
    "is bounded: the sampling blocks run once and once per 2^24 iterations; per-iteration overhead "
    "is the counter update, one shift and one compare."
)
NOTE_INTA_CELLS = (
    "trignat/trigcons cells (IDENTICAL addresses: S1/S2, C0..C5, E0..E3, A_S0..A_S8/A_P1/A_E0/"
    "A_E1/A_P2, B_D0..B_D3/B_P3) plus the two fresh all-zero 4 KB pages after them: "
    "all_zero_pages[11] = 0x153000 carries B_D4..B_D7 + B_P4 (5); all_zero_pages[12] = 0x154000 "
    "carries L1_ISP/L1_ACT/L1_HPP/L1_OU0/L1_PSR, L2_ISP/L2_ACT/L2_HPP/L2_OU0/L2_PSR, L_CNT and "
    "L_SNT (12).  Every cell is 0x00000000 at BOTH the BAR0 and the ACP-alias offsets in "
    "barmap_ep0_bar0.bin, 4-byte aligned, >= 8 bytes apart, outside the four excluded tables and "
    "distinct from every earlier cell."
)


def adds_imm(rd: int, rn: int, imm3: int) -> bytes:
    """ADDS (immediate) T1: `adds Rd, Rn, #imm3`, low registers, imm3 in 0..7."""
    if not 0 <= imm3 <= 7:
        raise PatchError(f"adds immediate out of range: {imm3}")
    return struct.pack("<H", 0x1C00 | (imm3 << 6) | ((rn & 7) << 3) | (rd & 7))


def cmp_imm(rn: int, imm8: int) -> bytes:
    """CMP (immediate) T1: `cmp Rn, #imm8`, low register, imm8 in 0..255."""
    if not 0 <= imm8 <= 255:
        raise PatchError(f"cmp immediate out of range: {imm8}")
    return struct.pack("<H", 0x2800 | ((rn & 7) << 8) | imm8)


def lsls_imm(rd: int, rm: int, imm5: int) -> bytes:
    """LSLS (immediate) T1: `lsls Rd, Rm, #imm5`, imm5 in 0..31."""
    if not 0 <= imm5 <= 31:
        raise PatchError(f"lsls immediate out of range: {imm5}")
    return struct.pack("<H", (imm5 << 6) | ((rm & 7) << 3) | (rd & 7))


def _store_cpsr_block(cell: int) -> bytes:
    """`mrs r0,<PSR>` then movw/movt the cell into r1 and `str r0,[r1]`.  The F3EF 8rd0 form is
    the FULL-CPSR read (not a flags-only APSR read): the firmware's own I-bit test at file 0x8706a
    (`mrs r3,<PSR> ; lsls r3,r3,#0x18 ; bpl`) depends on bit 7 moving to N, which no flags-only
    read would supply.  Reading the CPSR does not change the mask; r0/r1 are saved by push/pop."""
    return b"".join([
        mrs_apsr(0),
        movw(1, cell & 0xFFFF),
        movt(1, cell >> 16),
        str_imm(0, 1, 0),
    ])


def select_cells_inta(barmap: bytes):
    """trignat's cells (IDENTICAL addresses) plus all_zero_pages[11] (B_D4..B_D7 + B_P4) and
    all_zero_pages[12] (L1_*/L2_*/L_CNT/L_SNT), by the same rule."""
    cells, sel = select_cells_trignat(barmap)
    ok = _cell_ok(barmap)
    pages = _zero_page_spans(barmap)
    if len(pages) < INTA_L_PAGE_IDX + 1:
        raise PatchError(f"inta selection failed: fewer than {INTA_L_PAGE_IDX + 1} all-zero 4 KB "
                         "pages in the band")
    p_b2, p_l = pages[INTA_B2_PAGE_IDX], pages[INTA_L_PAGE_IDX]
    b2 = _take_cells(p_b2, INTA_B2_NCELLS, ok, cells)
    if len(b2) < INTA_B2_NCELLS:
        raise PatchError(f"inta selection failed: page {p_b2:#x} has fewer than {INTA_B2_NCELLS} "
                         "usable cells")
    lc = _take_cells(p_l, INTA_L_NCELLS, ok, b2)
    if len(lc) < INTA_L_NCELLS:
        raise PatchError(f"inta selection failed: page {p_l:#x} has fewer than {INTA_L_NCELLS} "
                         "usable cells")
    sel = dict(sel)
    sel.update({
        "inta_rule": "trignat's cells (identical addresses) plus all_zero_pages[11] (B_D4..B_D7 + "
                     "B_P4) and all_zero_pages[12] (L1_*/L2_*/L_CNT/L_SNT), by the same rule",
        "inta_b2_page": hex(p_b2), "inta_l_page": hex(p_l),
        "inta_b2_page_idx": INTA_B2_PAGE_IDX, "inta_l_page_idx": INTA_L_PAGE_IDX,
        "inta_b2_cells": [hex(a) for a in b2], "inta_l_cells": [hex(a) for a in lc],
        "inta_note": NOTE_INTA_CELLS,
    })
    return cells + b2 + lc, sel


def pad_drain_inta(pad: int, b_cells: list[int], next_pad: int) -> bytes:
    """The inta Pad B2 (devcpu.md section 4.1): EXACTLY trigcons's Pad B (site 0x86F74, the
    announce wait's own `movw r3,#0xcece`) - B_D0..B_D3 + the B_P3 sentinel, pop, re-emit
    `movw r3,#0xcece`, restore flags - except that its tail branches to the companion pad `next_pad`
    (which carries the added cells) instead of straight to the loop head.  Splitting the extended
    drum into two pads is a build-node necessity: the loaded image holds only one 0x00 run >= 157
    bytes, so a single 210-byte pad cannot be placed; the program (and the sampled instant) is
    identical."""
    b_d, b_p = b_cells[0:4], b_cells[4]
    head = b"".join([
        mrs_apsr(12),                                            # +0  save the condition flags
        push(PAD_SAVE),                                          # +4  24 bytes, SP stays 8-aligned
        gic_read_store_block(TRIGNAT_B_READS[0], b_d[0]),        # B_D0 out[0] (8 = still pending)
        gic_read_store_block(TRIGNAT_B_READS[1], b_d[1]),        # B_D1 out[1]
        gic_read_store_block(TRIGNAT_B_READS[2], b_d[2]),        # B_D2 ISPENDR2 w2
        gic_read_store_block(TRIGNAT_B_READS[3], b_d[3]),        # B_D3 HPPIR
        _store_imm_block(TRIGNAT_SENTINEL, b_p),                 # B_P3 page-10 sentinel
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(3, 0xcece),                                         # reproduce `movw r3,#0xcece`
        msr_apsr(12),                                            # restore the saved flags
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, next_pad)


def pad_drain_extra_inta(pad: int, b2_cells: list[int], next_pad: int = TRIGCONS_CONT_B) -> bytes:
    """The inta drain companion (devcpu.md section 4.1's added cells): entered by the `b.w` at the
    tail of Pad B2, so it samples at the SAME instant.  B_D4 (ISACTIVER2 word 2, CA 0x40161308),
    B_D5 (the full CPSR via `mrs r0,<PSR>`), B_D6 (GICC_CTLR, CA 0x40160100), B_D7 (GICC_PMR, CA
    0x40160104) and the page-11 sentinel B_P4; then pop and a tail branch.  r0-r5 are saved/
    restored, so r1 (the 0x4000010c spin pointer) and r3 (0xcece) survive.  `next_pad` is the
    loop head 0x86F78 for inta/inta2/inta3 and the take1 giccpu pad (which then returns to the
    same loop head), so the inta3 callers' bytes are unchanged by the default."""
    b2 = b"".join([
        push(PAD_SAVE),                                          # r0-r5 are clobbered by the reads
        gic_read_store_block(GICD_ISACTIVER2, b2_cells[0]),      # B_D4 ISACTIVER2 w2 (active)
        _store_cpsr_block(b2_cells[1]),                          # B_D5 the full CPSR (I bit)
        gic_read_store_block(INTA_GICC_CTLR, b2_cells[2]),       # B_D6 GICC_CTLR
        gic_read_store_block(INTA_GICC_PMR, b2_cells[3]),        # B_D7 GICC_PMR
        _store_imm_block(TRIGNAT_SENTINEL, b2_cells[4]),         # B_P4 page-11 sentinel
        pop(PAD_SAVE),
    ])
    back = pad + len(b2)
    return b2 + b_w(back, next_pad)


def pad_loop_inta(pad: int, l_cells: list[int]) -> bytes:
    """The inta Pad L (devcpu.md section 4.2): the delayed sample at the 0xcece spin head
    (file 0x86F78).  L_CNT++ each visit; the L1 block (iteration 1) and the L2 block (a nonzero
    multiple of 2^24 iterations) sample ISPENDR2/ISACTIVER2/HPPIR/out[0] + the CPSR; the tail
    re-emits the replaced `ldr r2,[r1]`/`cmp r2,r3` and branches to 0x86F7C."""
    l1, l2, cnt, snt = l_cells[0:5], l_cells[5:10], l_cells[10], l_cells[11]

    def gic_block(cells: list[int], sentinel: bool) -> bytes:
        b = b"".join([
            gic_read_store_block(INTA_L_READS[0], cells[0]),   # ISPENDR2 (bit 12 = pending)
            gic_read_store_block(INTA_L_READS[1], cells[1]),   # ISACTIVER2 (bit 12 = active)
            gic_read_store_block(INTA_L_READS[2], cells[2]),   # HPPIR
            gic_read_store_block(INTA_L_READS[3], cells[3]),   # out[0]
            _store_cpsr_block(cells[4]),                       # the CPSR
        ])
        if sentinel:
            b += _store_imm_block(INTA_SENTINEL, snt)          # L_SNT (page 12)
        return b

    head = b"".join([
        mrs_apsr(12),                                            # save the condition flags
        push(PAD_SAVE),                                          # 24 bytes, SP stays 8-aligned
        movw(0, cnt & 0xFFFF), movt(0, cnt >> 16),               # r0 = &L_CNT
        ldr_imm(3, 0, 0),                                        # r3 = counter
        adds_imm(3, 3, 1),                                       # r3++
        str_imm(3, 0, 0),                                        # L_CNT = r3
        cmp_imm(3, 1),                                           # iteration 1?
    ])
    beq_addr = pad + len(head)
    mid = lsls_imm(2, 3, 8) + cmp_imm(2, 0)                      # (r3 & 0xFFFFFF) == 0 ?
    bne_addr = beq_addr + 2 + len(mid)
    l2b = gic_block(l2, False)
    tail_body = pop(PAD_SAVE) + INTA_LOOP_PAIR
    l2_start = bne_addr + 2
    tail_start = l2_start + len(l2b)
    tail = tail_body + b_w(tail_start + len(tail_body), INTA_CONT_L)
    l1_start = tail_start + len(tail)
    l1b = gic_block(l1, True)
    l1 = l1b + b_w(l1_start + len(l1b), tail_start)
    return (head + b_cond(beq_addr, l1_start, COND_EQ) + mid + b_cond(bne_addr, tail_start, COND_NE)
            + l2b + tail + l1)


def verify_disasm_inta(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int, pad_d: int,
                       pad_m: int, pad_l: int, s1: int, s2: int, gic_cells: list[int],
                       e_cells: list[int], a_cells: list[int], b_cells: list[int],
                       b2_cells: list[int], l_cells: list[int]) -> dict:
    """Byte-equality of the six pads against their reconstruction PLUS the block orders: Pad A/B
    (byte-identical to trigcons's, B extended), Pad L's counter/L1/L2/tail structure, the site
    bytes and the forbidden-CA absence."""
    if len(a_cells) != TRIGNAT_A_NCELLS:
        raise PatchError(f"inta expected {TRIGNAT_A_NCELLS} A cells, got {len(a_cells)}")
    if len(b_cells) != TRIGNAT_B_NCELLS:
        raise PatchError(f"inta expected {TRIGNAT_B_NCELLS} B cells, got {len(b_cells)}")
    if len(b2_cells) != INTA_B2_NCELLS:
        raise PatchError(f"inta expected {INTA_B2_NCELLS} B2 cells, got {len(b2_cells)}")
    if len(l_cells) != INTA_L_NCELLS:
        raise PatchError(f"inta expected {INTA_L_NCELLS} L cells, got {len(l_cells)}")
    every = [s1, s2] + gic_cells + e_cells + a_cells + b_cells + b2_cells + l_cells
    if len(set(every)) != len(every):
        raise PatchError("inta cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2])
    code_b = pad_bringup(pad_b, s2, gic_cells)
    code_s = pad_send_trignat(pad_s, a_cells)
    code_p = pad_post(pad_p, e_cells)
    code_d = pad_drain_inta(pad_d, b_cells, pad_m)
    code_m = pad_drain_extra_inta(pad_m, b2_cells)
    code_l = pad_loop_inta(pad_l, l_cells)
    for name, off, code in (("thunk", pad_i, code_i), ("bringup", pad_b, code_b),
                            ("send", pad_s, code_s), ("post", pad_p, code_p),
                            ("drain", pad_d, code_d), ("drain_extra", pad_m, code_m),
                            ("loop", pad_l, code_l)):
        if data[off:off + len(code)] != code:
            raise PatchError(f"the inta {name} pad at {off:#x} is not the intended bytes")

    # Pad A: identical to trigcons's (the natural post + the H2D ring), byte-compared above.
    if write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL) not in code_s:
        raise PatchError("the inta Pad A lost the H2D ring")

    # Pad B2 (trigcons's program) + the drain companion (the added cells, entered by B2's b.w).
    for ca, cell, nm in ((TRIGNAT_OUT0_CA, b_cells[0], "B_D0"), (TRIGNAT_OUT1_CA, b_cells[1], "B_D1"),
                         (GICD_ISPENDR2, b_cells[2], "B_D2"), (GICC_HPPIR, b_cells[3], "B_D3")):
        if gic_read_store_block(ca, cell) not in code_d:
            raise PatchError(f"inta Pad B2 is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_imm_block(TRIGNAT_SENTINEL, b_cells[4]) not in code_d:
        raise PatchError("inta Pad B2 is missing the B_P3 sentinel")
    if movw(3, 0xcece) not in code_d:
        raise PatchError("inta Pad B2 must re-emit `movw r3,#0xcece`")
    if b_w(pad_d + len(code_d) - 4, pad_m) != code_d[-4:]:
        raise PatchError("inta Pad B2 does not branch to its drain companion")
    order_d = [code_d.index(gic_read_store_block(TRIGNAT_B_READS[i], b_cells[i])) for i in range(4)]
    order_d += [code_d.index(_store_imm_block(TRIGNAT_SENTINEL, b_cells[4])),
                code_d.index(pop(PAD_SAVE)), code_d.index(movw(3, 0xcece))]
    if order_d != sorted(order_d) or len(set(order_d)) != len(order_d):
        raise PatchError("the inta Pad B2 order is not B_D0..B_D3 -> B_P3 -> pop -> movw r3,#0xcece")

    # the drain companion: push, B_D4..B_D7 + B_P4, pop, b.w to the loop head.
    for ca, cell, nm in ((GICD_ISACTIVER2, b2_cells[0], "B_D4"), (INTA_GICC_CTLR, b2_cells[2], "B_D6"),
                         (INTA_GICC_PMR, b2_cells[3], "B_D7")):
        if gic_read_store_block(ca, cell) not in code_m:
            raise PatchError(f"inta drain companion is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_cpsr_block(b2_cells[1]) not in code_m:
        raise PatchError("inta drain companion is missing the B_D5 CPSR read")
    if _store_imm_block(TRIGNAT_SENTINEL, b2_cells[4]) not in code_m:
        raise PatchError("inta drain companion is missing the B_P4 sentinel")
    if code_m.count(push(PAD_SAVE)) != 1 or code_m.count(pop(PAD_SAVE)) != 1:
        raise PatchError("inta drain companion must save/restore r0-r5 exactly once")
    if b_w(pad_m + len(code_m) - 4, TRIGCONS_CONT_B) != code_m[-4:]:
        raise PatchError("inta drain companion does not return to the loop head 0x86F78")
    order_m = [code_m.index(push(PAD_SAVE)),
               code_m.index(gic_read_store_block(GICD_ISACTIVER2, b2_cells[0])),
               code_m.index(_store_cpsr_block(b2_cells[1])),
               code_m.index(gic_read_store_block(INTA_GICC_CTLR, b2_cells[2])),
               code_m.index(gic_read_store_block(INTA_GICC_PMR, b2_cells[3])),
               code_m.index(_store_imm_block(TRIGNAT_SENTINEL, b2_cells[4])),
               code_m.index(pop(PAD_SAVE))]
    if order_m != sorted(order_m) or len(set(order_m)) != len(order_m):
        raise PatchError("the inta drain companion order is not push -> B_D4..B_D7 -> B_P4 -> pop")

    # Pad L: the counter, the two sample blocks, the gating branches and the tail.
    counter = (movw(0, l_cells[10] & 0xFFFF) + movt(0, l_cells[10] >> 16) + ldr_imm(3, 0, 0)
               + adds_imm(3, 3, 1) + str_imm(3, 0, 0) + cmp_imm(3, 1))
    if counter not in code_l:
        raise PatchError("inta Pad L is missing the L_CNT counter update")
    if lsls_imm(2, 3, 8) + cmp_imm(2, 0) not in code_l:
        raise PatchError("inta Pad L is missing the 2^24 gating (`lsls r2,r3,#8` + `cmp r2,#0`)")
    for read_ca, c1, c2, nm in ((GICD_ISPENDR2, l_cells[0], l_cells[5], "L_ISP"),
                                (GICD_ISACTIVER2, l_cells[1], l_cells[6], "L_ACT"),
                                (GICC_HPPIR, l_cells[2], l_cells[7], "L_HPP"),
                                (TRIGNAT_OUT0_CA, l_cells[3], l_cells[8], "L_OU0")):
        if gic_read_store_block(read_ca, c1) not in code_l:
            raise PatchError(f"inta Pad L is missing L1 {nm}")
        if gic_read_store_block(read_ca, c2) not in code_l:
            raise PatchError(f"inta Pad L is missing L2 {nm}")
    for cell, nm in ((l_cells[4], "L1_PSR"), (l_cells[9], "L2_PSR")):
        if _store_cpsr_block(cell) not in code_l:
            raise PatchError(f"inta Pad L is missing {nm}")
    if _store_imm_block(INTA_SENTINEL, l_cells[11]) not in code_l:
        raise PatchError("inta Pad L is missing the L_SNT sentinel")
    if pop(PAD_SAVE) not in code_l or INTA_LOOP_PAIR not in code_l:
        raise PatchError("inta Pad L is missing the pop / re-emitted `ldr r2,[r1]` / `cmp r2,r3`")
    if not any(b_w(pad_l + i, INTA_CONT_L) == code_l[i:i + 4]
               for i in range(0, len(code_l) - 3, 2)):
        raise PatchError("inta Pad L has no `b.w` to the loop's `bne` at 0x86F7C")

    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d), ("drain_extra", code_m),
                       ("loop", code_l)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"the inta {name} pad addresses a forbidden CA: {bad.hex()}")

    return {
        "thunk_pad": dis(pad_i, len(code_i)),
        "bringup_pad": dis(pad_b, len(code_b)),
        "send_pad": dis(pad_s, len(code_s)),
        "post_pad": dis(pad_p, len(code_p)),
        "drain_pad": dis(pad_d, len(code_d)),
        "drain_extra_pad": dis(pad_m, len(code_m)),
        "loop_pad": dis(pad_l, len(code_l)),
        "inta": {
            "site_a": hex(TRIGNAT_SITE_A), "cont_a": hex(TRIGNAT_CONT_A),
            "site_b": hex(TRIGCONS_SITE_B), "cont_b": hex(TRIGCONS_CONT_B),
            "site_l": hex(INTA_SITE_L), "cont_l": hex(INTA_CONT_L),
            "site_l_replaced": INTA_SITE_L_BYTES.hex(),
            "b2_reads": [hex(GICD_ISACTIVER2), "CPSR", hex(INTA_GICC_CTLR), hex(INTA_GICC_PMR)],
            "l_reads": [hex(x) for x in INTA_L_READS] + ["CPSR"],
            "b2_cells": [hex(c) for c in b2_cells], "l_cells": [hex(c) for c in l_cells],
            "send_pad_len": len(code_s), "drain_pad_len": len(code_d), "loop_pad_len": len(code_l),
        },
    }


def make_inta(data: bytes, barmap: bytes, refs: set[int]):
    """devcpu.md sections 4.1/4.2: trigcons plus the extended drain pad (B_D4..B_D7 + B_P4) and
    the delayed Pad L at the 0xcece spin head 0x86F78."""
    cells, sel = select_cells_inta(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    off_a = 2 + GICV_NCELLS + GICP_NCELLS
    ac = cells[off_a:off_a + TRIGNAT_A_NCELLS]
    off_b = off_a + TRIGNAT_A_NCELLS
    bc = cells[off_b:off_b + TRIGNAT_B_NCELLS]
    off_b2 = off_b + TRIGNAT_B_NCELLS
    b2c = cells[off_b2:off_b2 + INTA_B2_NCELLS]
    off_l = off_b2 + INTA_B2_NCELLS
    lc = cells[off_l:off_l + INTA_L_NCELLS]
    if (len(ec) != GICP_NCELLS or len(ac) != TRIGNAT_A_NCELLS or len(bc) != TRIGNAT_B_NCELLS
            or len(b2c) != INTA_B2_NCELLS or len(lc) != INTA_L_NCELLS):
        raise PatchError("internal error: inta cells were not selected")

    need_s = len(pad_send_trignat(0, ac))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    need_d = len(pad_drain_inta(0, bc, 0))          # length is independent of the branch target
    need_m = len(pad_drain_extra_inta(0, b2c))
    need_l = len(pad_loop_inta(0, lc))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p), ("drain", need_d), ("drain_extra", need_m),
                                   ("loop", need_l)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]
    (pad_d, len_d), (pad_m, len_m) = pads["drain"], pads["drain_extra"]
    (pad_l, len_l) = pads["loop"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send_trignat(pad_s, ac)
    code_p = pad_post(pad_p, ec)
    code_d = pad_drain_inta(pad_d, bc, pad_m)
    code_m = pad_drain_extra_inta(pad_m, b2c)
    code_l = pad_loop_inta(pad_l, lc)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p, pad_d,
                                drain_site=TRIGCONS_SITE_B, loop_pad=pad_l))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p),
                      (pad_d, code_d), (pad_m, code_m), (pad_l, code_l)):
        out[off:off + len(code)] = code
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the patch changed the image size")
    for site, pad in ((SITE_THUNK, pad_i), (BRINGUP_SITE, pad_b), (SEND_SITE, pad_s),
                      (POST_SITE, pad_p), (TRIGCONS_SITE_B, pad_d), (INTA_SITE_L, pad_l)):
        if out[site:site + 4] != bl(site, pad):
            raise PatchError(f"internal error: site {site:#x} bytes are not the intended bl")
    if out[0x8702C:0x87030] != data[0x8702C:0x87030]:
        raise PatchError("internal error: the original ISENABLER store at file 0x8702c was altered")
    if out[0x87030:0x87036] != data[0x87030:0x87036]:
        raise PatchError("internal error: the itet block 0x87030..0x87035 was altered")
    if data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] != bytes.fromhex("1a600122"):
        raise PatchError("the inta Pad A site is not `str r2,[r3]`+`movs r2,#1`")
    if data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] != TRIGCONS_SITE_B_BYTES:
        raise PatchError("the inta Pad B2 site is not `movw r3,#0xcece` (4cf6ce63)")
    if data[INTA_SITE_L:INTA_SITE_L + 4] != INTA_SITE_L_BYTES:
        raise PatchError("the inta Pad L site is not `ldr r2,[r1]`+`cmp r2,r3` (0a689a42)")
    if INTA_LOOP_PAIR != INTA_SITE_L_BYTES:
        raise PatchError("internal error: the encoder does not re-emit the loop pair")
    if data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] != TRIGNAT_DRAIN_POP:
        raise PatchError("the stock old announce-exit site is not `pop.w {r3..sb,lr}`")
    if out[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] != data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4]:
        raise PatchError("internal error: inta altered the old announce-exit site 0x86F7E")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d), ("drain_extra", code_m),
                       ("loop", code_l)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"internal error: the inta {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    verify_disasm_inta(out, pad_i, pad_b, pad_s, pad_p, pad_d, pad_m, pad_l, s1, s2, gc, ec, ac, bc,
                       b2c, lc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ac[:4]):
        records[f"A_S{i}"] = cell_record(barmap, a)
    records["A_P1"] = cell_record(barmap, ac[4])
    records["A_E0"] = cell_record(barmap, ac[5])
    records["A_E1"] = cell_record(barmap, ac[6])
    for i, a in enumerate(ac[7:12]):
        records[f"A_S{4 + i}"] = cell_record(barmap, a)
    records["A_P2"] = cell_record(barmap, ac[12])
    for i, a in enumerate(bc[:4]):
        records[f"B_D{i}"] = cell_record(barmap, a)
    records["B_P3"] = cell_record(barmap, bc[4])
    for i, a in enumerate(b2c[:4]):
        records[f"B_D{4 + i}"] = cell_record(barmap, a)
    records["B_P4"] = cell_record(barmap, b2c[4])
    for i, a in enumerate(lc[:5]):
        records[f"L1_{['ISP', 'ACT', 'HPP', 'OU0', 'PSR'][i]}"] = cell_record(barmap, a)
    for i, a in enumerate(lc[5:10]):
        records[f"L2_{['ISP', 'ACT', 'HPP', 'OU0', 'PSR'][i]}"] = cell_record(barmap, a)
    records["L_CNT"] = cell_record(barmap, lc[10])
    records["L_SNT"] = cell_record(barmap, lc[11])

    manifest = {
        "variant": "inta",
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000", "GICC_base": "0x40160100",
            "ISACTIVER2": hex(GICD_ISACTIVER2), "GICC_CTLR": hex(INTA_GICC_CTLR),
            "GICC_PMR": hex(INTA_GICC_PMR),
            "never_read": "0x4016010c (GICC IAR - acknowledging) and 0x10161000 (RC misc, panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, W1C) and the masked glue word 0x21",
            "ring": {"ca": hex(TRIGNAT_RING_CA), "value": hex(TRIGNAT_RING_VAL),
                     "note": NOTE_TRIGCONS_A},
            "gate": {"ca": "0x4000010c", "wait_value": "0x0000cece",
                     "site": hex(TRIGCONS_SITE_B), "cont": hex(TRIGCONS_CONT_B),
                     "pad_l_site": hex(INTA_SITE_L), "pad_l_cont": hex(INTA_CONT_L),
                     "note": NOTE_TRIGCONS_B},
            "pad_b2_note": NOTE_INTA_B2,
            "pad_l_note": NOTE_INTA_L,
            "cells_note": NOTE_INTA_CELLS,
        },
        "classification": {
            "instrument": "trigcons Pad A (the natural post at 0x86F5A + the H2D ring) and Pad B2 "
                           "(the extended drain at 0x86F74: out[0]/out[1]/ISPENDR2/HPPIR + "
                           "ISACTIVER2/CPSR/GICC_CTLR/GICC_PMR), plus Pad L (the delayed sample at "
                           "the 0xcece spin head 0x86F78: ISPENDR2/ISACTIVER2/HPPIR/out[0]/CPSR "
                           "at iteration 1 and at the latest 2^24-multiple revisit, with the "
                           "persistent L_CNT).",
            "ROW_1_or_2": "devcpu.md section 5: B_D4 bit 12 SET or L2_ACT bit 12 SET => "
                          "DEVCPU-TOOK; B_D2 bit 12 SET and L2_ISP bit 12 SET with B_D4 = L2_ACT = "
                          "0 => DEVCPU-MASKED/never-took, split by the CPSR I bit (B_D5/L2_PSR).",
            "branches_note": NOTE_TRIGCONS_BRANCHES,
            "bounds": "one-shot latched samples; the L2 block is the latest periodic snapshot of a "
                      "parked loop, not a trace; Pad L does not touch I/F (it saves/restores flags "
                      "only), so the mask it observes is the firmware's.",
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "code_length": len(code_b), "code_hex": code_b.hex()},
            "send_a": {"file_offset": hex(pad_s), "code_length": len(code_s), "code_hex": code_s.hex()},
            "post": {"file_offset": hex(pad_p), "code_length": len(code_p), "code_hex": code_p.hex()},
            "drain_b2": {"file_offset": hex(pad_d), "code_length": len(code_d), "code_hex": code_d.hex()},
            "drain_extra": {"file_offset": hex(pad_m), "code_length": len(code_m), "code_hex": code_m.hex()},
            "loop_l": {"file_offset": hex(pad_l), "code_length": len(code_l), "code_hex": code_l.hex()},
        },
        "sites": {
            "send_a": {"file_offset": hex(TRIGNAT_SITE_A), "cont": hex(TRIGNAT_CONT_A),
                       "replaced_bytes": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
                       "after": bl(TRIGNAT_SITE_A, pad_s).hex()},
            "drain_b2": {"file_offset": hex(TRIGCONS_SITE_B), "cont": hex(TRIGCONS_CONT_B),
                         "replaced_bytes": data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4].hex(),
                         "after": bl(TRIGCONS_SITE_B, pad_d).hex()},
            "loop_l": {"file_offset": hex(INTA_SITE_L), "cont": hex(INTA_CONT_L),
                       "replaced_bytes": data[INTA_SITE_L:INTA_SITE_L + 4].hex(),
                       "after": bl(INTA_SITE_L, pad_l).hex()},
            "old_drain_b": {"file_offset": hex(TRIGNAT_SITE_B),
                            "bytes": data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4].hex(),
                            "unchanged": out[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4] ==
                                         data[TRIGNAT_SITE_B:TRIGNAT_SITE_B + 4]},
        },
        "preserved": {
            "original_gic_write": {"file_offset": "0x8702c",
                                   "bytes_identical": out[0x8702C:0x87030] == data[0x8702C:0x87030]},
            "itet_block": {"file_offset": "0x8702a..0x87035",
                           "bytes_identical": out[0x87030:0x87036] == data[0x87030:0x87036]},
            "announce_loop_body": {"file_offset": "0x86f7c..0x86f7e",
                                   "bytes_identical": out[0x86F7C:0x86F7E] == data[0x86F7C:0x86F7E]},
            "old_announce_exit_continuation": {"file_offset": "0x86f7e..",
                                               "bytes_identical": out[0x86F7E:0x86F92] ==
                                                                  data[0x86F7E:0x86F92]},
        },
    }
    return out, manifest


# ---- inta2: the POST-EXIT take sample (take2.md sections 2/3, variant "inta2")
# take2.md: the inta run proved the unlock but not the take - the delayed Pad L sat INSIDE the
# 0xcece gate loop (site 0x86F78), so once the loop exits nothing re-visits it (L_CNT = 1, every
# L2_* = 0).  inta2 moves the delayed sample to the two sites execution reaches AFTER the gate:
#   * Site F = file 0x86F7E, the loop's own `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}` (stock bde8f843) - the
#     first instruction executed post-unlock and the only clean 4-byte slot there; the pad samples
#     ISACTIVER2 (bit 12 = the IAR was read) / ISPENDR2 / HPPIR / out[0] / the full CPSR + the
#     page-13 sentinel F_SNT, then re-emits the pop.w and branches to 0x86F82.
#   * Site N = file 0x86F5A, the firmware's own out[1] post (Pad A's existing site): Pad A's entry
#     block is WIDENED into the take set - after A_E0/A_E1 and BEFORE the post is reproduced, the
#     same four reads + the CPSR + the page-14 sentinel N_SNT are deposited.  The sample lands on
#     the NEXT visit's send site, an instant after the prior visit's unlock/interrupt window.
# Pad L is DROPPED: 0x86F78..0x86F7C returns to the firmware's own `ldr r2,[r1]` + `cmp r2,r3` +
# `bne 0x86f78` (INTA_LOOP_PAIR + the stock bne).  Pad B2 and its drain companion are KEPT
# byte-identical to inta's (the pre-exit baseline B_D0..B_D7 the branch table needs).  The thunk /
# bring-up / post pads and the S1/S2/C0..C5/E0..E3/A_*/B_* cells keep their inta addresses.
# NEVER writes 0x400392f0 or the masked word 0x21; NEVER reads the IAR 0x4016010c or 0x10161000;
# every added GIC read (ISPENDR2/ISACTIVER2/HPPIR) is non-acknowledging.
INTA2_F_PAGE_IDX = TRIGNAT_B_PAGE_IDX + 3     # all_zero_pages[13] = 0x155000 (F_ACT..F_SNT)
INTA2_N_PAGE_IDX = TRIGNAT_B_PAGE_IDX + 4     # all_zero_pages[14] = 0x157000 (N_ACT..N_SNT)
INTA2_F_NCELLS = 6                            # F_ACT, F_ISP, F_HPP, F_OU0, F_PSR, F_SNT
INTA2_N_NCELLS = 6                            # N_ACT, N_ISP, N_HPP, N_OU0, N_PSR, N_SNT
INTA2_A_NCELLS = TRIGNAT_A_NCELLS + INTA2_N_NCELLS   # Pad A's cells = the 13 + the 6 N cells
INTA2_TAKE_READS = (GICD_ISACTIVER2, GICD_ISPENDR2, GICC_HPPIR, TRIGNAT_OUT0_CA)  # + CPSR
INTA2_SITE_F = 0x86F7E                        # the loop's own `pop.w {r3..sb,lr}` (stock bde8f843)
INTA2_CONT_F = 0x86F82                        # continuation: `ldr r0,[pc,#0x3c]`
INTA2_SITE_N = TRIGNAT_SITE_A                 # 0x86f5a - Pad A's site (the out[1] post)
INTA2_F_NAMES = ("F_ACT", "F_ISP", "F_HPP", "F_OU0", "F_PSR", "F_SNT")
INTA2_N_NAMES = ("N_ACT", "N_ISP", "N_HPP", "N_OU0", "N_PSR", "N_SNT")

NOTE_INTA2_F = (
    "Site F (take2.md section 2.1) is the NEW pad at file 0x86F7E, the 0xcece gate loop's own "
    "`pop.w {r3,r4,r5,r6,r7,r8,sb,lr}` (stock bde8f843) - the first instruction executed after the "
    "unlock and the only clean 4-byte slot there.  It samples F_ACT (CA 0x40161308 ISACTIVER2 word "
    "2; bit 12 SET = the CPU read the IAR, i.e. the id-0x4c interrupt is ACTIVE), F_ISP (CA "
    "0x40161208 ISPENDR2 word 2; bit 12 = pending), F_HPP (CA 0x40160118 GICC HPPIR; 0x4c = "
    "pending vs 0x3ff = none), F_OU0 (CA 0x40039010 out[0]; 8 = unconsumed, 0 = the dispatcher "
    "ran), F_PSR (the full CPSR via `mrs r0,<PSR>` = F3EF 8000, bit 7 = I) and the page-13 "
    "sentinel F_SNT, then re-emits the replaced pop.w and branches to 0x86F82.  The pad never "
    "returns through lr (it ends in `b.w`), so the `bl`'s lr clobber is inert exactly as Pad B2's."
)
NOTE_INTA2_N = (
    "Site N (take2.md section 2.2) is a REUSE of Pad A's site (file 0x86F5A, the firmware's own "
    "out[1] post).  Only the entry block is widened: after the unchanged A_E0/A_E1 entry reads and "
    "BEFORE the post is reproduced and BEFORE the ring, the pad deposits N_ACT (ISACTIVER2 w2, CA "
    "0x40161308) / N_ISP (ISPENDR2 w2, CA 0x40161208) / N_HPP (GICC HPPIR, CA 0x40160118) / "
    "N_OU0 (out[0], CA 0x40039010) / N_PSR (the full CPSR) and the page-14 sentinel N_SNT.  The "
    "sample therefore lands on the send site of the NEXT visit - an instant after the prior "
    "visit's unlock, exit and interrupt window.  Pad A's post, glue-mask, submission, ring, A_S* "
    "reads and sentinels stay byte-identical to trignat's."
)
NOTE_INTA2_DROP = (
    "Pad L is DROPPED (take2.md section 2.3): the site 0x86F78..0x86F7C returns to the stock "
    "`ldr r2,[r1]` + `cmp r2,r3` + `bne 0x86f78` (0a689a42 + fcd1).  The in-loop pad was the only "
    "site the parked CPU re-visited, and it is void once the park ends (the inta run: L_CNT = 1, "
    "every L2_* = 0).  The old announce-exit site 0x86F7E, which trignat/trigcons/inta left stock, "
    "is now Site F's site."
)
NOTE_INTA2_CELLS = (
    "trignat/inta cells (IDENTICAL addresses: S1/S2, C0..C5, E0..E3, A_S0..A_S8/A_P1/A_E0/A_E1/"
    "A_P2, B_D0..B_D3/B_P3, B_D4..B_D7/B_P4) plus the two fresh all-zero 4 KB pages after inta's "
    "[12]: all_zero_pages[13] = 0x155000 carries F_ACT/F_ISP/F_HPP/F_OU0/F_PSR/F_SNT (6); "
    "all_zero_pages[14] = 0x157000 carries N_ACT/N_ISP/N_HPP/N_OU0/N_PSR/N_SNT (6).  "
    "(0x156000 is not all-zero and is skipped, exactly as take2.md section 3 records.)  Every cell "
    "is 0x00000000 at BOTH the BAR0 and the ACP-alias offsets in barmap_ep0_bar0.bin, 4-byte "
    "aligned, >= 8 bytes apart, outside the four excluded tables and distinct from every earlier "
    "cell.  Pad L's page-12 cells are NOT used."
)


def select_cells_inta2(barmap: bytes):
    """trignat's cells (identical addresses) + all_zero_pages[11] (B_D4..B_D7 + B_P4, kept from
    "inta) + all_zero_pages[13] (F_*) and all_zero_pages[14] (N_*).  No Pad L cells."""
    cells, sel = select_cells_trignat(barmap)
    ok = _cell_ok(barmap)
    pages = _zero_page_spans(barmap)
    if len(pages) < INTA2_N_PAGE_IDX + 1:
        raise PatchError(f"inta2 selection failed: fewer than {INTA2_N_PAGE_IDX + 1} all-zero 4 KB "
                         "pages in the band")
    p_b2, p_f, p_n = pages[INTA_B2_PAGE_IDX], pages[INTA2_F_PAGE_IDX], pages[INTA2_N_PAGE_IDX]
    b2 = _take_cells(p_b2, INTA_B2_NCELLS, ok, cells)
    if len(b2) < INTA_B2_NCELLS:
        raise PatchError(f"inta2 selection failed: page {p_b2:#x} has fewer than {INTA_B2_NCELLS} "
                         "usable cells")
    fc = _take_cells(p_f, INTA2_F_NCELLS, ok, b2)
    if len(fc) < INTA2_F_NCELLS:
        raise PatchError(f"inta2 selection failed: page {p_f:#x} has fewer than {INTA2_F_NCELLS} "
                         "usable cells")
    nc = _take_cells(p_n, INTA2_N_NCELLS, ok, fc)
    if len(nc) < INTA2_N_NCELLS:
        raise PatchError(f"inta2 selection failed: page {p_n:#x} has fewer than {INTA2_N_NCELLS} "
                         "usable cells")
    sel = dict(sel)
    sel.update({
        "inta2_rule": "trignat's cells + all_zero_pages[11] (B_D4..B_D7 + B_P4) + "
                      "all_zero_pages[13] (F_*) + all_zero_pages[14] (N_*); no Pad L cells",
        "inta2_b2_page": hex(p_b2), "inta2_f_page": hex(p_f), "inta2_n_page": hex(p_n),
        "inta2_b2_page_idx": INTA_B2_PAGE_IDX, "inta2_f_page_idx": INTA2_F_PAGE_IDX,
        "inta2_n_page_idx": INTA2_N_PAGE_IDX,
        "inta2_b2_cells": [hex(a) for a in b2], "inta2_f_cells": [hex(a) for a in fc],
        "inta2_n_cells": [hex(a) for a in nc], "inta2_note": NOTE_INTA2_CELLS,
        "inta2_dropped": "Pad L (site 0x86f78) removed - the site is the firmware's own again",
    })
    return cells + b2 + fc + nc, sel


# ---- inta3: the inta2 take with the N cells on the RETENTION-VERIFIED page (witness2.md FLAW 2)
# The inta2 run's Site N deposited NOTHING: all six N_* read 0x00000000 - including the constant
# sentinel N_SNT (0x50AA7E49) and the live CPSR, values that cannot legitimately be zero - while the
# SAME send pad's A_* deposits all landed.  So page 14 (runtime 0x157000) simply did not retain;
# in the same boot pages 9-13 DID.  inta3 is therefore inta2 with ONE change: the six N cells move
# to page 10 (runtime 0x150000, alias 0x40808000) - the pair verified retained across the last two
# runs' barmap reads - at the next free 8-byte slots after the page-10 cells already taken
# (A_S4..A_S8/A_P2/B_D0..B_D3/B_P3 end at 0x150050), i.e. 0x150058..0x150080.  Every pad PROGRAM is
# byte-identical to inta2's (only the N cell addresses move); Site F keeps page 13 (0x155000).
# NEVER writes 0x400392f0 or the masked word 0x21; NEVER reads the IAR 0x4016010c or 0x10161000.
INTA3_N_PAGE_IDX = TRIGNAT_B_PAGE_IDX       # all_zero_pages[10] = 0x150000 (the retaining band)
INTA3_N_NCELLS = INTA2_N_NCELLS             # 6: N_ACT/N_ISP/N_HPP/N_OU0/N_PSR/N_SNT
INTA3_N_FIRST = 0x150058                    # the first free 8-byte slot after B_P3 (0x150050)

NOTE_INTA3_N = (
    "Site N is inta2's (Pad A's widened entry at file 0x86F5A, the firmware's own out[1] post), "
    "depositing N_ACT (ISACTIVER2 w2, CA 0x40161308) / N_ISP (ISPENDR2 w2, CA 0x40161208) / "
    "N_HPP (GICC HPPIR, CA 0x40160118) / N_OU0 (out[0], CA 0x40039010) / N_PSR (the full CPSR) and "
    "the sentinel N_SNT.  ONLY the six cell addresses changed vs inta2: they now sit on page 10 "
    "(0x150058..0x150080), the retention-VERIFIED band (witness2.md FLAW 2), instead of page 14."
)
NOTE_INTA3_CELLS = (
    "trignat/inta cells (IDENTICAL addresses) plus all_zero_pages[11] (B_D4..B_D7/B_P4, kept) "
    "and all_zero_pages[13] (F_ACT..F_SNT, kept), and - THE FIX - the six N cells on "
    "all_zero_pages[10] = 0x150000 instead of inta2's all_zero_pages[14] = 0x157000.  They take "
    "0x150058..0x150080, the next free 8-byte slots after A_S4..A_S8/A_P2/B_D0..B_D3/B_P3 (which "
    "end at 0x150050).  witness2.md FLAW 2: page 14 did NOT retain the inta2 run's deposits "
    "(N_SNT/N_PSR read 0x0) while pages 9-13 did, so the fresh cells now sit in the verified band.  "
    "Every cell is 0x00000000 at BOTH the BAR0 and the ACP-alias offsets in barmap_ep0_bar0.bin, "
    "4-byte aligned, >= 8 bytes apart, outside the four excluded tables and distinct."
)


def select_cells_inta3(barmap: bytes):
    """witness2.md FLAW 2 fix: inta2's cells with the six N cells on all_zero_pages[10] """
    cells, sel = select_cells_trignat(barmap)
    ok = _cell_ok(barmap)
    pages = _zero_page_spans(barmap)
    if len(pages) < INTA2_F_PAGE_IDX + 1:
        raise PatchError(f"inta3 selection failed: fewer than {INTA2_F_PAGE_IDX + 1} all-zero 4 KB "
                         "pages in the band")
    p_b2, p_f, p_n = pages[INTA_B2_PAGE_IDX], pages[INTA2_F_PAGE_IDX], pages[INTA3_N_PAGE_IDX]
    if p_n != pages[TRIGNAT_B_PAGE_IDX]:
        raise PatchError(f"inta3 selection failed: the N page is not the retaining page 10 ({p_n:#x})")
    b2 = _take_cells(p_b2, INTA_B2_NCELLS, ok, cells)
    if len(b2) < INTA_B2_NCELLS:
        raise PatchError(f"inta3 selection failed: page {p_b2:#x} has fewer than {INTA_B2_NCELLS} "
                         "usable cells")
    fc = _take_cells(p_f, INTA2_F_NCELLS, ok, b2)
    if len(fc) < INTA2_F_NCELLS:
        raise PatchError(f"inta3 selection failed: page {p_f:#x} has fewer than {INTA2_F_NCELLS} "
                         "usable cells")
    # the retention fix: the N walk continues from the LAST page-10 cell already taken (B_P3 at
    # 0x150050), so its candidates below that address are rejected and it lands at 0x150058.
    nc = _take_cells(p_n, INTA3_N_NCELLS, ok, cells)
    if len(nc) < INTA3_N_NCELLS:
        raise PatchError(f"inta3 selection failed: page {p_n:#x} has fewer than {INTA3_N_NCELLS} "
                         "free slots after the trignat cells")
    if nc[0] != INTA3_N_FIRST:
        raise PatchError(f"inta3 selection failed: the first N cell is {nc[0]:#x}, not the first "
                         f"free slot {INTA3_N_FIRST:#x}")
    sel = dict(sel)
    sel.update({
        "inta3_rule": "trignat's cells + all_zero_pages[11] (B_D4..B_D7/B_P4, kept) + "
                      "all_zero_pages[13] (F_*, kept) + the N cells on all_zero_pages[10] "
                      "(0x150000, the retention-verified band) - witness2.md FLAW 2 fix",
        "inta3_b2_page": hex(p_b2), "inta3_f_page": hex(p_f), "inta3_n_page": hex(p_n),
        "inta3_b2_page_idx": INTA_B2_PAGE_IDX, "inta3_f_page_idx": INTA2_F_PAGE_IDX,
        "inta3_n_page_idx": INTA3_N_PAGE_IDX,
        "inta3_b2_cells": [hex(a) for a in b2], "inta3_f_cells": [hex(a) for a in fc],
        "inta3_n_cells": [hex(a) for a in nc], "inta3_note": NOTE_INTA3_CELLS,
        "inta3_n_first": hex(INTA3_N_FIRST),
        "inta3_dropped": "inta2's page-14 N cells (0x157000 did not retain) - Pad L stays dropped",
    })
    return cells + b2 + fc + nc, sel


def pad_send_inta2(pad: int, a_cells: list[int]) -> bytes:
    """take2.md section 2.2: trignat/inta's Pad A (the natural out[1] post at 0x86F5A) with its
    ENTRY block widened into the take set.  Order: A_E0/A_E1 (unchanged) -> N_ACT/N_ISP/N_HPP/
    N_OU0/N_PSR + N_SNT (the added take reads, all BEFORE the post is reproduced and before the
    ring) -> the post / mask-open / H2D submission / pre-ring A_S0..A_S2 / THE RING / post-ring
    A_S3..A_S8 / A_P1/A_P2 (byte-identical to trignat's) -> pop, `movw r2,#1`, msr, b.w 0x86F5E."""
    a_s0_3, a_p1, a_e = a_cells[0:4], a_cells[4], a_cells[5:7]
    a_s4_8, a_p2 = a_cells[7:12], a_cells[12]
    n = a_cells[13:19]
    head = b"".join([
        mrs_apsr(12),
        push(PAD_SAVE),
        gic_read_store_block(TRIGNAT_OUT0_CA, a_e[0]),        # A_E0 entry read of out[0]
        gic_read_store_block(TRIGNAT_OUT1_CA, a_e[1]),        # A_E1 entry read of out[1]
        gic_read_store_block(INTA2_TAKE_READS[0], n[0]),      # N_ACT ISACTIVER2 w2
        gic_read_store_block(INTA2_TAKE_READS[1], n[1]),      # N_ISP ISPENDR2 w2
        gic_read_store_block(INTA2_TAKE_READS[2], n[2]),      # N_HPP GICC HPPIR
        gic_read_store_block(INTA2_TAKE_READS[3], n[3]),      # N_OU0 out[0]
        _store_cpsr_block(n[4]),                              # N_PSR the full CPSR
        _store_imm_block(INTA_SENTINEL, n[5]),                # N_SNT page-14 sentinel
        str_imm(2, 3, 0),                                     # reproduce `str r2,[r3]`
        write_ca_block(TRIGNAT_GLUE_MASK, TRIGNAT_MASK_OPEN),  # glue mask OPEN (0x20)
        write_ca_block(TRIGNAT_OUT0_CA, TRIGNAT_SUBMIT_VAL),   # H2D submission out[0] <= 8
    ])
    body = b"".join([
        gic_read_store_block(TRIGNAT_PRE_READS[0], a_s0_3[0]),
        gic_read_store_block(TRIGNAT_PRE_READS[1], a_s0_3[1]),
        gic_read_store_block(TRIGNAT_PRE_READS[2], a_s0_3[2]),
        write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL),
        gic_read_store_block(TRIGNAT_POST_READS[0], a_s0_3[3]),
        gic_read_store_block(TRIGNAT_POST_READS[1], a_s4_8[0]),
        gic_read_store_block(TRIGNAT_POST_READS[2], a_s4_8[1]),
        gic_read_store_block(TRIGNAT_POST_READS[3], a_s4_8[2]),
        gic_read_store_block(TRIGNAT_POST_READS[4], a_s4_8[3]),
        gic_read_store_block(TRIGNAT_POST_READS[5], a_s4_8[4]),
        _store_imm_block(TRIGNAT_SENTINEL, a_p1),
        _store_imm_block(TRIGNAT_SENTINEL, a_p2),
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        movw(2, 1),
        msr_apsr(12),
    ])
    back = pad + len(head) + len(body) + len(tail)
    return head + body + tail + b_w(back, TRIGNAT_CONT_A)


def pad_fallthrough_inta2(pad: int, f_cells: list[int]) -> bytes:
    """take2.md section 2.1: the NEW Site F pad at file 0x86F7E (the 0xcece gate loop's own
    `pop.w {r3,r4,r5,r6,r7,r8,sb,lr}`).  Reads F_ACT (ISACTIVER2 w2) / F_ISP (ISPENDR2 w2) /
    F_HPP (GICC HPPIR) / F_OU0 (out[0]) / F_PSR (the full CPSR) + the page-13 sentinel F_SNT, then
    re-emits the replaced pop.w and branches to 0x86F82.  r0-r5 and the flags are saved/restored."""
    head = b"".join([
        mrs_apsr(12),
        push(PAD_SAVE),
        gic_read_store_block(INTA2_TAKE_READS[0], f_cells[0]),   # F_ACT ISACTIVER2 w2
        gic_read_store_block(INTA2_TAKE_READS[1], f_cells[1]),   # F_ISP ISPENDR2 w2
        gic_read_store_block(INTA2_TAKE_READS[2], f_cells[2]),   # F_HPP GICC HPPIR
        gic_read_store_block(INTA2_TAKE_READS[3], f_cells[3]),   # F_OU0 out[0]
        _store_cpsr_block(f_cells[4]),                           # F_PSR the full CPSR
        _store_imm_block(INTA_SENTINEL, f_cells[5]),             # F_SNT page-13 sentinel
    ])
    tail = b"".join([
        pop(PAD_SAVE),
        msr_apsr(12),
        TRIGNAT_DRAIN_POP,                                       # reproduce pop.w {r3..sb,lr}
    ])
    back = pad + len(head) + len(tail)
    return head + tail + b_w(back, INTA2_CONT_F)


def verify_disasm_inta2(data: bytes, pad_i: int, pad_b: int, pad_s: int, pad_p: int, pad_d: int,
                        pad_m: int, pad_f: int, s1: int, s2: int, gic_cells: list[int],
                        e_cells: list[int], a_cells: list[int], b_cells: list[int],
                        b2_cells: list[int], f_cells: list[int]) -> dict:
    """Byte-equality of the seven pads against their reconstruction PLUS the block orders: Pad A's
    widened entry (N_* before the post), Site F's take reads + the re-emitted pop.w + b.w 0x86F82,
    Pad B2 + companion unchanged from inta, the stock loop head, and the forbidden-CA absence."""
    if len(a_cells) != INTA2_A_NCELLS:
        raise PatchError(f"inta2 expected {INTA2_A_NCELLS} A cells, got {len(a_cells)}")
    if len(b_cells) != TRIGNAT_B_NCELLS:
        raise PatchError(f"inta2 expected {TRIGNAT_B_NCELLS} B cells, got {len(b_cells)}")
    if len(b2_cells) != INTA_B2_NCELLS:
        raise PatchError(f"inta2 expected {INTA_B2_NCELLS} B2 cells, got {len(b2_cells)}")
    if len(f_cells) != INTA2_F_NCELLS:
        raise PatchError(f"inta2 expected {INTA2_F_NCELLS} F cells, got {len(f_cells)}")
    every = [s1, s2] + gic_cells + e_cells + a_cells + b_cells + b2_cells + f_cells
    if len(set(every)) != len(every):
        raise PatchError("inta2 cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code_i = pad_thunk(pad_i, s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2])
    code_b = pad_bringup(pad_b, s2, gic_cells)
    code_s = pad_send_inta2(pad_s, a_cells)
    code_p = pad_post(pad_p, e_cells)
    code_d = pad_drain_inta(pad_d, b_cells, pad_m)
    code_m = pad_drain_extra_inta(pad_m, b2_cells)
    code_f = pad_fallthrough_inta2(pad_f, f_cells)
    for name, off, code in (("thunk", pad_i, code_i), ("bringup", pad_b, code_b),
                            ("send", pad_s, code_s), ("post", pad_p, code_p),
                            ("drain", pad_d, code_d), ("drain_extra", pad_m, code_m),
                            ("fallthrough", pad_f, code_f)):
        if data[off:off + len(code)] != code:
            raise PatchError(f"the inta2 {name} pad at {off:#x} is not the intended bytes")

    # Pad A: the added N_* take reads must sit in the ENTRY block, before the reproduced post.
    n = a_cells[13:19]
    for ca, cell, nm in ((INTA2_TAKE_READS[0], n[0], "N_ACT"), (INTA2_TAKE_READS[1], n[1], "N_ISP"),
                         (INTA2_TAKE_READS[2], n[2], "N_HPP"), (INTA2_TAKE_READS[3], n[3], "N_OU0")):
        if gic_read_store_block(ca, cell) not in code_s:
            raise PatchError(f"inta2 Pad A is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_cpsr_block(n[4]) not in code_s:
        raise PatchError("inta2 Pad A is missing the N_PSR CPSR read")
    if _store_imm_block(INTA_SENTINEL, n[5]) not in code_s:
        raise PatchError("inta2 Pad A is missing the N_SNT sentinel")
    if write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL) not in code_s:
        raise PatchError("the inta2 Pad A lost the H2D ring")
    post_off = code_s.index(str_imm(2, 3, 0))
    order_n = [code_s.index(gic_read_store_block(INTA2_TAKE_READS[i], n[i])) for i in range(4)] \
        + [code_s.index(_store_cpsr_block(n[4])), code_s.index(_store_imm_block(INTA_SENTINEL, n[5]))]
    if order_n != sorted(order_n) or len(set(order_n)) != len(order_n) or max(order_n) > post_off:
        raise PatchError("the inta2 Pad A N_* block is not before the reproduced post")

    # Pad B2 + companion: unchanged from inta (the pre-exit baseline).
    if movw(3, 0xcece) not in code_d or b_w(pad_d + len(code_d) - 4, pad_m) != code_d[-4:]:
        raise PatchError("inta2 Pad B2 lost its `movw r3,#0xcece` / companion branch")
    if b_w(pad_m + len(code_m) - 4, TRIGCONS_CONT_B) != code_m[-4:]:
        raise PatchError("inta2 drain companion does not return to the loop head 0x86F78")
    if _store_cpsr_block(b2_cells[1]) not in code_m:
        raise PatchError("inta2 drain companion is missing the B_D5 CPSR read")

    # Site F: the take reads, the re-emitted pop.w and the branch to 0x86F82.
    for ca, cell, nm in ((INTA2_TAKE_READS[0], f_cells[0], "F_ACT"), (INTA2_TAKE_READS[1], f_cells[1], "F_ISP"),
                         (INTA2_TAKE_READS[2], f_cells[2], "F_HPP"), (INTA2_TAKE_READS[3], f_cells[3], "F_OU0")):
        if gic_read_store_block(ca, cell) not in code_f:
            raise PatchError(f"inta2 Site F is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_cpsr_block(f_cells[4]) not in code_f:
        raise PatchError("inta2 Site F is missing the F_PSR CPSR read")
    if _store_imm_block(INTA_SENTINEL, f_cells[5]) not in code_f:
        raise PatchError("inta2 Site F is missing the F_SNT sentinel")
    if code_f.count(TRIGNAT_DRAIN_POP) != 1:
        raise PatchError("inta2 Site F must re-emit the replaced pop.w exactly once")
    if b_w(pad_f + len(code_f) - 4, INTA2_CONT_F) != code_f[-4:]:
        raise PatchError("inta2 Site F has no `b.w` to 0x86F82")
    order_f = [code_f.index(gic_read_store_block(INTA2_TAKE_READS[i], f_cells[i])) for i in range(4)] \
        + [code_f.index(_store_cpsr_block(f_cells[4])),
           code_f.index(_store_imm_block(INTA_SENTINEL, f_cells[5])),
           code_f.index(TRIGNAT_DRAIN_POP)]
    if order_f != sorted(order_f) or len(set(order_f)) != len(order_f):
        raise PatchError("the inta2 Site F order is not F_ACT..F_OU0 -> F_PSR -> F_SNT -> pop.w")

    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d), ("drain_extra", code_m),
                       ("fallthrough", code_f)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"the inta2 {name} pad addresses a forbidden CA: {bad.hex()}")

    return {
        "thunk_pad": dis(pad_i, len(code_i)),
        "bringup_pad": dis(pad_b, len(code_b)),
        "send_pad": dis(pad_s, len(code_s)),
        "post_pad": dis(pad_p, len(code_p)),
        "drain_pad": dis(pad_d, len(code_d)),
        "drain_extra_pad": dis(pad_m, len(code_m)),
        "fallthrough_pad": dis(pad_f, len(code_f)),
        "inta2": {
            "site_n": hex(INTA2_SITE_N), "cont_n": hex(TRIGNAT_CONT_A),
            "site_b2": hex(TRIGCONS_SITE_B), "cont_b2": hex(TRIGCONS_CONT_B),
            "site_f": hex(INTA2_SITE_F), "cont_f": hex(INTA2_CONT_F),
            "site_f_replaced": TRIGNAT_DRAIN_POP.hex(),
            "site_l": hex(INTA_SITE_L), "site_l_stock": INTA_LOOP_PAIR.hex(),
            "take_reads": [hex(x) for x in INTA2_TAKE_READS] + ["CPSR"],
            "f_cells": [hex(c) for c in f_cells], "n_cells": [hex(c) for c in n],
            "send_pad_len": len(code_s), "fallthrough_pad_len": len(code_f),
        },
    }


def _make_inta_like(data: bytes, barmap: bytes, refs: set[int], select_fn, variant: str,
                    n_note: str, cells_note: str):
    """The shared body of the inta2/inta3 instruments: trigcons/inta's thunk + bring-up + post
    pads, Pad A's entry widened with the N_* take reads, the inta Pad B2 + drain companion kept,
    Pad L dropped (0x86F78 stock) and the NEW Site F pad at 0x86F7E.  `select_fn` supplies the
    cells (the ONLY difference between inta2 and inta3 is the N cells' page); `variant`,
    `n_note` and `cells_note` name the output and its notes."""
    cells, sel = select_fn(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    off_a = 2 + GICV_NCELLS + GICP_NCELLS
    ac = cells[off_a:off_a + TRIGNAT_A_NCELLS]
    off_b = off_a + TRIGNAT_A_NCELLS
    bc = cells[off_b:off_b + TRIGNAT_B_NCELLS]
    off_b2 = off_b + TRIGNAT_B_NCELLS
    b2c = cells[off_b2:off_b2 + INTA_B2_NCELLS]
    off_f = off_b2 + INTA_B2_NCELLS
    fc = cells[off_f:off_f + INTA2_F_NCELLS]
    off_n = off_f + INTA2_F_NCELLS
    nc = cells[off_n:off_n + INTA2_N_NCELLS]
    ac2 = ac + nc
    if (len(ec) != GICP_NCELLS or len(ac) != TRIGNAT_A_NCELLS or len(bc) != TRIGNAT_B_NCELLS
            or len(b2c) != INTA_B2_NCELLS or len(fc) != INTA2_F_NCELLS
            or len(nc) != INTA2_N_NCELLS or len(ac2) != INTA2_A_NCELLS):
        raise PatchError("internal error: inta2 cells were not selected")

    need_s = len(pad_send_inta2(0, ac2))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    need_d = len(pad_drain_inta(0, bc, 0))
    need_m = len(pad_drain_extra_inta(0, b2c))
    need_f = len(pad_fallthrough_inta2(0, fc))
    pads = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                   ("post", need_p), ("drain", need_d),
                                   ("drain_extra", need_m), ("fallthrough", need_f)])
    (pad_s, len_s), (pad_i, len_i) = pads["send"], pads["thunk"]
    (pad_b, len_b), (pad_p, len_p) = pads["bringup"], pads["post"]
    (pad_d, len_d), (pad_m, len_m) = pads["drain"], pads["drain_extra"]
    (pad_f, len_f) = pads["fallthrough"]

    code_i = pad_thunk(pad_i, s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pad_b, s2, gc)
    code_s = pad_send_inta2(pad_s, ac2)
    code_p = pad_post(pad_p, ec)
    code_d = pad_drain_inta(pad_d, bc, pad_m)
    code_m = pad_drain_extra_inta(pad_m, b2c)
    code_f = pad_fallthrough_inta2(pad_f, fc)
    out = bytearray(patch_sites(data, pad_i, pad_b, pad_s, pad_p, pad_d,
                                drain_site=TRIGCONS_SITE_B, loop_pad=pad_f, loop_site=INTA2_SITE_F))
    for off, code in ((pad_i, code_i), (pad_b, code_b), (pad_s, code_s), (pad_p, code_p),
                      (pad_d, code_d), (pad_m, code_m), (pad_f, code_f)):
        out[off:off + len(code)] = code
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the inta2 patch changed the image size")
    for site, pad in ((SITE_THUNK, pad_i), (BRINGUP_SITE, pad_b), (SEND_SITE, pad_s),
                      (POST_SITE, pad_p), (TRIGCONS_SITE_B, pad_d), (INTA2_SITE_F, pad_f)):
        if out[site:site + 4] != bl(site, pad):
            raise PatchError(f"internal error: site {site:#x} bytes are not the intended bl")
    if data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] != bytes.fromhex("1a600122"):
        raise PatchError("the inta2 Pad A site is not `str r2,[r3]`+`movs r2,#1`")
    if data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] != TRIGCONS_SITE_B_BYTES:
        raise PatchError("the inta2 Pad B2 site is not `movw r3,#0xcece` (4cf6ce63)")
    if data[INTA2_SITE_F:INTA2_SITE_F + 4] != TRIGNAT_DRAIN_POP:
        raise PatchError("the inta2 Site F site is not the stock `pop.w {r3..sb,lr}` (bde8f843)")
    if data[INTA_SITE_L:INTA_SITE_L + 4] != INTA_LOOP_PAIR:
        raise PatchError("the inta2 dropped Pad-L site is not the stock `ldr r2,[r1]`+`cmp`")
    if out[INTA_SITE_L:INTA_SITE_L + 4] != data[INTA_SITE_L:INTA_SITE_L + 4]:
        raise PatchError("internal error: inta2 altered the dropped Pad-L site 0x86F78")
    if out[0x86F7C:0x86F7E] != data[0x86F7C:0x86F7E]:
        raise PatchError("internal error: inta2 altered the loop's `bne 0x86f78`")
    if out[INTA2_CONT_F:0x86F92] != data[INTA2_CONT_F:0x86F92]:
        raise PatchError("internal error: inta2 altered the byte stream after Site F")
    if out[0x8702C:0x87030] != data[0x8702C:0x87030]:
        raise PatchError("internal error: the original ISENABLER store at file 0x8702c was altered")
    if out[0x87030:0x87036] != data[0x87030:0x87036]:
        raise PatchError("internal error: the itet block 0x87030..0x87035 was altered")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s),
                       ("post", code_p), ("drain", code_d), ("drain_extra", code_m),
                       ("fallthrough", code_f)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0)):
            if bad in code:
                raise PatchError(f"internal error: the inta2 {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    verify_disasm_inta2(out, pad_i, pad_b, pad_s, pad_p, pad_d, pad_m, pad_f, s1, s2, gc, ec, ac2,
                        bc, b2c, fc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ac[:4]):
        records[f"A_S{i}"] = cell_record(barmap, a)
    records["A_P1"] = cell_record(barmap, ac[4])
    records["A_E0"] = cell_record(barmap, ac[5])
    records["A_E1"] = cell_record(barmap, ac[6])
    for i, a in enumerate(ac[7:12]):
        records[f"A_S{4 + i}"] = cell_record(barmap, a)
    records["A_P2"] = cell_record(barmap, ac[12])
    for i, a in enumerate(bc[:4]):
        records[f"B_D{i}"] = cell_record(barmap, a)
    records["B_P3"] = cell_record(barmap, bc[4])
    for i, a in enumerate(b2c[:4]):
        records[f"B_D{4 + i}"] = cell_record(barmap, a)
    records["B_P4"] = cell_record(barmap, b2c[4])
    for nm, a in zip(INTA2_F_NAMES, fc):
        records[nm] = cell_record(barmap, a)
    for nm, a in zip(INTA2_N_NAMES, nc):
        records[nm] = cell_record(barmap, a)

    manifest = {
        "variant": variant,
        "selection": sel,
        "cells": records,
        "gic_map": {
            "GICD_base": "0x40161000", "GICC_base": "0x40160100",
            "ISACTIVER2": hex(GICD_ISACTIVER2), "ISPENDR2": hex(GICD_ISPENDR2),
            "HPPIR": hex(GICC_HPPIR),
            "never_read": "0x4016010c (GICC IAR - acknowledging) and 0x10161000 (RC misc, panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, W1C) and the masked glue word 0x21",
            "ring": {"ca": hex(TRIGNAT_RING_CA), "value": hex(TRIGNAT_RING_VAL),
                     "note": NOTE_TRIGCONS_A},
            "gate": {"ca": "0x4000010c", "wait_value": "0x0000cece",
                     "site_b2": hex(TRIGCONS_SITE_B), "cont_b2": hex(TRIGCONS_CONT_B),
                     "note": NOTE_TRIGCONS_B},
            "site_f_note": NOTE_INTA2_F,
            "site_n_note": n_note,
            "pad_l_dropped_note": NOTE_INTA2_DROP,
            "cells_note": cells_note,
        },
        "classification": {
            "instrument": "the POST-EXIT take sample: Pad B2 (the pre-exit drain baseline at "
                           "0x86F74) + the NEW Site F at the gate's own fall-through 0x86F7E "
                           "(ISACTIVER2/ISPENDR2/HPPIR/out[0]/CPSR) + Pad A's widened entry at "
                           "0x86F5A (N_ACT/N_ISP/N_HPP/N_OU0/N_PSR at the NEXT visit's send site).",
            "ROW_1": "take2.md section 4: F_ACT bit12 SET or N_ACT bit12 SET => TAKEN-AND-ACTIVE "
                      "(cross-check F_OU0/N_OU0: 0 = the dispatcher consumed it too; still 8 = the "
                      "residual is inside the ISR dispatch).",
            "ROW_2": "F_ISP bit12 SET and N_ISP bit12 CLEAR (or both clear), F_ACT = N_ACT = 0 => "
                      "PENDING-CLEARED - an IAR read (the take) between the samples, or the "
                      "firmware's own disable+clear path.",
            "ROW_3": "F_ISP bit12 SET and N_ISP bit12 SET and F_ACT = N_ACT = 0 => STILL-PENDING-"
                      "UNTAKEN; the CPSR pair splits it (I=1 at both => still inside a masked "
                      "section; I=0 with the GIC armed => the CPU-interface -> core hand-off).",
            "ROW_4": "F_SNT absent => the routine never fell through the gate; N_SNT absent => the "
                      "routine was not re-entered in this boot (single visit: N is void, F alone "
                      "carries the record).",
            "bounds": "instants, not a trace: F_* is one read at the fall-through, N_* one read at "
                      "the send site's next entry; a take that both starts and finishes between the "
                      "two samples is caught only by its persistent effect (N_ISP bit 12 clear / "
                      "N_OU0 = 0).  The pad touches no I/F state (mrs/msr apsr_nzcvq only).",
        },
        "padding": {
            "thunk": {"file_offset": hex(pad_i), "code_length": len(code_i), "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pad_b), "code_length": len(code_b), "code_hex": code_b.hex()},
            "send_n": {"file_offset": hex(pad_s), "code_length": len(code_s), "code_hex": code_s.hex()},
            "post": {"file_offset": hex(pad_p), "code_length": len(code_p), "code_hex": code_p.hex()},
            "drain_b2": {"file_offset": hex(pad_d), "code_length": len(code_d), "code_hex": code_d.hex()},
            "drain_extra": {"file_offset": hex(pad_m), "code_length": len(code_m), "code_hex": code_m.hex()},
            "fallthrough_f": {"file_offset": hex(pad_f), "code_length": len(code_f),
                              "code_hex": code_f.hex()},
        },
        "sites": {
            "send_n": {"file_offset": hex(TRIGNAT_SITE_A), "cont": hex(TRIGNAT_CONT_A),
                       "replaced_bytes": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
                       "after": bl(TRIGNAT_SITE_A, pad_s).hex()},
            "drain_b2": {"file_offset": hex(TRIGCONS_SITE_B), "cont": hex(TRIGCONS_CONT_B),
                         "replaced_bytes": data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4].hex(),
                         "after": bl(TRIGCONS_SITE_B, pad_d).hex()},
            "fallthrough_f": {"file_offset": hex(INTA2_SITE_F), "cont": hex(INTA2_CONT_F),
                              "replaced_bytes": data[INTA2_SITE_F:INTA2_SITE_F + 4].hex(),
                              "after": bl(INTA2_SITE_F, pad_f).hex()},
            "loop_head_stock": {"file_offset": hex(INTA_SITE_L),
                                "bytes": data[INTA_SITE_L:INTA_SITE_L + 4].hex(),
                                "unchanged": out[INTA_SITE_L:INTA_SITE_L + 4] ==
                                             data[INTA_SITE_L:INTA_SITE_L + 4]},
        },
        "preserved": {
            "original_gic_write": {"file_offset": "0x8702c",
                                   "bytes_identical": out[0x8702C:0x87030] == data[0x8702C:0x87030]},
            "itet_block": {"file_offset": "0x87030..0x87035",
                           "bytes_identical": out[0x87030:0x87036] == data[0x87030:0x87036]},
            "announce_loop_head": {"file_offset": "0x86f78..0x86f7e",
                                   "bytes_identical": out[0x86F78:0x86F7E] == data[0x86F78:0x86F7E]},
            "announce_exit_continuation": {"file_offset": "0x86f82..",
                                            "bytes_identical": out[INTA2_CONT_F:0x86F92] ==
                                                               data[INTA2_CONT_F:0x86F92]},
        },
        variant: {
            "site_n": hex(INTA2_SITE_N), "cont_n": hex(TRIGNAT_CONT_A),
            "site_b2": hex(TRIGCONS_SITE_B), "cont_b2": hex(TRIGCONS_CONT_B),
            "site_f": hex(INTA2_SITE_F), "cont_f": hex(INTA2_CONT_F),
            "site_f_replaced": TRIGNAT_DRAIN_POP.hex(),
            "site_l": hex(INTA_SITE_L), "site_l_stock": INTA_LOOP_PAIR.hex(),
            "take_reads": [hex(x) for x in INTA2_TAKE_READS] + ["CPSR"],
            "f_cells": [hex(c) for c in fc], "n_cells": [hex(c) for c in nc],
            "send_pad_len": len(code_s), "fallthrough_pad_len": len(code_f),
        },
    }
    return out, manifest


def make_inta2(data: bytes, barmap: bytes, refs: set[int]):
    """take2.md sections 2/3: trigcons/inta's thunk + bring-up + post pads, Pad A's entry widened
    with the N_* take reads, the inta Pad B2 + drain companion kept, Pad L dropped (0x86F78 stock)
    and the NEW Site F pad at 0x86F7E; the F cells on all_zero_pages[13], the N cells on
    all_zero_pages[14] (take2.md section 3)."""
    return _make_inta_like(data, barmap, refs, select_cells_inta2, "inta2", NOTE_INTA2_N,
                           NOTE_INTA2_CELLS)


def make_inta3(data: bytes, barmap: bytes, refs: set[int]):
    """witness2.md FLAW 2 fix: inta2 byte-for-byte EXCEPT the six N cell addresses, which move
    from page 14 (runtime 0x157000 - which did NOT retain the inta2 run's deposits while pages
    9-13 did) to page 10 (0x150000), the pair verified retained across the last two runs' barmap
    reads.  The N cells land at 0x150058..0x150080 - the next free 8-byte slots after the page-10
    cells the trignat Pad A already uses (A_S4..A_S8/A_P2/B_D0..B_D3/B_P3 end at 0x150050).  Every
    pad program is byte-identical to inta2's; Site F keeps its page-13 cells (0x155000)."""
    return _make_inta_like(data, barmap, refs, select_cells_inta3, "inta3", NOTE_INTA3_N,
                           NOTE_INTA3_CELLS)


# ---- take1: the IRQ-VECTOR CANARY + the two CPSR milestones + the giccpu.md cell set
# (build/tmp/inta-spec/fwprobe.md sections 2-5, plus giccpu.md sections 4/5).
#
# The instrument is inta3's (thunk / bring-up / Pad A(N) at 0x86f5a / Pad B2 at 0x86f74 / the drain
# companion / Site F at 0x86f7e; Pad L dropped) PLUS the three fwprobe sites and their pads:
#   * V_SITE file 0x82efc - the firmware ISR's first instruction `push.w {r0,r1,r4,r5,r6,r7,r8,sl,fp,
#     lr}` (stock 2de9f34d), reached only through the ARM IRQ stub's `blx 0xC2EFC` (build_refs is
#     Thumb-only, so the site has no static Thumb reference - the canary is the dynamic proof).  A
#     `b.w` (NOT `bl`: the pushed lr is the epilogue's return) to the NEW vec pad, which re-emits
#     the stock push.w, arms V_MAGIC (0xa4a4a4a4 - a CPSR is never 0, so a zero V_PSR can only mean
#     the pad did not run), stores the entry CPSR in V_PSR (I=1, M[4:0]=0x13 expected), increments
#     the persistent ISR-entry counter V_CNT and branches to 0x82f00 (the IAR read at 0x82f04 has
#     no branch before it, so V_CNT counts IAR reads).
#   * M1_SITE file 0x82f4a - `blx r5` + `cpsid i` (stock a84772b6; the site is 2-mod-4, legal for a
#     Thumb-2 BL), replaced by `bl m1`; the pad saves r0-r3, stores the CPSR of the ISR's live-IRQ
#     window (0x82f46 `cpsie i`) in M1_PSR, restores r0-r3, re-emits `blx r5` + `cpsid i` and
#     branches to 0x82f4e.  The pad runs only when the stock `cbz r5,0x82f4c` at 0x82f48 is not
#     taken (a non-null handler; id 0x4c holds 0x00040295).
#   * M2_SITE file 0x8270a - the release `0x826e0` guard `mrs r2, apsr` (stock eff30082), replaced
#     by `bl m2`; the pad saves r0/r1, stores the CPSR the guard sees in M2_PSR (I=1 = the `bmi` at
#     0x82710 skips the release body; I=0 = the body runs), restores r0/r1, re-emits `mrs r2, apsr`
#     byte-exact and branches to 0x8270e.
#   No pad sets flags (push/pop/movw/movt/str/ldr/adds/mrs only) and none returns through lr (all
#   end in `b.w`), so the `bl`s' lr clobber is inert - the enclosing frames restore pc from the
#   stack (fwprobe.md sections 4/7).
#
# PLUS the giccpu.md cell set, sampled on the drain chain at the announce wait's own `movw
# r3,#0xcece` (file 0x86f74, the pre-exit instant): C_GRP0 (CA 0x40160114, canonical GICC_RPR /
# giccpu.md's IGRPEN0 prediction), C_GRP1 (CA 0x40160118, canonical GICC_HPPIR - the same word the
# tool already samples), C_GRP2 (CA 0x4016011c, canonical GICC_ABPR / the legacy IGRPEN1
# candidate), F_BPR (CA 0x40160108, canonical GICC_BPR - the image's only writer, file 0x8305a) and
# the C_SNT sentinel.  The acknowledging aliased IAR (CA 0x40160120, GICC_AIAR) is deliberately NOT
# read: giccpu.md sec.4 names the four-word candidate block 0x40160114/18/1c/20, but reading 0x20
# would acknowledge, and the take must be the CPU's, not the pad's.  F_CTLR / F_PMR / C_PSR are the
# existing B_D6 / B_D7 / B_D5 cells (giccpu.md's reuse instruction), aliased in the manifest.
# The chain is pad_d (B2) -> pad_m (drain companion, program byte-identical to inta3's) -> the NEW
# giccpu pad -> the loop head 0x86f78, so the added reads land at the SAME pre-exit instant.
#
# ALL new cells sit on PAGE 10 (runtime 0x150000), the retention-verified band (witness2.md FLAW 2);
# giccpu.md's page-15 claim (0x158000) was a barmap-baseline all-zero check, never a retention
# test.  The V/M cells keep fwprobe.md's exact addresses 0x1500a4..0x1500b4 (the first free slots
# above the inta3 N cells, which end at 0x150080); the five giccpu cells take the next free
# contiguous words 0x1500b8..0x1500c8.  NEVER writes 0x400392f0 / 0x40039af0; NEVER reads the IAR
# 0x4016010c or 0x10161000 (the gate word 0x4000010c is a DIFFERENT address); every added GIC read
# is non-acknowledging.
TAKE1_V_MAGIC = 0x1500A4
TAKE1_V_PSR = 0x1500A8
TAKE1_V_CNT = 0x1500AC
TAKE1_M1_PSR = 0x1500B0
TAKE1_M2_PSR = 0x1500B4
TAKE1_C_GRP0 = 0x1500B8
TAKE1_C_GRP1 = 0x1500BC
TAKE1_C_GRP2 = 0x1500C0
TAKE1_F_BPR = 0x1500C4
TAKE1_C_SNT = 0x1500C8
TAKE1_V_CELLS = (TAKE1_V_MAGIC, TAKE1_V_PSR, TAKE1_V_CNT, TAKE1_M1_PSR, TAKE1_M2_PSR)
TAKE1_CP_CELLS = (TAKE1_C_GRP0, TAKE1_C_GRP1, TAKE1_C_GRP2, TAKE1_F_BPR, TAKE1_C_SNT)
TAKE1_V_NAMES = ("V_MAGIC", "V_PSR", "V_CNT", "M1_PSR", "M2_PSR")
TAKE1_CP_NAMES = ("C_GRP0", "C_GRP1", "C_GRP2", "F_BPR", "C_SNT")
TAKE1_V_SITE = 0x82EFC                         # the ISR entry `push.w` (runtime 0xC2EFC)
TAKE1_M1_SITE = 0x82F4A                        # `blx r5` + `cpsid i` (runtime 0xC2F4A)
TAKE1_M2_SITE = 0x8270A                        # the release guard `mrs r2, apsr` (runtime 0xC270A)
TAKE1_V_CONT = 0x82F00                         # the ISR body continues at the IAR read
TAKE1_M1_CONT = 0x82F4E                        # the EoI store follows
TAKE1_M2_CONT = 0x8270E                        # the guard's `lsls r3,r2,#0x18` follows
TAKE1_V_SITE_STOCK = bytes.fromhex("2de9f34d")     # push.w {r0,r1,r4,r5,r6,r7,r8,sl,fp,lr}
TAKE1_M1_SITE_STOCK = bytes.fromhex("a84772b6")    # blx r5 ; cpsid i
TAKE1_M2_SITE_STOCK = bytes.fromhex("eff30082")    # mrs r2, apsr
TAKE1_BLX_R5 = bytes.fromhex("a847")               # the re-emitted `blx r5` (T1)
TAKE1_CPSID_I = bytes.fromhex("72b6")              # the re-emitted `cpsid i`
TAKE1_PRINTABLE = 0xA4A4A4A4                   # the V_MAGIC canary word
TAKE1_GICC_RPR = 0x40160114                    # giccpu.md's C_GRP0 (canonical GICC_RPR)
TAKE1_GICC_HPPIR = GICC_HPPIR                  # giccpu.md's C_GRP1 (canonical GICC_HPPIR, 0x40160118)
TAKE1_GICC_ABPR = 0x4016011C                   # giccpu.md's C_GRP2 (canonical GICC_ABPR)
TAKE1_GICC_BPR = 0x40160108                    # giccpu.md's F_BPR (canonical GICC_BPR)
TAKE1_GICC_READS = (TAKE1_GICC_RPR, TAKE1_GICC_HPPIR, TAKE1_GICC_ABPR, TAKE1_GICC_BPR)
TAKE1_NEVER_READ = "0x40160120 (GICC_AIAR, the aliased acknowledging IAR) - never read"
TAKE1_NEW_CELLS = len(TAKE1_V_CELLS) + len(TAKE1_CP_CELLS)

NOTE_TAKE1_V = (
    "fwprobe.md sections 2-4: V_SITE (file 0x82efc, the ISR's stock `push.w {r0,r1,r4,r5,r6,r7,r8,"
    "sl,fp,lr}`) is replaced by a `b.w` to the vec pad, which re-emits the stock push.w, arms "
    "V_MAGIC (0x1500a4 <= 0xa4a4a4a4), stores the ISR-entry CPSR in V_PSR (0x1500a8; expect I=1, "
    "M[4:0]=0x13, T=1), increments the persistent ISR-entry counter V_CNT (0x1500ac) and branches "
    "to 0x82f00.  M1_SITE (file 0x82f4a, `blx r5` + `cpsid i`) is replaced by `bl m1`, whose pad "
    "stores the live-IRQ-window CPSR (0x82f46 `cpsie i`) in M1_PSR (0x1500b0; expect I=0).  "
    "M2_SITE (file 0x8270a, the release 0x826e0 guard `mrs r2, apsr`) is replaced by `bl m2`, whose "
    "pad stores the guard's CPSR in M2_PSR (0x1500b4; I=1 = the bmi at 0x82710 skips the release "
    "body, I=0 = the body runs)."
)
NOTE_TAKE1_CP = (
    "giccpu.md sections 4/5: the added drain-chain pad reads C_GRP0 (CA 0x40160114), C_GRP1 (CA "
    "0x40160118 = the canonical GICC_HPPIR the tool already samples), C_GRP2 (CA 0x4016011c) and "
    "F_BPR (CA 0x40160108) into 0x1500b8..0x1500c4 and arms the C_SNT sentinel at 0x1500c8, then "
    "returns to the announce loop head 0x86f78.  The acknowledging aliased IAR (0x40160120) is NOT "
    "read.  F_CTLR (0x153010 = B_D6), F_PMR (0x153018 = B_D7) and C_PSR (0x153008 = B_D5) are the "
    "existing drain-companion cells (aliases, not new reads)."
)
NOTE_TAKE1_CELLS = (
    "the ten NEW cells all sit on PAGE 10 (runtime 0x150000, the retention-VERIFIED band: witness2.md "
    "FLAW 2 showed page 14 did not retain while pages 9-13 did; giccpu.md's 0x158000 was only a "
    "barmap-baseline zero check).  The V/M cells keep fwprobe.md's exact addresses "
    "0x1500a4..0x1500b4 (the first free slots above inta3's N cells, which end at 0x150080); the "
    "five giccpu cells take the next free contiguous words 0x1500b8..0x1500c8.  All ten are "
    "0x00000000 at BOTH the BAR0 and the ACP-alias offsets in barmap_ep0_bar0.bin, 4-byte aligned "
    "and distinct from every earlier cell."
)
NOTE_TAKE1_CHAIN = (
    "Pad B2's tail branches to the inta3 drain companion (its program byte-identical to inta3's), "
    "whose tail now branches to the NEW giccpu pad instead of straight to the loop head; the "
    "giccpu pad's tail returns to 0x86f78.  Every pad is a straight-line trampoline ending in "
    "`b.w`, so the chain adds no lr dependency."
)


def pad_vec_take1(pad: int, v_cells: list[int], cont: int) -> bytes:
    """fwprobe.md section 4's `vec` pad: re-emit the stock push.w, arm V_MAGIC, store the entry
    CPSR in V_PSR (V_MAGIC+4), increment the persistent V_CNT and branch to 0x82f00."""
    v_magic, v_psr, v_cnt = v_cells[0], v_cells[1], v_cells[2]
    if v_psr != v_magic + 4:
        raise PatchError("take1 vec pad expects V_PSR = V_MAGIC + 4 (the `str r0,[r1,#4]` form)")
    body = b"".join([
        TAKE1_V_SITE_STOCK,
        movw(0, TAKE1_PRINTABLE & 0xFFFF), movt(0, TAKE1_PRINTABLE >> 16),
        movw(1, v_magic & 0xFFFF), movt(1, v_magic >> 16),
        str_imm(0, 1, 0),
        mrs_apsr(0),
        str_imm(0, 1, 4),
        movw(2, v_cnt & 0xFFFF), movt(2, v_cnt >> 16),
        ldr_imm(3, 2, 0), adds_imm(3, 3, 1), str_imm(3, 2, 0),
    ])
    return body + b_w(pad + len(body), cont)


def pad_m1_take1(pad: int, m1_cell: int, cont: int) -> bytes:
    """fwprobe.md section 4's `m1` pad: save r0-r3, store the live-IRQ-window CPSR in M1_PSR,
    restore r0-r3, re-emit `blx r5` + `cpsid i` and branch to 0x82f4e."""
    body = b"".join([
        push([0, 1, 2, 3]),
        mrs_apsr(0),
        movw(1, m1_cell & 0xFFFF), movt(1, m1_cell >> 16),
        str_imm(0, 1, 0),
        pop([0, 1, 2, 3]),
        TAKE1_BLX_R5,
        TAKE1_CPSID_I,
    ])
    return body + b_w(pad + len(body), cont)


def pad_m2_take1(pad: int, m2_cell: int, cont: int) -> bytes:
    """fwprobe.md section 4's `m2` pad: save r0/r1, store the release guard's CPSR in M2_PSR,
    restore r0/r1, re-emit `mrs r2, apsr` byte-exact and branch to 0x8270e."""
    body = b"".join([
        push([0, 1]),
        mrs_apsr(0),
        movw(1, m2_cell & 0xFFFF), movt(1, m2_cell >> 16),
        str_imm(0, 1, 0),
        pop([0, 1]),
        TAKE1_M2_SITE_STOCK,
    ])
    return body + b_w(pad + len(body), cont)


def pad_giccpu_take1(pad: int, cp_cells: list[int], next_pad: int) -> bytes:
    """giccpu.md sections 4/5's cell set on its OWN pad (chained after the inta3 drain companion so
    that pad's program stays byte-identical): C_GRP0/C_GRP1/C_GRP2/F_BPR (CA 0x40160114/0x40160118/
    0x4016011c/0x40160108, all non-acknowledging) plus the C_SNT sentinel, then `next_pad` (the
    announce loop head 0x86f78).  r0-r5 are saved/restored."""
    body = b"".join([
        push(PAD_SAVE),
        gic_read_store_block(TAKE1_GICC_READS[0], cp_cells[0]),
        gic_read_store_block(TAKE1_GICC_READS[1], cp_cells[1]),
        gic_read_store_block(TAKE1_GICC_READS[2], cp_cells[2]),
        gic_read_store_block(TAKE1_GICC_READS[3], cp_cells[3]),
        _store_imm_block(INTA_SENTINEL, cp_cells[4]),
        pop(PAD_SAVE),
    ])
    return body + b_w(pad + len(body), next_pad)


def verify_disasm_take1(data: bytes, pads: dict[str, int], s1: int, s2: int,
                        gic_cells: list[int], e_cells: list[int], a_cells: list[int],
                        b_cells: list[int], b2_cells: list[int], f_cells: list[int],
                        v_cells: list[int], cp_cells: list[int]) -> dict:
    """Byte-equality of the eleven take1 pads against their reconstructions PLUS the block
    structure: inta3's five pads, the vec/m1/m2 pads' re-emitted stock instructions and tails, the
    giccpu pad's read order and tail, the nine site bytes and the forbidden-CA absence."""
    if len(a_cells) != INTA2_A_NCELLS:
        raise PatchError(f"take1 expected {INTA2_A_NCELLS} A cells, got {len(a_cells)}")
    if len(b_cells) != TRIGNAT_B_NCELLS:
        raise PatchError(f"take1 expected {TRIGNAT_B_NCELLS} B cells, got {len(b_cells)}")
    if len(b2_cells) != INTA_B2_NCELLS:
        raise PatchError(f"take1 expected {INTA_B2_NCELLS} B2 cells, got {len(b2_cells)}")
    if len(f_cells) != INTA2_F_NCELLS:
        raise PatchError(f"take1 expected {INTA2_F_NCELLS} F cells, got {len(f_cells)}")
    if len(v_cells) != len(TAKE1_V_CELLS):
        raise PatchError(f"take1 expected {len(TAKE1_V_CELLS)} V/M cells, got {len(v_cells)}")
    if len(cp_cells) != len(TAKE1_CP_CELLS):
        raise PatchError(f"take1 expected {len(TAKE1_CP_CELLS)} giccpu cells, got {len(cp_cells)}")
    every = ([s1, s2] + gic_cells + e_cells + a_cells + b_cells + b2_cells + f_cells + v_cells
             + cp_cells)
    if len(set(every)) != len(every):
        raise PatchError("take1 cells are not all distinct")

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def dis(off: int, size: int) -> list[str]:
        return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(data[off:off + size], off)]

    code = {
        "thunk": pad_thunk(pads["thunk"], s1, gic_cells, apsr_cell=e_cells[3], req_cell=e_cells[2]),
        "bringup": pad_bringup(pads["bringup"], s2, gic_cells),
        "send_n": pad_send_inta2(pads["send"], a_cells),
        "post": pad_post(pads["post"], e_cells),
        "drain_b2": pad_drain_inta(pads["drain"], b_cells, pads["drain_extra"]),
        "drain_extra": pad_drain_extra_inta(pads["drain_extra"], b2_cells, next_pad=pads["giccpu"]),
        "giccpu": pad_giccpu_take1(pads["giccpu"], cp_cells, TRIGCONS_CONT_B),
        "fallthrough_f": pad_fallthrough_inta2(pads["fallthrough"], f_cells),
        "vec": pad_vec_take1(pads["vec"], v_cells, TAKE1_V_CONT),
        "m1": pad_m1_take1(pads["m1"], v_cells[3], TAKE1_M1_CONT),
        "m2": pad_m2_take1(pads["m2"], v_cells[4], TAKE1_M2_CONT),
    }
    pad_of = {"send_n": "send", "drain_b2": "drain", "fallthrough_f": "fallthrough"}
    for name, c in code.items():
        off = pads[pad_of.get(name, name)]
        if data[off:off + len(c)] != c:
            raise PatchError(f"the take1 {name} pad at {off:#x} is not the intended bytes")

    # inta3's structural invariants (unchanged programs, moved tail targets only)
    if write_ca_block(TRIGNAT_RING_CA, TRIGNAT_RING_VAL) not in code["send_n"]:
        raise PatchError("the take1 Pad A(N) lost the H2D ring")
    if movw(3, 0xcece) not in code["drain_b2"]:
        raise PatchError("take1 Pad B2 must re-emit `movw r3,#0xcece`")
    if b_w(pads["drain"] + len(code["drain_b2"]) - 4, pads["drain_extra"]) != code["drain_b2"][-4:]:
        raise PatchError("take1 Pad B2 does not branch to the drain companion")
    if _store_cpsr_block(f_cells[4]) not in code["fallthrough_f"]:
        raise PatchError("take1 Site F is missing the F_PSR CPSR read")
    if code["fallthrough_f"].count(TRIGNAT_DRAIN_POP) != 1:
        raise PatchError("take1 Site F must re-emit the replaced pop.w exactly once")
    if b_w(pads["fallthrough"] + len(code["fallthrough_f"]) - 4, INTA2_CONT_F) != \
            code["fallthrough_f"][-4:]:
        raise PatchError("take1 Site F has no `b.w` to 0x86f82")

    # the drain companion: same program as inta3's, tail now on the giccpu pad
    for ca, cell, nm in ((GICD_ISACTIVER2, b2_cells[0], "B_D4"), (INTA_GICC_CTLR, b2_cells[2], "B_D6"),
                         (INTA_GICC_PMR, b2_cells[3], "B_D7")):
        if gic_read_store_block(ca, cell) not in code["drain_extra"]:
            raise PatchError(f"the take1 drain companion is missing {nm}: CA {ca:#x} -> {cell:#x}")
    if _store_cpsr_block(b2_cells[1]) not in code["drain_extra"]:
        raise PatchError("the take1 drain companion is missing the B_D5 CPSR read")
    if _store_imm_block(TRIGNAT_SENTINEL, b2_cells[4]) not in code["drain_extra"]:
        raise PatchError("the take1 drain companion is missing the B_P4 sentinel")
    if code["drain_extra"].count(push(PAD_SAVE)) != 1 or code["drain_extra"].count(pop(PAD_SAVE)) != 1:
        raise PatchError("the take1 drain companion must save/restore r0-r5 exactly once")
    if b_w(pads["drain_extra"] + len(code["drain_extra"]) - 4, pads["giccpu"]) != code["drain_extra"][-4:]:
        raise PatchError("the take1 drain companion does not branch to the giccpu pad")

    # the giccpu pad: push, C_GRP0..F_BPR (in CA order), C_SNT, pop, tail to 0x86f78
    order_cp = [code["giccpu"].index(gic_read_store_block(ca, cell))
                for ca, cell in zip(TAKE1_GICC_READS, cp_cells[:4])]
    order_cp += [code["giccpu"].index(_store_imm_block(INTA_SENTINEL, cp_cells[4])),
                 code["giccpu"].index(pop(PAD_SAVE))]
    if order_cp != sorted(order_cp) or len(set(order_cp)) != len(order_cp):
        raise PatchError("the take1 giccpu order is not C_GRP0 -> C_GRP1 -> C_GRP2 -> F_BPR -> C_SNT -> pop")
    if code["giccpu"].count(push(PAD_SAVE)) != 1:
        raise PatchError("the take1 giccpu pad must save r0-r5 exactly once")
    if b_w(pads["giccpu"] + len(code["giccpu"]) - 4, TRIGCONS_CONT_B) != code["giccpu"][-4:]:
        raise PatchError("the take1 giccpu pad does not return to the loop head 0x86f78")

    # the vec pad: the re-emitted push.w, the canary/CPSR/counter block and the tail
    vd = dis(pads["vec"], len(code["vec"]))
    if not vd or not vd[0].startswith("push.w "):
        raise PatchError(f"the take1 vec pad does not re-emit the stock push.w: {vd!r}")
    for want in ("movw r0, #0xa4a4", "movt r0, #0xa4a4", "str r0, [r1]", "str r0, [r1, #4]",
                 "ldr r3, [r2]", "adds r3, r3, #1", "str r3, [r2]"):
        if want not in vd:
            raise PatchError(f"the take1 vec pad lost `{want}`: {vd!r}")
    if not any(s.startswith("mrs r0, ") for s in vd):
        raise PatchError(f"the take1 vec pad lost the V_PSR `mrs r0,<PSR>`: {vd!r}")
    if b_w(pads["vec"] + len(code["vec"]) - 4, TAKE1_V_CONT) != code["vec"][-4:]:
        raise PatchError("the take1 vec pad has no `b.w` to 0x82f00")

    # the m1 pad: push r0-r3, M1_PSR, pop, the re-emitted `blx r5` + `cpsid i`, the tail
    md1 = dis(pads["m1"], len(code["m1"]))
    for want in ("push {r0, r1, r2, r3}", "pop {r0, r1, r2, r3}", "blx r5", "cpsid i"):
        if want not in md1:
            raise PatchError(f"the take1 m1 pad lost `{want}`: {md1!r}")
    if not any(s.startswith("mrs r0, ") for s in md1):
        raise PatchError(f"the take1 m1 pad lost the M1_PSR `mrs r0,<PSR>`: {md1!r}")
    if b_w(pads["m1"] + len(code["m1"]) - 4, TAKE1_M1_CONT) != code["m1"][-4:]:
        raise PatchError("the take1 m1 pad has no `b.w` to 0x82f4e")

    # the m2 pad: push r0/r1, M2_PSR, pop, the byte-exact re-emitted guard, the tail
    md2 = dis(pads["m2"], len(code["m2"]))
    for want in ("push {r0, r1}", "pop {r0, r1}"):
        if want not in md2:
            raise PatchError(f"the take1 m2 pad lost `{want}`: {md2!r}")
    if not any(s.startswith("mrs r0, ") for s in md2) or not any(s.startswith("mrs r2, ") for s in md2):
        raise PatchError(f"the take1 m2 pad lost an `mrs` (M2_PSR / the re-emitted guard): {md2!r}")
    if TAKE1_M2_SITE_STOCK not in code["m2"]:
        raise PatchError("the take1 m2 pad does not re-emit `mrs r2, apsr` byte-exact")
    if b_w(pads["m2"] + len(code["m2"]) - 4, TAKE1_M2_CONT) != code["m2"][-4:]:
        raise PatchError("the take1 m2 pad has no `b.w` to 0x8270e")

    # the nine sites
    for site, pad, want_bytes in ((SITE_THUNK, pads["thunk"], bl(SITE_THUNK, pads["thunk"])),
                                  (BRINGUP_SITE, pads["bringup"], bl(BRINGUP_SITE, pads["bringup"])),
                                  (SEND_SITE, pads["send"], bl(SEND_SITE, pads["send"])),
                                  (POST_SITE, pads["post"], bl(POST_SITE, pads["post"])),
                                  (TRIGCONS_SITE_B, pads["drain"],
                                   bl(TRIGCONS_SITE_B, pads["drain"])),
                                  (INTA2_SITE_F, pads["fallthrough"],
                                   bl(INTA2_SITE_F, pads["fallthrough"])),
                                  (TAKE1_V_SITE, pads["vec"], b_w(TAKE1_V_SITE, pads["vec"])),
                                  (TAKE1_M1_SITE, pads["m1"], bl(TAKE1_M1_SITE, pads["m1"])),
                                  (TAKE1_M2_SITE, pads["m2"], bl(TAKE1_M2_SITE, pads["m2"]))):
        if data[site:site + 4] != want_bytes:
            raise PatchError(f"take1 site {site:#x} is not the intended branch: "
                             f"{data[site:site + 4].hex()} != {want_bytes.hex()}")

    for name, c in code.items():
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0),
                    gic_read_store_block(0x40160120, 0)):
            if bad in c:
                raise PatchError(f"the take1 {name} pad addresses a forbidden CA: {bad.hex()}")

    return {
        "thunk_pad": dis(pads["thunk"], len(code["thunk"])),
        "bringup_pad": dis(pads["bringup"], len(code["bringup"])),
        "send_pad": dis(pads["send"], len(code["send_n"])),
        "post_pad": dis(pads["post"], len(code["post"])),
        "drain_pad": dis(pads["drain"], len(code["drain_b2"])),
        "drain_extra_pad": dis(pads["drain_extra"], len(code["drain_extra"])),
        "giccpu_pad": dis(pads["giccpu"], len(code["giccpu"])),
        "fallthrough_pad": dis(pads["fallthrough"], len(code["fallthrough_f"])),
        "vec_pad": dis(pads["vec"], len(code["vec"])),
        "m1_pad": dis(pads["m1"], len(code["m1"])),
        "m2_pad": dis(pads["m2"], len(code["m2"])),
        "take1": {
            "v_site": hex(TAKE1_V_SITE), "v_cont": hex(TAKE1_V_CONT),
            "m1_site": hex(TAKE1_M1_SITE), "m1_cont": hex(TAKE1_M1_CONT),
            "m2_site": hex(TAKE1_M2_SITE), "m2_cont": hex(TAKE1_M2_CONT),
            "v_site_stock": TAKE1_V_SITE_STOCK.hex(),
            "m1_site_stock": TAKE1_M1_SITE_STOCK.hex(),
            "m2_site_stock": TAKE1_M2_SITE_STOCK.hex(),
            "v_cells": [hex(c) for c in v_cells], "cp_cells": [hex(c) for c in cp_cells],
            "printable": hex(TAKE1_PRINTABLE),
            "gicc_reads": [hex(x) for x in TAKE1_GICC_READS],
            "aliases": {"F_CTLR": hex(INTA_GICC_CTLR), "F_PMR": hex(INTA_GICC_PMR),
                        "C_PSR": "B_D5"},
        },
    }


def make_take1(data: bytes, barmap: bytes, refs: set[int]):
    """fwprobe.md sections 2-5 + giccpu.md sections 4/5: inta3's instrument (thunk / bring-up /
    Pad A(N) / Pad B2 / drain companion / Site F; Pad L dropped) PLUS the three fwprobe sites and
    pads (V_SITE 0x82efc -> the vec canary pad, M1_SITE 0x82f4a -> the m1 CPSR pad, M2_SITE 0x8270a
    -> the m2 release-guard pad) PLUS the giccpu cell pad chained after the drain companion.  All
    ten new cells sit on page 10 (the retention-verified band)."""
    cells, sel = select_cells_inta3(barmap)
    s1, s2 = cells[0], cells[1]
    gc = cells[2:2 + GICV_NCELLS]
    ec = cells[2 + GICV_NCELLS:2 + GICV_NCELLS + GICP_NCELLS]
    off_a = 2 + GICV_NCELLS + GICP_NCELLS
    ac = cells[off_a:off_a + TRIGNAT_A_NCELLS]
    off_b = off_a + TRIGNAT_A_NCELLS
    bc = cells[off_b:off_b + TRIGNAT_B_NCELLS]
    off_b2 = off_b + TRIGNAT_B_NCELLS
    b2c = cells[off_b2:off_b2 + INTA_B2_NCELLS]
    off_f = off_b2 + INTA_B2_NCELLS
    fc = cells[off_f:off_f + INTA2_F_NCELLS]
    off_n = off_f + INTA2_F_NCELLS
    nc = cells[off_n:off_n + INTA2_N_NCELLS]
    ac2 = ac + nc
    vc = list(TAKE1_V_CELLS)
    cpc = list(TAKE1_CP_CELLS)
    if (len(ec) != GICP_NCELLS or len(ac) != TRIGNAT_A_NCELLS or len(bc) != TRIGNAT_B_NCELLS
            or len(b2c) != INTA_B2_NCELLS or len(fc) != INTA2_F_NCELLS
            or len(nc) != INTA2_N_NCELLS or len(ac2) != INTA2_A_NCELLS):
        raise PatchError("internal error: take1 inta3 cells were not selected")
    ok = _cell_ok(barmap)
    for a in vc + cpc:
        if not ok(a):
            raise PatchError(f"take1 new cell {a:#x} is not a zero cell at both views")
    if set(vc + cpc) & set(cells):
        raise PatchError("take1 new cells collide with an inta3 cell")
    if vc != [TAKE1_V_MAGIC, TAKE1_V_PSR, TAKE1_V_CNT, TAKE1_M1_PSR, TAKE1_M2_PSR]:
        raise PatchError("internal error: take1 V/M cell order changed")

    need_s = len(pad_send_inta2(0, ac2))
    need_i = len(pad_thunk(0, s1, gc, apsr_cell=ec[3], req_cell=ec[2]))
    need_b = len(pad_bringup(0, s2, gc))
    need_p = len(pad_post(0, ec))
    need_d = len(pad_drain_inta(0, bc, 0))
    need_m = len(pad_drain_extra_inta(0, b2c))
    need_f = len(pad_fallthrough_inta2(0, fc))
    need_g = len(pad_giccpu_take1(0, cpc, 0))
    need_v = len(pad_vec_take1(0, vc, 0))
    need_1 = len(pad_m1_take1(0, vc[3], 0))
    need_2 = len(pad_m2_take1(0, vc[4], 0))
    alloc = alloc_pads(data, refs, [("send", need_s), ("thunk", need_i), ("bringup", need_b),
                                    ("post", need_p), ("drain", need_d),
                                    ("drain_extra", need_m), ("fallthrough", need_f),
                                    ("giccpu", need_g), ("vec", need_v), ("m1", need_1),
                                    ("m2", need_2)])
    pads = {name: off for name, (off, _run) in alloc.items()}

    code_i = pad_thunk(pads["thunk"], s1, gc, apsr_cell=ec[3], req_cell=ec[2])
    code_b = pad_bringup(pads["bringup"], s2, gc)
    code_s = pad_send_inta2(pads["send"], ac2)
    code_p = pad_post(pads["post"], ec)
    code_d = pad_drain_inta(pads["drain"], bc, pads["drain_extra"])
    code_m = pad_drain_extra_inta(pads["drain_extra"], b2c, next_pad=pads["giccpu"])
    code_g = pad_giccpu_take1(pads["giccpu"], cpc, TRIGCONS_CONT_B)
    code_f = pad_fallthrough_inta2(pads["fallthrough"], fc)
    code_v = pad_vec_take1(pads["vec"], vc, TAKE1_V_CONT)
    code_1 = pad_m1_take1(pads["m1"], vc[3], TAKE1_M1_CONT)
    code_2 = pad_m2_take1(pads["m2"], vc[4], TAKE1_M2_CONT)

    out = bytearray(patch_sites(data, pads["thunk"], pads["bringup"], pads["send"], pads["post"],
                                pads["drain"], drain_site=TRIGCONS_SITE_B, loop_pad=pads["fallthrough"],
                                loop_site=INTA2_SITE_F))
    out[TAKE1_V_SITE:TAKE1_V_SITE + 4] = b_w(TAKE1_V_SITE, pads["vec"])
    out[TAKE1_M1_SITE:TAKE1_M1_SITE + 4] = bl(TAKE1_M1_SITE, pads["m1"])
    out[TAKE1_M2_SITE:TAKE1_M2_SITE + 4] = bl(TAKE1_M2_SITE, pads["m2"])
    for off, code in ((pads["thunk"], code_i), (pads["bringup"], code_b), (pads["send"], code_s),
                      (pads["post"], code_p), (pads["drain"], code_d),
                      (pads["drain_extra"], code_m), (pads["giccpu"], code_g),
                      (pads["fallthrough"], code_f), (pads["vec"], code_v), (pads["m1"], code_1),
                      (pads["m2"], code_2)):
        out[off:off + len(code)] = code
    out = bytes(out)

    if len(out) != len(data):
        raise PatchError("internal error: the take1 patch changed the image size")
    if data[TAKE1_V_SITE:TAKE1_V_SITE + 4] != TAKE1_V_SITE_STOCK:
        raise PatchError("the take1 V_SITE stock bytes are not the ISR entry `push.w` (2de9f34d)")
    if data[TAKE1_M1_SITE:TAKE1_M1_SITE + 4] != TAKE1_M1_SITE_STOCK:
        raise PatchError("the take1 M1_SITE stock bytes are not `blx r5`+`cpsid i` (a84772b6)")
    if data[TAKE1_M2_SITE:TAKE1_M2_SITE + 4] != TAKE1_M2_SITE_STOCK:
        raise PatchError("the take1 M2_SITE stock bytes are not `mrs r2, apsr` (eff30082)")
    if data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4] != bytes.fromhex("1a600122"):
        raise PatchError("the take1 Pad A site is not `str r2,[r3]`+`movs r2,#1`")
    if data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4] != TRIGCONS_SITE_B_BYTES:
        raise PatchError("the take1 Pad B2 site is not `movw r3,#0xcece` (4cf6ce63)")
    if data[INTA2_SITE_F:INTA2_SITE_F + 4] != TRIGNAT_DRAIN_POP:
        raise PatchError("the take1 Site F site is not the stock `pop.w {r3..sb,lr}` (bde8f843)")
    if data[INTA_SITE_L:INTA_SITE_L + 4] != INTA_LOOP_PAIR:
        raise PatchError("the take1 dropped Pad-L site is not the stock `ldr r2,[r1]`+`cmp`")
    # continuations and the untouched bodies
    for a, b_, nm in ((TAKE1_V_CONT, 0x82F4A, "the ISR body up to M1_SITE"),
                      (TAKE1_M1_CONT, 0x82F78, "the ISR body after M1_SITE"),
                      (0x826E0, TAKE1_M2_SITE, "the release body up to the guard"),
                      (TAKE1_M2_CONT, 0x82730, "the release spin after the guard"),
                      (INTA2_CONT_F, 0x86F92, "the announce-exit continuation"),
                      (INTA_SITE_L, 0x86F7E, "the announce loop head")):
        if out[a:b_] != data[a:b_]:
            raise PatchError(f"take1 altered {nm} ({a:#x}..{b_:#x})")
    if out[0x8702C:0x87030] != data[0x8702C:0x87030]:
        raise PatchError("internal error: the original ISENABLER store at file 0x8702c was altered")
    if out[0x87030:0x87036] != data[0x87030:0x87036]:
        raise PatchError("internal error: the itet block 0x87030..0x87035 was altered")
    for name, code in (("thunk", code_i), ("bringup", code_b), ("send", code_s), ("post", code_p),
                       ("drain", code_d), ("drain_extra", code_m), ("giccpu", code_g),
                       ("fallthrough", code_f), ("vec", code_v), ("m1", code_1), ("m2", code_2)):
        for bad in (write_ca_block(0x400392F0, 1), gic_read_store_block(0x4016010C, 0),
                    write_ca_block(0x10161000, 0), gic_read_store_block(0x10161000, 0),
                    gic_read_store_block(0x40160120, 0)):
            if bad in code:
                raise PatchError(f"internal error: the take1 {name} pad addresses a forbidden CA")

    check_original_gic_write(out)
    verify_disasm_take1(out, pads, s1, s2, gc, ec, ac2, bc, b2c, fc, vc, cpc)

    records = {"S1": cell_record(barmap, s1), "S2": cell_record(barmap, s2)}
    for i, a in enumerate(gc):
        records[f"C{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ec):
        records[f"E{i}"] = cell_record(barmap, a)
    for i, a in enumerate(ac[:4]):
        records[f"A_S{i}"] = cell_record(barmap, a)
    records["A_P1"] = cell_record(barmap, ac[4])
    records["A_E0"] = cell_record(barmap, ac[5])
    records["A_E1"] = cell_record(barmap, ac[6])
    for i, a in enumerate(ac[7:12]):
        records[f"A_S{4 + i}"] = cell_record(barmap, a)
    records["A_P2"] = cell_record(barmap, ac[12])
    for i, a in enumerate(bc[:4]):
        records[f"B_D{i}"] = cell_record(barmap, a)
    records["B_P3"] = cell_record(barmap, bc[4])
    for i, a in enumerate(b2c[:4]):
        records[f"B_D{4 + i}"] = cell_record(barmap, a)
    records["B_P4"] = cell_record(barmap, b2c[4])
    for nm, a in zip(INTA2_F_NAMES, fc):
        records[nm] = cell_record(barmap, a)
    for nm, a in zip(INTA2_N_NAMES, nc):
        records[nm] = cell_record(barmap, a)
    for nm, a in zip(TAKE1_V_NAMES, vc):
        records[nm] = cell_record(barmap, a)
    for nm, a in zip(TAKE1_CP_NAMES, cpc):
        records[nm] = cell_record(barmap, a)
    aliases = {"C_PSR": "B_D5", "F_CTLR": "B_D6", "F_PMR": "B_D7"}

    manifest = {
        "variant": "take1",
        "spec": "build/tmp/inta-spec/fwprobe.md sections 2-5 + giccpu.md sections 4/5",
        "selection": sel,
        "cells": records,
        "aliases": aliases,
        "take1": {
            "v_site": hex(TAKE1_V_SITE), "v_cont": hex(TAKE1_V_CONT),
            "m1_site": hex(TAKE1_M1_SITE), "m1_cont": hex(TAKE1_M1_CONT),
            "m2_site": hex(TAKE1_M2_SITE), "m2_cont": hex(TAKE1_M2_CONT),
            "v_site_stock": TAKE1_V_SITE_STOCK.hex(),
            "m1_site_stock": TAKE1_M1_SITE_STOCK.hex(),
            "m2_site_stock": TAKE1_M2_SITE_STOCK.hex(),
            "v_cells": [hex(c) for c in vc], "cp_cells": [hex(c) for c in cpc],
            "new_cells": [hex(c) for c in vc + cpc],
            "printable": hex(TAKE1_PRINTABLE),
            "gicc_reads": [hex(x) for x in TAKE1_GICC_READS],
            "aliases": aliases,
        },
        "take1_cells_note": NOTE_TAKE1_CELLS,
        "gic_map": {
            "GICD_base": "0x40161000", "GICC_base": "0x40160100",
            "ISACTIVER2": hex(GICD_ISACTIVER2), "ISPENDR2": hex(GICD_ISPENDR2),
            "HPPIR": hex(GICC_HPPIR),
            "take1_reads": [hex(x) for x in TAKE1_GICC_READS],
            "take1_reads_note": "C_GRP0 0x40160114 (RPR) / C_GRP1 0x40160118 (HPPIR, the word "
                                 "the tool already samples) / C_GRP2 0x4016011c (ABPR) / "
                                 "F_BPR 0x40160108 (BPR)",
            "never_read": "0x4016010c (GICC IAR - acknowledging), " + TAKE1_NEVER_READ +
                          ", and 0x10161000 (RC misc, panics)",
            "never_written": "0x400392f0 (ctrl-rb intr-clear, W1C) and the masked glue word 0x21",
            "ring": {"ca": hex(TRIGNAT_RING_CA), "value": hex(TRIGNAT_RING_VAL),
                     "note": NOTE_TRIGCONS_A},
            "gate": {"ca": "0x4000010c", "wait_value": "0x0000cece",
                     "site_b2": hex(TRIGCONS_SITE_B), "cont_b2": hex(TRIGCONS_CONT_B),
                     "note": NOTE_TRIGCONS_B},
            "site_f_note": NOTE_INTA2_F,
            "site_n_note": NOTE_INTA3_N,
            "pad_l_dropped_note": NOTE_INTA2_DROP,
            "vec_note": NOTE_TAKE1_V,
            "giccpu_note": NOTE_TAKE1_CP,
            "chain_note": NOTE_TAKE1_CHAIN,
        },
        "classification": {
            "instrument": "inta3's POST-EXIT take sample (Pad B2 + Site F + Pad A(N)) PLUS the "
                           "IRQ-vector canary (V_SITE -> the vec pad: V_MAGIC/V_PSR/V_CNT) and the "
                           "two CPSR milestones (M1_PSR in the cpsie-i window, M2_PSR at the "
                           "release guard) PLUS the giccpu cell pad chained after the drain "
                           "companion.",
            "ROW_1": "fwprobe.md section 6.1: V_MAGIC == 0xa4a4a4a4 and V_CNT >= 1 (V_PSR I=1, "
                      "M[4:0]=0x13, T=1) => VECTOR ENTERED - the core took the IRQ and the IAR "
                      "was read: precondition 3 OBSERVED; then M1_PSR I=0 proves the service window "
                      "ran live, and the inta3 cells must agree in the same epoch (F_ACT bit 12 "
                      "SET / N_ACT bit 12 SET, out[0] 8->0).",
            "ROW_2": "fwprobe.md section 6.2: V_MAGIC == 0 and V_CNT == 0 => VECTOR NEVER ENTERED "
                      "- the CPU never took the IRQ this boot, whatever ISPENDR2/ISACTIVER2 say "
                      "(matches exp/20261005-200139: the gate is the core take, not the wire).",
            "ROW_3": "fwprobe.md section 6.3/6.5: V_CNT >= 1 with M1_PSR == 0 => the ISR ran but "
                      "never reached 0x82f4a (a null fn_array entry or a spurious id); M2_PSR with "
                      "I=1 => the release guard ran with the mask still set, the `bmi` at 0x82710 "
                      "skips the body and the release never issues.",
            "ROW_4": "giccpu.md section 2: F_CTLR (B_D6)/F_PMR (B_D7)/C_GRP0/C_GRP1/C_GRP2/F_BPR "
                      "close the two unmeasured config candidates - a CPU-interface group enable "
                      "reading 0 (a 1/0 pair among the candidate words) or a CTLR bit2/bit3 quirk; "
                      "the armed-consistent survivor is the mask (C_PSR = B_D5).",
            "bounds": "one-shot latched samples, not a trace: V_CNT is a plain ldr/adds/str in a "
                      "pad that runs with IRQs live, so a nested IRQ can race it (undercount <= 1 "
                      "per nested entry) - V_MAGIC is the binary proof.  M1_PSR exists only when "
                      "fn_array[id] != 0.  M2_PSR/M1_PSR are latched by the LAST visit.",
        },
        "padding": {
            "thunk": {"file_offset": hex(pads["thunk"]), "code_length": len(code_i),
                      "code_hex": code_i.hex()},
            "bringup": {"file_offset": hex(pads["bringup"]), "code_length": len(code_b),
                        "code_hex": code_b.hex()},
            "send_n": {"file_offset": hex(pads["send"]), "code_length": len(code_s),
                       "code_hex": code_s.hex()},
            "post": {"file_offset": hex(pads["post"]), "code_length": len(code_p),
                     "code_hex": code_p.hex()},
            "drain_b2": {"file_offset": hex(pads["drain"]), "code_length": len(code_d),
                         "code_hex": code_d.hex()},
            "drain_extra": {"file_offset": hex(pads["drain_extra"]), "code_length": len(code_m),
                            "code_hex": code_m.hex()},
            "giccpu": {"file_offset": hex(pads["giccpu"]), "code_length": len(code_g),
                       "code_hex": code_g.hex()},
            "fallthrough_f": {"file_offset": hex(pads["fallthrough"]), "code_length": len(code_f),
                              "code_hex": code_f.hex()},
            "vec": {"file_offset": hex(pads["vec"]), "code_length": len(code_v),
                    "code_hex": code_v.hex()},
            "m1": {"file_offset": hex(pads["m1"]), "code_length": len(code_1),
                   "code_hex": code_1.hex()},
            "m2": {"file_offset": hex(pads["m2"]), "code_length": len(code_2),
                   "code_hex": code_2.hex()},
        },
        "sites": {
            "send_n": {"file_offset": hex(TRIGNAT_SITE_A), "cont": hex(TRIGNAT_CONT_A),
                       "replaced_bytes": data[TRIGNAT_SITE_A:TRIGNAT_SITE_A + 4].hex(),
                       "after": bl(TRIGNAT_SITE_A, pads["send"]).hex()},
            "drain_b2": {"file_offset": hex(TRIGCONS_SITE_B), "cont": hex(TRIGCONS_CONT_B),
                         "replaced_bytes": data[TRIGCONS_SITE_B:TRIGCONS_SITE_B + 4].hex(),
                         "after": bl(TRIGCONS_SITE_B, pads["drain"]).hex()},
            "fallthrough_f": {"file_offset": hex(INTA2_SITE_F), "cont": hex(INTA2_CONT_F),
                              "replaced_bytes": data[INTA2_SITE_F:INTA2_SITE_F + 4].hex(),
                              "after": bl(INTA2_SITE_F, pads["fallthrough"]).hex()},
            "vec": {"file_offset": hex(TAKE1_V_SITE), "cont": hex(TAKE1_V_CONT),
                    "replaced_bytes": data[TAKE1_V_SITE:TAKE1_V_SITE + 4].hex(),
                    "after": b_w(TAKE1_V_SITE, pads["vec"]).hex()},
            "m1": {"file_offset": hex(TAKE1_M1_SITE), "cont": hex(TAKE1_M1_CONT),
                   "replaced_bytes": data[TAKE1_M1_SITE:TAKE1_M1_SITE + 4].hex(),
                   "after": bl(TAKE1_M1_SITE, pads["m1"]).hex()},
            "m2": {"file_offset": hex(TAKE1_M2_SITE), "cont": hex(TAKE1_M2_CONT),
                   "replaced_bytes": data[TAKE1_M2_SITE:TAKE1_M2_SITE + 4].hex(),
                   "after": bl(TAKE1_M2_SITE, pads["m2"]).hex()},
            "loop_head_stock": {"file_offset": hex(INTA_SITE_L),
                                "bytes": data[INTA_SITE_L:INTA_SITE_L + 4].hex(),
                                "unchanged": out[INTA_SITE_L:INTA_SITE_L + 4] ==
                                             data[INTA_SITE_L:INTA_SITE_L + 4]},
        },
        "preserved": {
            "original_gic_write": {"file_offset": "0x8702c",
                                   "bytes_identical": out[0x8702C:0x87030] == data[0x8702C:0x87030]},
            "itet_block": {"file_offset": "0x87030..0x87035",
                           "bytes_identical": out[0x87030:0x87036] == data[0x87030:0x87036]},
            "announce_loop_head": {"file_offset": "0x86f78..0x86f7e",
                                   "bytes_identical": out[0x86F78:0x86F7E] == data[0x86F78:0x86F7E]},
            "announce_exit_continuation": {"file_offset": "0x86f82..",
                                            "bytes_identical": out[INTA2_CONT_F:0x86F92] ==
                                                               data[INTA2_CONT_F:0x86F92]},
            "isr_body_around_m1": {"file_offset": "0x82f00..0x82f4a / 0x82f4e..0x82f78",
                                   "bytes_identical": out[TAKE1_V_CONT:TAKE1_M1_SITE] ==
                                                      data[TAKE1_V_CONT:TAKE1_M1_SITE] and
                                                      out[TAKE1_M1_CONT:0x82F78] ==
                                                      data[TAKE1_M1_CONT:0x82F78]},
            "release_body_around_m2": {"file_offset": "0x826e0..0x8270a / 0x8270e..0x82730",
                                       "bytes_identical": out[0x826E0:TAKE1_M2_SITE] ==
                                                          data[0x826E0:TAKE1_M2_SITE] and
                                                          out[TAKE1_M2_CONT:0x82730] ==
                                                          data[TAKE1_M2_CONT:0x82730]},
        },
    }
    return out, manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="patch_fw_scratch.py", description=__doc__.splitlines()[0])
    ap.add_argument("--fw", default="build/tmp/FIRMWARE.bin", help="input blob (READ-ONLY)")
    ap.add_argument("--barmap", default="opensource/build/register-dumps/barmap_ep0_bar0.bin",
                    help="normal-op BAR0 baseline used for S1/S2 selection")
    ap.add_argument("--out", help="output blob (never the input)")
    ap.add_argument("--variant", choices=("probe", "scratch", "gicview", "gicsend", "gicpost",
                                          "gicmask", "gicking", "gicunmask", "trigring", "trignat",
                                          "trigcons", "inta", "inta2", "inta3", "take1"),
                    help="probe: one non-executed byte flip; scratch: the two instrumentation "
                         "stores; gicview: scratch + six device-side GIC reads into cells C0..C5; "
                         "gicsend: gicview + a third trampoline at the firmware's out[1] message "
                         "post (file 0x86F5A) reading ISPENDR2/HPPIR/ISACTIVER2 into cells D0..D2; "
                         "gicpost: gicsend + a fourth trampoline at file 0x87036 (the first "
                         "boundary after the conditional enable store) reading ISENABLER2 back "
                         "POST-write into E0 and ISPENDR2 into E1, with the enable-gate pad's "
                         "APSR deposit in E3; gicmask: gicpost + the send pad's eight "
                         "delivery-configuration reads (GICC_CTLR/PMR, GICD ITARGETSR/IPRIORITYR/"
                         "ICFGR for id 0x4c, glue mask/raw/masked status) into F0..F7 with the "
                         "per-page sentinels F8/F9 and the F9 handshake request; gicking: gicmask "
                         "+ the H2D RING (CA 0x400392d4 <= 0x1 at the send pad, immediately before "
                         "the GIC sample) and the polarity discriminator (the pad drives the glue "
                         "mask 0x2e8: 0x21 masked across the ring, then 0x20 open) plus the "
                         "GICD_IGROUPR word-2 read for id 0x4c (CA 0x40161088) into G0..G2 with the "
                         "G3 sentinel; gicunmask: gicpost's S/C/E instrument with the gicking pads as "
                         "the base, but the send pad rings the H2D doorbell with the glue mask OPEN "
                         "(0x20) and samples ISPENDR2 (H0, the decisive read), HPPIR (H1), "
                         "ISACTIVER2 (H2), glue raw (H3) and glue status (H4) immediately, re-reads "
                         "ISPENDR2 at the next post (H5) and arms one sentinel per used page (H6/H7); "
                         "trigring: trigger.md section 3's candidate - the send pad performs the ring "
                         "the firmware never issues at the firmware's OWN natural post (0x86F5A, "
                         "between the reproduced out[1] `*0x40039014 = 4` and the natural D2H notify), "
                         "writing CA 0x400392d4 <= 0x1 (the value of `str rX,[r3 + 0x2c0]`, r3 = "
                         "0x40039014) with the glue mask OPEN (0x20) across the ring, and takes the "
                         "PRE-ring (T0..T3) AND POST-ring (T4..T7) samples of ISPENDR2 word 2 / "
                         "HPPIR / glue raw / glue status in the SAME visit plus one sentinel per "
                         "page (T8/T9); trignat: trigger2.md section 3 - the firmware's OWN natural "
                         "post (0x86F5A) performs the host's two stores (reproduce out[1] <= 4, then "
                         "the H2D submission out[0] <= 8 and the ring CA 0x400392d4 <= 0x1) with the "
                         "glue mask OPEN, takes the pre-ring A_S0..A_S2 / post-ring A_S3..A_S8 reads "
                         "plus the next-visit entry reads A_E0/A_E1 and the page sentinels A_P1/A_P2, "
                         "and a second pad at the announce routine's exit (0x86F7E, after the 0xcece "
                         "handshake wait) reads the device-dispatcher consumption witnesses B_D0 "
                         "(out[0] = 0) / B_D2 (ISPENDR2 bit 12 clear) into the B cells with B_P3; "
                         "trigcons: padb.md section 3 option (a) - trignat with Pad B MOVED to the "
                         "announce wait's own `movw r3,#0xcece` at file 0x86F74 (before the loop head "
                         "0x86F78, which never exits), taking the same B_D0..B_D3 + B_P3 cells, then "
                         "re-emitting `movw r3,#0xcece` and branching to 0x86F78; Pad A, the other "
                         "pads and every cell are identical to trignat's, and the old announce-exit "
                         "site 0x86F7E stays stock; inta: devcpu.md sections 4.1/4.2 - trigcons plus "
                         "the extended drain pad (B_D4 ISACTIVER2 / B_D5 CPSR / B_D6 GICC_CTLR / "
                         "B_D7 GICC_PMR + the B_P4 sentinel, all on all_zero_pages[11]) and the "
                         "delayed Pad L at the 0xcece spin head 0x86F78 (L1_*/L2_*/L_CNT/L_SNT on "
                         "all_zero_pages[12]), which re-emits the loop pair and returns to 0x86F7C"
                         "; inta2: take2.md sections 2/3 - the POST-EXIT take sample: inta's thunk/"
                         "bring-up/post pads, Pad A's entry widened with the N_ACT/N_ISP/N_HPP/N_OU0/"
                         "N_PSR/N_SNT take reads at the firmware's own out[1] post (0x86F5A), the inta "
                         "Pad B2 + drain companion kept (the pre-exit baseline), the NEW Site F pad at "
                         "the 0xcece gate's own fall-through 0x86F7E (pop.w -> the take reads -> b.w "
                         "0x86F82) and Pad L DROPPED (0x86F78 back to the stock loop head); the F_* "
                         "cells sit on all_zero_pages[13] and the N_* cells on all_zero_pages[14]; "
                         "inta3: witness2.md FLAW 2 fix - inta2 byte-for-byte EXCEPT the six N cell "
                         "addresses, which move from page 14 (0x157000 did not retain the inta2 run's "
                         "deposits) to page 10 (0x150000, the retention-verified band) at "
                         "0x150058..0x150080, the first free 8-byte slots after the trignat Pad A/B "
                         "cells (B_P3 = 0x150050); Site F keeps page 13, every pad program "
                         "unchanged; take1: fwprobe.md sections 2-5 + giccpu.md sections 4/5 - "
                         "inta3 plus the IRQ-vector canary (V_SITE file 0x82efc -> the vec pad: "
                         "V_MAGIC/V_PSR/V_CNT), the two CPSR milestones (M1_SITE 0x82f4a -> M1_PSR "
                         "in the cpsie-i window, M2_SITE 0x8270a -> M2_PSR at the release 0x826e0 "
                         "guard) and the giccpu cell pad (C_GRP0/C_GRP1/C_GRP2/F_BPR + C_SNT, CAs "
                         "0x40160114/18/1c/08) chained after the drain companion; all ten new cells "
                         "on page 10; the acknowledging AIAR 0x40160120 is never read")
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
                         else make_gicpost(data, barmap, refs) if args.variant == "gicpost"
                         else make_gicmask(data, barmap, refs) if args.variant == "gicmask"
                         else make_gicking(data, barmap, refs) if args.variant == "gicking"
                         else make_trigring(data, barmap, refs) if args.variant == "trigring"
                         else make_trignat(data, barmap, refs) if args.variant == "trignat"
                         else make_trigcons(data, barmap, refs) if args.variant == "trigcons"
                         else make_inta(data, barmap, refs) if args.variant == "inta"
                         else make_inta2(data, barmap, refs) if args.variant == "inta2"
                         else make_inta3(data, barmap, refs) if args.variant == "inta3"
                         else make_take1(data, barmap, refs) if args.variant == "take1"
                         else make_gicunmask(data, barmap, refs))
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
