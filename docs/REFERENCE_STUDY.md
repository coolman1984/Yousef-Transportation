# Reference Study — BAMS (coolman1984/Mr.Ayman-HR) → Trip Orders

Phase 0 deliverable. Studied on 2026-09-29 from a shallow clone of `main` (version 2.4.0).
Read: `README.md`, `CLAUDE.md`, `IDEAS.md`, `DISTRIBUTED_SYNC_ARCHITECTURE.md`, `docs/*`, `GUIDE_*.md`, `TASKS.md`,
`DEVELOPMENT_HISTORY.md`, `.claude/skills/bams-development/SKILL.md`, `config.json`, `.github/workflows/build.yml`,
and the code of `server/`, `js/`, `css/styles.css`, `tests/`, `tools/`, `installer/`.

## 1. What BAMS is (verified)

| Area | Fact (verified in code) | Where |
|---|---|---|
| Size | ≈ 5,100 lines Python server, ≈ 3,300 lines JS, 675 lines CSS, ≈ 2,700 lines tests | `server/`, `js/`, `tests/` |
| Runtime | Python **standard library only**, portable CPython 3.12 for Windows in `runtime/python` | `start.bat`, `runtime/` |
| Web | `ThreadingHTTPServer`, JSON API, every request permission-checked server-side, CSRF by Origin check | `server/app.py` |
| UI | single-page app, vanilla JS, hash routes, one CSS file, inline SVG icons/charts, **English only, light only, no i18n, no dark mode, no service worker** | `js/app.js`, `css/styles.css`, `index.html` |
| Data | SQLite WAL + `synchronous=FULL`; entities declared in one table `ENTITIES` (js key, column, kind, Excel header); common columns `id, ver, created_*, updated_*, deleted, deleted_*`; optimistic `ver`; soft delete + Recycle Bin | `server/store.py` |
| History | append-only `journal.db`; changesets hash-chained + Ed25519-signed (pure Python); HLC; version vectors; deterministic fold with multi-value registers, counters, resolvers (`max`, `rank:…`, `follow:…`) | `journal.py`, `replica.py`, `ed25519.py` |
| Multi-PC | every PC holds all data; TLS 1.3 with pinned self-signed certs; authority (admin) key; backup-authority PC; open join (2.4) | `sync.py`, `node.py`, `tlscert.py` |
| Accounts | PBKDF2 600k, lockout, idle logout (not while typing), tick-box permissions in groups, `ADMIN_PERMS` never on a link, built-in + custom profiles, personal links (HMAC token, only hash stored, POST-login page defeats link previews) | `auth.py`, `js/quick.js` |
| Logs | audit (every data change), activity (clicks/pages/exports), security (logins); JSONL monthly files never overwritten | `journal.py`, `data/logs/` |
| Backups | at start, every 6 h if changed, before import/restore, on demand; `PRAGMA integrity_check`; second folder (no network drives); restore = compensating change | `backup.py`, `store.restore_from` |
| Files | content-addressed `uploads/cas/<sha256>.<ext>`, resumable verified copy between PCs | `store.record_file`, `sync.py` |
| Excel | dependency-free **writer only** (`server/xlsx.py`, 105 lines): inline strings, numbers, bold frozen header, autofilter, widths. **No formulas, no dates/times, no number formats, no Excel Tables, no reader.** | `server/xlsx.py`, `store.export_sheets` |
| Delivery | Nuitka-compiled `BAMS.exe` with pages inside; Inno Setup installs and updates; data in `%ProgramData%`; GitHub Actions tests + builds + publishes a release per version | `tools/`, `installer/bams.iss`, `.github/workflows/build.yml` |
| Tests | unit (32 cases), convergence (random multi-replica), multi-node (36, real processes + TCP proxy), browser e2e (Playwright) | `tests/` |
| Method | rules in `CLAUDE.md`; skill; history with mistakes/lessons; `IDEAS.md`; review → fix → regression test | repo root |

## 2. Domain coupling of the engine

Occurrences of "area" per server module: `app.py` 39, `store.py` 64, `auth.py` 24 (per-user area restriction),
`journal.py` 10, `system.py` 2 — and **0** in `sync.py`, `replica.py`, `node.py`, `ed25519.py`, `tlscert.py`,
`backup.py`, `xlsx.py`. So the replication/security core is domain-free; the domain lives in `store.ENTITIES`,
`COUNTERS`, `RESOLVERS`, `AREA_CHILDREN`, the `auth.PERMISSIONS` list, the area restriction, sample data and all of
`js/app.js`. This confirms the DECIDED fork strategy is feasible.

## 3. Reuse as-is

`ed25519.py`, `tlscert.py`, `node.py`, `journal.py` (renamed prefixes), `replica.py`, `sync.py`, `backup.py`,
`nodectl.py`, `system.py` (lock, upgrade), `bams_main.py` pattern, `tests/harness.py`, `tests/cluster.py`,
`test_convergence.py`, the multi-node tests that are domain-free, `tools/build_windows.py`, `tools/make_assets.py`,
`installer/*.iss` (renamed), the release workflow, the `CLAUDE.md` / skill / history / `IDEAS.md` discipline.

## 4. Adapt

| Part | Change |
|---|---|
| `store.py` | new `ENTITIES` (vehicles, drivers, departments, people, places, routes, trip_categories, trips, trip_passengers, trip_photos, trip_amendments, submissions); resolvers: trip `status` = `rank:draft,sent,started,finished,reviewed,cancelled` (cancel wins), `end_km` follows status; no counters needed |
| `auth.py` | new `PERMISSIONS` groups (trips, dispatch, approvals, review, fleet, reports, finance, excel, settings, users); profiles Administrator / Dispatcher / GA Approver / Reviewer / Finance / Viewer; drop the per-area restriction or replace it by per-category restriction |
| `app.py` | trip routes; `/api/import/preview`, `/api/import/commit`; gateway settings; brand config |
| `xlsx.py` | extend: formulas (with cached value), date + time cells with number formats, styles table, **Excel Table part** (`xl/tables/table1.xml`), RTL-safe text, column widths |
| new `xlsx_read.py` | zip + XML reader: shared strings, inline strings, numbers, booleans, 1900 date serials, cached formula values, tables, merged cells |
| new `gateway_client.py` | push trip cards, pull submissions, ack, HMAC auth, backoff, idempotency by submission UUID |
| `js/app.js` | rewritten UI (same patterns: `ACT` actions, `modal`, `esc`) + i18n (EN/AR, RTL), themes, command palette, shortcuts |
| `css/styles.css` | new design system (see `docs/DESIGN.md`): tokens, light/dark, density, font scale |
| `js/help.js` | Help & guided tours for the new screens, both languages |
| sample data | generated from the September workbook (anonymised names option) instead of break areas |

## 5. Drop

Break-area domain, inventory counters, surveys, room placeholder SVGs, legacy browser-only JSON import,
"English only" UI rule (owner asked for English **and** Arabic).

## 6. Things BAMS does not have that we need

1. Excel **reader** and a richer writer (formulas, tables, dates).
2. Internet reachability for drivers → gateway (Cloudflare Worker + D1) and a PWA driver page (service worker,
   IndexedDB outbox, camera, compression, stamp). BAMS is LAN-only by design; the office PC stays that way.
3. Bilingual UI with RTL, light/dark themes, font and size choices, motion system.
4. Money: rates per km/hour, vendor reconciliation, cost allocation.

## 7. Data facts re-checked on the September workbook

Verified with a script on `Extra_Sep-26_Recovered.xlsx` (sheet `All Car`, `Table1` = `A1:P279`):

| Fact in the master prompt | Measured | Note |
|---|---|---|
| 232 trips | **232** ✓ | 141 `Manager car`, 91 `Extra` |
| 28 days | dates 1→28 Sep, **25 distinct days** | Fridays absent |
| 42 drivers | 42 raw strings, **41 after whitespace normalisation** | proves the need for normalisation |
| 46 cars | 46 raw plate strings, **44 after normalisation**, 7 trips with no plate | e.g. `' ل ص ط 1865'` (leading space) |
| 20 departments / 54 requesters | **20 / 54** ✓ | |
| Start/End empty in every row | **0 of 232 filled** ✓ | OT never computed |
| 13 odometer back-steps | **12** in row order with normalised plates (13 depending on ordering) | biggest: `و ق ر 3581` 191,220 → 160,200 (~31,000 km typo) |
| 56 of 224 Misr ≠ km | **56 of 223** trips with both kms | 8 trips have no km at all |
| 87 destinations | **90 raw, 89 case-insensitive** | top: `SEEG-BNS-SEEG` ×28 |
| `Column1` 1–7 on Extra | ✓ values 1–7 only on `Extra` rows | daily sequence of extra trips |
| Non-person employee names | ✓ `Visitor`, `Early leave`, `Cover Katamia- Line`, `EHS Audit` (in rent sheets) | → separate `purpose` field |
| Other sheets | `SUV Rent` 11 trips (no Excel Table), `Microbus Rent` 4 trips (`Table2`, `#` = `ROW()-1`, `TTL` totals row) | export must reproduce the totals row |

These become test fixtures (`tests/fixtures/sep26_expected.json`) in Phase 3.
