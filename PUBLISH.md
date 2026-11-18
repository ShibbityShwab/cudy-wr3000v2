# Publication policy - intentionally public lab notebook

**Updated:** 2026-11-18 · **Status:** active policy · **Applies to:**
`ShibbityShwab/cudy-wr3000v2` and the curated repositories below.

The root repository is **published on purpose**. It is a working reverse-engineering notebook for
a Cudy WR3000 v2.0 (HiSilicon luofu v2) router: the ledger, tools, failed hypotheses and analysis
are public because the record is the deliverable (portfolio/career use). Publication is
intentional; it is **not** an endorsement of any claim or upstream state. The honest live status
is always the newest dated entry in [`mem-entries.md`](mem-entries.md) and the current
[`STATUS.md`](STATUS.md) - bench gates are not upstream progress and no release is implied.

Where an older page still says the root repository is "private research material", "must stay
private", or "**NOT READY**" (e.g. `EVIDENCE-INDEX.md`, `CURRENT-TRUTHS.md`,
`REVERSAL-REPORT.md`, `STATUS.md`), **this file supersedes the policy part of that wording.**
The technical checklists those pages carry (history containment, license texts, GPL reply/receipt,
Wi-Fi + LAN-switch status) are still real and open; calling the notebook public does not close
them.

## Curated public repos

| repository | what it is | state |
| --- | --- | --- |
| [cudy-wr3000v2](https://github.com/ShibbityShwab/cudy-wr3000v2) | this notebook: bench ledger, harness/tools, reversal analysis, publish policy | public; HEAD sanitized 2026-11-18, history pre-policy |
| [cudy-wr3000v2-openwrt](https://github.com/ShibbityShwab/cudy-wr3000v2-openwrt) | the curated port repo: OpenWrt target skeleton, board DTS, 19-patch kernel series, image recipe and host-validated A/B install path | public; fresh history born clean (2026-11-18); host-validated only, nothing booted or flashed |
| [cudy-wr3000v2-cve](https://github.com/ShibbityShwab/cudy-wr3000v2-cve) | CVE-2026-71960 / CVE-2026-71961 writeups, sanitized PoCs and mitigation | public; fresh history born clean (2026-11-18) |

These are the curated surfaces. Other repositories under the same account are unrelated projects.

### Legacy repositories (public, pre-policy, superseded)

- **`cudy-wr3000v2-open-firmware`** (the root repo's `opensource/` submodule remote) is a
  **legacy** public repository: it was made public on 2026-09-30 and its history contains ten
  vendor TR6560 BSP `.o` files (introduced 2026-10-09, never deleted from any public ref). It is
  **superseded by `cudy-wr3000v2-openwrt`**; do not treat its contents as clean and do not use
  it as the publication surface. Containment (archive read-only, or make private) is an
  **owner-only** action; see `opensource/docs/PUBLISH-PREP.md` for the plan and the appendices.
- The **root notebook** was made public on 2026-10-16, before this policy. Its HEAD is sanitized
  on 2026-11-18 (secrets/MACs); its history carries pre-policy material (see the history note
  below). It stays public as the raw record.

## Publication strategy (owner decision, 2026-11-18)

The path is **new curated repos with new clean histories**, not a rewrite: the curated repos above
were born with their license/provenance/disclosure files in the first commit. The legacy
repositories are then superseded and contained by owner action. No force-push, `filter-repo`,
reflog/gc, branch deletion, visibility change or repository deletion is performed by the notebook
lanes; a history purge remains an **optional appendix** for later, owner-approved cleanup.

## Licenses and provenance split

- **Documentation, prose and original tools: MIT.** The curated `cudy-wr3000v2-openwrt` repo
  ships `LICENSE-MIT`, `LICENSE-GPL-2.0` and `NOTICE.md`; the legacy `opensource/` subtree ships
  MIT in `LICENSE`. The root notebook states the same split here; a root `LICENSE`/`NOTICE` pair
  is still pending (tracked in `opensource/docs/PUBLISH-READINESS.md`).
- **Kernel code and code derived from the vendor's GPL binaries: GPL-2.0.** The lab kernel
  modules carry SPDX headers and `MODULE_LICENSE("GPL")`, and the curated repo carries the
  GPL-2.0 text. Per-file copyright notices and DCO sign-offs are still pending; until they land,
  treat derived code as "GPL-2.0 intended", not as a signed-off submission.
- **Vendor binaries are not redistributed.** Firmware images, rootfs, kernel modules
  (`.o`/`.ko`), Wi-Fi firmware blobs, calibration data and dumps are excluded from the curated
  repos; where a recipe needs them it produces them locally from the reader's own device.

### Reverse-engineering provenance (not "clean-room")

The drivers, userspace analysis and CVE findings here are derived from the vendor's GPL-licensed
binaries by disassembly/static analysis, and from black-box probing of a device the owner
purchased - both GPL-compatible reverse engineering. This is **not** a clean-room
implementation and the docs say so. The vendor ships a Linux 5.10.201 / OpenWrt 22.03.6 system
with GPL `hi_*` kernel modules and no published source; the GPLv2 §3 source request was sent
2026-10-01 and no reply is held (`opensource/docs/GPL-REQUEST.md`). Any upstream submission must
state GPL-2.0 provenance with attribution. Bench results are experiments on one unit; they are
not vendor statements and not a claim of complete coverage.

## Forward rules: no vendor binaries, no secrets

These rules apply to every new commit from 2026-11-18 on and are enforced by
[`tools/check-repo.sh`](tools/check-repo.sh) where it can be:

1. **No vendor binaries or vendor-derived blobs in tracked text**: no vendor `.o`/`.ko`,
   firmware images, rootfs/calibration data, extracted DTS, de-crypted LuCI bytecode or dumps.
   They stay local under gitignored `build/`, `dumps/`, `firmware/`, `patched/`, etc. Known
   legacy HEAD residuals are listed under "history" below; new work must not add any.
2. **No secrets in tracked text**: no passwords, private keys, tokens, API keys, session cookies
   or proprietary licence material. Live values come from gitignored `.omo-secrets/` (or the
   environment) at runtime; tracked text carries placeholders such as
   `<ROUTER-WEB-PASSWORD>`, `<ROUTER-SSH-PASSWORD>`, `<BDINFO-SECRET>`.
3. **No per-unit identifiers**: per-unit MACs, serials and bdinfo `deviceid`/`secret` values
   are replaced by documentation values (`02:00:00:00:00:01`, `02:00:00:00:00:02`, ...). The
   surrounding explanation is kept; only the value is redacted.
4. **.gitignore is a safety net, not permission.** Never `git add -f` a secret; before any
   commit, `git grep` the staged paths for credential patterns.
5. **If a secret lands in tracked text anyway**: redact it in HEAD, add an entry to the append-only
   ledger recording the exposure date/commit, rotate the secret, and note the history risk below.

Values that are **not** secrets: constants that ship in the vendor firmware itself and are
required to explain a finding, e.g. the static LuCI wizard salt in
[`tools/web_login.sh`](tools/web_login.sh) or the bdinfo DES literal quoted by the CVE writeups.
They are public vendor values (anyone with the firmware has them) and are left in place with a
comment. Per-unit runtime values are a different class and are never published.

## Pre-policy public history is NOT clean (read this before trusting an old commit)

The repositories were public before this policy (root notebook since 2026-10-16, legacy
open-firmware since 2026-09-30). HEAD is sanitized; **history is not.** Known residuals, owned by
the publish-prep lane and deliberately not rewritten here (no force-push, no `filter-repo`; that
is the owner's separate decision):

- **Lab web-admin credential.** The credential recorded in `mem-entries.md` (PHASE 141, the
  `.omo-secrets` lab web-admin password set 2026-09-30) was committed on 2026-10-12 (`2f018c0`)
  and has been publicly readable since the repo went public (2026-10-16), including at
  `origin/master:mem-entries.md` lines 13429/13438. HEAD now says
  `Wr3***[REDACTED-2026-11-18]`. Treat it as **compromised forever**: never reuse it and rotate
  it wherever it may have been reused. The current stock box does not accept it, but that does
  not un-leak it.
- **Per-unit MACs and other identifiers.** Two unit MACs were public in the same history and in
  plan/state/ledger pages; HEAD uses documentation values, history does not.
- **Vendor/derived binaries in root-notebook history.** The public history contains two vendor
  `.ko` files and four vendor-derived LuCI bytecode files, plus five of our build outputs. As of
  this policy date HEAD still tracks the four `patched/*.lua` bytecode files; removing them from
  HEAD is owned by the publish-prep lane. Do not redistribute them from a clone.
- **Vendor objects in the legacy open-firmware repo.** Ten vendor TR6560 BSP `.o` files are in
  that repo's public history and were never deleted from a public ref; the superseded legacy
  repo is contained by owner action (`opensource/docs/PUBLISH-PREP.md`).

It is not safe to assume any pre-2026-11-18 commit is clean. The optional history purge
(`git filter-repo --replace-text` + force-push) and the legacy-repo containment are separate,
owner-approved operations. Until they happen: **assume older commits can contain credentials,
vendor artifacts and per-unit identifiers.**

## Reporting a leak

If you find a credential, per-unit identifier or vendor binary in one of these repos, do not paste
it into a public issue. Use GitHub's private security advisory on the affected repo, or contact
the owner via the profile on [github.com/ShibbityShwab](https://github.com/ShibbityShwab), and
include the file/commit. The response is redact-HEAD, ledger entry, rotate, then decide on a
history purge or legacy-repo containment.
