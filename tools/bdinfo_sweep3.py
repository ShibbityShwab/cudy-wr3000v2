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
data = open(r'C:/Users/ShibbityShwab/router-openwrt/dumps/bdinfo.bin','rb').read()
dec = DES.new(KEY, DES.MODE_ECB).decrypt(data[:(len(data)//8)*8])
for pat in (b'mac =', b'secret', b'deviceid', b'sn =', b' = '):
    idxs = [m.start() for m in re.finditer(re.escape(pat), dec)]
    print(pat, '->', [hex(x) for x in idxs[:8]], 'count', len(idxs))
if b'mac =' in dec:
    i = dec.find(b'mac =')
    print(dec[max(0,i-64):i+400].decode('latin1', 'replace'))
