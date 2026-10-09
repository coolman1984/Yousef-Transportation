<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

## Current work queue — first sale

Use LAUNCH_SCOPE.md gates L1–L6 before the historical unchecked backlog. Record verified evidence, not assumptions. Later-release work below stays available; do not tick it complete merely because it is deferred.

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

## Commercial readiness (`COMMERCIAL_READINESS_EXECUTION_PLAN.md`) – ledger
Status words: not started / in progress / implemented—verification pending / verified / blocked. Only `verified` closes a finding.
- [x] F06 Windows rebuild handle + refusal while running – verified (`test_unit.ToolsTest`, 3 tests, Windows, Python 3.12)
- [x] F01 state/report/export projection – verified (`test_permissions` a–d). Open: delta endpoints (none yet), `tripEvents` payloads, link hashes in state
- [x] F02 plain save cannot touch approval/status/link/lock/locked trips/amendments – verified (`test_permissions` e–h, `test_trips_api`)
- [x] F12 dispatcher cancel works; closed-trip cancel needs amend/review – verified (`test_permissions` i–j). Open: finance-only rate update path (`rates.manage` vs `categories.manage`, T14)
- [x] F03 trip photo authorization + private cache – verified (`test_permissions` k). Open: browser account-switch check, thumbnails if added
- [x] F08 driver events reduce the same in any arrival order; late start fills a finished trip; closed/cancelled untouched; malformed event cannot raise; one bad trip no longer blocks the pull – verified (`test_gateway_client` UnitTest f–h, IntegrationTest f; Linux, Python 3.13). Open: reviewed-correction check beyond closed/cancelled, event schema validation at the Worker (T11), durable office receipt vs mailbox receipt (F09)
- [x] F05 replaced link is removed from the gateway and tombstoned (a stale PC cannot republish it); `trips.oldLinks` keeps the hashes so any PC delivers the removal – verified (`gateway.test.js` 2 new, `test_gateway_client` IntegrationTest d). Open: device-release intent is still in memory (`GatewaySync.release`), link expiry policy (F19), old phone's unsent offline items stay on that phone, mixed-version PCs in one cluster (T28)
- [x] F07 (first slice) trips are priced with the rate of their own date: `server/pricing.py`, ``tripCategories.rateHistory` kept by the server (client cannot write it, full restore can), reports/allocation/reconciliation per trip, history is money information – verified (`test_pricing` 10 incl. real Chrome, Linux, Python 3.13). Open: rate editing by `rates.manage` only (T14), explicit "effective from" date / retro-correction, Decimal money and rounding point, missing rate shown as incomplete not 0 (T15), calculation snapshot on approval, two PCs editing a rate at once
- [x] F04 (non-breaking part) Host-header allow-list (DNS rebinding; the first administrator could be created through a foreign name), idle timeout 60 s, `max_connections`, damaged `Content-Length` answered – verified (`test_network` 8, Linux). **Owner decision 2026-10-06:** staff open the program from the same network AND from other networks, so `host` stays `0.0.0.0` and the web port stays reachable; protection is `server/netpolicy.py` (private networks only, `allowed_networks` to narrow; verified in `test_network` 13). Still open: plain HTTP crosses the company network (credentials in clear unless the WAN/VPN encrypts), HTTPS for the web port needs a certificate story, installer firewall `profile=any` (a `remoteip` private-ranges rule is the next step but cannot be tested without Windows), T08 ACLs
- [x] F13 (data level) backup sets are serialized, uniquely named, written under temporary names, verified (integrity, size, SHA-256), manifest with the history watermark, data file renamed last, failed run leaves the last good set, full-disk check, photos copied whole, account-only change makes a backup due, tampered set refused, banner in Settings > Data, clean-PC drill (`test_backup` 13 incl. real Chrome, Linux). `tool restore-set` for a clean PC (data level). Open: the field drill on a real second Windows PC (LAUNCH_SCOPE L4), identity recovery (the PC's keys in `data/node` and `gateway.json` are deliberately NOT in a set; the administrator key can be sealed with `export-authority`; a general sealed key package is not built), mixed-version restore, key rotation, interrupted copy on Windows, a backup destination that is a network share stays refused
- [x] F11 one time contract (`server/tz.py`, `domain.instant/parse_dt/duration/business_now/link_expiry`): aware times are exact instants, zone-less times are Cairo, durations are elapsed time (mixed offsets = 3 h, DST nights right), shown times Cairo, phone in a wrong zone corrected at ingestion with the original text + exact UTC receive time kept in the event payload, link expiry an aware UTC instant (same on every PC; the old naive-as-UTC reading made links 3 h late), "time in the clock-change hour" flag `Y_TIME_UNCLEAR`; built-in Egypt rules proven equal to the tz database for every half hour 2023-2030 – verified (`test_time` 10, `test_gateway_client` g; Linux, Python 3.13). Open: Windows run (no tz database there - the built-in rules are the path in the installed program), per-category override of the business zone (not needed for one-company pilots), Excel import of times typed as text with an offset, `startAtRecv` drift across a clock change (minutes only)
- [ ] T01 Windows test harness: `test_multinode` cannot run on Windows (harness `Server.stop` sends `SIGINT`, unsupported -> `setUpClass` errors, 10 of 12 tests; identical on the untouched commit 9f5ef29) and leaks the server processes it started (kill them by hand). `T35_SecondReview.test_d_many_wrong_logins_are_cut_short` is flaky on Windows (`WinError 10053`, 2 of 4 runs on the untouched commit). So the multi-PC suite gave NO evidence for slice 1 - run it on Linux CI or fix the harness first
- [x] F16 import error contract: stable codes (`FormatError.code`, `ImportError_.code`, `WordError.code`, `OfficeError.code`, `BadRequest.code` -> API `{error, code}` -> `js/views/excel.js` `CODE_KEY`): drm encrypted pdf image xlsb old empty unknown big damaged wordGiven sheetGiven noTable officeMissing officeTimeout officePassword officeFailed noColumns noTrips previewExpired nothingToImport noForm needCategory; the two refusal tests no longer depend on the Office installed on the PC (root cause reproduced: with Office present the DRM sample got Office's answer); a refused import changes no data and repeats no file content – verified on Linux (`test_import_errors` 6, `test_formats`; Office pretend-present). **Windows re-run of `test_formats` still to do** (the two known failures should be gone). Open: formula-injection review of exports (T18 remainder), the real Excel/Word COM run on an actual Office PC
- [x] F09 three receipt levels: phone (IndexedDB) -> mailbox (`sentAt`) -> office (`officeAt`, from the new gateway `receipts` table written on ACK and read by `POST /api/receipts/<token>`: office / mailbox / unknown); photos kept on the phone until the office receipt; "unknown" (purged by retention or never stored) is sent again by the same uuid (idempotent at gateway and office); office warning after 3 days (`late`, `oldestSeconds`); ACK batched (about 5 statements for 120 events instead of 120); lazy table for old mailboxes; service worker cache `to-driver-2` – verified (`gateway.test.js` 21, `test_e2e_driver` 8 incl. real Chrome: three ticks, photos kept, mailbox loses items and the phone resends; `test_gateway_client` h, i). Open: crash at every boundary of upload/apply/ACK in a real cloud, phone storage quota warning when the office is off for weeks, D1 statement budget of the other routes (F10), update of the page on phones mid-trip (F14), the first load after an update still runs the old script once
- [ ] F10, F14, F15, F17–F20 – not started (see the plan, §4 and T04–T34)
- Test map: `test_permissions` (read/write/photo permissions through the real server), `test_e2e_browser.ReportsPageTest.test_reviewer_without_money_permission_sees_no_rates_cards` (needs `TO_CHROMIUM`, e.g. the Chrome path on Windows)

## Phase 8 – Backlog
- [ ] Sealing · WhatsApp API · OCR · location · standing driver link · SMS
