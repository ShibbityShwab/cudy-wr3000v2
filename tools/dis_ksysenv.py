import struct
from elftools.elf.elffile import ELFFile
from capstone import *
base = r'C:/Users/ShibbityShwab/router-openwrt/rootfs-2.4.15/squashfs-root'
ko = ELFFile(open(base + '/lib/hisilicon/ko/hi_ksysenv.ko','rb'))
syms = []
for secname in ('.symtab',):
    s = ko.get_section_by_name(secname)
    if not s: continue
    for sym in s.iter_symbols():
        if 'boot' in sym.name or 'sysenv' in sym.name:
            syms.append((sym.name, sym['st_value'], sym['st_size']))
print('ko syms:', [(n, hex(v), sz) for n, v, sz in syms][:25])
text = ko.get_section_by_name('.text')
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
for name, val, size in syms:
    if name in ('boot_reg_store','boot_reg_show','boot_done_store','boot_done_show') and size and size < 400:
        code = text.data()[val - text['sh_addr']: val - text['sh_addr'] + size]
        print('== disasm', name, '==')
        for ins in md.disasm(code, val):
            print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}')
