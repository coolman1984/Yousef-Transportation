# Development History and Lessons Learned

Newest first. Every change adds an entry: what changed, why, mistakes, lessons.

---

## Product film, version 2 - cinematic camera and full resolution (2026-10-01)

**Why:** the owner found version 1 poor: small, soft picture, a still wide shot, little motion.
**What:** `studio/` re-shoots at full resolution (office 1920x1200, phone 786x1702 frames), draws its own cursor and finger taps from the
recorded path (sharp at any zoom), bakes one smoothed camera track per device in `cut.mjs` (follow shots that push in on the action, gentle
pull-outs, gaussian smoothing so the camera anticipates and never jerks), speed ramps for idle waits, 3D device entrances/exits, a rail with
kinetic titles, a step line and rolling counters, a new score (pad, plucks with a room, soft groove) with whooshes/chimes/rolls on the picture's beats,
and a 60 fps lossless-frame render in three parallel slices plus a two-pass copy under 30 MB for chat.
**Mistakes:** the screencast silently delivered CSS-size frames (1280x800) although the page ran at scale 1.5 - the whole first film was
recorded at a third of the pixels. It only gives device pixels when Chromium itself runs with `--force-device-scale-factor`. Then a 2x/3x shoot made
the machine twice as slow (typing 0.65 s per letter); the hand and typing are now time-based and the scale is what the zoom needs (1.5 / 2), not more.
**Lesson:** measure the raw material (frame size, frame rate) before judging the edit; check the first frame's pixel size in every shoot.

---

## CI failure on main for 1.0.1 (2026-10-01)

The release of 1.0.1 was never published: the test job failed on main (`ReportsPageTest`: "No trips in this month"). Real bug, not only a test problem:
the Reports page asked for the current month first and for the chosen month second, and the older answer arrived last and replaced the newer one.
Fix: every request has a number and only the newest may paint. Also `xlwt` is installed in CI so the old `.xls` test runs there too (4 tests were skipped).
Lesson: I told the owner the release "will appear" before looking at the build; check the run, then say it. I also merged PR #4 on his explicit order before CI finished.

---

## 1.0.2 - Microsoft Office (COM) route for protected files (2026-10-01)

**Why:** the owner's company files are DRM-protected; the company's agent lets Excel/Word open them on a company PC.
**What:** `server/com_office.py` runs a PowerShell script (stdlib only, no pywin32) that opens the file with Excel/Word COM (hidden, read-only, macros off,
no alerts, never saves) and writes the values / text as JSON to a private temp folder that is removed afterwards. Dates travel as OLE serials.
`formats.read_workbook/read_document(engine=auto|office|native)`: auto uses Office only for files no built-in reader can open (DRM, xlsb, Office 95, password);
`engine=office` forces it. `/api/state.office` says whether Excel/Word are present (checked once at start). Protected files go to the Excel or Word door by file extension.
**Tests:** `test_formats.OfficeRoute` (7) with a pretend PowerShell: JSON -> rows end to end, the protected bytes reach Office untouched, temp folder removed, timeout / password /
not-installed / no-answer messages, engine choices, script sanity (ASCII, balanced brackets, read-only, macros off, never saves).
**NOT verified:** the PowerShell scripts have never run against real Excel/Word - this sandbox has neither PowerShell nor Office and the CI Windows runner has no Office.
First real run is on the owner's PC; if it fails the message includes Office's own error text. Known limits: needs a logged-in desktop session (not a Windows service),
big sheets are slow (cell values are copied through COM), `.Value` vs `.Value2` behaviour for date detection should be watched.
**Security note:** the work files hold the protected file as received (still encrypted) and are deleted in `finally`; the JSON holds decrypted values for the seconds of the call.

---

## 1.0.1 - many file types, DRM files, slide bug (2026-10-01)

**Found by the owner's first real files:** both files he attached start with `<## NASCA DRM FILE - VER1.00 ##>`: his company's document-security
system encrypts them, so they are not xlsx/docx at all. No program can read them; the program now says so in plain words (AR/EN) and what to do
(open on a PC with the security agent, Save As a new copy, or export .csv). We do not try to defeat the protection.
**What:** `server/formats.py` recognises files by content and reads xlsx/xlsm/xltx, **xls (BIFF8)**, ods, csv/tsv/txt, HTML-as-xls, SpreadsheetML 2003,
docx/docm/dotx, **doc (Word 97)**, odt, rtf, HTML-as-doc. One door `/api/import/preview` (Word files ask for the trip category).
**Tests:** `test_formats` (15). The `.xls` test file is made by an independent library (xlwt), which caught nothing wrong. The `.doc` and RTF tests use
files made by the test itself, so they prove the reader follows the format as we understand it - **not yet tried on real Word-made `.doc`/`.rtf`**.
Not supported (message only): xlsb, Excel/Word 95, password-protected files.
**Bug:** welcome slides were blank after slide 1 in Arabic: the track is forced left-to-right in CSS but the script moved it the RTL way.
**Lesson:** never gate a file by its extension; look inside it.

---

## Phases 6-7 – reports, release (2026-09-30)

**What:** Reports page and presentation mode; version 1.0.0; the installer script no longer asks about "old version data" (BAMS leftover)
and the build now puts `gateway\` (worker bundle, schema, setup guide) next to the program; the workflow runs every test group
(node gateway tests, Playwright screen tests) and attaches the gateway files to the release; guides for dispatcher, admin, driver.

**Mistake:** rewriting `server/version.py` with `open(p,'w').write(open(p).read()...)` truncated the file before reading it. Read first, then write.

**Not verified here:** the Windows build (Nuitka/Inno Setup) and a real Cloudflare deployment - CI and the owner's first run are the check.

---

## Phases 4-5 – gateway, driver page, office link (2026-09-30)

**What:** `gateway/` (Cloudflare Worker + D1, no dependencies), the driver PWA, `server/gateway_client.py`, the link/WhatsApp/print
screens and Settings -> Mailbox, `docs/GATEWAY_SETUP.md`.

**Decisions**
- Tests run the *real* worker code in Node with a D1 stand-in on `node:sqlite` (`gateway/dev/d1.js`) - no wrangler download needed,
  and the same dev server is used by the Python tests, so the office client is tested against the real gateway code.
- A second phone is never blocked: its events are accepted and marked (trust rule `R_SECOND_DEVICE`, red). "Technology never blocks."
- Photos are one BLOB row each (<= 600 KB after compression to ~250 KB); D1 allows 2 MB per row, so no splitting.
- The dashboard bundle (`build.js`) embeds the driver page in the worker so the owner can deploy by copy/paste.
- The phone time and the gateway time are put in the *phone's own* zone before the drift check; otherwise a +03:00 phone looked 3 hours off.

**Mistakes / lessons**
- The service worker install failed silently because `/index.html` is not a route (only `/t/<token>`); offline reload then failed. Fixed by
  caching the shell from `/t/shell`. Lesson: test offline reload, not just offline sending.
- An event that failed while offline was not marked `queued` (only HTTP answers counted as a try). Network errors now count.
- `state.settings` is an object `{id: value}`, not a list: two places read it wrongly (Word brand text and print sheet). A test now sets the
  brand and reads it back.
- `wait_for_function` with a string is blocked by the strict CSP: poll with `evaluate` of a function instead.
- Not verified here: a real Cloudflare deployment (no account/network in the sandbox). The owner runs the 9-step smoke test.

---

## Phase 3 – Excel and Word in and out (2026-09-30)

**What:** dependency-free xlsx reader/writer and docx reader/writer; `excel_io.py` (find the header row by names, read every
sheet, match drivers/cars/people/departments/categories/places, duplicate detection by an import key, alerts, place-spelling
merge suggestions, one confirmed commit after an automatic `pre-import` backup); export in the owner's exact three-sheet
layout with live formulas, and a clean 10-sheet report; `reports.py` (summaries, overtime, vendor reconciliation, cost,
anomalies); `word_io.py` (printable form, reading filled forms, monthly report); the Excel page (import review, export, Word, Guide).

**Tests:** `test_xlsx`, `test_excel_io` (13), `test_word_io` (8), browser flow. openpyxl reads our files (acceptance check).

**Mistakes / lessons**
- The reader returned `0` for time-formatted cells until the built-in number formats 18-21 were treated as times.
- LibreOffice in this sandbox cannot load any xlsx (not even openpyxl's), so that check is skipped here; the openpyxl
  acceptance test replaces it. Open the exported files in real Excel once on the office PC.
- A test password containing the user name is refused by the server (good) - use another.
- The page state must be reset when the tab changes: a test that waited for the drop zone while the Guide tab was active failed.
- Import messages arrive as English text plus a code; the browser shows them from the dictionaries by code.

---

## Phase 2 – domain core and office screens (2026-09-30)

**What:** `server/domain.py` (text/plate/mobile normalisation, trip numbers with the PC letter, overtime, odometer chain,
unusual km, drift, trust colour), `server/tripsvc.py` (new trip, amendment, cancel, GA approval, insights, duplicate
refusal), locked-trip rule in the commit guard, `/api/trips/*` and `/api/insights`. UI: data layer with polling, shared
forms/tables (`ui.js`), lists (vehicles, drivers, people + departments, places, categories), trips list with filters and
summary, trip side panel, new-trip dialog (people created on the fly), Today board, Review queue, Activity log,
Settings → People & access (users, links, profiles, permission ticks in both languages), Settings → Data (Recycle Bin,
backups, complete export). Palette now finds trips, plates and drivers.

**Tests:** `test_domain` 23, `test_trips_api` 7, browser flow tests (lists, new trip, amendment, users, bin).
Whole suite: 118+ tests green.

**Mistakes / lessons**
- The page element `#view` was reused between pages, so every visit added another click handler and one click opened
  several panels. Fix: replace the element with a clean clone on every route change. Lesson: mount code must never
  attach listeners to an element that outlives the page.
- Bidi again: a trip number in an RTL drawer title reversed itself (`A-00002-26`); titles that hold codes need `dir="ltr"`.
- A phone overflowed by 9 px because a preview row could not wrap; every row that holds badges/plates needs `wrap`.
- Server-side normalisation (plates, names, mobiles) belongs in one place (`tripsvc.normalize_ops`), because the Excel
  import must produce the same keys as the screens. Duplicates of plates/drivers/places are refused, people may share names.

## Phase 1b – design system and application shell (2026-09-30)

**What:** `css/tokens.css` (5 themes: daylight, night, asphalt, highway, contrast; font, size, density, motion switches),
`css/base.css` (shell, cards, tables, forms, drawers, dialogs, toasts, tour, slides, login, animation), bundled OFL fonts
(`tools/install_fonts.py`), English + Arabic dictionaries with RTL, `js/` modules under one `TO` namespace
(core, i18n, prefs, shell, views: sign-in/first setup, overview, planned pages, settings→appearance, help),
command palette (Ctrl K), keyboard shortcuts that work on any keyboard layout (`e.code`), stackable side panels,
guided tour, welcome slides, phone menu. Planned pages show what they will contain in the final look.

**Tests:** `tests/test_design.py` (WCAG AA contrast of every theme, key parity EN/AR, no literal words in templates,
logical CSS only, no colours outside tokens, fonts exist), `tests/test_e2e_browser.py` (Playwright: language/direction,
theme persistence, palette + G-shortcuts, panels + Esc, live settings, phone menu, welcome slides).

**Mistakes / lessons**
- The server sends `script-src 'self'`: no inline scripts and no string `eval`; browser tests must use `wait_for_url`
  / selectors, not `wait_for_function` with a string. The pre-paint theme script had to be an external file (`js/boot.js`).
- `add_init_script` runs on every page load, so it must not overwrite saved settings in a reload test.
- Keys with a dynamic suffix (`nav.` + id) cannot be checked by a regex on `TO.t('...')`; a family test lists them.
- Bidi: a trip number like `26-A-00233` must sit in its own `.num` span or Arabic text reorders it.
- Focus the palette input synchronously, or fast typing (and tests) lose the first letters.

## Phase 1a – engine fork (2026-09-29)

**What:** copied the BAMS engine (BAMS commit `5f5b3ce`, version 2.4.0), renamed everything to Trip Orders
(`TO-` hash domains and headers, `TO_HOME`, `trips.db`, `TripOrders.exe`, ports 8090/8453, new installer AppId),
replaced the break-area domain by the trip domain in `store.ENTITIES` (13 entities, `docs/EXECUTION_PLAN.md` P2.1),
new permission groups and 7 built-in profiles in `auth.py`, permission mapping and category scopes in `app.py`
(a person can be limited to trip categories; journal/audit column `scope_id`, user field `scopes`).

**Tests:** engine tests kept. In-process tests use a test-only break-area style domain (`tests/engine_domain.py`,
registered by `tests/cluster.py`, never shipped) so counters, `max`/`rank`/`follow` resolvers and restores stay
covered; the multi-PC tests were rewritten on trips (photos = `tripPhotos`, limited user = category scope).
Removed: the upgrade-from-version-1 tests (they rebuilt BAMS history from git).
Result: unit + convergence 32 OK, multi-PC 35 OK.

**Mistakes / lessons**
- A blind `sed s/bams_/to_/` shortened the backup file prefix from 5 to 3 characters and broke code that sliced
  file names by position (`name[4:]`, `n[5:20]`). Lesson: after a rename, grep for numeric slices of the renamed strings.
- `git rm --cached -r .` was run by mistake while cleaning up; it only changed the index (fixed by `git reset`).
  Lesson: never run index-wide commands as a side effect of a rename.
- Fields like `description` that tests used are not real trip fields; conflict resolution must use the real field
  name (`notes`).

## Phase 0b – playbook for every agent (2026-09-29)

**What:** `docs/EXECUTION_PLAN.md` (how to work, environment, every task with exact rules, data model, API,
gateway protocol, workbook layout, checks, pitfalls, owner answers), `TASKS.md` (tracker), project skill
`.claude/skills/trip-orders/SKILL.md`, `.gitignore` for `samples/private/`.

**Why:** the owner wants any later agent to continue without mistakes, the same way.

**Owner answer:** demo data = the real sheet. The repository is **public**, so the real workbook is loaded at first
start on the office PC and never committed; the repo gets a synthetic sample with the same shape.

**Lessons**
- Check repository visibility before committing anything derived from the owner's files.

## Phase 0 – study and plan (2026-09-29)

**What:** studied the BAMS reference repository, the paper trip order and the September workbook; wrote
`docs/REFERENCE_STUDY.md`, `docs/PLAN.md`, `docs/DESIGN.md`, `CLAUDE.md`. Removed the first idea note
`PROJECT_PLAN.md` (it proposed passenger QR confirmation, which the owner decided against for version 1).

**Why:** the owner's master prompt asks for Phase 0 first; the owner also added bilingual UI, light/dark themes,
motion, shortcuts, slides and full admin control.

**Mistakes / lessons**
- The master prompt's workbook numbers were close but not exact (drivers 42 vs 41, cars 46 vs 44, back-steps 13 vs
  12, destinations 87 vs 89/90) – the differences come from whitespace and case. Lesson: every count depends on
  normalisation; tests must state the normalisation they use.
- BAMS has no Excel reader, no i18n, no dark mode and no service worker – these are new work, not reuse.
