from Crypto.Cipher import AES
data = open(r'C:/Users/ShibbityShwab/router-openwrt/pages/backup.bin','rb').read()
srcs = ['WR3000','WR3000V2','WR3000 V2.0','WR3000V2.0','WR3000-2.0','WR3000 2.0','Cudy','cudy','CudyWR3000','Cudy-WR3000','WR3000@aes#hex','Cudy@aes#hex','WR3000V2@aes#hex','WR3000 V2.0@aes#hex','secret','secret@aes#hex','board@aes#hex','board@secret','secret@board','HSAN','HSAN@aes#hex','2.4.15','2.4.15-20251030-114751','2.4.15-20251030-114751@aes#hex','114751','20251030','R116','WR3000V2-R116','d40dab641c73','d40dab641c73@aes#hex','000000000000','000000000000@aes#hex','4D50318802','4D50318802@aes#hex','admin','admin@aes#hex','Cudy@123','cudygogo2018@606','cudygogo2018@606@aes#hex','0123456789abcdef','30313233343536373839616263646566']
keys = set()
for s in srcs:
    b = s.encode()
    for pad in (b'\x00', b' ', b'0', b'@'):
        keys.add(b[:16].ljust(16, pad))
        keys.add(b[:24].ljust(24, pad))
        keys.add(b[:32].ljust(32, pad))
    keys.add(b[:16]); keys.add(b[:32])
ivs = [b'\x00'*16, b' '*16, b'0'*16, b'@'*16, b'0123456789abcdef', b'30313233343536373839616263646566']
hits = []
for off in (0, 2, 16, 18):
    blob = data[off:]
    cand_ivs = list(ivs)
    if len(blob) >= 16: cand_ivs.append(blob[:16])
    for k in list(keys):
        if len(k) not in (16, 24, 32): continue
        for iv in cand_ivs:
            if len(iv) != 16: continue
            try:
                pt = AES.new(k, AES.MODE_CBC, iv).decrypt(blob[:32])
            except Exception: continue
            if pt[:3] == b'\x1f\x8b\x08': hits.append((off, k.hex(), iv.hex(), pt.hex()))
print('tried', len(keys), 'keys x', len(ivs)+1, 'ivs x 4 offsets')
print('HITS:', hits if hits else 'none')
