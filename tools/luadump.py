#!/usr/bin/env python3
import struct
import sys

OPS = ["MOVE", "LOADK", "LOADBOOL", "LOADNIL", "GETUPVAL", "GETGLOBAL", "GETTABLE", "SETGLOBAL", "SETUPVAL",
       "SETTABLE", "NEWTABLE", "SELF", "ADD", "SUB", "MUL", "DIV", "MOD", "POW", "UNM", "NOT", "LEN", "CONCAT",
       "JMP", "EQ", "LT", "LE", "TEST", "TESTSET", "CALL", "TAILCALL", "RETURN", "FORLOOP", "FORPREP", "TFORLOOP",
       "SETLIST", "CLOSE", "CLOSURE", "VARARG"]

IABC, IABx, IAsBx = 0, 1, 2


class Reader:
    def __init__(self, b):
        self.b = b
        self.o = 0

    def byte(self):
        v = self.b[self.o]
        self.o += 1
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.o)[0]
        self.o += 4
        return v

    def num(self):
        v = struct.unpack_from("<d", self.b, self.o)[0]
        self.o += 8
        return v

    def string(self):
        n = self.u32()
        if n == 0:
            return None
        s = self.b[self.o:self.o + n - 1]
        self.o += n
        return s


def op_get(code):
    op = code & 0x3F
    a = (code >> 6) & 0xFF
    c = (code >> 14) & 0x1FF
    b = (code >> 23) & 0x1FF
    bx = (code >> 14) & 0x3FFFF
    sbx = bx - 131071
    return op, a, b, c, bx, sbx


def repr_const(k):
    if k is None:
        return "nil"
    if isinstance(k, bool):
        return "true" if k else "false"
    if isinstance(k, float):
        return repr(k)
    if isinstance(k, bytes):
        try:
            return '"' + k.decode("utf-8") + '"'
        except Exception:
            return repr(k)
    return repr(k)


def kname(consts, rk):
    i = rk - 256
    if 0 <= i < len(consts):
        return " K" + str(i) + " " + repr_const(consts[i])
    return ""


def parse_function(r, depth, show_code):
    out = []
    src = r.string()
    line = r.u32()
    lastline = r.u32()
    nups = r.byte()
    nparams = r.byte()
    isva = r.byte()
    maxstack = r.byte()
    ncode = r.u32()
    code = [r.u32() for _ in range(ncode)]
    nk = r.u32()
    consts = []
    for _ in range(nk):
        t = r.byte()
        if t == 0:
            consts.append(None)
        elif t == 1:
            consts.append(bool(r.byte()))
        elif t == 3:
            consts.append(r.num())
        elif t == 4:
            consts.append(r.string())
        elif t == 9:
            consts.append(struct.unpack_from("<i", r.b, r.o)[0])
            r.o += 4
        else:
            print("UNKNOWN CONST TYPE " + str(t) + " at file offset " + str(r.o - 1) +
                  " next16=" + r.b[r.o - 1:r.o + 15].hex())
            raise SystemExit(1)
    nprotos = r.u32()
    protos = [parse_function(r, depth + 1, show_code) for _ in range(nprotos)]
    nline = r.u32()
    for _ in range(nline):
        r.u32()
    nloc = r.u32()
    locvars = []
    for _ in range(nloc):
        nm = r.string()
        r.u32()
        r.u32()
        locvars.append(nm)
    nup = r.u32()
    ups = [r.string() for _ in range(nup)]
    out.append("  " * depth + "function @line " + str(line) + "-" + str(lastline) +
               " params=" + str(nparams) + " vararg=" + str(isva) + " stack=" + str(maxstack) +
               " code=" + str(ncode) + " consts=" + str(nk) + " protos=" + str(nprotos) +
               " upvals=" + str([None if u is None else u.decode('utf-8', 'replace') for u in (ups)]))
    for i, k in enumerate(consts):
        out.append("  " * depth + "  K" + str(i) + " = " + repr_const(k))
    if show_code:
        for i, c in enumerate(code):
            op, a, b, c2, bx, sbx = op_get(c)
            name = OPS[op] if op < len(OPS) else "OP" + str(op)
            detail = ""
            if name in ("LOADK", "GETGLOBAL", "SETGLOBAL"):
                detail = " K" + str(bx) + " " + (repr_const(consts[bx]) if bx < len(consts) else "?")
            elif name in ("CLOSURE",):
                detail = " P" + str(bx)
            elif name in ("GETUPVAL", "SETUPVAL"):
                detail = " U" + str(b)
            elif name in ("JMP",):
                detail = " -> " + str(i + 1 + sbx)
            elif name in ("GETTABLE", "SETTABLE", "SELF"):
                detail = kname(consts, c2)
            elif name in ("GETGLOBAL", "SETGLOBAL"):
                detail = " K" + str(bx) + " " + (repr_const(consts[bx]) if bx < len(consts) else "?")
            out.append("  " * depth + "  " + str(i).rjust(4) + ": " + name +
                       " A=" + str(a) + " B=" + str(b) + " C=" + str(c2) + detail)
    for p in protos:
        out.extend(p)
    return out


def main():
    path = sys.argv[1]
    show_code = "-c" in sys.argv
    b = open(path, "rb").read()
    sig = b[:4]
    print("sig", sig, "version", hex(b[4]), "fmt", b[5], "sizes", list(b[6:12]))
    r = Reader(b)
    r.o = 12
    lines = parse_function(r, 0, show_code)
    print("\n".join(lines))
    print("parsed to offset", r.o, "of", len(b), "remainder", len(b) - r.o)


if __name__ == "__main__":
    main()
