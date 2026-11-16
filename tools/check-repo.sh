#!/usr/bin/env bash
# check-repo.sh - fail if the docs/tools surface has drifted from the bench truth.
#
# This is the static counterpart to tools/session-brief.sh: it catches the defect class that
# has misled every past session - a live doc restating a retired fact, a doc pointing at a
# missing tool, the published half carrying vendor binaries, or STATUS older than the ledger.
# Read-only.
#
# usage: tools/check-repo.sh
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
export LC_ALL=C
FAIL=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$*"; }

echo "== repo consistency check =="

# ---- required files and executables ----
required="AGENTS.md START-HERE.md STATUS.md CURRENT-TRUTHS.md RUNBOOK.md LESSONS.md HARDWARE-IDENTITY.md EVIDENCE-INDEX.md BENCH-FACTS.md README.md PLAN-FULL-REVERSAL.md tools/AGENTS.md tools/session-brief.sh tools/fire-preflight.sh tools/uart-capture.sh tools/bench-link.sh tools/recovery-card.sh tools/bench-teardown.sh tools/check-repo.sh"
missing=""
for f in $required; do [ -f "$f" ] || missing="$missing $f"; done
if [ -z "$missing" ]; then pass "required docs/tools exist"; else fail "missing:$missing"; fi

need_exec="tools/fire.sh tools/fire-device.sh tools/fire-ssh.sh tools/check-init-shadow.sh tools/check-lab-src.sh tools/box-provision.sh tools/rsh.sh tools/rscp.sh tools/wifi-cal-snapshot.sh tools/wifi-cal-restore.sh tools/restore-now.sh tools/session-brief.sh tools/fire-preflight.sh tools/uart-capture.sh tools/bench-link.sh tools/recovery-card.sh tools/bench-teardown.sh tools/check-repo.sh"
noexec=""
for f in $need_exec; do [ -x "$f" ] || noexec="$noexec $f"; done
if [ -z "$noexec" ]; then pass "live tools are executable"; else fail "not executable:$noexec"; fi

# ---- guards ----
if "$ROOT/tools/check-init-shadow.sh" >/dev/null 2>&1; then pass "shadow guard PASS"; else fail "shadow guard FAILED"; fi
if "$ROOT/tools/check-lab-src.sh" --manifest-only >/dev/null 2>&1; then pass "tracked kernel snapshot PASS (manifest)"; else fail "tracked kernel snapshot FAILED"; fi

# ---- no vendor binaries on a publishable surface ----
if git ls-files -z 2>/dev/null | tr '\0' '\n' | grep -qE '^tools/vendor-mods/.*\.ko$'; then
	fail "root repo tracks tools/vendor-mods/*.ko (vendor GPL object code; must stay untracked)"
else
	pass "no tracked vendor .ko in the root repo"
fi
if git -C opensource ls-files 2>/dev/null | grep -qE '\.(o|ko)$'; then
	fail "opensource/ (published half) tracks vendor .o/.ko files; remove them before publishing"
else
	pass "no tracked vendor .o/.ko in the published half"
fi

# ---- docs freshness ----
STATUS_UPDATED=$(sed -n 's/^\*\*Updated:\*\* *//p' STATUS.md 2>/dev/null | head -1)
LATEST_LEDGER=$(grep -oE '^## [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}' mem-entries.md 2>/dev/null | tail -1 | sed 's/^## //')
if [ -z "$STATUS_UPDATED" ]; then fail "STATUS.md has no **Updated:** line"
elif [ -z "$LATEST_LEDGER" ]; then fail "cannot read newest dated entry from mem-entries.md"
elif [[ "${LATEST_LEDGER%% *}" > "$STATUS_UPDATED" ]]; then
	fail "STATUS.md ($STATUS_UPDATED) is older than the newest ledger entry ($LATEST_LEDGER)"
else
	pass "STATUS.md ($STATUS_UPDATED) is not older than the newest ledger entry ($LATEST_LEDGER)"
fi

# ---- retired claims that must not reappear in live docs ----
STALE_PATTERNS=(
	'UART is output-only'
	'exec 3<>'
	'192\.168\.10\.88'
	'next-persist\.sh'
	'/vendor mount can come up read-only'
	'phase3de slice was assembled'
)
STALE_HITS=$(python3 - <<'PY'
import re, subprocess
docs = [f for f in subprocess.check_output(["git", "ls-files", "*.md"], text=True).split()
        if not f.startswith(("mem-entries", "docs/archive/", "opensource/"))]
pats = [r"UART is output-only", r"exec 3<>", r"192\.168\.10\.88", r"next-persist\.sh",
        r"/vendor mount can come up read-only", r"phase3de slice was assembled"]
bad = []
for f in docs:
    for i, line in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
        low = line.lower()
        if any(w in low for w in ("never", "must not", "do not", "don't", "forbidden", "no longer")):
            continue
        for p in pats:
            if re.search(p, line, re.I):
                bad.append(f"{f}:{i}: {line.strip()[:90]}")
print(" | ".join(bad[:8]))
raise SystemExit(1 if bad else 0)
PY
) ; STALE_RC=$?
if [ "$STALE_RC" -eq 0 ]; then pass "no retired-claim phrases in live docs"; else fail "retired claims found: $STALE_HITS"; fi

# ---- relative markdown links ----
LINK_ERRS=$(python3 - <<'PY'
import os, re, subprocess, sys
files = [f for f in subprocess.check_output(["git", "ls-files", "*.md"], text=True).split()
         if not f.startswith("docs/archive/")]
bad = []
for f in files:
    try:
        text = open(f, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text):
        target = m.group(1).split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#", "<")):
            continue
        p = os.path.normpath(os.path.join(os.path.dirname(f), target))
        if not os.path.exists(p):
            bad.append(f + ": " + target)
print("; ".join(bad))
sys.exit(1 if bad else 0)
PY
) ; LINK_RC=$?
if [ "$LINK_RC" -eq 0 ]; then pass "relative markdown links resolve"; else fail "broken links: $LINK_ERRS"; fi

# ---- docs must not reference missing live tools ----
TOOL_ERRS=$(python3 - <<'PY'
import os, re, subprocess, sys
docs = [f for f in subprocess.check_output(["git", "ls-files", "*.md"], text=True).split()
        if not f.startswith(("mem-entries", "docs/archive/", "opensource/"))]
# archived pages carry dead relative links by design; only the archive README is live
bad = []
seen = set()
for f in docs:
    text = open(f, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"(?<![\w/])(tools/[A-Za-z0-9_./-]+\.(?:sh|py|js))", text):
        t = m.group(1).rstrip(".,)")
        if t in seen:
            continue
        seen.add(t)
        if not os.path.exists(t):
            bad.append(f + ": " + t)
print("; ".join(bad))
sys.exit(1 if bad else 0)
PY
) ; TOOL_RC=$?
if [ "$TOOL_RC" -eq 0 ]; then pass "no doc references a missing live tool"; else fail "missing tool referenced: $TOOL_ERRS"; fi

echo
if [ "$FAIL" -gt 0 ]; then
	echo "REPO CHECK: FAIL ($FAIL problem(s)) - fix the live docs/tools before the next session"
	exit 1
fi
echo "REPO CHECK: PASS"
