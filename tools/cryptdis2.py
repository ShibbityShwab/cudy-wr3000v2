import re, struct
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/rootfs-2.4.15/squashfs-root/usr/bin/crypt'
f = open(p,'rb'); e = ELFFile(f)
text = e.get_section_by_name('.text'); tb = text.data(); tva = text['sh_addr']
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
insns = list(md.disasm(tb, tva))
print('insn count', len(insns))
targets = {0x1226c:'%s@aes#hex', 0x1227c:'%s@%s', 0x12284:'/etc/rom_version', 0x12298:'Unable', 0x123fa:'build: %s'}
regs = {}
hits = []
for idx, ins in enumerate(insns):
    m = ins.mnemonic
    r = re.match(r'(r\d+|r\d+|ip|sp|lr), #(0x[0-9a-fA-F]+)', ins.op_str)
    if m == 'movw' and '#' in ins.op_str:
        rr, imm = ins.op_str.split(', #'); regs[rr.strip()] = (int(imm,16), idx)
    elif m == 'movt' and '#' in ins.op_str:
        rr, imm = ins.op_str.split(', #'); hi = int(imm,16)
        if rr.strip() in regs:
            lo, widx = regs[rr.strip()]
            v = (hi << 16) | lo
            if v in targets or (0x12200 <= v <= 0x12450):
                hits.append((v, widx, idx))
            del regs[rr.strip()]
print('resolved refs:', [(hex(v), targets.get(v, 'rodata+'), hex(tva+wi), hex(tva+ti)) for v, wi, ti in hits])
done = set()
for v, wi, ti in hits:
    if v in done: continue
    done.add(v)
    lo = max(0, wi-70); hi = min(len(insns), ti+40)
    print(f'==== window for {targets.get(v, hex(v))} ====')
    for ins in insns[lo:hi]:
        tail = ' <-- ref' if ins.address in (tva+wi, tva+ti) else ''
        print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}{tail}')
    print()
