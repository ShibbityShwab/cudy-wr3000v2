import itertools, hashlib
from Crypto.Cipher import AES
data = open(r'C:/Users/ShibbityShwab/router-openwrt/pages/backup.bin','rb').read()
print('cipher bytes:', len(data), data[:8].hex())
srcs = ['WR3000','WR3000V2','WR3000 2.0','WR3000V2.0','WR3000-2.0','Cudy','cudy','Cudy-WR3000','V2.0','2.0','admin','WR3000@aes#hex','Cudy@aes#hex','0123456789abcdef','30313233343536373839616263646566','000000000000','0000000000000000','d40dab641c73','D40DAB641C73','d4:0d:ab:64:1c:73','4D50318802','CudyRouter','cudyrouter','Cudy@2023','cudygogo2018@606','WR3000V2@aes#hex','wr3000@aes#hex']
keys = set()
for s in srcs:
    b = s.encode()
    keys.add(b[:16].ljust(16, b'\x00')); keys.add(b[:16].ljust(16, b' ')); keys.add(b[:16].ljust(16, b'0'))
    keys.add(b[:32].ljust(32, b'\x00')); keys.add(b[:24].ljust(24, b'\x00'))
    keys.add(b[:32].ljust(32, b'@'))
    if len(b) >= 32: keys.add(bytes.fromhex(s[:32]))
    if len(b) >= 16 and all(c in '0123456789abcdefABCDEF' for c in s[:16]): keys.add(bytes.fromhex(s[:16]))
ivs = [b'\x00'*16, b' '*16, b'0'*16, b'0123456789abcdef', bytes.fromhex('30313233343536373839616263646566')]
def check(blob, iv, key):
    try:
        if len(key) not in (16, 24, 32): return None
        c = AES.new(key, AES.MODE_CBC, iv)
        pt = c.decrypt(blob[:32])
        if pt[:3] == b'\x1f\x8b\x08': return pt[:16]
    except Exception: pass
    return None
hits = []
for off in (0, 2):
    blob = data[off:]
    for k in list(keys):
        for iv in ivs + [k[:16], k[:16].ljust(16, b'\x00')]:
            r = check(blob, iv if len(iv)==16 else iv[:16], k)
            if r: hits.append((off, k.hex(), iv.hex(), r.hex()))
print('candidate keys tried:', len(keys))
print('HITS:', hits if hits else 'none')
