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

## Phase 3 – Excel
- [ ] P3.1 `xlsx_read.py`
- [ ] P3.2 Layout spec (`excel_io.LAYOUT`)
- [ ] P3.3 Writer: formulas, dates, styles, tables, panes
- [ ] P3.4 Import preview + commit
- [ ] P3.5 Export today + clean
- [ ] P3.6 Samples: synthetic generator + fixtures; "load my real workbook" at first start
- [ ] P3.7 Round-trip test

## Phase 4 – Gateway + driver page
- [ ] P4.1 Worker routes + D1 schema + retention cron
- [ ] P4.2 Security (HMAC, limits, headers, no token logs)
- [ ] P4.3 Event + card formats
- [ ] P4.4 Driver page (5 screens, outbox, camera, stamp, service worker)
- [ ] P4.5 Local run + gateway tests + mobile browser tests

## Phase 5 – Office ↔ gateway
- [ ] P5.1 `gateway_client.py` push/pull/ack/idempotency
- [ ] P5.2 Secrets + link tokens
- [ ] P5.3 WhatsApp sending
- [ ] P5.4 Printable order
- [ ] P5.5 Gateway settings page + `docs/GATEWAY_SETUP.md`

## Phase 6 – Reports & presentation
- [ ] P6.1 Month sheet, per-entity reports
- [ ] P6.2 Vendor reconciliation + cost allocation + overtime
- [ ] P6.3 Anomalies
- [ ] P6.4 Presentation mode + live board polish

## Phase 7 – Hardening & delivery
- [ ] P7.1 Independent review + fixes
- [ ] P7.2 Installer + release workflow (also remove the 'data of the old version' page of the installer, add the portable runtime)
- [ ] P7.3 Guides (dispatcher, admin, driver) + release notes

## Phase 8 – Backlog
- [ ] Sealing · WhatsApp API · OCR · location · standing driver link · SMS
