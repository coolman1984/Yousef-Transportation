# First-sale contract — Trip Orders

**Decision:** limited assisted pilot for one transport office/site and one primary Windows PC. Sell “every trip recorded, corrections visible, and the monthly report ready.” Hessa is the default first commercial priority; an already-committed transport buyer can take priority without expanding this scope.

## First paid pilot: included core

Trips; drivers, vehicles and destinations; office entry of start/end time and kilometres; authorized review/approval/corrections; basic operational report; native Excel/CSV import with preview and export; users/roles; verified backup/restore. Driver facts may be entered manually at the office with provenance. Support only the customer's validated tariff. Financial reconciliation/allocation is included only after historical rates, time/duration, rounding and screen/export consistency pass the applicable acceptance checks; otherwise offer operational tracking and explicitly exclude monetary settlement.

**Acceptance journey:** create trip → enter office-recorded start/end → review and approve/correct with history → produce matching monthly report/export → restart and retry safely → restore on another PC and confirm records. Unauthorized approval, locked-trip edits and attachment reads are refused. A changed current rate must not reprice a past trip in any included monetary report.

## Later releases and separately accepted extras

| Lane | Features | Boundary |
| --- | --- | --- |
| Next release / optional add-on | Driver phone link, camera/photos, internet mailbox, more office PCs, broader validated tariff models | Excluded from first office-only offer; existing code retained, live end-to-end acceptance required |
| Later enhancements | GPS/location, OCR, automatic messaging, standing driver links, richer organization/preferences UI, hidden developer remote support, automatic updates | Not first-pilot dependencies; attended manual support and assisted setup are acceptable |
| Future discovery | Route optimization, full accounting/maintenance, multi-site consolidation, hosted multi-customer service | Separate scope and quotation, no date promised |

Driver rollout must first prove revoked links stay revoked, event order/retries preserve facts, phone/mailbox/office receipts distinguish durability, photos survive agreed outages/recovery, and real cloud capacity/timezone behavior is acceptable. Office-only scope does not waive host/origin/session/local-file protection: verify the restricted deployment and disable/unconfigure unused internet paths. Complex/protected Office formats can be excluded; native agreed inputs must work.

## Repository facts and required integration

At decision time main bd9273b contained recent permission/rebuild fixes; branch ccr-a760379a-lzybk5 had newer rate-history, event-order, link-revocation and network restrictions work (latest fetched head 312544a). Those are application fixes to integrate/review separately, not merged by this documentation task. Recheck subsequent commits. Historical 1.0.2 installer predates the recent fixes; select/build/test a matching candidate instead. The 34-task commercial-readiness plan remains a reference: tasks are launch gates only when they affect the included promise, data/security or supported deployment; optional support/cloud/advanced distribution tasks are future lanes. Known risks are preserved, never marked resolved by reducing scope.

## Authority and agent workflow

Owner-approved on 6 October 2026: prioritize a narrow first paid pilot over completing the entire historical roadmap.
This document takes precedence over older launch scope, mandatory optional features, and instructions to take the first unchecked historical task. Later explicit owner instructions still win.

Read this file before CLAUDE.md, TASKS.md and the older execution plans. Select the earliest unverified **launch gate** below; do not start a deferred feature merely because it is unchecked in TASKS.md. Completed checkboxes record implementation history, not customer acceptance. Keep existing features/code/data; deferral changes the sales promise and work priority, not implementation status. Fix regressions and security/data risks in existing optional features if they can affect the core, or explicitly isolate/disable the affected path through reviewed implementation. This documentation update does not itself change or hide the UI.

Record each work slice in DEVELOPMENT_HISTORY.md: branch/source commit, gate, actual checks, skips, remaining dependency and next step. Recheck this contract from origin/main before starting and before publishing work; merge or cherry-pick the latest documentation if an old session lacks it. Never overwrite another agent's work, force-push or merge application changes merely to distribute these docs. Use a PR for main. All branches carry the same contract, but may have different application code; no branch-wide code/readiness equivalence is claimed.

## Minimum quality that cannot be traded away

- Correct money and historical calculations for the explicitly supported pricing model; no silent duplication on retry.
- Server-enforced roles and access to records, reports, contacts and attachments.
- Visible save success only after saving; understandable failure/retry; manual recovery with an audit trail.
- Verified backup and restoration on a different clean Windows PC; records and identities needed for the promised use survive.
- Install/start/restart and safe upgrade on the exact customer candidate; do not sell an old binary as the current source.
- Keep existing design and simple Arabic guidance. Restrict the supported deployment rather than adding architectural scope.

Acceptable compromises: manual entry, operator-assisted configuration/training, one site/primary PC, a small feature set, manual scheduled backups with a proven restore process, and later visual polish. Never waive a core data/security failure under “not perfect”. Advanced support tooling, automatic updates, commercial licensing automation and presentation films are not first-pilot dependencies. Customer support may be attended and manual. A wider self-service/public release needs its own verified distribution/signing/support decision; do not label the limited pilot a general production release.

## Launch gate ledger — no acceptance claimed by this documentation

| Gate | Evidence required | Current contract status |
| --- | --- | --- |
| L1 Candidate | One explicit source commit, integrated required fixes, matching installer and clear supported scope | Pending candidate selection/verification |
| L2 Core journey | Real user completes the journey below, including correction, retry and denied-role paths | Pending exact-candidate acceptance |
| L3 Windows and devices | Clean install, restart, safe upgrade; test the actual printer/phone only when included | Pending field verification |
| L4 Recovery | Backup then restore to another clean PC; verify records, totals, login and required configuration | Pending field drill |
| L5 Paid pilot | One named customer/site, agreed limits, assisted onboarding and documented support | Pending customer agreement |
| L6 Quote and handoff | Written scope/exclusions, acceptance checklist, support terms and separately priced extras | Pending customer-specific quotation |

Do not assign future software version numbers now or lower/bump the application's version for this docs-only change. “Next release” below is a commercial roadmap lane, not a claim that code is absent or an irrevocable delivery date. Start outreach/quotations while gates are being closed; customer operational use waits for the applicable gates.

## Quotation / RFQ contract

Quote one site, the supported device/user allowance, setup and data-import limits, training, license and bounded support. Itemize optional internet services, hardware and later features separately. Price from onboarding/support cost and customer willingness to pay; no price was approved here. Write the customer's acceptance scenario and supported capacity into the quote. No tax/accounting certification, guaranteed message delivery, unlimited hosting or “never lose data” claims. A hosted multi-customer service is a separate future decision, not silently included in this local pilot.

## Branch distribution

This owner decision is distributed as documentation-only commits to every existing remote development branch and main via a documentation PR. Snapshot targets: `ccr-68432423-3fdaqz`, `ccr-a760379a-lzybk5`, `main`. New branches must inherit it from main. Active agents must fetch and integrate it; uncommitted sessions are not updated automatically.
