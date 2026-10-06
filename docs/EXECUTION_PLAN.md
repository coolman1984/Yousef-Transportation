<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Execution Plan — the playbook for every agent on this project

> Read this whole file before you touch anything. It is written so that any agent can continue the work
> **exactly** the way it was started: same method, same decisions, same quality bar.
> If something here conflicts with the owner's newest message, the owner wins — then update this file.

Companion files: `CLAUDE.md` (rules), `docs/PLAN.md` (decisions, defaults, phases), `docs/DESIGN.md` (design
system), `docs/REFERENCE_STUDY.md` (what we take from BAMS), `TASKS.md` (task tracker — **where to continue**),
`DEVELOPMENT_HISTORY.md` (what happened and lessons), `.claude/skills/trip-orders/SKILL.md` (short working memory).

---

## Part A — How to work (be the same engineer)

### A1. The loop for every session

1. `git status`, `git log --oneline | head`, read `TASKS.md` → find the first task that is not `[x]`.
2. Read the task's section in Part C of this file and the files it names. Read before you write.
3. If the task needs facts from the data (workbook, form) **measure them with a script**, never copy numbers
   from memory or from a prompt. Write the measured number and the normalisation used.
4. Write a 3–6 line plan in your head or in the reply; list assumptions; if a question is OPEN, use its default
   (`docs/PLAN.md` §2) and say so — never block.
5. Implement the smallest complete slice: code + tests + docs in the same commit series.
6. Run the checks (Part E). Nothing is pushed red.
7. Re-read your own diff adversarially: what breaks on RTL? on dark theme? offline? with two PCs? with an empty
   database? with the September data? Fix before pushing.
8. Update `TASKS.md` (tick, add found sub-tasks), `DEVELOPMENT_HISTORY.md` (what, why, mistakes, lessons),
   `IDEAS.md` (new reusable idea), guides/help if screens changed.
9. Commit (English, imperative, body says why), push to the session branch, never `main`, never force-push.
10. Report to the owner (A2).

### A2. How to talk to the owner

- Simple Egyptian Arabic, no English words where an Arabic word exists (say "إكسل", "الشاشة", "الرابط").
- Order: **الخلاصة** (one or two lines) → **اللي اتعمل** (short numbered list) → **محتاج منك** (decisions with the
  default in brackets) → **الخطوة الجاية**.
- Never paste code or long file lists at him. Mention at most the 1–3 files that matter.
- When something failed or was skipped, say it plainly with the reason.
- Ask all open questions in **one** message, each with a default.

### A3. Decision rules when you are unsure

| Situation | Do |
|---|---|
| Two designs, one simpler | choose the simpler one unless it breaks a rule in `CLAUDE.md` |
| A fact from data | measure it; if the measure differs from the docs, trust the measure and document the difference |
| Missing input file | ask the owner; meanwhile use the synthetic sample (C3.6) |
| A rule would block a trip | never block the trip; record it and colour it (trust colours) |
| Something may lose data | stop; design it as a new change / soft delete / queue |
| Library temptation | office side: standard library only. Gateway/driver page: plain JS, no framework, no runtime npm packages. Dev tools (wrangler, Playwright) are allowed for tests only |
| UI text | add an i18n key in both `en.js` and `ar.js` — never a literal string in a view |
| Colour | use tokens; green/amber/red only for trust |

### A4. Quality bar (what "done" means for any task)

- Works in **both languages** (RTL checked), **both main themes**, font size XL, and on a 360 px wide phone
  where relevant.
- Empty state, loading state (skeleton), error state (what happened + how to fix) exist.
- Every write is audited, permission-checked on the server, and reversible (soft delete / amendment).
- Tests: unit for logic, browser test for a new screen flow, regression test for every bug fixed.
- Docs updated in the same commit series.

---

## Part B — Environment

### B1. Get the reference and the inputs

```
# reference (read-only; public, anonymous git read works through the session proxy)
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/coolman1984/mr.ayman-hr /home/user/coolman1984/mr.ayman-hr
```
Inputs from the owner (never commit them — this repository is **public**):
- `samples/private/Extra_Sep-26_Recovered.xlsx` (the real workbook)
- `samples/private/trip_order_form.docx` (the paper form)
`samples/private/` is in `.gitignore`. If the files are not there, ask the owner to upload them again; tests that
need them are skipped with a clear message, and the synthetic sample (C3.6) is used instead.

### B2. Tools

- Python 3.11+ (CI uses 3.11, the Windows build uses the portable 3.12 like BAMS). Standard library only at runtime.
- For checks only: `pip install openpyxl` (to cross-check our xlsx reader/writer in tests — optional, skipped if
  missing), Playwright with the pre-installed Chromium (`executablePath: '/opt/pw-browsers/chromium'`), Node 20+ and
  `wrangler` for the gateway (Phase 4).
- Never run `playwright install`.

### B3. Target repository layout (grow into it; do not create empty files early)

```
CLAUDE.md  README.md  TASKS.md  DEVELOPMENT_HISTORY.md  IDEAS.md  LICENSE.txt  config.json  start.bat  .gitignore
.claude/skills/trip-orders/SKILL.md
.github/workflows/build.yml
docs/  PLAN.md  EXECUTION_PLAN.md  DESIGN.md  REFERENCE_STUDY.md  BUILD_AND_RELEASE.md  RELEASE_NOTES.md
       GATEWAY_SETUP.md (owner, Arabic)  GUIDE_*.md
server/                      # office app (Python stdlib)
  app.py  auth.py  store.py  journal.py  replica.py  sync.py  node.py  ed25519.py  tlscert.py
  backup.py  system.py  nodectl.py  version.py  to_main.py        # engine (from BAMS, renamed prefixes)
  domain.py        # normalisation, trip numbers, odometer chain, trust colours, OT, drift, unusual km
  xlsx.py          # writer (extended: formulas, dates, styles, tables)
  xlsx_read.py     # reader (new)
  excel_io.py      # workbook layout spec, import preview/commit, "same as today" + clean export
  reports.py       # reconciliation, allocation, OT, anomalies, per-entity summaries
  gateway_client.py# push cards, pull events/photos, ack, HMAC, backoff
  sample.py        # demo data: from the owner's workbook, or synthetic
index.html
css/ tokens.css base.css components.css pages.css print.css
fonts/ *.woff2 + OFL.txt per family
js/  core.js (api, state, router, esc, modal, toast)  i18n.js  i18n/en.js  i18n/ar.js
     shell.js (sidebar, topbar, side panel, command palette, shortcuts, themes)
     views/*.js (one file per page)  help.js  tours.js  slides.js  charts.js  quick.js
gateway/                     # Cloudflare Worker + driver page
  wrangler.toml  schema.sql  src/worker.js  src/office.js  src/driver.js  src/limits.js
  public/ index.html  app.js  sw.js  camera.js  outbox.js  i18n.js  style.css  manifest.webmanifest  fonts/
  test/*.test.js
tools/ make_assets.py  make_icon.py  build_windows.py  make_sample_workbook.py  subset_fonts.py
installer/ trip-orders.iss
tests/ harness.py cluster.py test_unit.py test_convergence.py test_multinode.py test_domain.py
       test_xlsx.py test_excel_io.py test_reports.py test_gateway_client.py test_e2e_browser.py test_e2e_driver.py
       fixtures/ sample_expected.json
samples/private/   (gitignored)
```

---

## Part C — Phases and tasks (IDs match `TASKS.md`)

### Phase 1 — Engine fork and the new shell

**P1.1 Copy the engine.** Copy from BAMS: `server/{ed25519,tlscert,node,journal,replica,sync,backup,system,nodectl,
version,xlsx}.py`, `server/app.py`, `server/auth.py`, `server/store.py`, `server/bams_main.py` → `to_main.py`,
`tests/{harness,cluster,test_convergence,test_unit,test_multinode}.py`, `tools/*`, `installer/bams.iss` →
`trip-orders.iss`, `.github/workflows/build.yml`, `start.bat`, `reset_admin.bat`, `runtime/` (portable Python,
binary — copy as-is), `LICENSE.txt` (ask owner about holder name; default keep owner Mohamed Fawzy as in BAMS).
Record the BAMS commit hash in `DEVELOPMENT_HISTORY.md`.

**P1.2 Rename.** `BAMS` → `TO` (Trip Orders) in: hash domain strings (`BAMS-CS1` → `TO-CS1`, `BAMS-SESSION1` →
`TO-SESSION1`, `BAMS-LINK1` → `TO-LINK1`), headers (`X-BAMS-*` → `X-TO-*`), env `BAMS_HOME` → `TO_HOME`, data
folder `%ProgramData%\TripOrders`, exe `TripOrders.exe`, db `bams.db` → `trips.db`. Do it with a script and a
`grep -ri bams` that must return only history/docs mentions. Reason: two programs on one PC must never share keys,
ports or folders. Default ports: web **8090**, sync **8453** (BAMS uses 8080/8443 and may run on the same PC).

**P1.3 Remove the domain.** Empty `store.ENTITIES` except `settings` and `files`; remove `AREA_CHILDREN`, counters,
resolvers, area restriction in `auth.py` (replace later by category restriction), sample break areas, area routes
in `app.py`. Delete break-area tests; keep engine tests. **Gate: `python3 -m unittest test_unit test_convergence`
and `test_multinode` green before any domain code.** If an engine test depended on break areas, rewrite it on a
tiny neutral entity `notes` defined only in tests.

**P1.4 Design tokens and themes.** `css/tokens.css` exactly from `docs/DESIGN.md` §2; themes via
`<html data-theme="daylight|night|asphalt|highway|contrast">`; `data-density`, `data-font`, `data-size`,
`data-motion="off"`. Unit test `test_unit.ContrastTest` parses `tokens.css` and checks WCAG AA (4.5:1 text,
3:1 large/UI) for ink on canvas/surface and white/ink on brand/signal in every theme.

**P1.5 Fonts.** Download OFL fonts (IBM Plex Sans Arabic, IBM Plex Sans, Cairo, Tajawal, Noto Kufi Arabic) from
their official GitHub releases, subset with `tools/subset_fonts.py` (needs `fonttools` at build time only; commit
the resulting `.woff2` + `OFL.txt`). If the network blocks downloads, ask the owner; fall back to system fonts
(`"Segoe UI", Tahoma`) and keep the setting working.

**P1.6 i18n.** `js/i18n.js`: `t(key, vars)`, `setLang('ar'|'en')` sets `<html lang dir>`; plural-free keys.
Numbers: always Western digits (`Intl.NumberFormat('en')`), dates `dd/mm/yyyy` in both languages, times 24 h.
Test: every key in `en.js` exists in `ar.js` and vice versa; a static check fails on user-visible literals in
`js/views/*.js` (regex for `>[A-Za-z؀-ۿ]{3,}` inside template literals, with an allow-list).
CSS: only logical properties (`margin-inline-start`, `padding-inline`, `inset-inline-end`, `text-align: start`);
a check greps `css/` for `left|right` outside an allow-list (print, icons).

**P1.7 Shell.** Sidebar (groups: Operations · Fleet & people · Control · System; collapsible, remembers state),
topbar (search, language, theme, sync light for admins, user menu), content with page toolbar, side panel host
(stack of panels, `Esc` pops), toast area, modal. Router: hash routes with query string filters
(`#/trips?date=2026-09-28&cat=extra`). Motion per `DESIGN.md` §6 with `prefers-reduced-motion` respected.

**P1.8 Command palette + shortcuts.** `Ctrl/Cmd K` palette: fuzzy search over pages, actions and (from Phase 2)
trips by number, plates, drivers, people. Shortcuts table in `DESIGN.md` §5, registered in one place
(`shell.js` `KEYS`), shown in a `?` sheet and tooltips, disabled inside inputs, per-profile switch.

**P1.9 Settings → Appearance.** Per-user: theme, font, size, density, motion, language — stored in the user's
replicated preferences (so they follow the person to any PC) and applied before first paint (inline boot script
reads a small cookie to avoid a flash). Admin "lock for everybody" per option.

**P1.10 Help, tours, welcome slides skeleton.** `help.js` (BAMS Q&A pattern, both languages), `tours.js`
(spotlight steps defined per page), `slides.js` (welcome deck, 6 slides). Content filled as pages land.

**P1.11 Brand config.** `config.json` → `brand {name, short, logo, colors}`, `form {legal_text_en, legal_text_ar}`;
Settings → Organisation edits them (admin). Default name "Trip Orders" / "أوامر التشغيل", no logo.

Exit: engine tests green; browser smoke test opens every shell part in ar+daylight and en+night; screenshots
attached to the PR; Arabic report to the owner with screenshots.

### Phase 2 — Domain core

**P2.1 Entities** in `store.ENTITIES` (js key, column, kind, header). All get the engine's common columns.

| Entity | Fields (js key : kind) |
|---|---|
| `vehicles` | plate:T (display), plateKey:T (normalised, unique among active), type:T, categoryId:T, ownership:T (`own`/`rent`), vendor:T, active:B, notes:T, startKm:I (baseline) |
| `drivers` | name:T, nameKey:T, mobile:T (E.164 `+20…`), vendor:T, licenseNo:T, licenseExpiry:T (date), active:B |
| `departments` | name:T, code:T, active:B |
| `people` | name:T, nameKey:T, departmentId:T, mobile:T, isRequester:B, isPassenger:B, active:B |
| `places` | name:T, nameAr:T, key:T, aliases:J (list of keys), active:B |
| `routes` | name:T, stops:J (place ids), standardKm:I, billableKm:I |
| `tripCategories` | name:T, nameAr:T, exportSheet:T (`All Car`/`SUV Rent`/`Microbus Rent`/custom), hasSequence:B, openLimitHours:I, ratePerKm:R, ratePerOtHour:R, rateHistory:J (server-kept: [{until, ratePerKm, ratePerOtHour}] oldest first; a trip dated before `until` uses that entry - see `server/pricing.py`), vendor:T, order:I |
| `trips` | no:T, date:T, categoryId:T, vehicleId:T, driverId:T, requesterId:T, departmentId:T, destination:T (display route string), stops:J, purpose:T, gaApproved:T (`yes`/`no`/``), gaBy:T, gaAt:T, status:T, seq:I (Column1 override), startKm:I, endKm:I, startAt:T, endAt:T, startAtRecv:T, endAtRecv:T, routeText:T, billableKm:I, linkHash:T, linkNonce:T, linkExpiry:T, oldLinks:J (hashes of replaced links, newest first, max 5), boundDevice:T, source:T (`app`/`excel`/`paper`), importKey:T, notes:T, locked:B |
| `tripPassengers` | tripId:T, personId:T, freeText:T |
| `tripPhotos` | tripId:T, kind:T (`start_odo`/`end_odo`/`paper`), src:T (cas path), sha256:T, takenAt:T, fallback:B, eventId:T |
| `tripAmendments` | tripId:T, field:T, old:J, new:J, reason:T, by:T, at:T |
| `tripEvents` | tripId:T, uuid:T (gateway submission id, unique), type:T, payload:J, phoneAt:T, recvAt:T, deviceId:T |

Resolvers: `trips.status` = `rank:draft,sent,started,finished,closed,cancelled` (cancelled wins everything, the
driver's data is still kept and the trip is flagged); `endKm`,`endAt` follow `status`; everything else LWW
surfaced. `tripEvents` insert-only keyed by `uuid` (random id = `ev-<uuid>` so a double pull on two PCs produces the
**same id** → merges instead of duplicating). Raise `journal.SCHEMA` and `sync.SCHEMA_VERSION` whenever fields are
added after the first release.

**P2.2 `server/domain.py` — exact rules.**
- `norm_text(s)`: NFKC, remove tatweel `ـ` and zero-width chars, collapse whitespace, strip.
- `key_text(s)`: `norm_text` + casefold + Arabic unification (`أإآ→ا`, `ى→ي`, `ة→ه`, `ؤ→و`, `ئ→ي`) + drop
  punctuation except `-`.
- `norm_plate(s)` → `(display, key)`: Arabic-Indic digits → Western; split into Arabic letters and digits;
  display = letters joined by single spaces + space + digits (`ط و ي 6829`); key = letters without spaces +
  digits (`طوي6829`). Reject if no digits (keep as text, flag).
- `norm_mobile_eg(s)`: digits only; `01xxxxxxxxx` → `+201xxxxxxxxx`; `201…` → `+201…`; else keep + flag.
- `trip_no(year, pc_code, counter)` → `26-A-00233`. **Why the PC letter:** PCs create trips offline at the same
  time; a plain counter would collide. `pc_code` is assigned in the roster (A = administrator PC, B, C…).
  Uniqueness test with two offline PCs.
- `duration(startAt, endAt)` with full datetimes (crossing midnight is fine); `ot(d, threshold_h=12)` =
  `max(0, d - threshold)`.
- `odometer_chain(trips_of_vehicle)`: order by `startAt` (fallback date, then trip no.); for consecutive trips
  a→b: `b.startKm < a.endKm` → **back-step** (red on b); `b.startKm > a.endKm` → **gap** of `b.startKm-a.endKm`
  (info only, never a colour).
- `unusual_km(trip, history)`: history = finished trips with the same normalised destination key; needs ≥ 3;
  unusual if `|km - median| > max(0.25*median, 30)`.
- `drift(phoneAt, recvAt)`: > 10 min (setting) → flag; if the event was queued offline (payload `queued: true`),
  compare with the phone's own sequence instead and only flag phone-time going backwards.
- `trust(trip, ctx)` → `(colour, reasons[])`, deterministic, computed on read (cached, not replicated):

| Code | Colour | Rule |
|---|---|---|
| `R_BACKSTEP` | red | odometer back-step vs previous trip of the vehicle |
| `R_END_LE_START` | red | `endKm <= startKm` |
| `R_NO_PAPER` | red | status finished/closed, source `app`, no `paper` photo |
| `R_SECOND_DEVICE` | red | an event from a device ≠ `boundDevice` |
| `R_OPEN_TOO_LONG` | red | started and not finished after `openLimitHours` of the category (default 16) |
| `Y_FALLBACK_PHOTO` | yellow | any photo with `fallback` |
| `Y_NO_START_PHOTO` | yellow | finished without `start_odo` photo |
| `Y_KM_UNUSUAL` | yellow | `unusual_km` |
| `Y_DRIFT` | yellow | `drift` |
| `Y_CLOSED_BY_OFFICE` | yellow | finished by an office amendment |
| `Y_AMENDED` | yellow | any amendment after lock |
| `Y_IMPORT_WARN` | yellow | imported row with warnings (missing plate/km, unknown names) |
| `Y_BILLABLE_DIFF` | yellow | `billableKm` set and ≠ km (information for finance; setting may turn it off) |
| — | green | none of the above and status finished/closed |
Trips not finished have no colour (grey "in progress").

**P2.3 Screens (Phase 2 set).** Overview, Trips list, Trip panel, New trip (≤ 1 minute: keyboard-first, lists with
type-ahead, last used values remembered, "same as yesterday" for manager cars), Today board, Review queue,
Vehicles (+ odometer chain chart), Drivers, People, Departments, Places (aliases, merge), Categories, Amendments on
the trip panel ("Change after lock" asks for a reason), Recycle bin (engine). Each page registers: route,
permission, sidebar entry, palette entries, shortcuts, tour steps, help topics, empty state.

**P2.4 Permissions** (`auth.PERMISSIONS`, groups): Pages (`overview.view`, `trips.view`, `board.view`,
`review.view`, `fleet.view`, `people.view`, `reports.view`, `finance.view`, `logs.view`), Trips (`trips.create`,
`trips.edit`, `trips.cancel`, `trips.send`, `trips.approve` (GA), `trips.review`, `trips.amend`, `trips.delete`),
Fleet & lists (`vehicles.manage`, `drivers.manage`, `people.manage`, `places.manage`, `categories.manage`),
Excel (`excel.import`, `excel.export`), Money (`rates.manage`), Admin group (`users.manage`, `settings.manage`,
`backup.manage`, `devices.manage`, `gateway.manage`) = `ADMIN_PERMS`. Profiles: Administrator, Dispatcher,
GA Approver, Reviewer, Finance, Viewer (ticks listed in `auth.BUILTIN_PROFILES`). Category restriction replaces
the BAMS area restriction.

Exit: `tests/test_domain.py` covers every rule above with table-driven cases, including the September edge cases
(leading-space plate, the ~31,000 km typo back-step, crossing midnight, cancelled-vs-finished merge on two PCs).

### Phase 3 — Excel both ways

**P3.1 `xlsx_read.py`.** Input bytes → `Workbook{sheets:[Sheet{name, rows:[[Cell]], tables:[{name, ref, columns}],
merged:[ref]}]}`; `Cell{v, kind: 's'|'n'|'b'|'d'|'t'|'e'|None, f: formula or None, fmt}`. Parse
`xl/workbook.xml`, `_rels`, `sharedStrings.xml` (rich text runs joined), `styles.xml` (`cellXfs` → `numFmtId`;
built-in date ids 14–22, 45–47 and custom codes containing `d`,`m`,`y`,`h`,`s` outside quotes/brackets = date/time),
sheets (`t="s"`, `inlineStr`, `b`, `e`, `str`, numbers; formulas keep `<f>` and use cached `<v>`), tables
(`xl/tables/*.xml` via sheet rels), merged cells. Dates: 1900 system with the Lotus 1900-02-29 bug
(serial ≥ 61 → minus 1 day) and `date1904` flag. Times = fractional day. Zip-bomb guard: max 50 MB uncompressed,
max 200k cells. Test against openpyxl when installed, and against hand-written tiny xlsx files in tests.

**P3.2 Workbook layout spec** (`excel_io.LAYOUT`) — measured from the real file:

| Sheet | Excel Table | Columns (exact header text, in order) | Formulas |
|---|---|---|---|
| `All Car` | `Table1`, style `TableStyleMedium2`, row stripes | `Date, Driver Name, Car Plate, Requester, Employee Name, Trip Category, Depatment, Destination, Column1, Strat KM, End KM, " KM", Misr car KM, Start, End, OT Hours` (A–P) | L = `+Table1[[#This Row],[End KM]]-Table1[[#This Row],[Strat KM]]` (calculated column); P = `IF(O2-N2>TIME(12,0,0),O2-N2-TIME(12,0,0),0)` |
| `SUV Rent` | none (autofilter `A1:O…`) | same without `Column1` (A–O) | K = `+J2-I2`; O = `IF(N2-M2>TIME(12,0,0),N2-M2-TIME(12,0,0),0)`; totals row after data: I=`TTL`, K=`+SUM(K2:Kn)`, L=`+SUM(L2:Ln)`, O=`SUM(O2:On)` |
| `Microbus Rent` | `Table2` | `#` then the `SUV Rent` columns (A–P) | A = `+ROW()-1`; L = `+Table2[[#This Row],[End KM]]-Table2[[#This Row],[Strat KM]]`; P = OT on O/N; totals row after the table: J=`TTL`, L=`SUBTOTAL(109,Table2[[ KM]])`, M=`SUM(M2:Mn)`, P=`SUM(P2:Pn)` |

Formats: Date `mm-dd-yy` (numFmt 14), Start/End/OT `h:mm` (numFmt 20). Frozen first column (`All Car`, `SUV Rent`)
or first two (`Microbus Rent`), gridlines hidden. Column widths from the original (`A 11.9, B 28.1, C 13.4, D 24.6,
E 26.9, F 17.3, G 15.6, H 66.3, I 14.6, J 13.1, K 12.3, L 9, M 16, N 9.7, O 8.9, P 13.6`). Real file facts: the
`Table1` ref runs to row 279 with empty template rows (we write the ref to the last data row); `All Car` has **no**
Start/End times at all while `SUV Rent` has them. Note: the Excel OT formula uses times only, so it is wrong for
trips crossing midnight — the "same as today" export keeps the formula (fidelity) and the clean export shows the
true OT from full datetimes.

**P3.3 `xlsx.py` writer extension.** Add: styles part with number formats and bold header; date/time cells as
serial numbers with style; formulas `<c><f>…</f><v>cached</v></c>` (always write the cached value so viewers
without recalculation show numbers; set `fullCalcOnLoad="1"` in `workbook.xml`); Excel Table parts
(`xl/tables/tableN.xml` + sheet rels + content types, `calculatedColumnFormula`, `tableStyleInfo`); frozen panes;
`showGridLines="0"`; column widths; sheet names escaped. Keep the old API working for the engine's exports.

**P3.4 Import.** `POST /api/import/preview` (xlsx upload) → preview id, per row: sheet, row number, parsed values,
status `new` / `duplicate` (same `importKey`) / `problem`, matches (driver, vehicle, requester, passengers,
department, category, stops) each `matched` / `suggested (score)` / `new`. `importKey` = SHA-256 of
`key_text` of (sheet, date, driver, plateKey, requester, employee, category, department, destination, startKm,
endKm). Passenger split: `Employee Name` split on ` - ` / `-` only when every part matches a known person;
known non-person words (`Visitor`, `Early leave`, `EHS Audit`, `Audit`, `Cover …`) → `purpose`. Destination split
on `-` into stops matched to places by key/aliases; unknown stops get suggestions with
`difflib.SequenceMatcher` ratio ≥ 0.85 (e.g. `Musiem`/`Mueiem` → `Museum`). The preview screen shows coloured rows,
a "suggested merges" list the user accepts one by one, and totals. `POST /api/import/commit {previewId, accepted
merges}` writes **one** changeset per import (label "Excel import <file> <n> trips"), trips `source: excel`,
`locked: true`. Nothing is written before confirm. Re-import = all duplicates, nothing written. A verified backup
is taken before commit (engine pattern).

**P3.5 Export.** `GET /api/export/month?ym=2026-09&layout=today` → the three sheets per P3.2 (category →
`exportSheet`; `Column1` = `seq` or the daily order of `hasSequence` trips); `layout=clean` → sheets `Trips`,
`By vehicle`, `By driver`, `By department`, `Overtime`, `Vendor reconciliation`, `Anomalies` with proper headers
(language of the user, header row bold, numbers typed, photo links as text URLs to the office app).

**P3.6 Samples.**
- `tools/make_sample_workbook.py --seed 26` writes a **synthetic** workbook with exactly the real structure
  (P3.2) and the same statistical shape: 232 `All Car` trips over the working days 1–28 Sep (141 manager car,
  91 extra), 11 SUV, 4 microbus, ~41 drivers, ~44 cars, 20 departments, 54 requesters, ~89 destinations with
  spelling variants, empty Start/End in `All Car`, 12 odometer back-steps (one ≈ 31,000 km), 56 billable
  differences, 8 trips without km, 7 without plate, a leading-space plate, duplicate-by-whitespace driver names.
  Fake Egyptian-style names and plates. Committed output: `tests/fixtures/sample_sep26_synthetic.xlsx` +
  `tests/fixtures/sample_expected.json` (the measured facts).
- **Owner's decision (2026-09-29): demo data = the real sheet ("زي الشيت").** First start offers
  "Load my real workbook" (file picker → normal import, badged "Sample" and removable in one step) and
  "Try with the synthetic sample". Real names never go into the repository because the repository is public;
  they live only in the office data folder.
- Tests: synthetic always; real file tests run only when `samples/private/Extra_Sep-26_Recovered.xlsx` exists.

**P3.7 Round-trip test.** Import sample → export `today` → read both with `xlsx_read` → every non-formula cell equal
(after the documented normalisation: trimmed plate display, unified driver name only when the user accepted the
merge — the test accepts none) and formulas equal as text; row count per sheet equal; totals rows present.

Exit: `test_xlsx.py`, `test_excel_io.py` green; the exported file opens in LibreOffice headless without repair
(`soffice --headless --convert-to csv` in CI if available, else openpyxl load).

### Phase 4 — Gateway and driver page (local first)

**P4.1 Worker skeleton.** `gateway/src/worker.js` (ES module, no dependencies). Routes:

| Method + path | Who | Does |
|---|---|---|
| `GET /t/:token` | driver | serves `public/index.html` (token is read by JS from the path; never logged) |
| `GET /app/*` | driver | static assets, `Cache-Control: immutable` with version in the file name |
| `GET /api/card/:token` | driver | card JSON for `sha256(token)`; `410` with `{cancelled:true}` if cancelled; `404` unknown |
| `POST /api/bind/:token` | driver | `{deviceId}` → `{bound:true}` or `{bound:false, readOnly:true}` (first device wins) |
| `POST /api/event/:token` | driver | JSON event (P4.3) → `{ok, recvAt}` = ✓✓; idempotent by `uuid` |
| `PUT /api/photo/:token/:uuid` | driver | raw `image/jpeg` body ≤ 600 KB, headers `X-Kind`, `X-Sha256`, `X-Fallback`; idempotent |
| `PUT /office/cards` | office (HMAC) | batch upsert/delete cards |
| `GET /office/inbox?after=<cursor>&limit=100` | office | events + photo ids not yet acked |
| `GET /office/photo/:uuid` | office | photo bytes (reassembled) |
| `POST /office/ack` | office | `{events:[uuid], photos:[uuid]}` → deleted |
| `GET /office/status` | office | counts, oldest unacked age, version |

D1 schema (`gateway/schema.sql`): `cards(token_hash PK, trip_id, body TEXT, cancelled INT, bound_device TEXT,
expires_at INT, updated_at INT)`, `events(uuid PK, token_hash, trip_id, type, body TEXT, device_id, phone_at TEXT,
recv_at INT)`, `photos(uuid, part INT, data BLOB, sha256, size, kind, fallback INT, trip_id, recv_at, PRIMARY KEY
(uuid, part))`, `nonces(nonce PK, at INT)`, `rate(key PK, window INT, count INT)`. Photos are split into parts of
≤ 512 KB (verify the current D1 row/value limit in the official docs first; adjust). Daily cron (Worker scheduled
event) deletes items older than `RETENTION_DAYS` (30) and expired cards.

**P4.2 Security.** Office HMAC: headers `X-TO-Time` (unix s), `X-TO-Nonce` (random 128-bit), `X-TO-Sig` =
hex HMAC-SHA256(secret, `method\npath\ntime\nnonce\nsha256(body)`); reject skew > 300 s or reused nonce. Driver
limits: 60 requests/10 min per token, 300/10 min per IP, bodies ≤ 600 KB, JSON ≤ 16 KB. Headers: CSP
`default-src 'self'; img-src 'self' blob: data:; connect-src 'self'`, `X-Content-Type-Options`,
`Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(self), geolocation=()`. No CORS (same origin).
Never log paths containing tokens (custom logger strips `/t/…` and `/api/*/:token`).

**P4.3 Event format** (driver → gateway → office):
```json
{"uuid":"<uuid v4 made on the phone>","v":1,"type":"start|end|route|note","tripId":"…",
 "deviceId":"<random id kept in IndexedDB>","seq":3,"phoneAt":"2026-09-28T09:41:12+03:00","queued":false,
 "data":{"startKm":291382}}               // end: {"endKm":291747,"routeText":"…","stops":["…"]}
```
Photos reference the event: `X-Event: <uuid>`. Card format (office → gateway): `{tripId, no, date, driverName,
plate, vehicleType, destination, stops, passengers:[names], category, lastKm, cancelled, expiresAt, lang}` —
nothing else.

**P4.4 Driver page.** Files in `gateway/public/`. Screens per master prompt §5.3 (مشوارك · البداية · في الطريق ·
النهاية · تم) with a progress indicator, ✓/✓✓ badge, Arabic default + English toggle, dark mode by
`prefers-color-scheme`, outdoor high-contrast option. `outbox.js`: IndexedDB stores `drafts` (per trip, saved on
every input), `outbox` (events + photo blobs), `meta` (deviceId). Sending: try now; on failure retry with backoff
1 s → 2 → 4 … max 5 min; also on `online`, on `visibilitychange` visible, on page open; Background Sync where
available. Delete from outbox only after the gateway answered `ok`. `camera.js`: `getUserMedia({video:{facingMode:
'environment'}})`, capture to canvas, resize long side 1280, burn a bottom band with trip no., date, time, plate,
JPEG quality stepped down until ≤ 250 KB; fallback `<input type=file accept=image/* capture=environment>` sets
`fallback: true`. `sw.js`: cache-first for `/app/*` and the shell, network-first for `/api/card`. Budget check in
tests: sum of gzip sizes of first-load files < 150 KB excluding fonts.

**P4.5 Local run + tests.** `npx wrangler dev --local` with a local D1; `gateway/test/*.test.js` with Node's test
runner against `unstable_dev`/Miniflare: every endpoint, limits, HMAC replay, idempotency, cancelled card, second
device, retention cron, CPU time per request with a 300 KB photo (must stay well under 10 ms of CPU; log it).
Playwright mobile (Pixel 5 viewport) `tests/test_e2e_driver.py`: full trip online; network offline after screen 2
then back; page closed and reopened mid-trip; second browser context = second device; cancelled trip; phone clock
+15 min.

### Phase 5 — Office ↔ gateway

**P5.1 `gateway_client.py`.** Thread started by the office app when `gateway.url` and `gateway.secret` are set.
Push: on trip create/change/cancel, enqueue card; worker sends batches (`PUT /office/cards`). Pull: every
`poll_seconds` (60) → `GET /office/inbox` → for each event: build the trip changes (status, km, times, route,
`tripEvents` insert with id `ev-<uuid>`) and commit them as **one normal changeset** with actor "Driver link
(<driver name>)"; for each photo: download, verify SHA-256, store content-addressed, insert `tripPhotos`; then
`POST /office/ack`. Idempotent: an event whose `ev-<uuid>` already exists is acked without changes. Backoff 5 s →
10 min when offline. Status for the UI: last contact, last error, items waiting, oldest age.

**P5.2 Secrets.** `link_secret` and `gateway_secret` created on the administrator PC at gateway setup, replicated
to office PCs only through authority-signed admin changesets into `auth.db` (never in `trips.db`, backups of it
are fine because `auth.db` copies are local like BAMS), never shown again after setup except "replace".
Link token = base64url(HMAC-SHA256(link_secret, `TO-LINK1|<tripId>|<nonce>`)[:16]) → any office PC can
re-create the link for "resend"; `trips.linkHash` = SHA-256(token) hex; "replace link" = new nonce.

**P5.3 Sending.** Trip panel button "ابعت على واتساب / Send on WhatsApp" → `https://wa.me/<mobile without +>?text=`
+ URL-encoded message from settings template (both languages) containing trip no., date, car, destination and the
link. Opens in a new tab; the action is logged; status `draft → sent`.

**P5.4 Printable order.** `#/print/trip/<id>` → A4 page reproducing the paper form layout generically (fields of the
form, legal text from config, trip no. big, QR of the trip no. only — reuse BAMS `lib/qrcode.min.js`), prints
with `print.css`. Both languages.

**P5.5 Gateway settings page + setup guide.** Settings → Gateway: URL, secret (generate / replace), test
connection, poll interval, retention, status card. `docs/GATEWAY_SETUP.md` (Arabic, owner): create free
Cloudflare account, create D1, deploy with one command or from the dashboard, paste URL and secret.

### Phase 6 — Reports and presentation

Reports (all filterable by month, category, vendor, department; export clean xlsx; print):
- **Month sheet** (= export today layout on screen).
- **Per vehicle / driver / department / requester:** trips, km, hours, OT, trust mix.
- **Vendor reconciliation:** per vendor/category: sum km (from odometers) vs sum billable km, difference km ×
  `ratePerKm` = money, list of trips with differences.
- **Cost allocation:** per department: km × rate + OT hours × OT rate.
- **Overtime:** per driver per day.
- **Anomalies:** back-steps, gaps (info), drift, missing photos, unusual km, never closed, duplicates from import.
Charts: inline SVG (BAMS `charts` pattern), following the `dataviz` skill rules; colours from tokens.
Presentation mode `#/present?ym=2026-09`: full-screen slides generated from the data (month in numbers, km by
department, top routes, OT, vendor difference, anomalies), arrows/space to move, `P` to print as PDF.
Live board polish: "on the road" with elapsed timers, count-up numbers, amber pulse, auto-refresh.

### Phase 7 — Hardening and delivery

Independent review (security + correctness) with a separate agent, fix every verified finding with a regression
test; installer `installer/trip-orders.iss` (BAMS pattern, new AppId GUID, new folders, ports 8090/8453);
workflow builds and publishes `TripOrders-Setup-<version>.exe`; `README.md`, `GUIDE_Dispatcher.md`,
`GUIDE_Admin.md`, `GUIDE_Driver.md` (one page, Arabic, with pictures), `docs/RELEASE_NOTES.md`.

### Phase 8 — Backlog

End-to-end sealing (X25519 + AES-GCM on the phone, pure-Python X25519 on the office side with RFC 7748 vectors);
WhatsApp Cloud API; odometer OCR; start/end location (opt-in); standing driver link listing today's trips; SMS.

---

## Part D — Office API (added to the engine's `/api/*`)

| Method + path | Permission | Notes |
|---|---|---|
| `POST /api/commit` | per entity (engine) | generic saves (lists, trips) with server guards from `domain.py` |
| `POST /api/trips/new` | `trips.create` | allocates `no`, returns trip |
| `POST /api/trips/:id/link` | `trips.send` | `{replace:bool}` → `{waUrl, url}`; pushes card |
| `POST /api/trips/:id/cancel` | `trips.cancel` | reason required; card cancelled |
| `POST /api/trips/:id/approve` | `trips.approve` | `{yes:bool}` |
| `POST /api/trips/:id/amend` | `trips.amend` | `{field, value, reason}` → amendment + change |
| `POST /api/trips/:id/release-device` | `trips.amend` | clears binding |
| `GET /api/trips/:id/trust` | `trips.view` | colour + reasons |
| `GET /api/board?date=` | `board.view` | today board data |
| `POST /api/import/preview` · `POST /api/import/commit` | `excel.import` | P3.4 |
| `GET /api/export/month` | `excel.export` | P3.5 |
| `GET /api/reports/<name>` | `reports.view` / `finance.view` | Phase 6 |
| `GET/POST /api/gateway/*` | `gateway.manage` | settings, test, status, pull-now |

Every endpoint: server-side permission check, CSRF origin check (engine), audit entry, JSON errors
`{error, message_key}` where `message_key` is an i18n key.

---

## Part E — Checks before every push

```
cd tests && python3 -m unittest test_unit test_convergence test_domain test_xlsx test_excel_io   # fast, always
python3 -m unittest test_multinode            # before a PR (≈ 3 min)
python3 -m unittest test_e2e_browser test_e2e_driver   # when screens changed
cd gateway && node --test test/                # when gateway changed
grep -rn "BAMS" server js css | grep -v "# from BAMS"   # must be empty after P1.2
```
Do not edit `server/` or `js/` while multi-PC or browser tests run.

## Part F — Pitfalls (inherited + new; add every new one)

- Record ids random, never count+1; trip numbers carry the PC letter.
- `<meta name="referrer" content="no-referrer">` breaks form POST origin checks (BAMS lesson).
- New replicated fields → `ALTER TABLE` for old DBs + schema raise.
- Link previews (WhatsApp) GET the link: GET must never change state; binding happens on an explicit POST.
- iOS Safari: no Background Sync, may evict IndexedDB after 7 days of no use → retry on open; keep outbox small;
  never delete before ✓✓.
- `getUserMedia` needs HTTPS (the gateway is HTTPS; local tests use `localhost`, which counts as secure).
- Excel: header `" KM"` has a leading space; `Depatment` and `Strat KM` are misspelt on purpose — never "fix" them.
- Excel dates: 1900 leap-year bug; times are fractions; formulas need cached values.
- RTL: never use `left/right`; mirror directional icons; numbers stay LTR inside RTL text (`<bdi>` / `dir="ltr"`
  on km, plates digits, trip numbers).
- Tokens only as hashes in the office DB and gateway; never in logs, Excel, error messages or the activity log.
- The repository is public: never commit the owner's workbook, form, photos, secrets or real names.
- Kill test servers by PID, not `pkill -f` (matches your own shell).
- Wait for automatic PR reviews too before merging; merge only when the owner says so.

## Part G — Owner answers log

| Date | Question | Answer |
|---|---|---|
| 2026-09-29 | Demo data: real names or anonymised? | **Real, like the sheet.** Implemented as "load my real workbook" at first start (data stays in the office folder); repository keeps only the synthetic sample because it is public. |
| 2026-09-29 | Other questions (Misr car KM, default language, location, rates, Cloudflare account) | not answered yet → defaults in `docs/PLAN.md` §2 |
