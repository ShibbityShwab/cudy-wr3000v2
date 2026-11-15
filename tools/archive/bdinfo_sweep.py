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
print('size', len(data), 'head', data[:32].hex())
nz = [i for i in range(0, len(data), 4096) if any(data[i:i+4096])]
print('nonzero 4K pages (first 20):', [hex(x) for x in nz[:20]], '... total', len(nz))
import re
for off in (0, 8, 16, 32, 64, 128, 256, 512, 1024, 4096, 65536, 131072):
    if off + 4096 > len(data): continue
    try:
        pt = DES.new(KEY, DES.MODE_CBC, b'\x00'*8).decrypt(data[off:off+4096])
    except Exception as e:
        continue
    txt = pt.decode('latin1')
    printable = sum(1 for c in txt if 32 <= ord(c) < 127 or c in '\r\n\t') / len(txt)
    hit = ('mac' in txt) or ('secret' in txt) or ('deviceid' in txt)
    head = ''.join(c if (32 <= ord(c) < 127) else '.' for c in txt[:64])
    if printable > 0.8 or hit:
        print('OFF', off, 'printable', round(printable,2), 'hit', hit, ':', head)
