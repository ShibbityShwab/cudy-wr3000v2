# patched/ - stock LuCI bytecode (annotated dumps)

## OVERVIEW
Compiled Lua 5.1 (`LuaQ` header, byte-swapped) lifted out of the device rootfs and kept as annotated dumps. These files are **data to read**, not source to edit or run. They exist to prove what the stock web UI does, mainly where it hands attacker-controlled strings to a shell.

## STRUCTURE
```
patched/
├── system.lua       # controller route table (attack surface map)
├── rpc.lua          # JSON-RPC auth/uci/sys entry points
├── backup.lua       # backup+restore CBI, shells crypt/tar/md5sum
└── servicectl.lua   # servicectl status/restart/initilize
```

## WHERE TO LOOK
| File | Lines | Role |
|------|-------|------|
| `system.lua` | 51 | `luci.controller.system`: the full admin route table (`system/systime`, `system/backup`, `system/terminal`, `system/reboot`, poe helpers) - map of the attack surface |
| `rpc.lua` | 48 | `luci.controller.rpc`: `rpc_auth`/`rpc_uci`/`rpc_sys`/`rpc_sysupgrade`; contains `| crypt -ea` / `| crypt -da` shell pipes and `fork_exec` |
| `backup.lua` | 12 | backup/restore CBI: shells `crypt -d -i %q -o /tmp/backup.tar.gz`, `tar -tzf /tmp/backup.tar.gz >/dev/null`, `md5sum %q` |
| `servicectl.lua` | 7 | `luci.controller.servicectl`: `action_status` / `action_restart` / `action_initilize`; `nixio` + `/bin/sh` exec, `Access-Control-Allow-Origin: *` |

Sibling payload at repo root: `../rpc_inj.json` - a raw JSON-RPC `login` request whose password param is
`x'; echo PWN1 > /www/luci-static/rpc_inj.txt; echo PWN2 > /www/rpc_inj2.txt; echo '`.

Companion disassembler: `../tools/luadump.py` (Lua 5.1 bytecode -> readable ops).

## CONVENTIONS
- Format is Lua 5.1 bytecode dumped verbatim; printable string constants and symbol names are the readable parts. Use `pyenv/Scripts/python.exe ../tools/luadump.py <file> -c` to disassemble.
- Annotations/restored fragments are appended after the bytecode blob; the trailing plain-text region is the added commentary.
- Corresponding stock sources are read-only: same files also exist compiled inside the firmware images (`rootfs-2.4.15/`, `rootfs-2.5.24/`).
- Line counts are small (7-51) because these are dumps, not readable modules; read the string constants, not the byte stream.

## ANTI-PATTERNS
- Never edit, reformat, or "fix" these files - they are forensic evidence; an edit destroys the proof.
- Never treat a string found here as the live source without re-checking the matching firmware image.
- The `system.lua` route table is bytecode-derived; do not assume a route is reachable just because it is listed (`system/terminal` returns 403 as shipped).
- Do not run `luadump.py` output through a formatter or linter - it is a disassembly, not Lua source.
- Do not mix these dumps with the submodule's `opensource/docs/` writeups: the dumps are evidence, the docs are the narrative.
