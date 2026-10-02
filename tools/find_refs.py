import struct
from elftools.elf.elffile import ELFFile
p = r'C:/Users/ShibbityShwab/router-openwrt/rootfs-2.4.15/squashfs-root/usr/lib/libhi_upgrade.so'
data = open(p,'rb').read()
e = ELFFile(open(p,'rb'))
targets = [0xf610, 0xf2c2, 0xf2ce]
for off in range(0, len(data) - 4, 4):
    w = struct.unpack_from('<I', data, off)[0]
    for t in targets:
        if w == t or w == t+1:
            secname = '?'
            for s in e.iter_sections():
                if s['sh_offset'] <= off < s['sh_offset'] + s['sh_size']:
                    secname = s.name; break
            print('ref to', hex(t), 'at file off', hex(off), 'sect', secname)
