import struct, re
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/rootfs-2.4.15/squashfs-root/usr/bin/crypt'
raw = open(p,'rb').read()
e = ELFFile(open(p,'rb'))
print('sections:', [(s.name, hex(s['sh_addr']), hex(s['sh_offset']), hex(s['sh_size'])) for s in e.iter_sections()])
for tgt in (0x1226c, 0x1227c, 0x12284, 0x12298, 0x123fa):
    pat = struct.pack('<I', tgt)
    off = 0; found = []
    while True:
        off = raw.find(pat, off)
        if off < 0: break
        found.append(hex(off)); off += 1
    print('word', hex(tgt), 'at file offsets', found)
    pat2 = struct.pack('<I', tgt + 1)
    off = 0; found2 = []
    while True:
        off = raw.find(pat2, off)
        if off < 0: break
        found2.append(hex(off)); off += 1
    if found2: print('   (+1 thumb) at', found2)
text = e.get_section_by_name('.text'); tb = text.data(); tva = text['sh_addr']
for mode, name in ((CS_MODE_ARM, 'ARM'), (CS_MODE_THUMB, 'THUMB')):
    md = Cs(CS_ARCH_ARM, mode)
    insns = list(md.disasm(tb, tva))
    print(f'--- {name} first 12 ---')
    for ins in insns[:12]: print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}')
    regs = {}; hits = []
    for idx, ins in enumerate(insns):
        mm = ins.mnemonic
        if mm in ('movw','movw.w','movw.n') and '#' in ins.op_str:
            rr, imm = ins.op_str.split(', #'); regs[rr.strip()] = (int(imm,16), idx)
        elif mm in ('movt','movt.w') and '#' in ins.op_str:
            rr, imm = ins.op_str.split(', #'); hi = int(imm,16)
            if rr.strip() in regs:
                lo, widx = regs.pop(rr.strip()); v = (hi<<16)|lo
                if 0x12200 <= v <= 0x12450: hits.append((v, widx, idx))
    print(f'{name} resolved rodata refs:', [(hex(v), hex(tva+wi)) for v, wi, ti in hits][:20])
