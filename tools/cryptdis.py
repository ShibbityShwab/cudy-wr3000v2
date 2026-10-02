import struct
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/router-openwrt/rootfs-2.4.15/squashfs-root/usr/bin/crypt'
f = open(p, 'rb'); e = ELFFile(f)
print('machine', e.header.e_machine, 'type', e.header.e_type, 'entry', hex(e.header.e_entry))
text = e.get_section_by_name('.text'); ro = e.get_section_by_name('.rodata')
tb = text.data(); tva = text['sh_addr']; rb = ro.data(); rva = ro['sh_addr']
def findstr(s):
    i = rb.find(s.encode())
    return (rva + i) if i >= 0 else None
names = ['%s@aes#hex', '%s@%s', '/etc/rom_version', 'build: %s', 'Unable to get build time']
addrs = {n: findstr(n) for n in names}
print('string addrs:', {k: (hex(v) if v else None) for k, v in addrs.items()})
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
seen = set()
for n, a in addrs.items():
    if not a: continue
    pat = struct.pack('<I', a); i = 0
    while True:
        i = tb.find(pat, i)
        if i < 0: break
        base = i & ~3
        if base not in seen:
            seen.add(base)
            print(f'==== ref to {n} at {hex(tva+base)} ====')
            start = max(0, base - 120); end = base + 120
            for ins in md.disasm(tb[start:end], tva + start):
                mark = ' <--' if ins.address == tva + base else ''
                print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}{mark}')
        i += 1
