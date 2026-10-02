import struct, re
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/rootfs-2.4.15/squashfs-root/usr/lib/libhi_upgrade.so'
e = ELFFile(open(p,'rb'))
ro = e.get_section_by_name('.rodata'); text = e.get_section_by_name('.text')
rva = ro['sh_addr']; rb_ = ro.data(); tb = text.data(); tva = text['sh_addr']
tgt = rva + rb_.find(b'/sys/devices/platform/sysenv/boot_reg')
fmt = rva + rb_.find(b'echo 0x%x > ')
print('targets', hex(tgt), hex(fmt))
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
insns = list(md.disasm(tb, tva))
regs = {}; hits = []
for idx, ins in enumerate(insns):
    if ins.mnemonic == 'movw' and '#' in ins.op_str:
        rr, imm = ins.op_str.split(', #'); regs[rr.strip()] = (int(imm,16), idx)
    elif ins.mnemonic == 'movt' and '#' in ins.op_str:
        rr, imm = ins.op_str.split(', #'); hi = int(imm,16)
        if rr.strip() in regs:
            lo, widx = regs.pop(rr.strip()); v = (hi<<16)|lo
            if v in (tgt, fmt, tgt+1, fmt+1): hits.append((v, widx))
print('movw/movt hits:', [(hex(v), hex(tva+insns[w].address - tva)) for v, w in hits][:6])
for v, w in hits[:3]:
    lo = max(0, w-40); hi = min(len(insns), w+80)
    print('== window', hex(v), '==')
    for ins in insns[lo:hi]:
        print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}')
