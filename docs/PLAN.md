# Plan — Trip Orders (working name)

Source of truth for scope: the owner's master prompt (2026-09-29). This file records how we execute it.
Step-by-step playbook for every agent: `docs/EXECUTION_PLAN.md`; progress: `TASKS.md`.
Design: `docs/DESIGN.md`. Reference study: `docs/REFERENCE_STUDY.md`.
Supersedes the first idea note (`PROJECT_PLAN.md`, removed): passenger QR confirmation is **not** in version 1
(paper signatures stay; proof = photos).

## 1. Decided (do not re-open)

Paper stays for signatures · only the driver gets a link · link via `wa.me` · proof = photos read by people ·
one trip number on paper and system · office fills who/where, driver fills how much/when · office brain + internet
mailbox (Cloudflare Worker + D1 free plan), office PC never reachable from the internet · technology never blocks
a trip (trust colours) · fork the BAMS engine.

Added by the owner on 2026-09-29: **English + Arabic** UI, **light + dark** themes (light with depth and motion),
theme / font / font size choices, command palette and shortcuts, side panels, slides and guided tours,
administrator controls everything, rich demo data from the real workbook.

## 2. Assumptions (defaults used until the owner says otherwise)

| # | Topic | Default |
|---|---|---|
| A1 | `Misr car KM` | vendor **billable km**, entered by the office (can be pre-filled from a standard route km) |
| A2 | `Column1` | daily sequence of `Extra` trips, generated, editable |
| A3 | Office UI language | both; default **Arabic** for new users, switch per user; Excel headers stay English |
| A4 | Location on the driver page | **off** |
| A5 | Link lifetime | 48 h after trip end |
| A6 | Mailbox retention | 30 days |
| A7 | Poll interval | 60 s with backoff |
| A8 | OT threshold | 12 h (setting) |
| A9 | Trip number format | `YY-NNNNN` per year, e.g. `26-00233` |
| A10 | Photo size | long side 1280 px, JPEG ≈ 250 KB |
| A11 | Brand | generic: "Trip Orders" in config, no logo, navy + amber |
| A12 | Rented vehicles | same trip flow; vendor + rate on the vehicle/category |

## 3. Phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0 Study & plan | this file, `REFERENCE_STUDY.md`, `DESIGN.md`, `CLAUDE.md`, history | owner answered or defaults accepted |
| 1 Engine fork + shell | BAMS engine copied, domain removed, engine tests green; new shell: i18n EN/AR + RTL, themes (Daylight, Night Road, +3), fonts bundled, font size/density, motion system, command palette, shortcuts, side panel framework, help centre skeleton, brand config | engine tests green + UI smoke test in both languages and both themes |
| 2 Domain core | entities, lists screens, trip create/edit/cancel/reassign, amendments, trust colours, odometer chain, profiles & permissions, live board "Today", review queue | unit tests for formulas, chain, trust rules, permissions |
| 3 Excel | `xlsx_read`, import preview/confirm with merges and fingerprints, "same as today" export with formulas + Tables + totals row, clean export, September sample as demo data | round-trip test cell-by-cell on the sample; fixtures from REFERENCE_STUDY §7 |
| 4 Gateway + driver page (local) | Worker + D1 in the local simulator, 5 driver screens, offline drawer, camera, compression, stamp, binding, ✓/✓✓ | Playwright mobile tests incl. offline and reopen |
| 5 Office ↔ gateway | push cards, pull/ack, idempotency, retention warnings, `wa.me` button, printable pre-filled form with trip-no QR | multi-PC double-pull test |
| 6 Reports & show | vendor reconciliation, cost allocation, OT, anomalies, per vehicle/driver/department/requester, presentation-mode slides, welcome slides, guided tours | report numbers match fixtures |
| 7 Hardening & delivery | independent security review, installer, release workflow, user guides EN/AR, gateway set-up guide | CI green, installer smoke test |
| 8 Backlog | sealing, WhatsApp API, OCR, location, standing driver link | — |

Each phase: tests green, docs updated in the same PR, short Arabic summary to the owner.

## 4. Open questions (asked once, defaults above apply)

1. `Misr car KM` meaning (A1).
2. Default office language (A3).
3. Location on the driver page (A4).
4. ~~Demo data real or anonymised?~~ **Answered 2026-09-29: real, like the sheet.** The owner's workbook is loaded
   at first start into the office data folder ("Load my real workbook"). The repository is public, so it keeps only
   a synthetic sample with the same structure (see EXECUTION_PLAN P3.6).
5. Is there an official price per km / per OT hour per vendor now (for reconciliation screens)? Default: empty,
   admin fills it.
6. A Cloudflare account: will the owner create it (free, no card) when we reach Phase 4? Default: yes, with our
   one-page guide.

## 5. Risks

| Risk | Mitigation |
|---|---|
| Worker CPU limit (10 ms) with photos | raw binary bodies, no parsing; measure in tests; fallback R2 / paid plan documented |
| iOS Safari PWA limits (no Background Sync, storage eviction) | retry on open/online/timer; keep outbox small; ✓✓ before deleting |
| In-page camera blocked on some phones | file-input fallback marked "fallback" (yellow) |
| Fork drift from BAMS fixes | keep engine files close to BAMS; note BAMS version in history; port fixes deliberately |
| Bilingual UI doubles text work | all strings via keys from day one; test for missing keys |
