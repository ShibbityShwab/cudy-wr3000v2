# Archive

Historical scratch tools kept for reference. They are not part of the live surface.
Several hardcode `C:/Users/...` paths, and most execute at import instead of under
`__main__`. Do not use them in a current workflow; use the tools in the parent
directory.

| files | what they were |
| --- | --- |
| `bdinfo_sweep*.py` | superseded bdinfo scans; `decrypt_bdinfo.py` is the current tool |
| `cryptbrute*.py` | hash-cracking experiments; `crack.py` is the current tool |
| `cryptdis*.py` | DES and crypto disassembly experiments |
| `dis_bootreg*.py` | `boot_reg` disassembly; `dis_bootreg2.py` was the old code-map keeper |
| `dis_bootwrite.py`, `dis_ksysenv.py` | one-off disassembly |
| `dump_payload.py` | reads an `.omo` agent transcript; unrelated to firmware work |
| `find_refs.py`, `try_guess.py` | one-off searches |
| `dtc-check.sh` | old MinGW `dtc.exe` wrapper; use the kernel build's `dtc` |
| `local-build.bat` | old Windows/WSL build wrapper; use the parent `RUNBOOK.md` |
| `sr-carrier-detached.sh`, `ep0win-detached.sh`, `fwaccept-detached.sh`, `wifidrv1-detached.sh` | old Wi-Fi lane detached wrappers |

If one of these is still needed, port the logic into a current tool with a
`__main__` guard and a repo-relative path. Do not add a new numbered variant here.
