import re
from Crypto.Cipher import DES
def parity(b):
    out = bytearray()
    for x in b:
        x &= 0xFE
        p = bin(x).count('1') & 1
        out.append(x | (1 - p))
    return bytes(out)
def dstk(s):
    if len(s) % 2: s += b'\x00'
    temp = bytearray(8)
    for i, ch in enumerate(s):
        temp[i % 8] ^= (ch << 1) & 0xFF
        if i >= 8: temp[7 - (i % 8)] ^= ch
    cbc = DES.new(b'\x00'*8, DES.MODE_CBC, b'\x00'*8)
    return parity(cbc.encrypt(parity(temp)))
KEY = dstk(b'88T3j05dtFu8=')
data = open(r'C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2/dumps/bdinfo.bin','rb').read()
rx = re.compile(rb'[a-z_]{2,14} = [\x21-\x7e]')
ecb = DES.new(KEY, DES.MODE_ECB)
hits = []
for off in range(0, len(data) - 8, 8):
    pt = ecb.decrypt(data[off:off+8])
    if rx.match(pt): hits.append(off)
print('aligned hits:', [hex(h) for h in hits[:20]], 'total', len(hits))
for h in hits[:3]:
    pt = DES.new(KEY, DES.MODE_CBC, b'\x00'*8).decrypt(data[h:h+4300])
    print('--- at', hex(h), '---')
    print(pt[:300].decode('latin1'))
for off in (4,):
    blob = data[off:]
    pt = DES.new(KEY, DES.MODE_CBC, b'\x00'*8).decrypt(blob[:4200])
    print('off4 head:', ''.join(chr(c) if 32<=c<127 else '.' for c in pt[:120]))
