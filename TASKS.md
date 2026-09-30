# Tasks – where to continue

Tick `[x]` when a task is done (code + tests + docs). Details of every ID: `docs/EXECUTION_PLAN.md` Part C.
Add sub-tasks you discover under the task that caused them. Never delete a line; strike through with a reason.

## Phase 0 – Study & plan
- [x] P0.1 Study BAMS, the form and the workbook → `docs/REFERENCE_STUDY.md`
- [x] P0.2 Plan, defaults, open questions → `docs/PLAN.md`
- [x] P0.3 Design system → `docs/DESIGN.md`
- [x] P0.4 Playbook for every agent → `docs/EXECUTION_PLAN.md`, skill, this file
- [ ] P0.5 Owner answers the remaining open questions (defaults apply meanwhile) – see PLAN §4

## Phase 1 – Engine fork + shell
- [x] P1.1 Copy the engine from BAMS (commit 5f5b3ce). Not copied: `runtime/` portable Python (21 MB binary) – add it at delivery (P7.2) or use system Python for `start.bat`
- [x] P1.2 Rename BAMS → TO (strings, headers, folders, ports 8090/8453, own installer AppId)
- [x] P1.3 Remove the break-area domain; engine tests green (gate): unit+convergence 32, multi-PC 35
- [x] P1.4 Tokens + 5 themes + contrast test (`tests/test_design.py`)
- [x] P1.5 Fonts bundled (OFL) via `tools/install_fonts.py` (fontsource packages, 34 woff2, 0.8 MB)
- [x] P1.6 i18n EN/AR + RTL + checks (key parity, no literal words in templates, logical CSS only, no colours outside tokens)
- [x] P1.7 Shell: sidebar, topbar, side panels, router with filters, motion
- [x] P1.8 Command palette + shortcuts (palette lists pages/actions; trips/plates/drivers search is added with their pages in P2)
- [ ] P1.9 Settings → Appearance: DONE on this device (localStorage). TODO: per-user copy on the server (`userPrefs` entity, own id only) and the admin lock per option
- [x] P1.10 Help, tours, welcome slides
- [ ] P1.11 Brand config: TODO Settings → Organisation (name, short name, logo, colours) + `config.json` `brand`/`form` keys; the name is still the generic dictionary text

## Phase 2 – Domain core
- [x] P2.1 Entities + resolvers (done in phase 1a; `trips.status` rank, followers)
- [x] P2.2 `domain.py` rules + `test_domain.py` (23 cases) + `tripsvc.py` (numbering, amend, cancel, approve, insights) + `test_trips_api.py` (7)
- [x] P2.3 Screens: Overview, Trips, Trip panel, New trip, Today board, Review queue, Vehicles, Drivers, People + Departments, Places, Categories (Settings → Trips & rules), Activity log, Recycle Bin + backups (Settings → Data). TODO later: standard routes screen (entity exists), odometer chain chart on the vehicle page, per-place merge tool
- [x] P2.4 Permissions + profiles + category restriction (Settings → People & access: users, personal links, tick boxes, profiles)

## Phase 3 – Excel + Word
- [x] P3.1 `xlsx_read.py` (dependency-free reader, dates/times/durations, zip-bomb limits)
- [x] P3.2 Layout spec (`excel_io.TODAY_HEADERS`, `HEADER_FIELDS`)
- [x] P3.3 `xlsx_write.py`: formulas with cached values, dates, styles, tables, panes, totals
- [x] P3.4 Import preview + commit (`/api/excel/preview|commit`, review UI in `js/views/excel.js`)
- [x] P3.5 Export "same as today" + "clean report" (10 sheets, EN/AR) + empty template
- [x] P3.6 Synthetic sample (`tools/make_sample_workbook.py`, `tests/fixtures/`); real workbook stays in `samples/private/`
- [x] P3.7 Round-trip test (`test_excel_io`): import → export equals the original cells
- [x] P3.8 Word: `docx_write.py`, `docx_read.py`, `word_io.py` (trip order form EN/AR blank or filled, read filled forms incl. the original paper form, monthly report), `/api/word/*`, `test_word_io`
- [x] P3.9 Review step, alerts, plain error messages, month summary, Guide (12 Q&A + error list) in the Excel page; browser test `ExcelPageTest`
- Test map: `test_xlsx` (reader/writer), `test_excel_io` (plan, alerts, API flow), `test_word_io` (times/dates/forms/API), `test_e2e_browser.ExcelPageTest`

## Phase 4 – Gateway + driver page
- [x] P4.1 Worker routes + D1 schema + daily cleanup (`gateway/src/worker.js`, `schema.sql`); photos stored as one BLOB (<= 600 KB, D1 row limit is 2 MB)
- [x] P4.2 Security: HMAC (time + nonce + body hash), rate limits, size limits, CSP/nosniff/no-referrer headers, tokens stored only as hashes
- [x] P4.3 Event + card formats (see `worker.js` header and `gateway_client.card_for`)
- [x] P4.4 Driver page `gateway/public/` (5 steps, IndexedDB drafts + outbox, retry with backoff, live camera with stamp, gallery fallback marked, service worker, AR/EN, dark + high contrast)
- [x] P4.5 Tests: `gateway/test/gateway.test.js` (15, node:test with a D1 stand-in), `tests/test_e2e_driver.py` (7: online trip, offline + reopen, second phone, cancelled/unknown, low km, gallery fallback, language). NOT yet run against real Cloudflare (no account in this sandbox) - do the smoke test in `docs/GATEWAY_SETUP.md` step 9
- [x] P4.6 Single-file bundle `gateway/build.js` -> `dist/trip-orders-gateway.js` (pasteable in the Cloudflare dashboard); attached to the release by CI

## Phase 5 – Office <-> gateway
- [x] P5.1 `gateway_client.py`: push cards, pull events/photos, apply as one change per trip, ack; idempotent (`ev-<uuid>`, `ph-<uuid>`); time zone-safe drift
- [x] P5.2 Secrets in `gateway.json` per PC (never in the shared DB/logs); setup code for other PCs; link token = HMAC of trip + nonce (only its hash is stored)
- [x] P5.3 WhatsApp `wa.me` button, copy link, new link, free the phone (trip panel)
- [x] P5.4 Printable order (A4, QR of the trip number) + Word form
- [x] P5.5 Settings -> Mailbox + `docs/GATEWAY_SETUP.md` (Arabic, dashboard steps)
- Test map: `test_gateway_client` (9), `test_e2e_link_ui` (2), plus the driver and gateway tests above

## Phase 6 – Reports & presentation
- [x] P6.1 `reports.py` summaries per vehicle/driver/department/requester/category/day + top routes; `/api/reports`
- [x] P6.2 Vendor reconciliation, cost allocation, overtime (page + Excel clean export + Word report)
- [x] P6.3 Anomalies list
- [x] P6.4 Reports page with bar charts and presentation mode (`js/views/reports.js`); browser test `ReportsPageTest`

## Phase 7 – Hardening & delivery
- [ ] P7.1 Independent review + fixes (self-review of security points done: hashes only, HMAC, limits, escaping; a second reviewer is still recommended)
- [x] P7.2 Installer + release workflow (old-version page removed). Portable `runtime/python` for start.bat is NOT added (the installer is the delivery path)
- [x] P7.3 Guides (dispatcher, admin, driver) + release notes

## Phase 8 – Backlog
- [ ] Sealing · WhatsApp API · OCR · location · standing driver link · SMS
