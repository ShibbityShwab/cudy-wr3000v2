import sys, multiprocessing as mp
from passlib.hash import md5_crypt, sha512_crypt
T1 = '$1$fXMCMnxb$6CrSBrlB9vPMJzXbXMa/q1'
T2 = '$6$BdGjxNsn5jLeZfuN$QzZLGST9MbUxajYZr980U3p3L0vMuHlnZOuXynBbmGs2m6JZhVNUD67GVC30E69/zwjC.ATYApkb1z1hsjJo9.'
def check(w):
    if md5_crypt.verify(w, T1): return 'root-md5:' + w
    if sha512_crypt.verify(w, T2): return 'system-sha512:' + w
    return None
def main(paths):
    words = set()
    base = ['admin','password','123456','12345678','123456789','12345','root','cudy','Cudy','cudy123','cudy1234','Cudy123','Cudy1234','Cudy@123','Cudy@2018','cudygogo2018','cudygogo2018@606','wr3000','WR3000','cudy3000','Cudy3000','admin123','Admin123','password1','qwerty123','1234567890','cudyadmin','admin@123','cudytech','Cudytech','CudyTech','cudy2018','cudy2020','cudy2021','cudy2022','cudy2023','cudy2024','cudy2025','cudy2026','88888888','66666666','11111111','cudycudy','CudyCudy','WR3000v2','wr3000v2','111111','000000','123123','cudy12345','cudy@2023','cudy@2024','cudy@2025','Cudy@2023','Cudy@2024','Cudy@2025','iloveyou','sunshine','monkey','dragon','abc123','letmein','welcome','master','shadow','superman','whatever','zxcvbnm','asdfghjkl','cudyWR3000','WR3000cudy','Cudy2020','Cudy2021','Cudy2022','Cudy2023','Cudy2024','Cudy2025','0218','2018','cudy0218']
    for w in base: words.add(w)
    for path in paths:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = line.rstrip('\n\r')
                    if w: words.add(w)
        except FileNotFoundError:
            print('missing ' + path)
    words = sorted(words)
    print('[*] candidates: ' + str(len(words)), flush=True)
    with mp.Pool(16) as pool:
        for i, r in enumerate(pool.imap_unordered(check, words, chunksize=200)):
            if r:
                print('[+] FOUND: ' + r, flush=True)
                pool.terminate()
                return
            if i % 20000 == 0 and i: print('...' + str(i), flush=True)
    print('[-] not found', flush=True)
if __name__ == '__main__':
    main(sys.argv[1:])
