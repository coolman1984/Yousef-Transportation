# Trip Orders: commercial readiness and execution plan

**Prepared:** 5 October 2026  
**Reviewed application:** `9f5ef29cf3abeb587ddedec73e61d6c92399c719`, version `1.0.2`  
**Intended implementers:** Opus 5.5, Sonnet 5.5, SOL 6.1, or another capable engineering agent  
**Current status:** planning and review complete; implementation and release approval remain future work. This document does not certify the application as ready to sell.

## 0. Read this before doing anything

This is the single requested planning deliverable. During its preparation, application code, configuration, existing documentation, and workflows were not changed. Existing tests and isolated synthetic probes were run to distinguish actual failures from assumptions. Future agents must implement the repairs; this document itself does not fix them.

### 0.1 The owner's latest requirements take priority

1. **Keep the current design and style.** Preserve the existing layout, visual identity, navigation conventions, components, fonts, colours, themes, spacing, and bilingual presentation. Do not redesign the dashboard, replace the frontend, introduce a new design system, or turn this into a different product.
2. **Users are nontechnical. Keep the app very simple and effective.** Improve defaults, wording, validation, feedback, and recovery within the current screens. Technical complexity belongs behind the scenes. Do not make staff learn synchronization, certificates, gateways, conflicts, or deployment.
3. **Separate three concerns:** everyday Settings; the customer's Administration; and a hidden Developer Support capability for Mohamed. Developer Support must be separate from both Settings and the customer's administrator permissions.
4. **Mohamed must be able to connect remotely and help.** Provide an authenticated developer console, bounded diagnostics and repair actions, and customer-controlled temporary support sessions. Hiding the menu is a presentation requirement, not the security mechanism.
5. **Deliver as a Windows EXE installer built by GitHub.** Customers must not install Python, Node, development tools, or configure Cloudflare themselves. Installation, updating, backup, and support must form a complete experience.
6. **Keep this plan and communication in English.** Retain the application's Arabic and English UI. English-only communication does not authorize removal of Arabic product functionality.
7. **Do not implement anything during this planning task.** Future implementation starts only when the owner asks an agent to execute the plan. Do not interpret the generic request to “finish the app” as permission to change code in this planning turn.

The two original identical HR URLs refer to one project. The second intended reference, subsequently supplied by the owner, is [Teachers](https://github.com/coolman1984/Teachers). The first is [Mr.Ayman-HR / BAMS](https://github.com/coolman1984/Mr.Ayman-HR).

### 0.2 Instruction and scope precedence

Read `CLAUDE.md`, `.claude/skills/trip-orders/SKILL.md`, `docs/EXECUTION_PLAN.md`, `TASKS.md`, `docs/PLAN.md`, `docs/DESIGN.md`, and `DEVELOPMENT_HISTORY.md` before implementation. Use this plan as the readiness overlay on the existing work, not as permission to discard it.

Where older documents conflict with the owner's latest instructions, use the latest instructions: English conversation; no redesign; simple daily operation; separate customer administration and hidden developer support. The planning-only, one-file restriction overrides the older requirement to update several documents during this task. During later code changes, resume the normal history, guides, release-notes, and test-map updates.

Do not push to `main`, force-push, merge, publish a release, contact customers, or enable remote access without the applicable authorization. Preparing and testing a release candidate is distinct from publishing it. Never commit real customer workbooks, photos, credentials, support tickets containing personal data, or production databases.

### 0.3 Product decision

The first commercial product is **a dependable trip-order application for Egyptian office dispatchers, general-affairs staff, reviewers, finance staff, and drivers**. Its main job is to replace repeated phone calls, disconnected spreadsheets, and missing trip evidence with a clear trip record.

The core journey remains:

**Create trip → send driver link → driver records start/end and evidence → office reviews → finance exports the agreed report.**

The daily experience must become easier while the current appearance remains recognizable. Do not expand launch scope into a full fleet ERP, public ride-hailing marketplace, payroll system, school transport platform, or accounting package.

## 1. Observable success criteria

These are release gates, not aspirations. Every gate requires recorded evidence on the actual candidate build.

| Gate | Observable acceptance criterion |
|---|---|
| S1 — Simple operation | In a pilot with at least five representative nontechnical users, at least four complete their assigned core journey without developer coaching after a short introduction. A routine repeat trip can be prepared and shared in under two minutes, excluding waiting for the driver. Record observed times; this is a target, not a current measurement. |
| S2 — Design preservation | Before/after screenshots use identical data, viewport, language, theme, density, and font size. No unrequested changes to the existing visual system, screen structure, or navigation. The specifically requested Administration separation and hidden Developer Support are the only planned structural additions. |
| S3 — Trustworthy records | Duplicate submissions, retries, a double-click, reconnecting PCs, and an out-of-order driver event do not lose evidence or silently change approved facts. Corrections preserve the old value, reason, actor, and time. |
| S4 — Correct reports | Historical charges remain stable after a new rate is introduced. Screen, Excel, and Word agree on the same fixture. Missing measurements and rates remain distinguishable from zero. |
| S5 — Real authorization | Denied actions remain denied through direct API calls, generic commits, file URLs, exports, and support endpoints. Customer A cannot access Customer B. Customer administrators cannot grant themselves developer privileges. |
| S6 — Reliable installation | A clean supported Windows x64 machine installs and runs the signed EXE without Python, Node, Office, or development tools. Upgrade, repair, uninstall/reinstall, and user-data retention are tested. |
| S7 — Useful remote help | The customer can allow and end a support session in simple language. Mohamed can connect from a different network, diagnose a seeded failure, perform one allowed repair, and produce an audit record. Expired, replayed, cross-customer, and revoked access fails. |
| S8 — Release evidence | Required CI jobs, actual installer tests, supported-browser checks, real cloud staging checks, recovery drills, and pilot gates pass. No unresolved critical/high security or data-loss issue. Medium issues need a recorded disposition and must not defeat a core journey. |

Suggested initial validation envelope: one company per installation cluster, 1–5 office PCs, up to 100,000 archived trip records, a pilot workload of 100 trips/day, and 20 active drivers. These are **test targets, not supported capacity claims**. Reduce the advertised envelope if measurements cannot justify it; do not silently reduce tests to obtain a green build.

## 2. What exists and what was actually verified

### 2.1 Architecture and useful assets

| Area | Existing implementation |
|---|---|
| Office backend | Python standard-library application, `server/app.py`; SQLite data and accounts; signed journal and replicated changes in `journal.py`, `replica.py`, `node.py`, `sync.py`, `system.py`. |
| Business logic | `domain.py`, `tripsvc.py`, `reports.py`; trips, categories, drivers, vehicles, people, approvals, amendments, trust indicators, reports. |
| UI | Plain JavaScript, existing reusable UI helpers, Arabic/English dictionaries, local fonts, themes, RTL, keyboard controls, trip panels and existing settings tabs. |
| Driver connectivity | Cloudflare Worker/D1 mailbox, small driver cards, HMAC office requests, IndexedDB outbox, camera flow and service worker; `gateway/` and `server/gateway_client.py`. |
| File exchange | Native spreadsheet/document readers and writers; import preview; existing-format Excel export; optional Windows Office COM path. |
| Recovery | SQLite backup API, integrity checks, pre-operation backups, soft deletion, compensating restore, journal rebuild CLI. |
| Packaging | Nuitka standalone application, Inno Setup installer, GitHub Actions workflow. The delivery format already exists; it needs hardening and real acceptance testing. |

Preserve these investments. Do not rewrite the replication engine, adopt a frontend framework, replace SQLite, or add microservices merely to make the project appear more sophisticated.

### 2.2 Evidence ledger from this review

Environment: Windows, Python `3.12.10`, Node `25.2.1`. Current CI uses Python 3.11 and Node 22. This difference must be recorded when interpreting results.

| Check | Result and limits |
|---|---|
| Repository status before review | Clean tracked working tree. No application changes made by the reviewer. |
| Existing non-browser suite | From `tests/`: `python -B -m unittest test_unit test_convergence test_design test_domain test_trips_api test_xlsx test_excel_io test_word_io test_formats test_gateway_client`. Completed in 173.629 seconds: **136 tests; 130 passed, 3 failed, 3 skipped**. |
| Windows failure 1 | `test_unit.ToolsTest.test_rebuild_gives_identical_data`: `WinError 32` while `nodectl.cmd_rebuild` renames the live SQLite file. See F06. |
| Windows failures 2–3 | `test_formats.SpreadsheetTypes.test_refusals_are_plain` and `test_formats.WordTypes.test_refusals`: expected a document-security message but the Office-installed path attempted COM and returned an interface/visibility error. See F16. |
| Skipped dependencies/private input | Three skips occurred. The suite contains optional LibreOffice, xlwt, openpyxl and private-workbook branches. The captured non-verbose run did not identify each skipped test by name; capture a verbose skip inventory in T01 rather than inventing that mapping. |
| First sandbox attempt | Failed because temporary-folder access was restricted: 119 tests reported, 41 errors, 3 skips. These are environment errors and are not counted as 41 product defects. The usable baseline is the subsequent run above. |
| Gateway unit tests | `node --test --test-isolation=none --no-warnings test/gateway.test.js`: **14 passed; one bundle test blocked by `spawnSync node EPERM`**. The normal isolated runner also hit `spawn EPERM`. No clean full-gateway-suite pass is claimed. The bundle test would generate `gateway/dist`; it was not completed during the one-file review task. |
| Synthetic API probes | A `trips.view`-only account received rate and driver-contact data; an account with `trips.edit` but no `trips.approve` set approval through `/api/commit`; a `trips.amend` account edited a closed trip through generic commit without increasing the amendment count. All against disposable local test data. |
| Synthetic function probes | A 100 km historical trip changed from 1,000 to 2,000 cost units after changing the current rate from 10 to 20. Mixed-offset duration returned 0 hours for an actual three-hour interval. An end-before-start event set `finished`; the later start returned `False` and did not fill start data. |
| Not executed | Full multi-node suite, browser acceptance, real Cloudflare deployment, installer compilation/installation, Authenticode signing, live customer support, security scanner suite, or a real customer pilot. |

Tests revealed meaningful Windows-specific failures even though much of the existing suite passes. GitHub being green on Linux alone will not establish readiness for an EXE product.

### 2.3 Reference-project evidence and limits

**BAMS / Mr.Ayman-HR:** the local checkout at `D:\WORK\Software Development\GitHub\Break Area Management System` points to the requested remote but is an older snapshot, `99e0400878cff8e72126a2780325120ea85be594` dated 24 September 2026. Its server, backup implementation, README and UI source were inspected. It predates the later authentication/replication architecture. This project also contains `docs/REFERENCE_STUDY.md`, recording a 29 September study of BAMS 2.4.0; `TASKS.md` records the engine fork as `5f5b3ce`. Treat those as historical project evidence, not a fresh independent verification of current upstream. Attempts to retrieve current upstream through the web reader and GitHub API failed with cache misses/TLS timeouts. T01 must pin and compare the current upstream when available.

**Teachers / Hessa:** inspected the local source at `D:\WORK\Software Development\GitHub\Teachers`, remote `coolman1984/Teachers`, local HEAD `695729dd057e17f0b4592b6ee9befdcedd65ebcc` dated 5 October 2026. Read its instructions, task list, settings, overview, help, relevant server code, and workflow. The browser-visible public default branch showed `a596a01`; these are different snapshots. Do not describe the local worktree as the exact current public release. No Teachers test results were independently rerun here.

| Reference lesson | Apply to Trip Orders | Important boundary |
|---|---|---|
| BAMS: safe backup, recycle bin and history | Make recovery reliable and understandable; retain compensating restores and pre-change backups. | The older local reference is not proof of modern security. Do not copy obsolete network-share or access defaults. |
| BAMS historical study: administrator/backup-authority devices, pairing, permission profiles, personal-link restrictions | Complete the customer administrator device workflow around the engine already present here. | A PC authority key governs replication; it is not a developer support credential. Never conflate these identities. |
| Teachers: permission-aware quick actions and useful next steps | Use existing buttons and notices to make the next action clear. | Do not copy the Teachers dashboard layout or add an “AI advisor” to this app. |
| Teachers: effective-date money history and reversible financial actions | Snapshot/version transport rates; preserve historical calculations and correction evidence. | Do not import student billing, cash shifts or payroll features. |
| Teachers: help tied to the current task | Improve the existing Help content and links with short answers. | Keep existing styling and route conventions. |
| Teachers: scoped responses, delta refresh, measured performance | Design server-side response filtering and targeted refresh without interrupting forms. | Recheck implementation and tests; comments about permissions are not proof. |
| Teachers: deliberate tag-based release workflow | Separate development builds from customer release publication. | Its task list still records incomplete release checks and legacy test migration. Do not copy test exclusions or assume production readiness. |
| Teachers: parent gateway work remains open in its task list | Reuse only verified patterns, not an unfinished gateway implementation. | Trip Orders' existing driver gateway is the starting point. |

## 3. Egyptian market research translated into a restrained product scope

Research date: 5 October 2026. Sources below are primary provider/regulator/documentation pages. Provider claims establish advertised capabilities, not independently verified performance. This is desk research, not customer interviews or a market-size study. No revenue forecast, invented competitor quotation, or claimed willingness-to-pay is included.

### 3.1 Market signals

| Evidence | What it suggests for this product | Launch decision |
|---|---|---|
| Swvl advertises corporate dispatch, reporting, transport-cost visibility and driver/rider coordination; its factory offering emphasizes shift and multi-site operations. [Corporate transit](https://www.swvl.com/use-cases/corporate-transit), [factory transit](https://www.swvl.com/use-cases/factory-transit). | Customers compare outcomes such as fewer missed trips and clearer transport bills. A small office may value accurate records without changing its transport supplier. This positioning is an inference. | Preserve the existing dispatch/evidence/reporting focus. Validate repeat-trip needs in the pilot; do not build route optimization or passenger booking for launch. |
| Orange Egypt's Metabe3 advertises tracking, alerts and vehicle reporting through ETIT. Its displayed monthly bundles are EGP 135/170/200, excluding tax, tracker equipment, installation and additional sensors. [Metabe3](https://www.orange.eg/en/business/business-solutions/metabe3). | GPS hardware subscriptions are an adjacent category, not a valid direct price for this software. Existing tracking could later supply data. | Do not buy hardware, promise live GPS, or build an integration without a customer need and an actual supported provider API. Recheck all pricing before commercial decisions. |
| NTRA publishes measured differences in mobile-network quality by area and operator. [Quality reports](https://www.tra.gov.eg/en/consumers/quality-of-services/quality-of-services-reports/). | Test the driver journey under variable connectivity instead of assuming that a nominal mobile connection means a successful upload. | Offline save, visible delivery state, retry and recovery are launch requirements. No claim that every Egyptian location has poor coverage. |
| ETA provides a formal eInvoice/eReceipt integration SDK. [ETA SDK](https://sdk.invoicing.eta.gov.eg/). | A transport reconciliation sheet is not automatically an ETA-compliant tax invoice. | Export supporting statements for the customer's accountant. Do not market tax compliance or implement tax submission in the first release. |
| PDPC identifies Law 151/2020 and Executive Regulations 816/2025 as the framework, and publishes cross-border transfer guidance. [PDPC](https://www.pdpc.gov.eg/), [official portal](https://portal.pdpc.gov.eg/). | Driver/passenger details, phone numbers, photos and support records need an explicit data-handling design. Hosting outside Egypt cannot simply be assumed acceptable. | Minimize data in cards/diagnostics; record hosting and retention; obtain a deployment-specific privacy/legal review before processing real customer data through the gateway or support relay. |

**Recommended position to test:** “Keep your current transport operation and familiar reports, with easier trip follow-up and fewer missing records.” This is proposed positioning, not a proven market claim.

### 3.2 What Egyptian users likely need — hypotheses to validate

- Familiar Arabic and English names, Egyptian phone normalization, Arabic/Western numeral input, and readable vehicle plates. Keep the existing report headers and plate display conventions.
- Fast selection of familiar driver/car/destination combinations; today as the default date; optional details kept optional. A simple repeat action is preferable to a scheduling subsystem if pilots request it.
- Reliable handling of overnight trips, different phone clocks, Egyptian civil time, holidays and temporary schedule changes. Do not hardcode a labour-law overtime rule or a universal weekend.
- Paper signatures and photos as already agreed. A missing phone or unavailable camera must have an office-assisted exception path with a reason, not stop real transport work.
- Clear differences between measured kilometres, vendor-billed kilometres and the agreed payable basis. A difference should be reviewed, not automatically labelled fraud.
- EGP amounts and contract-effective rates. Fixed/day/monthly charges, tolls, parking and allowances may matter, but add each only after representative contracts establish a need. The first release must calculate its supported tariff correctly and clearly identify unsupported contracts.
- Local support from a known person, an installer that works, and easy recovery are likely more valuable than additional dashboards. Test this with customers.

### 3.3 Discovery and commercial validation

In T02, speak with 5–8 representative people across dispatch, drivers, general affairs, finance and customer administration, covering at least two potential customer organizations. Use synthetic examples until there is authorization to inspect real files. Do not contact people automatically from this plan.

Ask them to demonstrate: yesterday's trip order; a changed driver; missing odometer evidence; a late/overnight trip; an invoice discrepancy; a rate change; an internet outage; and a request for help. Record the time and mistakes in the current process, the report they actually use, and who approves a correction. Observe, rather than requesting a wish list.

Commercial default: a simple company/site license with clearly stated office-PC allowance and optional annual support/hosted-connectivity service. Keep prices undecided until quotations and willingness-to-pay interviews exist. Calculate a floor from onboarding time, expected support hours, signing, cloud storage, backups, taxes and payment collection. Public EXE download and paid usage rights can coexist. Do not put customer secrets in a customized installer.

Launch scope must not grow because a competitor has more features. Defer GPS maps, route optimization, passenger apps, automated WhatsApp campaigns, OCR/AI, payments, full accounting, maintenance ERP and multi-company consolidated dashboards. Maintain extensibility only where a real contract requires it.

## 4. Prioritized findings

Labels: **R** = reproduced during this review; **C** = confirmed by source inspection; **V** = risk/coverage gap requiring targeted verification. A source-confirmed issue is not automatically a demonstrated exploit. Severity reflects a commercial release, not a formal CVSS score. File line numbers refer to the reviewed commit and may move.

### F01 — High: permissions do not filter the complete state response [R]

`server/app.py:528` calls `STORE.state(self.u['scopes'])`; `server/store.py:248` filters categories and trip children but does not take functional permissions. A user with only `trips.view` received `ratePerKm` and a driver's mobile number in the synthetic API probe. `/api/reports` checks `reports.view` but returns reconciliation/allocation data without a separate `finance.view` check.

**Repair:** centralize authorized projections for state, reports, exports, files, deltas and support data. Explicitly define what each role may read; removing a button is insufficient. Keep names/IDs needed for an allowed trip while removing restricted contacts/rates. **Proof:** a negative matrix for every relevant role and category, including generic URLs and a role changed during an existing session. **Tasks:** T03–T04.

### F02 — High: generic commit bypasses business permissions and amendment requirements [R]

`server/app.py:209`–`258` and `:754` allow generic trip updates based on broad intersections of permissions. An editor without `trips.approve` successfully set `gaApproved` and `gaBy` through `/api/commit`. A user with `trips.amend` changed a closed trip's notes through the generic route while the amendment count remained 1 before and after. `tripsvc.PROTECTED` applies in the amendment service, not to every generic write.

**Repair:** route protected transitions through one domain service; reject client-written identity, approval actor/time, link material and locked-trip edits at all other boundaries. A locked correction must atomically create its amendment. Keep separate server identities for driver ingress and imports. **Proof:** existing dedicated-route denials plus the equivalent generic-commit attacks. **Tasks:** T03, T05.

### F03 — High: attachment authorization and caching are too broad [C]

`server/app.py:654` exempts image extensions from `files.download`; `serve_file` at `:1077` performs containment/type checks but no trip/category ownership check. Uploaded files use `Cache-Control: public, max-age=31536000, immutable`. A signed-in user who obtains another trip's image path can reach this route without its scope being checked. The path need not be guessable for the missing authorization to matter.

**Repair:** authorize the attachment through its owning record before reading it, including thumbnail/placeholder responses; use an appropriate private cache policy with logout/account-switch tests. **Proof:** permitted, forbidden-category, revoked-user and shared-browser scenarios. **Task:** T04.

### F04 — High: LAN HTTP, broad firewall rule and broad local ACLs [C]

`config.json` and `server/app.py` bind the office web server to `0.0.0.0`; sessions are sent over HTTP and the cookie at `app.py:420` has no `Secure` attribute. Replication TLS does not encrypt this separate web interface. `installer/trip-orders.iss` grants `users-modify` over `%ProgramData%\TripOrders` and installs a `profile=any` inbound application rule. `gateway.json` contains operational secrets; Python `chmod(0600)` is not a substitute for deliberate Windows ACLs.

**Repair:** use loopback office UI by default, with each installed PC using the existing authenticated replication channel. Preserve a supported LAN-browser mode only behind deliberately provisioned HTTPS and trusted certificates. Restrict firewall profiles/ports/subnets and isolate service-owned secrets/data from normal Windows accounts. Test the chosen Windows service/user model before changing permissions. **Proof:** packet/endpoint checks, two Windows users, public-network profile, installation under standard-user daily operation. **Tasks:** T07, T08.

### F05 — High: replacing a driver link does not revoke the previous gateway card [C]

`tripsvc.make_link` at `:117` replaces the stored hash/nonce. `Gateway.push_cards` at `server/gateway_client.py:296` publishes current cards, but the old hash is not durably queued for removal. The Worker has a `remove` facility which this path does not use. Old cards can therefore remain until expiry; stale PCs can also publish older state. Device release is held in an in-memory set.

**Repair:** persist monotonic link generations and revocation/device-release intents, enforce them at the gateway, and prevent an old replica from resurrecting a revoked generation. Define handling of old-link offline submissions: preserve evidence for review without granting the old token new access. **Proof:** replace, cancel, restart, disconnected PC, stale publish, and delayed driver retry. **Task:** T10.

### F06 — High: Windows journal rebuild fails while renaming SQLite [R]

`server/nodectl.py:96` uses `with sqlite3.connect(old) as db`, then renames the database at `:113`. SQLite's connection context manager controls transactions; it does not close the connection. The Windows test failed with `WinError 32`. The rebuild flow also needs explicit coordination with the running app before any rename.

**Repair:** close handles explicitly, obtain the application's exclusive recovery lock, stage a verified rebuild, preserve the original database/journal/uploads, and provide a reversible recovery path. Do not claim that changing the test makes recovery safe. **Proof:** current failing test plus installed Windows recovery with the app stopped/running, corrupt materialized data, and interrupted rebuild. **Task:** T06.

### F07 — High: historical costs are recomputed from current rates [R]

`server/reports.py:24`, `:96`, `:117` read the category's current rate. A synthetic historical 100 km trip changed from 1,000 to 2,000 after the rate changed from 10 to 20. Reconciliation also groups by category name/vendor text rather than stable contract/rate identity.

**Repair:** effective-dated rate records and a versioned trip calculation snapshot, with explicit approval/correction semantics. Use decimal or integer minor-unit money arithmetic. Do not invent historical rates for existing data; mark an unknown migrated rate and request an authorized choice. **Proof:** rate changes, mixed rates within a month, zero rate, missing rate, rounding, amendments and identical exports. **Tasks:** T14–T15.

### F08 — High: out-of-order driver events lose start information in the projection [R]

`gateway_client.apply_event` only applies a start below `started` rank. Receiving an end first sets `finished`/locked; a later valid start is ignored. Raw events may remain, but the trip's usable start information stays missing. A malformed or unknown status can also hit dictionary indexing in the event handler.

**Repair:** reduce immutable driver events deterministically, preserve valid missing start/end facts regardless of arrival order, and retain conflicts for office review. Prevent an arbitrary late message from overwriting a reviewed correction. Validate the event schema before acceptance. **Proof:** all start/end/retry permutations, two devices, office correction, unknown event fields and replay on two PCs. **Task:** T11.

### F09 — High: delivery acknowledgement can overstate evidence durability [C]

The phone deletes a photo blob once the gateway acknowledges upload (`gateway/public/app/outbox.js`, success handler). The office later deletes gateway rows on ACK. Scheduled cleanup deletes old unacknowledged events/photos after retention. The phone's double-check display is based on gateway receipt, not confirmed office storage. A prolonged office outage or loss of the only receiving office PC can expose a durability gap.

**Repair:** specify and implement separate states for saved on phone, accepted by mailbox, and stored by office; retain evidence according to the promised recovery level. Do not claim “never lost.” Add capacity/retention warning and durable receipt/tombstone rules. Ensure valid retention erasure remains possible under the privacy policy. **Proof:** crash at every upload/apply/ACK boundary, office offline past warning thresholds, photo transfer between PCs and restoration. **Tasks:** T11–T13, T17.

### F10 — High: D1 free-tier batching assumptions do not match deployed limits [C + V]

The office sends batches of 100 cards; Worker handlers allow up to 500 card/removal or ACK items, potentially adding a statement per item plus nonce/auth queries. Official D1 limits currently list 50 queries per invocation on Free and 1,000 on Paid. Its maximum Free database is 500 MB. [D1 limits](https://developers.cloudflare.com/d1/platform/limits/). The local SQLite stand-in does not enforce these cloud limits.

**Repair:** budget every request's statements, bytes and execution work against the chosen plan, including authentication and release-device statements. Load-test the maximum batch in actual staging. Explicitly provision the chosen paid/free plan; do not promise free indefinite photo hosting. Evaluate object storage only if measured capacity requires it. **Task:** T12.

### F11 — Medium/high: timezone offsets are discarded [R]

`domain.parse_dt` at `:103` strips offsets. Duration between `2026-10-01T08:00:00+03:00` and `2026-10-01T08:00:00Z` returned zero instead of three hours. Gateway `local_pair` normalizes within the phone's offset, then stores naive strings; `_epoch` assumes naive expiry times mean UTC. Ambiguity remains around mixed sources, clock changes and expiry.

**Repair:** establish an explicit UTC/event-time and `Africa/Cairo` business-date contract, retaining original phone time/offset and server receipt. Package/test timezone data for Windows. Migrate old naive timestamps with provenance rather than pretending certainty. **Task:** T13.

### F12 — Medium/high: authorization rules conflict with intended cancellation and rate roles [C]

The default Dispatcher can cancel, but cancellation delegates to `amend`, which inserts `tripAmendments`; generic guard rules require `trips.amend` or `trips.review` for that insertion. The Finance profile has `rates.manage`, but category updates check `categories.manage`. Thus roles can be simultaneously too permissive on some paths and unable to perform their intended job on others.

**Repair:** operation-specific internal writes under the originally authorized action. Do not grant broad amendment/category privileges as a workaround. **Proof:** a normal dispatcher cancellation, cancellation of a finished trip under the agreed policy, and a finance-only rate update. **Tasks:** T03, T05, T14.

### F13 — Medium/high: backup sets are not a complete disaster-recovery contract [C + V]

`server/backup.py` names backups to the second, uses one destination `.tmp` without a backup-operation lock, and copies data/auth/journal separately. Its routine set does not include a documented protected identity/configuration/gateway recovery package. Automatic backup scheduling observes data version, which may miss account-only changes. Actual overlapping-write consistency and same-second collisions still require reproduction.

**Repair:** serialize backup creation, unique identifiers, a coherent manifest and integrity checks, protected recovery material, authentication-change triggers, disk-full behaviour and a fresh-PC recovery drill. Preserve separate semantics for data restore versus full disaster recovery. **Task:** T17.

### F14 — Medium: browser storage/update failures can be silent [C + V]

`saveDraft` swallows storage failures; outbox reads may return an empty list on error. Service-worker version is fixed at `to-driver-1`, assets are cache-first, and activation removes other cache names without a product-prefix filter. The exact user-visible failures need browser reproduction.

**Repair:** never display “saved” before a transaction succeeds; provide understandable retry/space instructions; version assets with the release; update without dropping an unfinished trip; clean only owned cache namespaces. **Task:** T16.

### F15 — High release gap: executable build is not a verified commercial installer [C]

The workflow grants `contents: write` globally, uses moving action tags and broad build-tool version ranges, publishes from any new application version on `main`, and only smoke-tests the compiled executable. It does not test installing the Inno Setup package. No signing, SBOM, checksums, attestation or verified update mechanism is present in the inspected workflow. Installer upgrades use forced process termination.

**Repair:** separate test/build/sign/release privileges and gates; test actual installation and upgrade on Windows; sign and verify the final artifacts; publish all assets atomically; establish safe update and rollback rules. **Tasks:** T25–T29.

### F16 — Medium: Office-installed file refusal path is not deterministic [R]

Two Windows tests fail because a protected-looking sample goes through the Office COM route and yields an environment-specific message. `com_office.py` is intentionally optional, but installed Office does not guarantee working automation. This is a product-path/test-contract mismatch, not proof that every protected file is unsupported.

**Repair:** stable error codes and translated explanations, deterministic unit mocks, plus separate installed-Office acceptance tests. Native formats must work without Office. Keep COM off the unattended service path; never execute macros or weaken document protection. **Task:** T18.

### F17 — Medium: settings placeholders and missing administrator UI [C]

`js/views/settings.js` still sends Organisation and Money to a “later” placeholder. Appearance is browser-local; no per-account admin policy is complete. Backend endpoints exist for devices/conflicts/key export, but the inspected frontend contains no calls to `/api/devices` or `/api/conflicts`. Current `TASKS.md` also marks branding and administration-related work incomplete.

**Repair:** complete supported business setup within Customer Administration, preserve existing styling, and move technical diagnostics to Developer Support. Expose only the minimum customer device controls. **Tasks:** T19–T21.

### F18 — Medium: data-validation and bounded-load gaps [C + V]

Generic `_plan` allows many fields without domain-wide reference/status/date validation; numeric coercion converts through floats. Complete state is loaded for each data refresh. This is a correctness and scaling concern, not a measured performance failure. Verify nonfinite numbers, oversized batches, invalid relationships, duplicate IDs/keys within one batch and concurrent cross-PC numbering. `my_letter` derives a PC letter from roster order instead of an explicitly reserved immutable prefix.

**Repair:** explicit domain validation at every entry point, bounded requests, server-assigned identity, persisted number allocation, targeted reads and measured indexes. **Tasks:** T05, T09, T30.

### F19 — Medium: lifecycle/documentation contradictions [C]

Older documents use `reviewed`, current code uses `closed`; the written default expiry is 48 hours after trip end, while `make_link` currently chooses at least seven days from now/three days from the planned date. `LICENSE.txt` still names Break Area Management System. Build documentation describes source protection in overly strong terms: compilation does not make shipped code or secrets unrecoverable.

**Repair:** one glossary/state machine, an explicit expiry policy, correct license/product names and accurate delivery claims. Preserve one visible business meaning for “reviewed/closed”; do not add statuses merely to match old prose. **Tasks:** T05, T10, T31.

### F20 — New mandatory capability: developer support does not exist yet [C]

The requested hidden, remotely reachable Developer Support control plane is a new requirement. Customer administrator accounts, personal links, driver links and replication authority keys cannot safely substitute for it. **Tasks:** T20, T22–T24.

### 4.1 Additional checks before release

T03/T07/T09/T12 must also check Host/Origin validation and DNS rebinding; CSRF and content types; request timeouts/slow clients; path traversal and junctions; archive expansion and XML limits; formula injection in exported text; uploaded image dimensions/content validation; gateway URL/redirect restrictions; log/URL secret redaction; UUID collisions across cards; brute force and quota abuse; session revocation across PCs; custom cryptographic implementation and recovery-key envelope review. These are checks, not claims of confirmed vulnerabilities. Do not weaken existing protections to make tests pass.

## 5. Product and interface contract: same appearance, easier work

### 5.1 Non-redesign rules for every implementation task

- Reuse `css/tokens.css`, `css/base.css`, existing themes/fonts, `js/ui.js`, panels, tables, notices and form components.
- Keep current ordinary navigation and screen structure. Do not merge/replace the current Overview, Trips and Today board as a design project.
- Repair clipping, focus, contrast, keyboard behaviour and invalid labels with the smallest localized change. Record why any visual delta is necessary.
- Do not add menu entries for internal mechanisms. Preserve appearance preferences already available; do not create a second preference system.
- A status explanation must say what happened and what the person should do. Keep identifiers, logs and technical details behind an optional support detail view.
- All daily actions work by ordinary clicks/taps. Shortcuts remain optional, and single-letter shortcuts must not fire while typing or unexpectedly alter a user's preferences.
- Do not use mandatory training slides as a substitute for usable screens. Existing tours can stay optional.
- The requested separated customer Administration may use the existing shell and visual components. Hidden Developer Support may have its own authenticated route/remote operator console, but must not redesign the customer app.

### 5.2 Core journey acceptance details

| Step | User experience within existing screens | Required failure/recovery behaviour |
|---|---|---|
| First run | Installer opens the app; customer admin creates an account and enters only necessary company information. Synthetic demo is an explicit choice, separate from live work. | Interrupted setup resumes safely. Existing installations are detected. No development configuration or sample data silently appears in live records. |
| Create | Existing trip form defaults to today and uses known driver/car/requester/category/destination lists. Save retains entered values while waiting. | Clear inline validation; no duplicate trip from double-click/retry; stale edit offers a useful comparison and retains the draft. |
| Send | Existing share/copy/WhatsApp action returns the right driver and trip. Distinguish link preparation from confirmation the driver has submitted anything. | Missing phone, gateway unavailable and copied link each have an understandable outcome. Opening WhatsApp does not prove delivery. |
| Driver | Preserve the existing step sequence, camera view and styling. Remember successful entries. Show one current action. | Offline save is truthful; camera denied has an allowed fallback; large image is handled; expired/replaced link explains how to contact the office. |
| Review | Existing trip panel shows measurements, evidence and reasons requiring attention. Reviewer corrects with one short reason. | Missing evidence can be recorded as an exception. No silent alteration of the driver's original record. |
| Report | Existing Reports/Excel/Word flow offers the agreed month and layout. Numbers explain whether they are measured, billable, estimated or approved. | No missing rate silently becomes a genuine zero-cost trip. A failed export preserves work and gives a retry. |
| Help | Existing Help offers task-specific short guidance and a simple support request entry. | Staff can report a problem; only an authorized customer admin enables privileged support. No secret copied to chat as an ordinary setup step. |

### 5.3 Settings, Customer Administration and Developer Support

| Area | Who sees it | Responsibilities | Forbidden shortcuts |
|---|---|---|---|
| Settings | Ordinary signed-in users | Their own language, appearance and supported personal preferences. | No business-wide user management, remote support credentials or system keys. |
| Customer Administration | Customer administrator only; separate from Settings | Company details, customer users/roles, business lists/rules/rates according to permissions, backup status, permitted restore workflow, connect/remove customer PCs, approve/end support. | Cannot create a developer identity, sign updates, see other customers, or extract developer credentials. |
| Developer Support | Mohamed's authenticated developer identity, hidden from customer navigation and not assigned through customer user management | Remote diagnostics, bounded repairs, supported backup/recovery tools, connectivity repair and signed update assistance during an authorized session. | No universal password, concealed always-on access, raw database editor, arbitrary shell, customer-admin impersonation, or remote port forwarding. |

Customer Administration is a business role; Developer Support is a separately authenticated maintenance capability. The current replication “administrator PC” is another concept: keep it technical and explain it as the main office PC only when the customer needs to act.

## 6. Hidden developer remote support — concrete design

### 6.1 Customer simplicity and control

Normal users do not see a Developer menu. In existing Help, they can report an issue using the existing UI style. A customer administrator sees **Allow support**, the verified helper identity, the stated purpose, the requested access scope, and **End support**. The active session is visible as a small status notice using the current notice component, not a permanent dashboard addition.

Default: diagnostic/read-only access, no attachment viewing, 30-minute session. Privileged repairs require an explicit action confirmation describing their effect. A session can be extended deliberately; never silently renew it. The customer does not paste keys, open firewall ports, operate Cloudflare, or understand cryptography.

“Hidden” means absent from ordinary navigation and unauthorized APIs; it does not mean concealing an active remote session from the company. Internet disconnection prevents remote help but must not prevent normal local work. No unattended remote-support promise in the first release.

### 6.2 Connection and identity model

1. Mohamed opens an HTTPS developer console on his own PC and authenticates using a managed identity provider with MFA/passkey. Verify provider availability/cost before adopting it; do not implement an identity provider from scratch.
2. Each customer installation has a unique installation/cluster identifier and protected device enrollment credentials. A one-time enrollment process binds it to the correct customer; installer binaries contain no customer or vendor private key.
3. The customer requests a session. The office makes **outbound HTTPS** calls to a support relay; the developer console uses the same relay. The office HTTP/sync ports are never exposed to the public internet.
4. The relay is a **separate service/deployment and credential boundary** from driver links. Prefer the team's existing Worker platform with a small per-customer queue and short retention; do not share the driver `OFFICE_SECRET`, D1 card tables, or driver bearer tokens.
5. Approval creates a short-lived, narrowly scoped grant bound to customer, installation, device, support operator, session and capability list. Each command carries a unique request ID, issue/expiry time, sequence, expected application/schema version, typed parameters and integrity/authenticity protection.
6. Both relay and office validate scope, expiry, identity, session state and allowed action. The office enforces policy even if relay storage is compromised. Decide the signed-command format in T22 and validate it using reviewed standard cryptography; no improvised encryption scheme.
7. Results are redacted, bounded, correlated and visible to the support operator. Record actions locally and remotely. Repeated command IDs return the prior result; expired queued work is discarded. A timeout never implies that an operation did not execute.
8. End support revokes the grant, stops new commands, clears queued commands and closes the operator view. If connectivity drops, expire locally too. For irreversible work, revocation stops before the next safe boundary; never corrupt a database by killing a transaction halfway through.

Default session lifetime is enforced locally from activation using a monotonic deadline as well as signed expiry checks. If the wall clock is implausible, deny new privileged grants with a readable support message. Rotation/revocation must work across the main and secondary PCs.

### 6.3 Allowed support actions and safeguards

| Action | Access | Required guard and evidence |
|---|---|---|
| Read health | Default diagnostic grant | Version, storage available, last successful backup, queue age, peer last-contact and error codes; no default names, phone numbers, tokens or document contents. |
| Read sanitized diagnostics | Explicit diagnostic capability | Allowlist fields; redact paths/usernames if not needed; preview before external upload. Never return auth databases, private keys or setup codes. |
| Retry connection/transfer | Customer-authorized repair | Idempotent, bounded retries; one customer/device; display outcome. Cannot change destination URL to an arbitrary host. |
| Create verified backup | Customer-authorized repair | Capacity preflight; unique backup ID; integrity result and manifest. |
| Verify journal/data consistency | Diagnostic or explicit maintenance grant depending on cost | Read-only by default; bounded resource use; no automatic repair on verification failure. |
| Repair a derived index/cache | Explicit repair grant | Strict operation allowlist, preconditions, backup if persistent state changes, result validation. No free-form SQL or code. |
| Restore/rebuild | Separate elevated grant and local customer confirmation | Safety backup, dry-run impact, exclusive lock, compatibility checks, irreversible-step warning, successful recovery validation. Default support access cannot do this. |
| Install a signed application update | Separate maintenance grant and customer-approved window | Verify publisher, manifest, artifact hashes and version; backup; graceful stop; health check; documented safe rollback. No executable supplied ad hoc by a support session. |
| View a specific trip/photo | Separate, short-lived data-view grant if essential | Show why; bind to the specific record/category; log access. Do not include this in routine diagnostics. |

Do not add remote arbitrary command execution to make repair easier. A repair outside the allowlist becomes a reviewed maintenance update or a separately agreed attended remote-assistance session. Microsoft Quick Assist is a possible **fallback**, not a replacement for the requested app-specific developer console; verify installation, customer policy and privilege limitations. [Microsoft Quick Assist](https://learn.microsoft.com/windows/client-management/quick-assist).

### 6.4 Support tests that block release

- Customer admin, dispatcher, driver token, personal link and revoked developer account cannot enter support APIs merely by discovering the URL.
- A valid grant for Customer A, PC A1 cannot operate on Customer B or PC A2 unless that exact scope was approved.
- Modify command arguments, replay a completed command, reuse a grant after expiry, reorder commands and deliver queued work after End support: all fail safely.
- Restart the app/relay during a repair: recover known state, do not execute twice, and retain audit evidence.
- No active grant means no privileged support polling or accessible maintenance action. Pending-session discovery may use a bounded nonprivileged channel only.
- An operator can recover a seeded gateway-sync failure from a different network. The customer sees plain progress and ends the session successfully.
- Vendor key compromise has a documented response: disable remote support, revoke/rotate credentials, notify affected customers through the authorized process, ship a verified trust update. Local transport work continues.

## 7. Architecture, data and operations decisions

### 7.1 Keep the current core; strengthen boundaries

Retain Python, plain JavaScript, SQLite and the signed event journal. Make targeted modules for authorization projections, domain transitions, rate calculation and support commands only where they remove duplicated policy. Keep entry points thin. A new table or service must have a stated lifecycle, owner and test need.

Use one installation cluster per customer for the first release. Do not bolt a tenant field onto every local table unless multi-company operation is actually required. Cloud driver resources and remote-support routing must nevertheless isolate customers from day one.

The stdlib HTTP server is not a general production web server; Python explicitly warns about its limited hardening. Defaulting customer UI to loopback reduces exposure but does not replace Host, CSRF, authorization and request-limit controls. If secure LAN-browser access is retained, document and test its supported HTTPS front end without asking office staff to configure it. [Python HTTP server documentation](https://docs.python.org/3.12/library/http.server.html).

### 7.2 Required data contracts

- **Trip identity:** stable random ID plus an immutable allocated PC prefix/counter for the visible number. Preserve number uniqueness after restore, revoked nodes, re-enrollment and disconnected creation. Do not renumber existing paper orders.
- **Business lifecycle:** retain `draft`, `sent`, `started`, `finished`, `closed`, `cancelled` internally unless migration evidence requires otherwise. Define allowed actors and transitions explicitly. Closing is an office review decision; cancellation has a reason. Approval remains separately recorded; do not infer it from status.
- **Measurements:** keep measured kilometres, billable kilometres, missing measurements, source, original device evidence and amendments distinguishable. Never silently “correct” anomalies.
- **Rates:** stable contract/rate identity, effective date, currency, charging basis, rounding policy, and calculated trip snapshot/version. Corrections create new evidence. Distinguish an explicit zero from no configured rate.
- **Time:** UTC instants for events, explicit business timezone/date, original phone timestamp and offset, receipt time, and provenance for legacy naive values. Offline queue delay is not evidence of clock tampering.
- **Driver link:** generation, issue/expiry/revocation, allowed trip, phone-binding state and delivery intent; no administrator permissions. Device binding is a signal, not proof of a person's identity.
- **Support grant:** separate installation/operator/session identity, capabilities, customer approval, expiry, revocation and one-time command IDs; never mix with customer users or driver links.
- **Migration:** version every schema/protocol change. New fields need safe defaults, evidence-preserving backfill, compatibility negotiation and mixed-version sync tests. Mark uncertain historical data; do not fabricate it.

### 7.3 Capacity and durability budget

Use an illustrative pilot budget of 100 trips/day × 3 photos × 250 KB = approximately 75 MB/day before database and metadata overhead. Seven days of uncollected photos is approximately 525 MB. This is arithmetic from planning assumptions, not observed traffic; it already shows why a 500 MB Free D1 database cannot be the sole long-outage plan. [D1 limits](https://developers.cloudflare.com/d1/platform/limits/).

Measure normal and outage storage, writes from rate limiting/nonces, daily scans, batch statement counts, CPU, request size and customer resource costs. Record current cloud prices when provisioning; [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/) is the reference, not old “free forever” wording. Prefer smaller bounded batches first. Adopt separate object storage for photos only if the selected retention/capacity contract requires it, with integrity verification and orphan cleanup.

Define business recovery targets in the pilot: no loss of acknowledged records under the tested crash scenarios; a suggested disaster RPO of one hour for committed office data and suggested RTO of two hours from an available verified recovery set. These targets require an implementation and a drill. A six-hour automatic backup alone does not meet a one-hour RPO. An unsubmitted phone photo cannot be promised recoverable after the phone is lost.

### 7.4 Security and privacy without burdening users

Apply protection automatically: precise permissions, safe storage ACLs, signed updates, scoped cloud resources, no-secret logs, expiry and backup validation. Keep raw error details in support diagnostics. Customers should not need to turn security switches on.

Determine controller/processor responsibilities, permissible hosting locations, international transfers, notices, retention, subject access/deletion and incident response with an Egyptian qualified reviewer before live commercial cloud processing. Do not hardcode regulatory deadlines, tax rates or labour rules from memory. Operational soft deletion and append-only audit must coexist with an approved retention/erasure process: tombstones/minimized audit metadata are preferable to keeping personal payloads forever in every backup and replica. Record how backup expiry and offline devices honor deletion decisions.

Keep secrets separate from the journal and business exports. Public source is not itself a licensing defect, and compilation is not a security boundary. Remote-support consent does not authorize indefinite access or copying customer data into an agent prompt.

## 8. Execution system for Opus 5.5, Sonnet 5.5 and SOL 6.1

The model names here are the owner's requested working labels, not verified API model IDs or availability promises. If a named model is unavailable, use an available capable model and record the substitution. A single agent can execute the entire sequence; multiple agents are optional during later implementation.

| Working role | Suggested model label | Responsibility |
|---|---|---|
| Lead and independent reviewer | Opus 5.5 | Resolve architecture/security/data-contract decisions; review high-risk changes and gate evidence; protect simplicity and scope. |
| Focused implementer and user-journey reviewer | Sonnet 5.5 | Small UX/administration/help slices using existing components; wording, accessibility and realistic journey tests. |
| Backend, test and delivery implementer | SOL 6.1 | Reproduce failures; domain/authorization/recovery repairs; Windows tests, CI, installer and integration work. |

These assignments organize work; they do not establish that one model is inherently qualified to approve its own work. A different reviewer should inspect authentication, replication, financial calculations, restore/update and remote-support changes. Human release ownership remains with Mohamed.

### 8.1 Rules for every task

1. Read the relevant existing implementation and tests before editing. Reproduce the finding or write down why it does not reproduce on the current commit.
2. Choose one narrow vertical slice. A task covering several concerns below is an epic: execute its listed sub-slices separately, normally at most 3–5 implementation files plus tests/docs per slice. Do not combine a framework change with a bug fix.
3. Add a regression test for a reproduced defect, then implement the smallest durable repair. Preserve public contracts or migrate explicitly.
4. Verify allowed and denied paths, rollback/recovery where applicable, both dictionaries, and current design. Do not use snapshot updates to conceal an accidental redesign.
5. Record real commands, environment, counts, skips, warnings and artifacts. “Tests added,” “CI configured,” or “should work” does not mean verified.
6. Update task/history/guides as required during implementation. Keep a running findings ledger with task IDs and commit references; do not mark a finding closed until its negative test fails before and passes after.
7. Use synthetic data. Isolate test servers from the customer's working data. Do not run recovery, stress, deletion or import tests on a live installation.
8. Stop a dependent slice when its prerequisite is blocked; continue unrelated useful work. Do not skip a gate because a session/context window is ending.

### 8.2 Dependency order

| Phase | Tasks | Exit gate |
|---|---|---|
| A — Establish truth and contracts | T01–T03 | Reproducible baseline, approved scope/defaults, permission/state contracts. |
| B — Correctness and local protection | T04–T09 | Authorization, recovery, network/storage boundaries and validation regression tests. |
| C — Reliable trip exchange and money | T10–T18 | Driver exchange, time, historical rates, offline recovery, backups and file exchange pass. |
| D — Separate administration and support | T19–T24 | Simple existing screens, separate customer admin, hidden authenticated remote support verified. |
| E — EXE and GitHub delivery | T25–T29 | Signed installed release candidate, migrations/update/recovery and provenance proven. |
| F — Real-world readiness | T30–T34 | Performance, legal/product documentation, pilot, adversarial review and owner-approved release. |

Early CI repairs in T25 may start after T01 so all other work benefits. Installer security work in T07/T08 starts early; final packaging in T26 follows those decisions. Visual/help work can run independently after T03 contracts, but it must not race changes to shared dictionaries or routes. Remote-support protocol work follows local authorization and recovery foundations.

### T01 — Establish a reproducible review baseline

**Lead:** SOL 6.1. **Dependencies:** none. **Scope:** two slices: test/tool inventory; reference/design baseline.

Read current HEAD and status, run the existing suites in an isolated environment, and classify the three known Windows failures. Record every skipped test by name. Obtain/pin current reference commits if network access allows; preserve the documented older snapshots if not. Capture existing screens in Arabic/English, light/dark and relevant mobile widths before later UI work.

**Likely files during implementation:** test harness, CI dependency lock/manifests, baseline evidence and task/history docs. No bulk formatter pass.

**Acceptance:** (1) current commit/runtime/commands/results are reproducible; (2) Windows recovery and both COM-path failures are either reproduced or explained with evidence; (3) design baseline and reference provenance are stored without customer data.

**Verification:** rerun the existing non-browser command in §2.2 with verbose output; run gateway suite in a writable test/build environment; run browser/multi-node suites separately. Gate on actual mandatory passes, not hidden skips. A remote-reference fetch failure does not block local repairs.

### T02 — Confirm the narrow customer and commercial contract

**Lead:** Opus 5.5 with product input. **Dependencies:** T01. **Scope:** discovery and decision record; no speculative feature implementation.

Execute §3.3 when introductions/permission exist. Until then, retain this plan's operational defaults and label hypotheses. Record the supported charging basis, meaning of vendor kilometres, approval/cancellation rules, timezone, report layout, customer size, support expectations and who owns cloud costs. Decide customer-facing product name and legal publisher identity before signing.

**Likely files:** product/operations/licensing documentation and task ledger.

**Acceptance:** (1) supported workflow and explicit exclusions fit on one page; (2) finance formulas have worked examples; (3) price/support assumptions are distinguished from customer-confirmed facts.

**Verification:** walk one synthetic trip and one invoice discrepancy through the contract with dispatch/finance representatives. Missing interview access blocks claims of product-market validation, not security fixes.

### T03 — Define permission, transition and response contracts

**Lead:** Opus 5.5; SOL implements tests. **Dependencies:** T01; use T02 defaults if discovery pending. **Scope:** three slices: policy matrix; read contracts; write contracts.

Enumerate every route and generic entity operation. Map current roles to view fields, allowed transitions, category scope, file access, exports and customer administration. Define developer support as a separate principal class. Specify who may approve/cancel/review, and which writes must be server generated. Include membership/permission changes during an active session.

**Likely files:** `server/auth.py`, `server/app.py`, policy/projection module if justified, permission regression tests.

**Acceptance:** (1) all sensitive routes have an explicit policy; (2) current legitimate role journeys remain possible; (3) no generic “admin means everything including developer support” rule remains.

**Verification:** table-driven tests cover one authorized and one denied case per operation, including every confirmed F01/F02/F12 bypass. Reviewer checks the full route inventory against handlers, not only a new document.

### T04 — Enforce read, export and attachment permissions

**Lead:** SOL 6.1. **Dependencies:** T03. **Scope:** state/reports projection, then file/export projection.

Repair F01/F03 through shared server-side projection and object ownership checks. Protect rates, contacts, settings, events, logs, exports and images. Decide cache policy for sensitive attachments and support shared-PC account switching. Avoid fetching a forbidden record before deciding whether the caller can see it when that leaks existence.

**Likely files:** `server/app.py`, `server/store.py`, `server/reports.py`, authorization tests; UI callers only if response shape changes.

**Acceptance:** (1) the reproduced rates/contact disclosure fails for the restricted account; (2) out-of-scope file access fails, including known hashes; (3) legitimate dispatcher/reviewer/finance screens and exports remain complete.

**Verification:** direct HTTP tests and browser account-switch test; compare raw response bodies, not just hidden DOM. Tests also cover reports, Word, Excel, delta endpoints if added, and deleted/reassigned attachment ownership.

### T05 — Enforce business transitions on every write path

**Lead:** SOL 6.1; Opus reviews. **Dependencies:** T03. **Scope:** protected fields; locked amendments; role-specific operations.

Repair F02/F12 and the state ambiguity in F19. Server-set identities, link fields, approval actor/time and review metadata cannot be forged through generic commits. Locked corrections create amendments atomically. Dispatcher cancellation must work without granting general amendment access. Restrict invalid status/date/reference values and define the reviewed-trip cancellation rule from T02.

**Likely files:** `server/tripsvc.py`, `server/app.py`, `server/store.py`, trip API/domain tests.

**Acceptance:** (1) generic approval bypass and reasonless locked edit are rejected; (2) allowed cancel/approve/review flows work for actual profiles; (3) forbidden transition leaves no partial journal/business update.

**Verification:** negative direct API tests and primary role journeys, including retry, stale version and mixed edits in one transaction. Preserve the generic editor for harmless list operations without letting it bypass trip rules.

### T06 — Repair Windows rebuild and recovery locking

**Lead:** SOL 6.1. **Dependencies:** T01. **Scope:** handle lifetime; exclusive recovery; interrupted recovery.

Fix F06 with explicit SQLite connection closure and correct process/data locking. Rebuild into a separate verified target, validate journal and reconstructed data, and swap only after all handles are closed. Existing data/journal are retained until the result is validated. A running app must be stopped through a supported handoff, not by renaming around it.

**Likely files:** `server/nodectl.py`, `server/system.py`, Windows recovery tests.

**Acceptance:** (1) the known Windows test passes; (2) running-app rebuild refuses safely or coordinates an exclusive stop; (3) interruption leaves a recoverable old or new state.

**Verification:** Windows source and later installed-binary drills, multiple restart points, disk full and invalid journal. Confirm final fingerprints and attachment hashes. Do not delete the original recovery evidence to tidy a test.

### T07 — Bound network exposure and request handling

**Lead:** SOL 6.1; Opus reviews boundary. **Dependencies:** T03. **Scope:** loopback default; HTTP request validation; optional LAN mode.

Implement the F04 deployment decision. Local browser UI stays local by default; retain existing TLS replication. Validate Host/Origin and acceptable methods/content types; enforce request size, timeouts and concurrency limits. If LAN browser mode is in the supported offer, provision/test HTTPS with a realistic certificate lifecycle before enabling it. Customer UI should not ask staff to reason about ports or certificates.

**Likely files:** `server/app.py`, `server/tlscert.py` if reused appropriately, `config.json`, network tests, installer firewall handling.

**Acceptance:** (1) no plain-HTTP credentials cross the LAN in the default mode; (2) foreign Host/Origin and malformed/slow requests fail safely; (3) authorized multi-PC operation still works.

**Verification:** two machines, private/public Windows network profiles, permitted/blocked peers and port conflict. A TLS-enabled sync port is not evidence for the separate browser port.

### T08 — Protect local data, keys and unattended execution

**Lead:** SOL 6.1. **Dependencies:** T07 design. **Scope:** Windows account/service model; ACL migration; operational secrets.

Choose a service-owned local data directory and protected key storage consistent with replication and support availability. Ordinary users reach the app through its API, not raw database access. Do not run Office COM inside an unattended service. Restrict backup/identity/support/gateway material and tighten firewall rules. Migrate existing permissive installations without losing access or data.

**Likely files:** `installer/trip-orders.iss`, `server/to_main.py`, `server/system.py`, secret-storage boundary and installer tests.

**Acceptance:** (1) a second normal Windows account cannot read or alter operational keys/auth data; (2) daily use needs no elevation; (3) service restarts/logoff behaviour and Office import ownership are defined and tested.

**Verification:** fresh and upgraded Windows VMs, standard/admin users, reboot, logoff, antivirus enabled, backup destination unavailable. Local machine administrators remain a powerful trust boundary; do not promise protection against an administrator controlling the OS.

### T09 — Validate identities, references and input limits

**Lead:** SOL 6.1. **Dependencies:** T05. **Scope:** domain validation; batch uniqueness; immutable number allocation.

Repair F18 with typed boundaries and a persisted PC-prefix assignment. Validate finite numbers, dates, reference existence, length/count limits and uniqueness inside a batch and across concurrent commits. IDs and visible numbers have separate responsibilities. Protect normalization without silently merging two different people with the same name.

**Likely files:** `server/domain.py`, `server/tripsvc.py`, `server/store.py`, `server/node.py` if prefix allocation requires it, focused tests.

**Acceptance:** (1) invalid input is rejected with a stable error and no partial change; (2) concurrent disconnected creation never reuses a visible number within the supported cluster; (3) old trip numbers remain unchanged after migration/recovery.

**Verification:** Arabic/Western digits, malformed phones/plates, numeric extremes, bad references, duplicate batch keys, re-enrollment and a restored/revoked PC.

### T10 — Make driver-link replacement and device release durable

**Lead:** SOL 6.1; Opus reviews protocol. **Dependencies:** T05, T09. **Scope:** generation/revocation schema; office publishing; gateway enforcement.

Repair F05/F19. Persist commands for link creation/replacement/revocation and device release; use a monotonic generation contract. Gateway rejects stale updates and old generations immediately after confirmed revocation. Adopt the agreed expiry policy and explicitly handle queued evidence from the old link. No server-generated secret appears in logs, ordinary state or exports.

**Likely files:** `server/tripsvc.py`, `server/gateway_client.py`, `gateway/src/worker.js`, `gateway/schema.sql`, protocol tests, separated into small changes.

**Acceptance:** (1) replaced/cancelled old link cannot submit as current; (2) stale PC cannot resurrect it; (3) a restart cannot lose pending release/revocation intent.

**Verification:** two office PCs, first/second phone, disconnected queue, duplicate commands, schema compatibility, and TTL boundary tests. Show “replacement pending” until cloud confirmation when offline.

### T11 — Make driver event processing deterministic and durable

**Lead:** SOL 6.1. **Dependencies:** T05, T10. **Scope:** schema validation; event reduction; durable receipt protocol.

Repair F08/F09. Reduce events by stable identity and business rules rather than arrival rank alone. Include duplicate-payload consistency checks and reject UUID reuse with incompatible content. Separate accepted mailbox receipt from durable office receipt. Do not ACK a photo before its content and metadata are stored/verified to the stated durability level.

**Likely files:** `server/gateway_client.py`, `gateway/src/worker.js`, `gateway/schema.sql`, gateway/client tests.

**Acceptance:** (1) late valid start fills missing information after an end; (2) reviewed corrections are not silently overwritten; (3) retries/crashes cannot produce a duplicate or false durable receipt.

**Verification:** event permutations, lost ACK, unknown trip, malformed event, two-PC simultaneous pull, photo write interruption and re-delivery after cloud ACK/tombstone expiry.

### T12 — Prove the cloud mailbox within real service limits

**Lead:** SOL 6.1. **Dependencies:** T10–T11. **Scope:** batching; quota/retention controls; staging deployment evidence.

Repair F10. Count all SQL statements, parameters and bytes per request; split batches below limits with headroom. Validate Worker/D1 behaviour on the selected plan, not just the stand-in. Add backoff respecting retry instructions, size limits while streaming where appropriate, orphan cleanup, bounded malicious-input handling and actionable support health codes.

**Likely files:** `gateway/src/worker.js`, `gateway/schema.sql`, `gateway/wrangler.toml`, `server/gateway_client.py`, deployment/test tooling.

**Acceptance:** (1) maximum legitimate card/ACK batch succeeds in staging; (2) quotas/storage pressure preserve evidence and show an operator alert; (3) deployments isolate customer resources and never use production secrets in tests.

**Verification:** sustained and burst workload, worst-case batch with release statements, large photographs, proxy/mobile interruptions, expired retention, cloud error injection and actual billable resource measurement. Archive staging run evidence.

### T13 — Normalize time without losing provenance

**Lead:** SOL 6.1. **Dependencies:** T11. **Scope:** shared time contract; legacy migration; report/expiry alignment.

Repair F11. Use aware instants for duration/expiry and the explicit company business timezone for calendar grouping. Preserve original phone time/offset, receive time and queue status. Bundle the timezone data required by the supported Windows runtime. Decide how historical naive values are interpreted and flag ambiguous rows for review.

**Likely files:** `server/domain.py`, `server/gateway_client.py`, `server/tripsvc.py`, report/import callers and focused fixtures.

**Acceptance:** (1) the reproduced mixed-offset interval returns three hours; (2) overnight and clock-transition trips group and calculate consistently; (3) the same link expires at the same instant on different PCs.

**Verification:** UTC/offset combinations, Cairo civil-time transitions from the actual timezone database, bad phone clock, queued uploads, leap date, month/year boundary and legacy migration. Do not substitute a fixed UTC+2/+3 constant for a timezone.

### T14 — Introduce effective rates with historical calculation snapshots

**Lead:** SOL 6.1; Opus reviews finance contract. **Dependencies:** T02 defaults, T05, T09, T13. **Scope:** rate schema; calculation service; migration.

Repair F07/F12. Introduce stable rate/contract references and retain the calculation inputs for a trip. Use Decimal or minor units with an explicit rounding point; reject nonfinite/negative values except where the business contract expressly permits a credit. Keep rate editing restricted to authorized finance/customer-admin roles.

**Likely files:** `server/store.py`, `server/reports.py` or a small pricing module, `server/tripsvc.py`, finance/domain tests.

**Acceptance:** (1) a later rate change cannot silently change a prior approved total; (2) multiple rates within one month reconcile; (3) unknown historical rates are flagged rather than invented.

**Verification:** hand-calculated examples, zero/missing rates, changed trip date, concurrent rate edits, import, amendment, migration and replica convergence. If additional charging bases are requested, implement each as a separate tested slice rather than a universal tariff engine.

### T15 — Align finance screen and all exported reports

**Lead:** Sonnet 5.5 / SOL 6.1. **Dependencies:** T04, T14. **Scope:** calculation consumers; reconciliation explanations; export parity.

Use the same calculated dataset for the existing Reports screen, Excel and Word. Group by stable IDs and rate versions. Display missing kilometres/rates as incomplete, not zero. Distinguish measured cost, vendor claim and approved payable basis. Preserve the owner's existing Excel layout and its English headers.

**Likely files:** `server/reports.py`, `server/excel_io.py`, `server/word_io.py`, `js/views/reports.js`, report fixtures.

**Acceptance:** (1) all outputs match the canonical fixture totals; (2) a missing measurement does not create a false financial variance; (3) existing appearance/layout remains intact.

**Verification:** manual ledger cross-check, multi-rate month, cancelled/unfinished trip, scoped finance user, localization and recalculation in actual Excel on a synthetic workbook. Name the exported statement accurately; it is not an ETA invoice.

### T16 — Repair phone persistence, status wording and safe updates

**Lead:** Sonnet 5.5; SOL integration support. **Dependencies:** T10–T13. **Scope:** storage failure handling; receipts; service-worker lifecycle.

Repair F14 and connect the truthful delivery states from T11. Surface storage-denied/full errors without losing entered values. Retain unfinished trip data during app upgrades and use versioned assets. Delete only the app's cache namespaces. Preserve the existing driver page design and step sequence.

**Likely files:** `gateway/public/app/outbox.js`, `app.js`, `sw.js`, `i18n.js`, driver browser tests.

**Acceptance:** (1) no “saved” message before durable local storage; (2) retry/reopen/update retains unfinished work; (3) driver can distinguish locally saved from office-received using simple existing status components.

**Verification:** Android Chrome and supported iPhone browser, 360 px viewport, offline reopen, quota failure, camera denial, two tabs, stale cache, interrupted release upgrade, replaced link and reconnect. First opening a never-visited link offline need not work; explain that limitation clearly.

### T17 — Make backups restorable, coherent and protected

**Lead:** SOL 6.1. **Dependencies:** T06, T08, T11. **Scope:** backup creation; recovery material; fresh-PC drill.

Repair F13. Serialize and uniquely identify backup runs, verify all required components, track a logical journal watermark, protect account/key material, and retain necessary configuration. Separate ordinary data restore from identity recovery. Add account-only-change triggers and operational alerts for stale backups/disk pressure without alarming daily staff unnecessarily.

**Likely files:** `server/backup.py`, `server/system.py`, `server/nodectl.py`, recovery tests and operations guide.

**Acceptance:** (1) simultaneous backup requests cannot overwrite one another; (2) a verified set restores the agreed data/identity level on a clean PC; (3) failure is visible and never replaces the last good backup.

**Verification:** USB unavailable, disk full, concurrent writes, key rotation, interrupted copy, journal verification, lost administrator PC and mixed-version restore. Preserve the established restriction against live databases on network shares; any approved remote backup must be a completed protected archive, not live SQLite synchronization.

### T18 — Make imports predictable with and without Office

**Lead:** SOL 6.1 / Sonnet 5.5 for explanations. **Dependencies:** T05, T09, T14. **Scope:** error contract; native import safety; optional COM path.

Repair F16 with stable machine-readable error codes and bilingual user explanations. Test COM availability separately from registry detection. Use native readers where possible; only use installed Office on a permitted interactive path. Maintain preview/confirm, atomic import, duplicate handling and safety backup. Protect against archive/XML expansion, external content and formula injection.

**Likely files:** `server/formats.py`, `server/com_office.py`, `server/excel_io.py`, `server/word_io.py`, format/API tests.

**Acceptance:** (1) both known Windows failures are resolved against an explicit error contract; (2) supported native formats work without Office; (3) import failures neither change data nor leak document contents in errors.

**Verification:** absent/broken/installed Office, representative synthetic formats, locked/corrupt/encrypted files, malicious archives and retry after preview expiry. Real DRM files are tested only with authorization on the user's permitted environment; no protection bypass.

### T19 — Simplify existing daily interactions without redesign

**Lead:** Sonnet 5.5. **Dependencies:** T03 contracts; integrate after T05/T16. **Scope:** wording/defaults; failure recovery; accessibility.

Walk the existing dispatcher/driver/reviewer journeys and remove unnecessary required inputs, duplicated confirmations and technical messages where business rules permit. Prevent duplicate clicks; retain drafts; make the next action clear with the existing components. Preserve current navigation, themes, layout, typography and visual identity. Do not add a new dashboard or onboarding framework.

**Likely files:** existing `js/views/trips.js`, `board.js`, `auth.js`, `help.js`, `js/ui.js`, dictionaries and focused UI tests, divided by journey.

**Acceptance:** (1) the same core task uses no more steps than baseline; (2) loading/empty/error/success states are understandable; (3) visual differences are limited to necessary fixes and approved administration separation.

**Verification:** screenshot comparison, keyboard/focus/zoom/RTL checks and timed uncoached pilot tasks. User confusion is a defect to address with wording/defaults before adding features.

### T20 — Separate Settings, customer administration and developer identity

**Lead:** Opus 5.5 for boundary; Sonnet/SOL implement. **Dependencies:** T03–T05, T08. **Scope:** backend role boundary; customer administration route; Settings cleanup.

Move company-wide management into a separate Customer Administration section using the existing shell/components. Ordinary Settings remains personal preferences. Preserve bookmarks with authorized redirects where necessary. Create a separate developer-support principal/capability domain that customer role editing cannot grant. No support account is seeded into every customer's users table.

**Likely files:** `server/auth.py`, `server/app.py`, `js/shell.js`, `js/views/settings.js`, new administration view only if needed; tests per slice.

**Acceptance:** (1) Settings and Administration are separate; (2) customer admin can perform normal management without developer access; (3) staff/customer-admin direct support API calls are denied regardless of URL knowledge.

**Verification:** role matrix, deep links, browser history, account switching, personal-link login and session permission change. Ensure legacy `is_admin` helpers cannot implicitly grant developer scope.

### T21 — Complete minimal customer administration

**Lead:** Sonnet 5.5 / SOL 6.1. **Dependencies:** T17, T20; T14 for rates. **Scope:** organisation/rules; users/devices; backup/support overview.

Complete F17: supported organization fields, users/profiles, rate management according to role, a simple connect/remove-PC journey around existing pairing, backup status and recovery entry. Move technical conflict resolution, key diagnostics and raw queue details into owner support. Pairing requires explicit acceptance of the correct company/device; changing PC names does not change identity.

**Likely files:** administration view, existing `access.js`/`datatab.js`, device handlers, dictionaries and administration tests.

**Acceptance:** (1) no “coming later” placeholder remains in a sold administration feature; (2) two PCs pair without terminal/config edits and revoke correctly; (3) customer admin sees only decisions they can safely make.

**Verification:** install second PC, bad/expired code, interrupted join, wrong company, rejoin, backup-authority recovery, authorized user-management and disabled-user login. Keep an advanced confirmation for destructive restore, not for every ordinary click.

### T22 — Specify and secure developer support enrollment and grants

**Lead:** Opus 5.5; independent security reviewer required. **Dependencies:** T08, T20. **Scope:** enrollment; grant schema; command trust/rotation.

Implement the identity/protocol decisions in §6 before any remote repair endpoint. Pin the managed authentication issuer/audience and operator entitlement; enroll each customer installation with one-time credentials; define canonical signed commands and protected keys. Use a separate support deployment and key hierarchy. Plan lost developer credentials, rotation and emergency disable.

**Likely files:** new support identity/protocol modules and tests; deployment configuration/documentation. Do not put vendor private keys in the public repository or installer.

**Acceptance:** (1) customer admin cannot mint developer access; (2) grants bind exact customer/device/operator/capabilities/expiry; (3) tamper/replay/rotation/revocation tests pass before diagnostics are exposed.

**Verification:** protocol negative tests, externally reviewed threat model and key lifecycle. Managed identity configuration is verified on staging, not mocked into a universal always-true check.

### T23 — Deliver hidden remote diagnostics end to end

**Lead:** SOL 6.1 backend; Sonnet 5.5 console/help. **Dependencies:** T20–T22. **Scope:** relay/client channel; customer consent; developer diagnostics.

Build the outbound support client and authenticated remote console. Add the minimal customer support request/allow/end flow in existing Help/Administration style. Default to redacted health data; list only installations the developer is entitled and currently permitted to support. Hide developer navigation from customers; enforce all security at the API boundary.

**Likely files:** support client, separate relay/console files, `server/app.py` support endpoints, Help/Administration views and support tests, split into three vertical slices.

**Acceptance:** (1) Mohamed connects from another network without opening an office port; (2) diagnostic data excludes secrets/personal payloads by default; (3) End support and expiry stop access promptly, including offline/reconnect scenarios.

**Verification:** two isolated customer installations, revoked operator, relay outage, no active session, clock skew, device restart, browser route probing and observable customer session state. The app continues ordinary trips if support is unavailable.

### T24 — Add bounded remote repairs and a support runbook

**Lead:** SOL 6.1; Opus reviews every mutating action. **Dependencies:** T06, T10, T17, T23; update action also depends on T28. **Scope:** safe retries/backups; guarded recovery; signed update assistance.

Implement only §6.3 allowlisted typed actions. Every persistent mutation records reason, operator, customer authorization, target, command ID, before/after summary and result. Use local transaction/operation locks and idempotency. Restore/rebuild/update require their stronger scopes and safety preconditions. Unimplemented repairs remain unavailable; no generic execution escape hatch.

**Likely files:** support command dispatcher, existing recovery/backup/gateway operations, support tests, private-data-free runbook.

**Acceptance:** (1) a seeded connectivity problem is repaired remotely; (2) crash/retry cannot execute a repair twice; (3) unauthorized restore/update or arbitrary command is rejected server-side.

**Verification:** real staging session, lost response, disconnect during action, changed application version, rejected precondition and early End support. Record recovery limitations; do not advertise unattended full-PC administration.

### T25 — Make GitHub detect regressions and security issues

**Lead:** SOL 6.1. **Dependencies:** T01; start early. **Scope:** reliable matrix; scanners/dependencies; permissions/required checks.

Harden `.github/workflows/build.yml` and add only justified workflows. Run Linux and Windows tests, explicit browser journeys, real packaged-app checks, secret scanning, CodeQL Python/JavaScript/Actions where supported, dependency review/audit of build and runtime inputs, and static checks. Pin actions to reviewed full commit SHAs and lock/hash build dependencies. Configure required checks/branch protection through an authorized repository change.

**Likely files:** workflows, dependency manifests/locks, test runner config, security policy and CI tests.

**Acceptance:** (1) required test failures block merge/release; (2) scanner findings create reviewed remediation work, not auto-published changes; (3) default token permissions are read-only, with write/sign/deploy permissions restricted to their jobs.

**Verification:** a controlled failing-test/security fixture proves each gate fires; no production secret reaches fork PRs; missing tools cause required suites to fail instead of skip. GitHub runs configured checks—it cannot guarantee finding or fixing every bug automatically. [GitHub secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

### T26 — Test the actual installer and Windows operating lifecycle

**Lead:** SOL 6.1. **Dependencies:** T07–T08, T17, T25. **Scope:** lifecycle; installed journey; uninstall/repair.

Test Inno Setup installation, not only the compiled executable. Pin build inputs and target supported x64 Windows versions. Make first-run, background availability, graceful shutdown, path discovery, config placement and upgrade safe. Handle existing ports and another product installed alongside this one. Preserve data on uninstall and explain intentional complete removal separately.

**Likely files:** `tools/build_windows.py`, `installer/trip-orders.iss`, `server/to_main.py`, packaged-app tests and delivery docs.

**Acceptance:** (1) a clean supported machine runs without development tools/Office; (2) a standard user completes the primary installed journey; (3) install/upgrade/uninstall/reinstall preserve the promised records and identity.

**Verification:** clean Windows VM, Unicode paths/usernames, low disk, denied elevation, offline installation, reboot/logoff, service crash, Defender enabled and coexistence with BAMS/Teachers ports/data. Do not require disabling antivirus.

### T27 — Sign and verify the release artifacts

**Lead:** SOL 6.1; Mohamed supplies publisher identity/service access. **Dependencies:** T25–T26. **Scope:** signing provider; artifact pipeline; verification.

Choose an Authenticode provider available for the publisher's jurisdiction and account; do not assume every Microsoft service accepts an Egyptian individual/business. Sign application binaries and installer, timestamp appropriately, and verify them after packaging. Keep signing keys in the provider or protected CI environment with least privilege. Generate SHA-256 sums, SBOM, build provenance and notices.

**Likely files:** build/release workflows, packaging hooks and verification tests/docs.

**Acceptance:** (1) final EXE shows the intended trusted publisher and valid timestamp/signature; (2) tampered artifacts fail verification; (3) artifacts/manifest agree on version and source commit.

**Verification:** fresh-machine signature checks and downloaded-installer tests. Signed files can still receive SmartScreen warnings; do not promise automatic reputation or advise bypassing enterprise policy. [Microsoft SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation). Missing signing credentials blocks commercial publication, not unsigned internal testing.

### T28 — Build safe upgrade, migration and rollback

**Lead:** SOL 6.1; Opus reviews migration compatibility. **Dependencies:** T06, T17, T26–T27. **Scope:** migrations; verified update handoff; recovery.

Implement a safe installer-driven update first. An in-app update notice may offer a verified installer, but do not add a custom updater framework unless required. Verify manifest/publisher/hash, preflight capacity, create a verified recovery point, stop gracefully, migrate once, restart and check health. Support remote invocation only through T24's bounded command.

**Likely files:** `server/system.py`, version/schema migration modules, installer/build workflow, upgrade fixtures/tests.

**Acceptance:** (1) N−1 upgrade retains trips/accounts/photos and resolves pending queues; (2) interrupted update resumes or restores a coherent state; (3) unsupported downgrade is blocked with a clear recovery path.

**Verification:** test the oldest supported production version and previous version, mixed-version PCs, offline driver outbox across upgrade, partial download, bad signature, failed migration and database schema incompatibility. Rolling back a binary over a newer schema is not a rollback plan.

### T29 — Publish deliberate, complete GitHub releases

**Lead:** SOL 6.1. **Dependencies:** T25–T28. **Scope:** release trigger/versioning; asset transaction; channel controls.

Build/test development commits without silently shipping them. Default publication trigger: approved version tag that matches `server/version.py`, package metadata and release notes and targets an authorized commit. Stage a draft release, upload/verify all assets, then publish when gates and owner authorization are satisfied. Never overwrite a published version with different bytes.

**Likely files:** release workflow, version validation, release notes/build guide.

**Acceptance:** (1) ordinary PR/main development does not publish a customer release; (2) tag/version mismatch fails; (3) a failed asset upload leaves no apparently complete public release.

**Verification:** staging repository/draft runs, re-run idempotency, concurrency protection, protected environment, fork PR and signing failure. Download and verify the exact artifacts eventually offered to customers.

### T30 — Measure supported scale and responsiveness

**Lead:** SOL 6.1. **Dependencies:** T04–T18, T23. **Scope:** representative dataset; bottleneck fix; regression budget.

Use the envelope in §1. Measure cold start, main views, save/search/export, multi-PC propagation, driver upload and remote diagnostics. Optimize evidence-backed hotspots: complete-state reloads, repeated report enrichment, unbounded lists and missing indexes. Use targeted queries/deltas only if measurement justifies them; do not copy a cache from Teachers without scope/version correctness.

**Likely files:** `server/store.py`, `server/reports.py`, `js/data.js`, targeted endpoints/indexes and performance fixtures.

**Acceptance:** (1) measured reference-machine goals: ordinary local save/search P95 under 500 ms, main data view under 2 s; (2) edits are never lost because a background refresh repaints them; (3) memory, payload and queue growth remain bounded at supported scale.

**Verification:** record reference hardware/runtime/data size and at least three comparable runs; stress exports/uploads alongside normal edits and slow-network sync. Targets are provisional budgets; report failure honestly and adjust advertised scale with evidence.

### T31 — Finish honest licensing, privacy, support and onboarding materials

**Lead:** Sonnet 5.5; owner/legal review for terms. **Dependencies:** T02, T17, T20–T24, T27–T29. **Scope:** product/terms; short guides; recovery/support documents.

Correct F19 branding/license mismatch and update supported features/limits. Produce short customer guides in the product's supported languages, task-specific Help, installation/update instructions, privacy/retention information, commercial terms, support availability, contact route, third-party notices and the owner operations runbook. Preserve code-owner rights while clearly granting customer usage/data-export rights.

**Likely files:** `LICENSE.txt`, `README.md`, existing `docs/GUIDE_*.md`, release notes and required privacy/support documents.

**Acceptance:** (1) the license names this product/publisher and the real commercial offer; (2) documentation matches tested behaviour including offline/retention limits; (3) every “coming soon” or unsupported claim is removed from sales material or explicitly labelled.

**Verification:** nontechnical customer reads install/help steps and completes them; qualified reviewer confirms applicable Egyptian legal/tax/privacy positions. Font/QR/runtime/build-tool redistribution obligations are inventoried. No claim that a shipped binary makes public code secret.

### T32 — Run the customer pilot without expanding the product

**Lead:** Sonnet 5.5 / product reviewer. **Dependencies:** T19–T24, candidate from T26–T29, T31. **Scope:** onboarding; real journeys; fixes/retest.

Run a controlled pilot with the agreed users on supported hardware and staged/suitably authorized data. Include an actual office day, an overnight trip, low connectivity, changed driver, a missing photo, a monthly report, second-PC activity and a support request. Observe where users hesitate. Fix defaults, wording and bugs before considering a new feature.

**Acceptance:** (1) S1/S2 usability and design gates pass; (2) participants recover from the tested errors without technical coaching; (3) finance signs off the report examples and customer admin demonstrates support approval/end.

**Verification:** dated scenario records, task times, assistance counts, issue severity and retest evidence. No private pilot footage/data in a public repository. A lack of pilot participants is a commercial-readiness blocker, not a reason to invent results.

### T33 — Independent adversarial review and release rehearsal

**Lead:** a reviewer who did not implement the relevant slice; Opus 5.5 suggested. **Dependencies:** T04–T32. **Scope:** security/recovery review; full rehearsal; findings closure.

Review every F finding and the additional checks, focusing on generic bypasses, support privilege separation, customer isolation, lost credentials, mixed-version recovery and financial history. Run the full test matrix against the exact candidate commit and installed artifacts. Inspect CI and service configuration as well as source. Reopen any issue whose evidence is insufficient.

**Acceptance:** (1) all high/critical findings closed by evidence; (2) medium residuals have owner/impact/mitigation and cannot break S1–S8; (3) final signed installer completes clean install, core journey, support, upgrade and restore rehearsal.

**Verification:** §9 matrix and independent review notes. No blanket “all bugs fixed” declaration; state the tested scope, supported versions and residual limitations.

### T34 — Owner handover, authorized publication and post-release verification

**Lead:** release owner, supported by SOL 6.1. **Dependencies:** T33 and explicit publication authorization. **Scope:** handover; publish; verify/support readiness.

Present the exact signed candidate, release checklist, known limitations, pricing/support terms, support-console access and recovery procedure to Mohamed. Obtain publication authorization for that candidate. Publish immutable assets and verify the public download. Onboard the first customers with the tested steps; monitor opt-in operational metrics and support reports, not personal trip contents.

**Acceptance:** (1) owner can issue/revoke a support session and execute the recovery runbook; (2) downloaded release matches hashes/signatures and works on a fresh machine; (3) there is a named incident owner, rollback/withdrawal procedure and support contact.

**Verification:** install from the actual release URL, check assets/notes/version, test support from an external network and record first-customer outcomes. If signing, legal hosting approval, staging access or pilot evidence is missing, leave the release blocked and describe precisely what remains; do not mark the product ready for sale.

## 9. Verification matrix and concrete scenarios

### 9.1 Required environments

| Environment | Required evidence |
|---|---|
| Linux CI | Deterministic domain, authorization, formats, journal/convergence, gateway tests and source checks. |
| Windows source test runner | Full supported Python/Node versions, SQLite handle/recovery, paths/ACLs, source API journeys, native formats; Office COM tests separately labelled by availability. |
| Clean supported Windows x64 VM | Actual installer, trusted signature, no development tools, standard-user use, background service, reboot/logoff, firewall and uninstall/repair. Supported OS editions/builds must be recorded. |
| Upgraded Windows installation | Previous/oldest supported release, data migration, mixed-version peers, queued driver work and recovery. |
| Desktop Chrome | Existing UI in Arabic/English, themes, keyboard, zoom, font XL, user role changes and design comparisons. Follow the machine's active browser instructions; the owner authorized direct research tools during this review. |
| Driver devices | Real Android Chrome and a supported iPhone browser over HTTPS, low-end viewport, camera, IndexedDB, offline/reopen and update. If iPhone cannot be tested, do not advertise validated iPhone support. |
| Cloud staging | Actual selected Worker/D1/storage plan, limits, separate test credentials, support managed identity, replay/isolation tests and quotas. |
| Multi-PC/network | At least two Windows PCs/VMs, partition, delay, restart, revocation, simultaneous updates, authority recovery and different networks for developer support. |

Browser tests are required for future readiness even though they were not run in this review. Optional real-customer/Office checks must be listed explicitly; required suites may not silently skip because a browser is missing.

### 9.2 Existing commands versus future checks

Existing commands are documentation, not instructions executed by merely reading this file:

- From `tests/`: `python -m unittest test_unit test_convergence test_design test_domain test_trips_api test_xlsx test_excel_io test_word_io test_formats test_gateway_client`.
- From `tests/`: `python -m unittest test_multinode`.
- From `tests/`: `python -m unittest test_e2e_browser test_e2e_driver test_e2e_link_ui`, after configuring a permitted real browser and isolated data.
- From `gateway/`: `node --test --no-warnings test/gateway.test.js` on the pinned supported Node version; the bundle test generates build output.
- On a prepared Windows build machine: `python tools/build_windows.py`; this generates compiled/generated assets and is implementation/release work, not part of the present one-file deliverable.

New authorization, support, migration, installer, finance and cloud-staging suites are **planned**. Their names/commands must be recorded once implemented. Do not cite nonexistent future commands as passed tests.

### 9.3 Golden acceptance scenarios

1. **Fresh customer:** install EXE → create customer admin → enter company details → add driver/car/category → create trip → share → phone finish → office review → Excel/Word export. No CLI, manual secret generation, or framework setup.
2. **Ordinary dispatcher:** permitted actions visible in the current layout; cannot approve by direct/generic API; can cancel under the agreed rule; permission error preserves draft.
3. **Reviewer correction:** finished trip has wrong reading → reason supplied → original preserved → amendment saved atomically → reports use approved interpretation consistently.
4. **Finance history:** two trips either side of a rate change → old trip retains old rate → mixed-rate statement totals agree in all formats → missing rate is explicit.
5. **Driver offline:** after first successful page load, save start/photo offline → close/reopen → record end → reconnect → single durable office record; no false successful storage during a quota failure.
6. **Out-of-order delivery:** receive end then start, with repeated photos/events → complete usable trip projection and retained evidence; reviewed office facts remain protected.
7. **Replace leaked/wrong link:** issue replacement → old link ceases current access after confirmation → stale office PC cannot restore it → queued evidence enters the agreed exception/review path.
8. **Second PC:** pair through customer administration → edit offline → reconnect → converged records; identity/trip numbers remain distinct; revoked PC cannot resume authorized participation.
9. **Photo privacy:** restricted user obtains another category's known image path → denied; logout/account switch does not expose cached confidential evidence.
10. **Main PC failure:** verified recovery set on another supported machine → identity restored through approved ceremony → journal/data/photos validate → no duplication or revived revoked account.
11. **Upgrade:** install N−1 → create data/pending driver work → install candidate → migrate once → resumed trip and unchanged history; interrupted upgrade recovers safely.
12. **Developer support:** staff reports issue → customer admin allows diagnostic session → Mohamed authenticates remotely → views redacted health → requests safe repair → customer approves → outcome/audit visible → customer ends access.
13. **Support attack:** normal user/customer admin guesses hidden route; another customer grant, stale command, modified action or expired operator session → no privileged access or mutation.
14. **Cloud outage:** office and phone show truthful pending states; local work continues; queue drains after recovery; storage/retention thresholds notify the responsible administrator before evidence is endangered.
15. **Input/import problem:** malformed file, external-content document, oversized image, bad date, formula-like text or invalid foreign key → no code execution, data corruption or sensitive diagnostic leak.

## 10. GitHub-to-customer release contract

### 10.1 Pipeline stages

1. **Pull request checks:** syntax/static checks, unit/API/permission/convergence tests, browser journeys, security scanners, dependency review and design-regression evidence. No production keys or signing access.
2. **Windows test/build:** locked build toolchain; actual OS tests; compile existing app; assemble gateway/support version compatibility and notices. Keep customer-specific provisioning separate from the generic installer.
3. **Candidate acceptance:** install in clean VM, exercise roles and core journey, validate upgrade/recovery/driver compatibility and support session, scan the actual packaged artifact. A compiled EXE starting successfully is not this gate.
4. **Signing:** protected trusted job signs the approved candidate; final signatures/hashes/manifests verified. No untrusted branch artifacts may flow into a signing job without provenance and approval checks.
5. **Draft release:** exact version/source commit, all assets uploaded and checked, migration/support notes present. Failures remain draft; no half-published version.
6. **Authorized publication:** protected tag/environment and owner authorization, publish immutable release, download and validate from customer URL. GitHub does not independently decide that a release is commercially acceptable.

GitHub scanning and dependency bots may open remediation PRs. An agent can triage, reproduce, repair and test them. Do not auto-merge an unreviewed vulnerability “fix” or let a scheduled workflow publish new binaries solely because a scanner proposed a patch.

### 10.2 Required customer/release assets

| Asset | Purpose |
|---|---|
| `TripOrders-Setup-<version>.exe` | Signed Windows installer; the file customers normally download. Product filename may change only after the owner chooses the brand. |
| Checksums and signed/verified update metadata | Integrity and source/version binding; checksums alone are not publisher authentication. |
| Release notes and compatibility statement | Supported OS/browser/upgrade paths, relevant fixes and known limits in plain language. |
| SBOM and third-party notices | Inventory of shipped runtime/libraries/assets and applicable licenses. |
| Provenance/build evidence | Source commit, tool versions, CI run, test results and signing verification. |
| Short installation/help guide | Enough for a normal customer to install and do the first trip. |
| Operator deployment bundle/runbook | Gateway/support schema and protocol compatibility, provisioning/rollback/recovery. Delivered to the operator, not a technical setup burden for the dispatcher. |

The EXE does not contain cloud account credentials, a universal customer password, a support master key, live data, or an activation secret shared across customers.

### 10.3 Commercial licensing without disrupting transport

Before adding license enforcement, settle the commercial model. A signed company entitlement can support offline operation without embedding private signing keys. License signing, code signing, support grants and replication authority must use separate purposes/keys. License expiry must not delete data or block export/backup; provide a clearly stated grace/support policy. Do not require drivers to create paid accounts or check an online license during every trip.

Keep billing/procurement outside the day-to-day app for launch. A payment gateway, customer billing portal or anti-piracy platform is not required to ship a properly licensed EXE. Do not advertise protection against determined modification of a public-source/local application.

## 11. Blockers, defaults and escalation

| Dependency | Safe work that can continue | What cannot be claimed complete |
|---|---|---|
| Current BAMS upstream cannot be fetched | Repair local confirmed findings; use historical study with provenance. | Fresh comparison with current upstream. |
| No cloud staging credentials/resources | Unit/protocol tests, configuration templates, local UI/installer work. | Real cloud limits, cross-network developer support, production hosting readiness. |
| No signing identity/provider access | Deterministic builds, unsigned internal candidate, installer tests. | Trusted signed commercial release. |
| No representative users/contracts | Core/security repairs and clearly labelled default formulas. | Verified usability, tariff fit, pricing validation or pilot acceptance. |
| No real private workbook/Office environment | Synthetic native format tests and deterministic COM mocks. | Customer-file compatibility or real protected-file COM acceptance. |
| No legal/hosting determination | Data map, minimization, retention controls, local-only testing. | Lawful production cross-border deployment or ETA/tax compliance claims. |
| No publication authorization | Finish draft release and all reviewable evidence. | Merge/public release/customer rollout. |

Do not ask the owner to decide routine implementation details already covered by this plan. Ask only when a choice changes the promised workflow, rights, cost, data location, support access or visual design. Present a concrete recommendation and its impact. Never use “the user is simple” as a reason to conceal data loss, false success or an active remote session.

## 12. Handoff templates and stop conditions

### 12.1 Prompt for the lead agent

> Read this entire readiness plan and the repository instructions. Honor the owner's latest requirements: preserve the existing design/style; keep ordinary use very simple; separate Settings, Customer Administration and hidden Developer Support; deliver a tested signed Windows installer. Establish the current task/evidence state. Select the earliest unblocked task, reproduce its issue, implement one bounded slice, verify it, and update the handoff record. Do not rewrite the app or add deferred features. Do not claim skipped/unrun checks passed. Continue until the assigned acceptance criteria are met or a concrete dependency blocks that slice.

### 12.2 Prompt for an implementation agent

> Execute task [ID/sub-slice] only. Read its dependencies, listed findings, current code and tests first. Preserve current UI design and public data contracts unless the task explicitly requires a migration. State the minimal files/behaviour involved, implement the repair with a regression test, run relevant checks, and report actual results. Keep customer data out of artifacts. Do not grant broader roles to bypass a failed permission check. Return the exact commit/diff, test evidence, migration/rollback implications, and the next action.

### 12.3 Prompt for an independent reviewer

> Review task [ID] against the plan and actual implementation. Try the forbidden paths as well as the intended flow. Pay particular attention to generic commits, scope filtering, financial history, old/stale peers, support grants, backup/rebuild and installed Windows behaviour. Compare visual evidence with baseline. Classify each finding as reproduced, source-confirmed or unverified; give a concrete repair and regression test. Do not approve based only on the implementer's summary or a green aggregate CI badge.

### 12.4 Per-session durable handoff

Record: task/sub-slice; starting/ending commit; files changed; intended user outcome; findings addressed; tests with counts/skips; Windows/browser/cloud evidence paths; schema/protocol versions; remaining risks; blocked prerequisites; exact next command/action; whether any approval is still required. Do not place secrets or private diagnostic payloads in this record.

Suggested status vocabulary: `not started`, `in progress`, `implemented—verification pending`, `verified`, `blocked`, `deferred by owner`. Only `verified` closes an acceptance criterion. A refactor with tests not run is not complete.

### 12.5 Stop conditions for the commercial-readiness effort

The work is finished when S1–S8 pass on the exact published candidate, the owner has authorized publication, all required findings are resolved, the first installation/support/recovery runbooks work, and residual limitations are clearly stated. Stop adding features at that point.

If a blocker prevents release, deliver the verified candidate and a precise blocker record. Do not replace missing evidence with “production ready,” “all security issues fixed,” or “bug-free.” This plan is intentionally finite: reliable existing work, simple administration, safe developer help and trustworthy delivery are the product.

## 13. Source register

All web sources were consulted on 5 October 2026. Recheck mutable prices, platform limits, legal guidance and provider availability at implementation/release time. The product recommendations are engineering judgments derived from the repository and these sources, not copied feature requirements.

| Source | Use and confidence boundary |
|---|---|
| [Mr.Ayman-HR](https://github.com/coolman1984/Mr.Ayman-HR) | Requested reference. Local older snapshot and in-repository historical study inspected; current upstream fetch failed. See §2.3. |
| [Teachers](https://github.com/coolman1984/Teachers) | Requested second reference. Local source inspected at recorded HEAD; visible remote/default-branch snapshot differs; no release-readiness inference. |
| [Swvl corporate transport](https://www.swvl.com/use-cases/corporate-transit) | Advertised dispatch/reporting/transport capabilities; no independent validation of performance claims. |
| [Swvl factory transport](https://www.swvl.com/use-cases/factory-transit) | Advertised shift and multi-site needs; informs hypotheses, not mandatory launch modules. |
| [Orange Egypt Metabe3](https://www.orange.eg/en/business/business-solutions/metabe3) | Adjacent GPS/vehicle-management category and dated public bundle prices/exclusions. Not a price quote for this app. |
| [NTRA quality reports](https://www.tra.gov.eg/en/consumers/quality-of-services/quality-of-services-reports/) | Official network-quality monitoring; supports testing variable connectivity, not a universal outage claim. |
| [ETA SDK](https://sdk.invoicing.eta.gov.eg/) | Official tax-document integration boundary; no assertion that this app is tax certified. |
| [PDPC](https://www.pdpc.gov.eg/) and [PDPC portal](https://portal.pdpc.gov.eg/) | Official privacy framework and cross-border guidance. Deployment-specific legal interpretation remains required. |
| [Cloudflare D1 limits](https://developers.cloudflare.com/d1/platform/limits/) and [pricing](https://developers.cloudflare.com/d1/platform/pricing/) | Cloud batching/capacity/cost constraints. The local stand-in is insufficient deployment evidence. |
| [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use) | Least privilege, trusted workflow boundaries, action pinning and scanning guidance. |
| [Python HTTP server](https://docs.python.org/3.12/library/http.server.html) | Stdlib network-server exposure boundary. |
| [Microsoft SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) | Signing and reputation limits; signing does not guarantee no warning. |
| [Microsoft Quick Assist](https://learn.microsoft.com/windows/client-management/quick-assist) | Optional attended full-desktop support fallback. The requested application-specific developer console remains mandatory. |

**Document acceptance:** one root Markdown file; English; no application code changes; evidence-backed findings; current appearance protected; simple everyday flow; distinct customer administration and hidden remote developer support; staged agent tasks with tests/dependencies; Egyptian market sources; Windows/GitHub/commercial release gates.
