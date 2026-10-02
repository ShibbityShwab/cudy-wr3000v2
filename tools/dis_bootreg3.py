import struct
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/router-openwrt/rootfs-2.4.15/squashfs-root/usr/lib/libhi_upgrade.so'
e = ELFFile(open(p,'rb'))
ro = e.get_section_by_name('.rodata'); rva = ro['sh_addr']; rb_ = ro.data()
print(rb_[0xf2a0-0xf000:0xf330-0xf000])
text = e.get_section_by_name('.text'); tb = text.data(); tva = text['sh_addr']
def scan(mode):
    md = Cs(CS_ARCH_ARM, mode)
    regs = {}; hits = []
    insns = list(md.disasm(tb, tva))
    for idx, ins in enumerate(insns):
        if ins.mnemonic in ('movw','movw.w') and '#' in ins.op_str:
            rr, imm = ins.op_str.split(', #'); regs[rr.strip()] = (int(imm,16), idx)
        elif ins.mnemonic in ('movt','movt.w') and '#' in ins.op_str:
            rr, imm = ins.op_str.split(', #'); hi = int(imm,16)
            if rr.strip() in regs:
                lo, widx = regs.pop(rr.strip()); v = (hi<<16)|lo
                if 0xf000 <= v <= 0xf800: hits.append((v, widx))
    return insns, hits
for mode, tag in ((CS_MODE_ARM, 'ARM'), (CS_MODE_THUMB, 'THUMB')):
    insns, hits = scan(mode)
    print(tag, 'rodata-window refs:', [(hex(v), hex(insns[w].address)) for v, w in hits][:10])
