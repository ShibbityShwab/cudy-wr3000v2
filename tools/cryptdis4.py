import struct, re
from elftools.elf.elffile import ELFFile
from capstone import *
p = r'C:/Users/ShibbityShwab/router-openwrt/rootfs-2.4.15/squashfs-root/usr/bin/crypt'
e = ELFFile(open(p,'rb'))
for secname in ('.rodata', '.data'):
    s = e.get_section_by_name(secname)
    if not s: continue
    d = s.data(); base = s['sh_addr']
    print(f'==== {secname} ({len(d)} bytes) ====')
    for i in range(0, len(d), 16):
        chunk = d[i:i+16]
        hexs = ' '.join(f'{b:02x}' for b in chunk)
        asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f'{base+i:06x}  {hexs:<48}  {asc}')
text = e.get_section_by_name('.text'); tb = text.data(); tva = text['sh_addr']
ro = e.get_section_by_name('.rodata'); rlo = ro['sh_addr']; rhi = rlo + ro['sh_size']
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
insns = list(md.disasm(tb, tva))
def poolval(ins):
    m = re.match(r'\w+, \[pc, #(0x[0-9a-fA-F]+)\]', ins.op_str)
    if not m: return None
    pool = (ins.address + 8 + int(m.group(1),16))
    off = pool - tva
    if 0 <= off <= len(tb)-4:
        return struct.unpack_from('<I', tb, off)[0]
    return None
res = []
for idx, ins in enumerate(insns):
    if ins.mnemonic.startswith('adr'):
        m = re.match(r'\w+, #(0x[0-9a-fA-F]+)', ins.op_str)
        if m:
            v = int(m.group(1),16)
            if rlo <= v < rhi: res.append((idx, 'adr', v))
    elif ins.mnemonic.startswith('ldr') and 'pc' in ins.op_str:
        v = poolval(ins)
        if v is not None and rlo <= v < rhi: res.append((idx, 'ldr-pc', v))
print('==== refs into rodata ====')
for idx, kind, v in res:
    print(f'{tva+insns[idx].address-tva:x} {kind} -> {hex(v)} at insn {idx}')
interest = [0x1226c, 0x1227c, 0x12284, 0x12298, 0x123fa]
for idx, kind, v in res:
    if any(abs(v - t) < 0x60 for t in interest):
        lo = max(0, idx-30); hi = min(len(insns), idx+50)
        print(f'==== window {hex(v)} ====')
        for ins in insns[lo:hi]: print(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}')
