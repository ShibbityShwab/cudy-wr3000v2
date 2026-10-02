from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/router-openwrt/rootfs-2.4.15/squashfs-root/usr/lib/libhi_upgrade.so'
e = ELFFile(open(p,'rb'))
syms = []
for secname in ('.dynsym','.symtab'):
    s = e.get_section_by_name(secname)
    if not s: continue
    for sym in s.iter_symbols():
        if 'boot_write' in sym.name or 'boot' in sym.name.lower():
            syms.append((sym.name, sym['st_value'], sym['st_size']))
print('boot syms:', [(n, hex(v), sz) for n, v, sz in syms][:20])
text = e.get_section_by_name('.text')
for name, val, size in syms:
    if name == '__upgrade_boot_write' and size:
        code = text.data()[val - text['sh_addr']: val - text['sh_addr'] + size]
        md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        print('== disasm', name, hex(val), '==')
        for ins in md.disasm(code, val):
            print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}')
