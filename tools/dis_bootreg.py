import struct
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/rootfs-2.4.15/squashfs-root/usr/lib/libhi_upgrade.so'
e = ELFFile(open(p,'rb'))
ro = e.get_section_by_name('.rodata'); text = e.get_section_by_name('.text')
rb_ = ro.data(); rva = ro['sh_addr']; tb = text.data(); tva = text['sh_addr']
def find(s):
    i = rb_.find(s)
    return rva + i if i >= 0 else None
for s in (b'/sys/devices/platform/sysenv/boot_reg', b'__upgrade_boot_write chip_id', b'chipt_id'):
    v = find(s)
    print(s, hex(v) if v else None)
v = find(b'/sys/devices/platform/sysenv/boot_reg')
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
hits = []
for i in range(0, len(tb) - 4, 4):
    w = struct.unpack_from('<I', tb, i)[0]
    if v and abs(w - v) < 8: hits.append((tva + i, w))
print('literal hits:', [(hex(a), hex(w)) for a, w in hits])
for a, w in hits[:2]:
    start = max(0, (a - tva) - 240); end = (a - tva) + 240
    print('== window around', hex(a), '==')
    for ins in md.disasm(tb[start:end], tva + start):
        mark = ' <== pool' if ins.address == a else ''
        print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}{mark}')
