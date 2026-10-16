<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

## Grok review round 1 — auth, licence poll, YT behavioural tests (2026-10-16)

**What/why:** Address independent review `review-grok-r1.md`: login and reset enumeration fixes, reset-code lockout and normalization, pending cap and re-apply, suspend/approve flows, `status`/`active` sync, state version short-circuit without full store load, km-only amend plausibility, Arabic `errkeys` + guide problem map, licence hub trial on source builds with server/client polling, access UI profile on approve.
**Checks:** `cd tests && python3 -m unittest` (CI module list incl. `test_yt_115`) — 428 run, OK, skipped=40. Gateway 24/24. Licence-hub 762/762. No hub migration.
**Next:** Owner re-review; commits on branch, no push.

## Yousef QA v1.1.4 fixes + auth (YT-01..18) — v1.1.5 (2026-10-16)

**What/why:** Branch `feat/auth-and-qa-fixes-1.1.5`: atomic login lockout, self-service sign-up with admin approve/reject and reset codes, licence page and activation UI on source builds, board cap and state `?version=` short-circuit, trip plausibility and passenger cap, i18n and UX items from report `/workspace/yousef-qa/report-v1.1.4.md`.
**Checks:** superseded by Grok round 1 entry above.
**Next:** Owner PR review; no push.

## Preserve saved licence hub on upgrade — review P2/P3 (2026-10-16)

**What/why:** `fix/1.1.4-qa-findings`, source `3049a8b`, L1/L3 upgrade regression: the default merged at config load hid a licence hub URL saved in `assist.db`. Resolve it last in Assist instead: environment → explicit config → saved database setting → default. Preserve disabled settings; fresh installs still use the default. Updated setup guide, release notes and test map. Lesson: defaults must not masquerade as explicit settings.
**Checks:** The two initial regression checks failed before the fix. `cd tests && python3 -m unittest test_qa_113.N1_LicenceHubPrecedence test_commercial_licence` — 74 tests passed, no skips, exit 0 (seven new precedence tests). The broader `cd tests && python3 -m unittest test_qa_113 test_assist test_commercial_licence` — 85 tests run, 11 errors, exit 1: the sandbox refuses socket creation (`PermissionError: Operation not permitted`), blocking local HTTP tests and class setup. Both runs used a temporary external-connection guard via `PYTHONPATH`; no external network used. Existing ResourceWarnings printed. `git diff --check` clean.
**Next:** Re-run the HTTP suites where local sockets are allowed; Windows upgrade acceptance remains unverified. No commit, push, fetch or deployment.

## Activity search window, no-matches state, and narrow audit columns (2026-10-16)

**What/why:** Review 8 on `fix/1.1.4-qa-findings` (from d16bdad). A miss inside the newest 1,000 rows hid the partial-results note and showed the empty-log text. That fetch still read every audit column, and a newer keystroke left the previous requests running.
**Fix:** The note shows when `total` is greater than the rows returned, including zero hits. A search with no rows uses its own English and simple formal Arabic empty state. The 1,000-row fetch asks only for `id,ts,user,node,label,entity,op,entity_id`. That response has exactly those keys: it does not add `node_name`. A request with no column list still returns the full row, including `node_name`. The screen reads the PC name from the `nodes` list. Search, permissions and the count are unchanged. Both requests share an AbortController; a changed or cleared search ignores late results and errors.
**Checks:** `cd tests && python3 -m unittest test_qa_113 test_e2e_browser test_unit` — 75 tests, OK, exit 0, 19 skips. Eighteen are every `test_e2e_browser` test: Python `playwright` is not installed and `/opt/pw-browsers/chromium` is missing, so the suite reports `Playwright or Chromium not available` and does not launch a browser. One is `test_unit.ToolsTest.test_rebuild_refuses_while_database_is_open` (Windows-only file lock). System Chrome 154 is installed; these tests do not use it, and Playwright was not installed. `cd gateway && node --test test/gateway.test.js` — 24 pass, 0 fail, 0 skipped, exit 0. `node --test tests/test_guides_frontend.js` — 15 pass, 0 fail, 0 skipped, exit 0. ResourceWarnings printed; they did not fail the run. Other test modules were not in these commands. `git diff --check` is clean.
**Next:** No commit yet.
## Trial grants ledger PR B — resolveTrial call sites (2026-10-15)

**What/why:** Route every trial signing path in `licence-api.js` through `resolveTrial` + atomic `trialGrantStatements` batches; lazy `ensureTrialGrantsBackfill` before first resolve; window-guard conflicts retry or map to `trial_grant_conflict`; PR B regression tests on approve/offline/force/paid expiry.
**Checks:** `cd licence-hub && npm test` (743 pass); `cd tests && python3 -m unittest test_licence_hub_signer test_hub_time` (2 pass).
**Next:** Owner review PR B; deploy hub after D1 `0004` + backfill marker on production.

## Trial grants ledger PR A — review round 8 (2026-10-15)

**What/why:** `trialGrantStatements` is async and uses the same device↔machine closure and earliest-window logic as `resolveTrial` (50-query budget, `link_limit`); propagate fills every closure subject missing a row with that window; guard fails only when the requested window differs from closure earliest; probes A/B + resolve→retry convergence tests.
**Checks:** `cd licence-hub && npm test` (718 pass).
**Next:** PR B call-site switch; owner review PR #40.

## Trial grants ledger PR A — review round 7 (2026-10-15)

**What/why:** Replace all-or-nothing grant with propagate (`INSERT OR IGNORE` + earliest-window COALESCE per subject, chunked ≤90 binds) and final NOT NULL window guard (`TRIAL_GRANT_WINDOW_GUARD_LAST`); README/PR B batch contract; regression probes (July rollback + June re-grant, device-only propagate, guard rolls back tail stmt); 99-seed paid peer only on hash index 90.
**Checks:** `cd licence-hub && npm test` (715 pass).
**Next:** PR B call-site switch; owner review PR #40.

## Trial grants ledger PR A — review round 6 (2026-10-15)

**What/why:** All-or-nothing `trialGrantStatements` (one INSERT, shared pre-check on device + listed machines; ≤90 binds / ≤11 hashes); normalized customer device match; README drops lock backfill claim; regression probes (July `b` row, lowercase paid, 95-hash `link_limit`, far-hash paid peer).
**Checks:** `cd licence-hub && npm test` (713 pass).
**Next:** PR B call-site switch; owner review PR #40.

## Trial grants ledger PR A — review round 4 (2026-10-15)

**What/why:** Owner option B lenient legacy backfill: requests/customers/`etw|` only (no d:/h: lock synthesis or `created_at` windows); chunk closure seeds under D1 bind cap; real query-count tests; paid-only locks → zero ledger; `''` paid `licence_expiry` falls back like NULL; README documents trial→paid overwrite edge case.
**Checks:** `cd licence-hub && npm test` (706 pass).
**Next:** PR B call-site switch; owner review PR #40.

## Trial grants ledger PR A — review round 3 (2026-10-15)

**What/why:** Close round-2 review on paid-replace lock backfill (ignore `lr.status`; monthly/paid + locks), skip `pending_timeout` expired rows, chunk D1 `IN` binds (≤90), drop `source_request` closure join (etw `source_request` null), `''` paid expiry vs `last_day`, expanded regression/matrix tests.
**Checks:** `cd licence-hub && npm test` (681 pass).
**Next:** PR B call-site switch; owner review PR #40.

## Trial grants ledger PR A — review round 2 (2026-10-15)

**What/why:** Close P1/high review on `resolveTrial` / backfill: no unordered `LIMIT`; recursive SQL closure (256 cap, `link_limit`); `currentTerm`-style blocking on closure; `blocked_by` on existing ledger rows; backfill set-based with `kind=trial` paid-replace evidence; `apply-migrations` always runs `0004` triggers; `normalizeMachineHash` without trim; table-driven tests + regression probes.
**Checks:** `cd licence-hub && npm test` (604 pass).
**Next:** PR B call-site switch; owner review PR #40.

## Trial grants ledger PR A — schema, backfill, resolver (2026-10-15)

**What/why:** Yousef #39 redesign part 1: D1 `trial_grants` insert-only ledger, `backfillTrialGrants` / `resolveTrial` / `linkedSubjects` / `trialGrantStatements` in `licence-hub/src/trial-grants.js`; `normalizeMachineHash` relocated (re-exported from `licence-api.js`). No call-site switch yet (PR B).
**Checks:** `cd licence-hub && npm test` (155 pass).
**Next:** PR B wires signing paths to `resolveTrial` + ledger batch writes; owner back up D1 then apply `0004_trial_grants.sql`.

## REV38 replay recovery + version on retry (2026-10-14)

**What/why:** Independent review (REV38-1): legacy hub replay without `poll_token` must not show “code refused” or offer a new request that rotates the nonce; office stays in waiting/backoff with `recovery_unavailable` and the licence screen explains that in Arabic. After an app update, replay must not 401 on version — office stores `version` at `begin()` and the hub ignores version on nonce replay (device/product/machine/shop/ref still enforced).
**Checks:** `cd licence-hub && timeout 300 npm test` (138 pass); `cd tests && timeout 900 python3 -m unittest test_commercial_licence test_licence_hub_signer` (69 pass).
**Next:** Merge with PR #38 after CI; deploy hub + office together.

## Lost-activation replay + D1 customer query budget (2026-10-14)

**Scope:** Owner-requested fixes for Codex review findings on PR #37 (P1 lost HTTP response blocks licence request; P2 customer list exceeds D1 Free's 50 SQL queries near 25 rows). Branch `fix/replay-recovery-batch-customers-20261014` from updated `main`.
**Fix:** Validate replay matches all persisted request identity fields (excluding app version metadata, which may change after an upgrade) before recovering the same HMAC-derived poll token; keep request id, so no duplicate owner notification or trial window. Office client keeps original nonce and backs off safely if a legacy hub omits the recovery token (never generates a colliding nonce). Customers endpoint gathers existing grants in batches of up to 40 device keys and chooses the strongest term in memory, preserving per-product isolation and offline IDs.
**Validation:** Regression tests added for lost response, identity mismatch, version upgrade during retry (Codex review PR #38), refusal reasons, and a 200-customer D1 query-budget scenario. GitHub CI must pass; no live deployment/real activation or clean Windows customer acceptance claimed.
**Next:** Review CI, require independent review, and deploy the updated hub and office client together only after explicit owner release approval. No automated deployment/merges.

## Apps-Factory hub-template hardening back-port (2026-10-14)

**What/why:** Sync `licence-hub/` with Apps-Factory `templates/licence-hub` (4f34038 + REV69/REV74/comb reviews): trial purge delivered-only; reissue vs `confirm_downgrade`; original trial window re-sign; sign-before-write batch; optional hashed `ref`; shop phone blanking; hub time v2; overlapping approve keeps winner locks; nonce replay without poll token; customer list strongest term; owner reissue/downgrade flows. Kept Yousef `wrangler.toml` (`trip-orders-licence-hub`, D1 `trip-orders-licence`, `LICENCE_DEFAULT_PRODUCT`, Arabic `LICENCE_PRODUCT_LABELS`, `customers.product` default `trip-orders`). No new D1 migration (payment ref still uses existing `ref` column as fingerprint).
**Checks:** `cd licence-hub && timeout 300 npm test` (134 pass); `cd tests && timeout 900 python3 -m unittest` (473 pass, 40 skipped).
**Next:** Owner deploy worker; legacy D1: `node scripts/apply-migrations.mjs --default-product trip-orders` on export if 0001–0003 not yet applied.

## Canonical trial-only key compare in afcodes (2026-10-14)

**What/why:** Vendored `server/afcodes.py` matches Apps-Factory: trial-hub enforcement compares decoded 32-byte Ed25519 keys (padded/url or std base64 aliases); malformed `trial_only_keys` entries are skipped; `trial_key_days` vs `trial_key_grace` split when span alone exceeds 14 vs grace pushes total past 14.
**Checks:** `cd tests && timeout 600 python3 -m unittest test_release_policy test_commercial_licence test_licence_hub_signer` (74 pass).
**Next:** Merge PR; no hub or release-key changes.

## REV-iso1 + af-REV74 hub cross-channel locks (2026-10-14)

**What/why:** Online/offline trial locks share `od:` + `pd:`/`ph:` (trip-orders still bridges via `d:`/`h:`); missing `PAID_SIGNING_KEY` on approve returns 503 `paid_key_missing` and leaves pending; owner tier picker defaults to trial when paid disabled; `0001` migrations per column + `0003` dedupe before unique index; `date_out_of_range` → 400; presets use `LICENCE_CALENDAR_TZ`; README documents sealed hub day replay guard + office regression test.
**Checks:** `cd licence-hub && timeout 120 npm test` (99 pass); `cd tests && timeout 600 python3 -m unittest` (full suite).
**Next:** Owner deploy hub worker; run `apply-migrations.mjs` on legacy D1 if needed.

## REV-owner7 hub product isolation (2026-10-14)

**What/why:** Customers keyed by `(product, device)` via migration `0003`; `currentTerm` and customer upserts filter by product; online locks use legacy `d:`/`h:` only for trip-orders and `pd:`/`ph:` for other products; `openRequestForDevice` and `trialUsedOnline` are per product; paid upgrade no longer steals trial locks; legacy migration skips `od:`/`pd:`/`ph:` rows.
**Checks:** `cd licence-hub && timeout 120 npm test` (93 pass); `cd tests && timeout 600 python3 -m unittest` (full suite).
**Next:** Owner apply `0003_customers_product.sql` on D1 before deploy.

## REV-owner6 hub downgrade and customers (2026-10-14)

**What/why:** `currentTerm` merges customers + issued/delivered rows (code may be cleared after ack); all issue paths return 409 `downgrade` with `current` unless `force`; reissue confirm no longer sends `force`; customers list joins `customers` with latest grant row per device+product.
**Checks:** `cd licence-hub && timeout 120 npm test` (88 pass); `cd gateway && node --test test/gateway.test.js`; `cd tests && timeout 600 python3 -m unittest` (398 pass, 40 skipped).
**Next:** Owner deploy hub worker; no D1 migration.

## REV-owner5 hub fixes (2026-10-14)

**What/why:** Block licence downgrades unless `force`; sign new codes before replacing stored rows (503 on missing key); pending cards preselect request kind; `d:` trial lock only for trip-orders; customer list shows tier; CI workflow_dispatch validates optional hub public keys.
**Checks:** `cd licence-hub && npm test` (84 pass); `cd tests && timeout 600 python3 -m unittest test_commercial_licence test_licence_hub_signer test_hub_time test_crypto`.
**Next:** Owner deploy hub worker; no D1 migration.

## REV-owner4 hub fixes (2026-10-14)

**What/why:** Paid/permanent online approval upgrades after trial without clearing one-trial locks; force reissue keeps trial lock; legacy `d:` / `offline:<device>` honoured for offline trip-orders; offline lock races check `storedGrantMatches`; owner approve cancel skips POST; customers API one row per device+product.
**Checks:** `cd licence-hub && timeout 120 npm test` (77 pass); `cd tests && timeout 600 python3 -m unittest` (full suite pass).
**Next:** Owner deploy hub worker; no D1 migration.

## REV-owner3 hub fixes (2026-10-14)

**What/why:** Offline activation rows keyed `offline:<product>:<device>` with product-aware grant match and locks; hub calendar signs only global trial/paid keys (documented); owner capabilities and panel tier controls per product; offline submit waits for products; customers list shows product.
**Checks:** `cd licence-hub && npm test` (71 pass); `cd gateway && node --test test/gateway.test.js` (24 pass); `cd tests && timeout 600 python3 -m unittest` (full suite pass).
**Next:** Owner deploy; ensure every product build trusts global `trial-hub` / `paid` public keys for hub time.

## REV-owner2 hub fixes (2026-10-14)

**What/why:** Purge stale codes by `licence_tier` only; register `GET /owner/api/products` before 405; hub time and owner capabilities honor per-product signing keys; real `0002` migration SQL, `--local` CLI note, `wrangler.toml` products list.
**Checks:** `cd licence-hub && timeout 120 npm test`; `cd tests && timeout 300 python3 -m unittest test_commercial_licence test_licence_hub_signer test_hub_time`.
**Next:** Owner deploy with optional `*_AL_STORE` secrets only if trip-orders globals omitted.

## Grok review fixes — hub seal, re-issue, multi-product (2026-10-14)

**What/why:** Address REV-owner1 (P1–Low): capped hub-day sealing in office; hub clock signing via plain env keys (trial then paid kid); grant-aware re-issue; trial-only code purge; D1 migration docs/guard; owner tier radios per card; Cairo month clamp; hub URL pin; multi-product `trip-orders` + `al-store`, route prefixes, `/licence/clock`.
**Checks:** `cd licence-hub && timeout 120 npm test` (61 pass); `cd tests && timeout 300 python3 -m unittest test_commercial_licence test_licence_hub_signer` (65 pass).
**Next:** Owner runs guarded migrations before deploy; set `LICENCE_PRODUCTS` and optional per-product keys on Cloudflare.

## Owner panel paid hub licences (2026-10-14)

**What/why:** Single owner panel issues trial, paid-until-date, and permanent codes (`PAID_SIGNING_KEY` kid `paid`); signed hub calendar time; office trusts `paid` keys, warns on corrupt clock file, seals hub day against hub URL rollback; CI workflow_dispatch optional trial-hub and paid public keys.
**Checks:** `cd licence-hub && timeout 300 npm test` (45 pass); `cd tests && timeout 600 python3 -m unittest test_commercial_licence test_licence_hub_signer test_hub_time` (64 pass).
**Next:** Owner deploy `PAID_SIGNING_KEY`, run D1 migration, rebuild commercial installers with `paid:<public>`.

## Merge origin/main into feat/licence-standard (2026-10-13)

**What/why:** Merged `main` into PR #31 branch after `feat/simple-trial-activation` merge; kept licence-standard hub catch-up cap and paid calendar recovery.
**Checks:** `timeout 900 python3 -W ignore::ResourceWarning -m unittest discover -s tests`; `cd licence-hub && timeout 300 node --test`.
**Next:** Push branch; PR #31 review.

## Merge feat/simple-trial-activation into feat/licence-standard (2026-10-13)

**What/why:** Resolved `server/licence.py` and `DEVELOPMENT_HISTORY.md` conflicts keeping PR #29 clock/bootstrap/review rules plus PR #31 paid hub-calendar recovery, calendar retry backoff, and hub time rate limiting. Hub poll catch-up is capped at eight seven-day steps per request so a stuck partial step cannot spin at 100% CPU; remaining days wait for the next scheduled retry.
**Checks:** `python3 -m unittest discover -s tests`; `cd licence-hub && node --test`.
**Next:** Push branch; PR #31 review.

## Paid hub calendar survives damaged profile clock (2026-10-13)

**Branch/source:** `feat/licence-standard`, local session fix for REVIEW-time3 P1.
**What/why:** After a hub business day was stored once, a missing or corrupt `licence-clock.v1` must not restore paid editing or count a calendar fetch as synced when the day did not persist. Assist marks `licence_hub_calendar_established` on first successful hub-day write; paid offices with that marker but no readable hub day stay read/export/backup only until the hub day is written again. Poll skips the six-hour success window while recovery is due; corrupt/sealed clock files are overwritten with the fetched hub day instead of empty fail-closed seals. Never-online paid PCs without a stored hub day are unchanged.
**Checks:** `python3 -m unittest tests.test_commercial_licence` (42 pass). `cd licence-hub && node --test` (42 pass).
**Next:** Local commit only; no push.

## Calendar failure recovery and public time protection (2026-10-13)

**Branch/source:** `feat/simple-trial-activation`, based on `5b8380a`; commercial candidate protection (L1), no pilot acceptance claimed. Implemented directly in this session without delegated coding tools.
**What/why:** Failed/invalid public calendar checks now retry after five minutes, doubling up to the six-hour successful-check interval. Only valid synchronization advances the success timestamp; success resets failure backoff. HTTP protocol errors (including truncated success/error bodies) and non-object JSON become transport failures; only canonical calendar dates can update the forward-only watermark. Trial watch fallback survives public-check failures, and activation/calendar operations have independent exception boundaries. Retry timers schedule network requests only; no licence runtime, usage or lockout counters were added. Business records, codes, signed paid grace, and read/export/backup permissions are preserved.
**Hub:** Public time GET uses the existing fixed-window pattern (120 requests/IP/600 seconds) in dedicated bounded memory, without D1 or secrets; 429 includes `Retry-After`. Deployment notes describe its per-isolate scope and recommended edge protection. Separately corrected the pre-existing approval-race test defect: select the actual loser rather than always assuming device B lost.
**Checks:** `PYTHONDONTWRITEBYTECODE=1 python3 -W ignore::ResourceWarning -m unittest discover -s tests -p test_commercial_licence.py`: 39 passed, no skips. `test_assist.py`: 22 passed, including real paid hub expiry over HTTP, denied writes, preserved records, export/backup and restart persistence. Full Python discovery with Playwright and existing Chrome enabled in an isolated test virtual environment: 445 run, 443 passed, two expected skips (Windows-only open-SQLite rename check; absent owner's private workbook), no failures. `cd licence-hub && npm test`: 40 passed; plain `node --test`: 42 discovered/passed including helper files; corrected race regression passed 12 additional runs. `git diff --check`: clean.
**Remaining/next:** Local commit only; no push, deployment, or Windows installer acceptance. Redeploy the hub and rebuild/verify the customer candidate separately. Built-in rate limiting is best effort per Worker isolate, not a global invocation-quota guarantee. The pre-existing contract-to-commercial 30-day upgrade allowance still uses `utcnow()`; this change does not claim hub-date enforcement for that separate allowance. The untracked review and `.model-fallback.log` remain untouched and uncommitted. No customer data or secrets were used.

## Windows binary licence clock writes (2026-10-13)

**What:** `os.O_BINARY` on profile/sealed file writes; read compat for CRLF clock separators and damaged auth keys; paid `activate()` bootstraps clock only when state is `missing`; CI journey DIAG removed.
**Why:** windows-installer: text-mode `os.open` on Windows corrupted HMAC payloads (`\r\n` separator) so every activation read `corrupt`.
**Checks:** `python3 -m unittest discover -s tests` from repo root.
**Next:** PR review and merge.

## Review 11 — paid bootstrap on fresh TO_HOME, block clock revive (2026-10-13)

**What:** Fresh paid `activate()` writes the first clock record when no code was stored yet (CI profile marker + missing/corrupt state); `status()` never auto-creates a clock when a code or profile auth already exists; trial replay blocked via `auth_key_on_disk()` in `_licence_clock_past_initial_use()`; hub refuses `TRIAL_DAYS` outside 1..14; regressions for wiped paid clocks, trial replay, and frozen `utcnow` catch-up.
**Why:** Review 11 / windows-installer: shared profile migration marker left paid activation at `state_corrupt`; removing auth from establishment reopened expired paid/trial clocks.
**Checks:** `cd licence-hub && node --test` (44 pass); `cd tests && python3 -m unittest discover -s . -p 'test_*.py'`.
**Next:** PR review and merge.

## CI journey fresh paid activation (2026-10-13)

**What:** `_profile_clock_established()` no longer treats a profile auth key file alone as established (fixes windows-installer journey when an earlier CI step created auth under the same Windows user); `ci_signing_key.py` writes `studio:` kid; regression test for ci-test paid activate with orphan auth.
**Why:** windows-installer `journey_exe.py first` returned `full=False` after valid standard activation on a fresh `TO_HOME`.
**Checks:** `cd licence-hub && node --test`; `cd tests && python3 -m unittest discover -s . -p 'test_*.py'`.
**Next:** PR review and merge.

## Review 10 — licence clock fail-closed hardening (2026-10-13)

**What:** Trial replay blocked when code/auth/marker/flag show prior use but clock file is gone or sealed; fail-closed seals rewrite migration marker; hub days clamp forward up to seven days per poll (frozen clock catch-up); profile lock contention no longer seals healthy state; paid activation clears trial fail-closed seal; established profile never recreates clock from a near hub day after file delete.
**Why:** Review 10: unsigned marker delete reopened trials, far hub days ignored forever on frozen PCs, lock errors sealed good trials, paid codes blocked by trial seal, deleted paid clock revived by near hub day.
**Checks:** `cd licence-hub && node --test` (43 pass); `cd tests && python3 -m unittest discover -s . -p 'test_*.py'` (452 run, 40 skipped, 0 failures).
**Next:** PR review and merge.

## Review 9 — profile marker establishment, paid clock tamper, hub jump cap (2026-10-13)

**What:** Profile migration marker counts as established clock state (assist.db flag clear no longer revives trials); paid licences deny `full` when established state file is missing without writing empty fail-closed seals; hub calendar days capped at `HUB_CALENDAR_MAX_JUMP_DAYS` per step; profile lock setup errors fail closed; Windows lock uses binary lock file with content.
**Why:** Review 9: state-file bypass after flag delete, paid hub expiry dropped on file delete, unbounded hub day latch, lock errors escaping `status()`.
**Checks:** `cd licence-hub && node --test` (43 pass); `cd tests && python3 -m unittest discover -s . -p 'test_*.py'` (448 run, 40 skipped, 0 failures).
**Next:** PR review and merge; owner hub redeploy unchanged unless already on branch.

## Paid licence calendar protection (2026-10-13)

**Branch/source:** `feat/simple-trial-activation` (PR #29), based on `1baa861`; licence protection for the commercial candidate (L1), no pilot acceptance claimed.
**What/why:** Public, uncached `/licence/time` reuses the hub calendar helper without DB/secrets. Client checks every six hours for all editions, even expired-looking codes or open requests; failed attempts stay rate limited and trial watch polling continues. Forward-only hub days expire paid codes beyond signed grace with `full=False`; existing read/export/backup access remains. No usage counters, secrets or user data changed. Updated hub guide, release notes and test map.
**Checks:** `cd tests && python3 -W ignore::ResourceWarning -m unittest test_unit test_licence_hub_signer test_release_policy test_commercial_licence test_assist test_release_files test_crypto`: 110 run, 109 pass, one Windows-only SQLite rename test skipped on Linux (commercial licence module: 34 pass). `cd licence-hub && node --test`: 40 pass; no `node_modules` present. `git diff --check`: clean.
**Remaining/next:** Local commit only; no push/deployment. Updated hub deployment, rebuilt Windows installer and field verification remain necessary. Existing `.model-fallback.log` left untouched and uncommitted.
## Review 8 — trial state integrity, hub idempotency, fail-closed reads (2026-10-13)

**What:** Block trial activation and legacy migration after established profile clock; monotonic `max_seen`; profile file lock + migration marker on save; corrupt auth/state reads fail closed without raising; hub approve/offline transactional claim cleanup, same-request idempotent issue, owner-path legacy `h:` migration, per-env offline queue + DB-authoritative code return.
**Why:** Codex review 8: missing-state replay, approval retry deleting winner locks, offline multi-instance duplicate codes, owner approve before migration, clock watermark rollback, damaged key crashes.
**Checks:** `cd licence-hub && node --test` (40 pass); `cd tests && python3 -m unittest test_unit test_licence_hub_signer test_release_policy test_commercial_licence test_assist test_release_files test_crypto` (107 pass, 1 skip).
**Next:** Owner redeploy licence hub; commercial rebuild only if shipping these server fixes.

## Review 7 — fail-closed trial state, D1 transactions, owner recovery (2026-10-13)

**What:** Profile licence clock seals permanently on corrupt/missing established state (no `_seen_now` revival); serialized `licence_state.mutate`; hub D1 awaits + batch issue/customer + loser lock cleanup + offline resume queue; legacy `h:` backfill; owner `/undelivered` list; HUB_SETUP base64url public key; README commercial vs relay URLs; assist tests use isolated profile dir.
**Why:** Codex review 7: corruption reopened trials, async D1 offline break, partial approval locks, undelivered code UX, doc drift.
**Checks:** `cd licence-hub && node --test` (37 pass); `cd tests && python3 -m unittest test_unit test_licence_hub_signer test_release_policy test_commercial_licence test_assist test_release_files test_crypto` (102 pass, 1 skip).
**Next:** Owner redeploy licence hub; rebuild commercial installers if policy docs changed only (no new keys required).

## Review 6 — trial policy, clock state, hub transactions (2026-10-13)

**What:** Commercial `TO_RELEASE_PUBLIC_KEYS` embeds `trial-hub` vs `studio` kids (`TRIAL_ONLY_PUBLIC_KEYS`); profile-bound authenticated licence clock state (`licence_state.py`) fails closed on corrupt/missing trial state; hub calendar separate from UTC watermark; monotonic hub poll scheduling; conditional SQL issue on approve; status hides orphan issued codes; legacy `machine_trials` migration; offline idempotent issue/recovery; owner issued-code panel + `/owner/api/issued`; `licence_hub_url` / `FACTORY_LICENCE_HUB_URL` separate from telemetry `hub_url`.
**Why:** Codex review 6: commercial builds trusting a leaked hub key for paid codes, assist.db tamper/revival, concurrent loser codes, frozen clock, Cairo midnight false rollback, owner handoff, upgrade lock gaps, offline trial burn, dual-URL setup.
**Checks:** `cd licence-hub && node --test` (33 pass); `cd tests && python3 -m unittest test_unit test_licence_hub_signer test_release_policy test_commercial_licence test_assist test_release_files test_crypto` (99 pass, 1 skip).
**Next:** Owner rebuild commercial installers with `trial-hub:` + `studio:` in `TO_RELEASE_PUBLIC_KEYS`; set `licence_hub_url` when telemetry stays on the relay.

## Licence-hub review fixes (2026-10-13)

**What:** Online trial lock on device code + machine hash; atomic D1 batch claim with `ON CONFLICT DO NOTHING`; pending TTL; `calendar_day` as `YYYY-MM-DD`; owner approve shows code; trial-only `trial-hub` kid enforcement in `afcodes`/`licence`; sealed `max_seen`/expiry latch (HMAC from machine tag); active-trial hub calendar poll; wider clock tolerance for paid editions; docs split telemetry relay vs licence hub and trial key generation.
**Why:** Review findings: second trial after `install_id` reset, stuck clock, race on approve/offline, poll squatting, and Studio key on Worker risk.
**Checks:** `cd licence-hub && node --test` (29 pass); `cd tests && python3 -m unittest test_unit test_licence_hub_signer test_release_policy test_commercial_licence test_assist test_release_files test_crypto` (94 pass, 1 skip).
**Next:** Owner deploy trial-hub key on Cloudflare; point office `hub_url` at licence hub only.

## Grok licence-hub + trial clock review (2026-10-13)

**What:** Device-keyed one-trial lock (online + offline), sign-before-claim approve, request validation and pending spam limits, trial expiry latch with 1h clock tolerance and hub `calendar_day`, ack clears codes + daily purge cron, HUB_SETUP points at `licence-hub/`, owner UI notes and force reissue, Arabic one-day trial strings.
**Why:** Grok-4.7 findings on duplicate trials, stranded pending rows, clock rollback, and doc drift.
**Checks:** `cd licence-hub && node --test` (26 pass); `cd tests && python3 -m unittest test_licence_hub_signer test_release_policy test_commercial_licence test_assist test_release_files` (49 pass).

## Licence-hub security review fixes (2026-10-13)

**What:** Hub hardening from independent review: atomic machine claim before signing (approve retry returns same code); monthly/permanent refused at request and approve (trial only online); deterministic poll token on nonce replay; CSRF requires header/body token plus Origin/same-site check; owner HTML served at `/owner/` with security headers and external boot scripts; PKCS#8 PEM signing key only; trial calendar days in `LICENCE_CALENDAR_TZ` (default Africa/Cairo). Tests in `licence-hub/test/*.test.js`.
**Why:** P1/P2 findings could issue duplicate trials, wrong edition, or strand approved licences.
**Checks:** `node --check licence-hub/src`, `cd licence-hub && npm test`, `tests/test_licence_hub_signer.py` (Cairo today).

## Licence tab review fixes + licence-hub Worker template (2026-10-13)

**What:** Licence tab keeps device code, paste box and Details during an active trial; one **Activate** button (paste wins, else online trial); request status/refused/failed and **Retry** on the main card with polling while the hub retries; paste survives poll redraw; `shop` on Details requests and in the preview; English day singular; formal Arabic strings; Details border token. New `licence-hub/` Cloudflare Worker template (hub protocol, owner RTL dashboard, Ed25519 signing compatible with `server/afcodes.py`). `docs/HUB_SETUP.md` privacy wording for organisation name.
**Why:** Grok review on the simple activation flow; owner needs a documented hub template without deploying from the repo.
**Checks:** `licence-hub` `npm test`, `tests/test_licence_hub_signer.py`, `tests/test_assist.py`, `tests/test_design.py`, `node --check` on `licence-hub/src`.

## Simple trial activation UI (2026-10-13)

**What:** Settings → Licence tab: one primary **Activate** path (online trial request with editable organisation name, or paste code), device code always visible, advanced hub options under **Details**. Trial countdown in the tab and a shell banner when ≤14 days remain. Licence requests may carry a custom `shop` name to the hub. Docs: `docs/HUB_SETUP.md` section «التفعيل البسيط».
**Why:** dispatchers need a short Arabic flow without replacing the existing signed-code licence system.
**Checks:** `tests/test_assist.py` (licence), `node --check` on changed JS.

## At-rest encryption stays off unless TRIPORDERS_ENCRYPT=1 (2026-10-12)

**What:** Opt-in SQLCipher / backup-archive encryption was already behind `TRIPORDERS_ENCRYPT=1`. Tests that opened archives or the live journal with raw `sqlite3` now go through `atrest` (`open_reader` / `connect`), so the same tests pass with the flag unset and set to `1`. Multi-PC crash and restore tests use a fresh temp directory per class and clean it up even when setup fails; the restore test cuts both sync directions before the offline trip. With the flag on, a missing `sqlcipher3` or `TRIPORDERS_ENCRYPT_BACKEND=file` refuses to start and does not write a plaintext work file. Docs state that recovery-key export, plaintext-to-encrypted migration, and second-PC restore are not implemented; the two-verified-backup procedure is labeled as planned. The flag must not be enabled for a real office until those exist. No vendor key and no silent plaintext fallback.
**Not changed on purpose:** the flag's default remains off. Plaintext databases are still refused when the flag is on (no in-place migration).
**Checks:** non-e2e suite in both modes; `test_backup` and `test_multinode` twice in each mode.

## PR #21 review fixes: CI installer isolation, fail-closed policy, upgrade grace (2026-10-12)

**What:** CI-test Inno Setup channel now has its own AppId, Program Files folder, ProgramData folder, and start-menu name so silent CI installs cannot upgrade over a customer install. Missing `_release_policy` on frozen/non-python executables fails closed as commercial with no keys. Offices upgrading from contract to commercial get a one-time 30-day edit grace (stored in data, not renewable; clock-back ends it; CI-test excluded). Runbook: `docs/COMMERCIAL_UPGRADE_RUNBOOK.md`. Tests: `test_commercial_licence`.
**Lesson:** installer identity and licence policy must be channel-specific; migration grace belongs in durable office data, not in the binary alone.

## Offline commercial licence and Windows executable hardening (2026-10-12, PR #21)

**Gate:** protect the paid installer without requiring internet and without intentionally harming customer data. **Branch:** security/offline-commercial-licensing-20261012, based on main c766f7ab. **What:** fail-closed commercial key policy embedded into Nuitka code, ignore writable key overrides in commercial builds, Windows CI uses ephemeral test-only keys and no automatic publication. The EXE removes docstrings, verifies no Python/debug artifacts ship, and moves optional gateway deployment materials outside the installer. The existing offline signed codes and read/export/backup during expiry are preserved. Licence title corrected. Documented a separate future storage-encryption/R2 restore project, **not yet implemented**.
**Risks & constraints:** Cannot encrypt a fully offline executable in a way that makes reverse engineering impossible; browser-delivered JS remains inspectable. No Windows commercial signing certificates or owner's real Ed25519 key embedded in CI. The currently public GitHub repository requires a separate visibility action. Never erase, corrupt or re-encrypt customer data as a tamper penalty.
**Acceptance:** full GitHub CI including Windows installed-product journey and independent review; do not merge with red/unknown status. Commercial release additionally requires real offline signing key, clean PC acceptance, upgrade and disaster-recovery checks.
**Lesson:** distinguish executable deterrence, licence enforcement and database confidentiality. They solve different problems and need different tests.

## Owner standards for every agent (2026-10-12)

**Gate:** none. Agent instructions only. The pilot promise, version, and application code are unchanged.
**What:** `.cursor/rules/owner-standards.mdc` (`alwaysApply: true`). It collects how to talk to the owner, the product bar (finished screens, personalization, Arabic RTL, offline-first, cheap tools), the stops that need the owner (secrets, customer data, money, deletion, a release), the branch-and-PR workflow, and the review checks (inputs, regression tests, both dictionaries, the Windows installer).
**Why:** those rules were already in `LAUNCH_SCOPE.md`, `CLAUDE.md`, `docs/EXECUTION_PLAN.md`, `docs/DESIGN.md`, and `docs/BUILD_AND_RELEASE.md`, but a new agent could miss them. The rule points back at the first-sale contract so a polished screen does not widen the pilot.
**Checks:** no product code, so the full suite was not run. The pull request is labeled `do-not-merge` so the hourly auto-finish does not merge it.
**Not touched:** branch `security/offline-commercial-licensing-20261012` and pull request #21.

## QA report of 12 October 2026: office-only correctness (2026-10-12)

**Gate:** L2 core journey (create trip → office start/end → review/approve/correct with history → matching report). Source: Grok's hands-on report in the Inbox repository; every item and its decision is in `docs/QA_2026-10-12_STATUS.md`.
**What changed:** (1) A trip the driver page never touched is no longer red for a missing paper or photo; the office's own entry shows yellow until someone presses **Reviewed** (stored as `reviewedBy/At`, a later correction brings the mark back). (2) `tripsvc.check_trip` refuses impossible dates, kilometres, times and statuses in new trips, hand amendments and plain saves; cancelled and closed are final. (3) One **Close the trip** form (+ **Start**) replaces five amendment dialogs. (4) Vehicles, drivers, categories, departments and requesters in use cannot be deleted; no duplicate categories/departments/people, no negative rates; department comes from the requester; place aliases are merged in reports. (5) Warnings for the same car or driver on overlapping trips, a driver over 16 hours in a day, an expired licence. (6) Imported-with-warnings trips now show yellow (the flag was never a stored column). (7) Mailbox: a wrong PC clock is reported as a clock problem with the minutes; opening a link no longer binds the phone; rate limits 120/1200.
**Mistakes / lessons:** `importWarn` was written to a column that does not exist, so it vanished silently - every flag a rule reads must be a stored field (the existing test used a flag the real flow never produced). Grok's code-review items were mostly checked before fixing: 3 of 5 were by design or already guarded - verify a reviewer's claim by a failing test first.
**Not changed on purpose:** overtime stays per trip (Excel parity); version stays 1.1.1 and nothing is merged or released without the owner.
**Checks:** new regression tests `test_trips_api` i-p, `test_domain` (overlap, office-only trust, reviewed, import warning, plate), `gateway.test.js` (clock reason, bind-on-first-message, limits), `test_gateway_client.test_0`; full suites run before the push.

## Mailbox secrets appear right after "Create the secrets" (2026-10-12)

**Gate:** supports the later-release lane "driver phone link / internet mailbox"; no change to the office-only first-pilot core.
**Bug (owner report):** as administrator, Settings → Mailbox → «اعمل الأسرار» showed «الأسرار اتعملت.» but the office secret and the
setup code never appeared, and «اعرض / اخفي الأسرار» never showed up while the gateway address was still empty.
**Root cause:** the secrets were created, but `GET /api/gateway/secrets` (and the setup code) required `SECRETS.configured`, which also
needs the address. The address only exists after the deploy, and the deploy needs the office secret: a circle. The 400 answer was then
lost in an unhandled promise, so the screen only showed the success toast. The show button depended on `configured` too.
**Fix:** `Secrets.has_secrets` (secrets exist, address or not). `/api/gateway/secrets`, the setup code and the "replace needs consent"
check use it; `GET /api/gateway` reports `hasSecrets`. The screen shows the secrets right after generating (the success toast now waits
for them), shows «اعرض / اخفي» whenever secrets exist, keeps «اعمل أسرار جديدة» as its own button with a confirmation before replacing,
adds Copy buttons for the office secret and the setup code, and says to copy the setup code again once the address is saved.
**Mistake / lesson:** a readiness flag that mixes two steps (secrets + address) blocked the first of them. Gate each action on exactly
what it needs. A promise chain after `U.run` must end in a handler, or an error disappears behind a success toast.
**Review (Codex, same day):** (1) the replace confirmation claimed every driver link stops - false, the gateway checks only each link's own hash, so the text now says links already sent keep working and how to cancel one (new link for that trip); revoking all links on rotation would be a separate feature. (2) Saving the address while the secrets were on screen left a stale setup code - the screen now reads the secrets again after every action (browser test covers it).
**Release:** version 1.1.1 (owner asked for the release on 2026-10-12); it also ships the one-command Cloudflare deploy, merged after 1.1.0.
**Checks:** regression tests `test_gateway_client.SecretsBeforeAddressTest` (API: no address, setup code to a second PC, replace needs
consent, secrets not in server output or activity log) and `test_e2e_link_ui` test 0 (real Chrome, Arabic: generate, fields visible,
copy, hide/show, cancel and confirm replace); both fail on the old code. Full suite and gateway tests run before the push.

## One-command Cloudflare deploy for the gateway (2026-10-11)

**Gate:** supports the later-release lane "driver phone link / internet mailbox"; no change to the office-only first-pilot core.
**Why:** the owner wants to take the repo and go live himself. The old guide had 9 manual dashboard steps (about 20 minutes, easy to get wrong).
**What:** `gateway/deploy.mjs` (+ `deploy.bat`): builds the single file, finds or creates the D1 database `trip-orders`, writes its id
in `wrangler.toml`, applies `schema.sql` (idempotent), deploys, then sets `OFFICE_SECRET` through stdin (never a file or a log).
Every step is safe to repeat. `.github/workflows/deploy-gateway.yml`: manual run from GitHub using three repository secrets, runs
the gateway tests first. `docs/GATEWAY_DEPLOY.md` (simple Arabic). The release now also carries the deploy files.
**Decisions (researched):** wrangler pinned to 4.45.0 (first version with D1 auto-provisioning, still beta) but the script creates the
database explicitly instead of relying on the beta feature; API token with "Edit Cloudflare Workers" + D1 Edit only; secrets only in
GitHub Secrets / Cloudflare, never in the public repo.
**Checks:** gateway tests 24/24; `node --check deploy.mjs`. **Not run:** a real deploy (no Cloudflare account in this sandbox); the
first run by the owner is the field test, `GATEWAY_SETUP.md` step 9 is the acceptance.
**Next:** owner runs `deploy.bat`, then the phone smoke test.

## Learning path per role, guide coach and simple formal Arabic help (2026-10-11)

**Why:** the owner's request (2026-10-09): every product has the same capabilities. A brand-new person learns alone and in
order, with a course for their role. The administrator's course starts by setting the office up. Pressing the guide shows
which step the person is at. All help is written in Arabic between formal and simple Egyptian: plain, slightly formal,
easy words. Trip Orders had only 8 questions, a tour and slides.
**What:**
- **Coach:** Hessa's guide coach is ported to `js/views/guides.js` (Trip Orders and Hessa share the engine). 28 guides, each
  with steps that open the page and outline the button.
- **"Solve a problem":** 35 situations of a transport office, each with "Take me there" and "Guide me".
- **Courses:** one per ready-made profile. Administrator (setup first), Centre manager (full access, without the
  administrator rights), dispatcher, GA approver, reviewer, finance and viewer.
- **"You are here":** `tripsvc.GUIDE_FACTS` / `guide_facts()`, served by `GET /api/guide-facts` to any signed-in person.
  Setup facts are office-wide. Daily-work facts count the person's own rows, so a new dispatcher in a busy office still has
  "create a trip" ahead.
- **Screens:** Help opens on "My path". The overview shows the next lesson with "Guide me".
- **Factory checks:** `tests/guide_catalogue.js` writes the help in the factory's af-guide format, and
  `tests/test_guide_gate.py` runs the factory checker `server/afguide.py` (af-guide 0.1.4) with `release=True`. The checks
  cover: complete texts in both languages, courses each profile can walk (`role-perm`), every page covered, every problem
  with a guide, and the «العربية الميسّرة» lint. Both new tests run in CI (`build.yml`).
**Mistakes:** the port was started with an earlier help checker that the factory replaced the same week. The gate was rewritten
for the factory format. The release lint then found 13 steps joining two actions, 5 long sentences and 3 «يعني»; all were
fixed. A pricing test still looked for the old Egyptian hint («بتفضل بالسعر القديم») and now reads the new sentence.
**Independent review** (no blockers) found two real problems, both fixed:
- The "print a trip order" fact also counted the month's Word report, because both are logged as "Word export". It now matches only the form (`Trip_order_*`), and a regression test (in `GuideFactsApiTest`) fails without the fix.
- The per-person facts searched the history without an index. `journal.py` now indexes `audit(user)` and `activity(user, type)`.

A guide id taken from the address is now looked up with `getElementById`, so a broken link cannot stop the Help page.
Codex's review of the PR found two more problems, both fixed:
- The course and finished lessons were saved per PC, so on a shared office PC the next person inherited them. They are now kept per signed-in person, and the facts cache knows whose facts it holds. A regression test is in `tests/test_guides_frontend.js`; the same fix went to Hessa (#32).
- The backup-folder save showed "copied" even when the copy failed. It now checks the answer first.
Codex then found that a failed facts fetch right after a change of person still returned the previous person's facts. It now returns nothing in that case, and a regression test covers it.
**Lessons:** check the factory's `main` before copying a shared part. A wording rule only holds when a test reads every text.

## Factory access standard: gate, Arabic profile names, new-person fix, "Who can do what" (2026-10-09)

**Why:** the owner made BAMS's people-and-permissions model a factory standard (`Apps-Factory/docs/ACCESS_AND_ADMINISTRATION_STANDARD.md`,
controls IAM-08…IAM-12) so Trip Orders, Hessa and Al-Store follow one set of rules instead of drifting copies.
**What:** `server/afaccess.py` (vendored from `Apps-Factory/packages/af-access`) and `tests/test_access_gate.py` check the
catalogue on every run. The first run found:
1. **The ready-made profiles had no Arabic names** — the Arabic screen showed "Dispatcher", "GA Approver"… Added `prof.*` words
   and the `roleLabel` of Hessa (data keeps the English name; the screen shows the reader's language unless renamed).
2. **A new person was saved under the wrong profile name:** the ticks were Viewer's but the list showed the first profile
   ("Full access"), and saving kept that name. Fixed as Hessa did (start = Viewer, list shows Viewer). Regression: browser test
   `test_who_can_do_what_and_a_new_person_starts_as_viewer`.
3. **"Money" sat in the Pages group but opens no page** — it decides whether rates and cost appear in reports and exports.
   Moved next to "Change rates" (id unchanged, nobody's rights change).
New: Settings → People & access → Profiles → **Who can do what**, every permission against every profile, printable (`TO.printHTML`).
**Tests:** `test_access_gate` (4), the browser test above. **Lesson:** a copied engine stays correct only if its rules are copied as a test.

## First-sale documentation review corrections (2026-10-06)

Keep copied/standalone optional-service guides independent of repository-relative contract paths; point implementers to the online source contract. For transport, remove the stale-release installation instruction and unconditional no-data-loss claim, and describe the office-only pilot before optional phone work. Documentation only; all branch copies retain the same contract and application history. Verified source/standalone link targets and Markdown-only diffs.

## Owner-approved first-sale scope (2026-10-06)

Added LAUNCH_SCOPE.md and linked every tracked Markdown guide, plan and agent skill to it. Prioritize the limited paid pilot; defer optional features without deleting code or changing historical completion status. Documentation only: no UI, runtime, pricing or application version changes. Validation: documentation links, identical contract across branch targets, skill metadata, and git diff checks. Windows/customer acceptance remains pending; follow the launch ledger.

# Development History and Lessons Learned

Newest first. Every change adds an entry: what changed, why, mistakes, lessons.

## Network default back to the office LAN (2026-10-11)

**Why:** the owner decided on 11 Oct 2026 to keep the 6 Oct 2026 decision: every PC of the office LAN can connect by default. The review's loopback default (B3) had flipped it.
**What:** `DEFAULT_CONFIG['host']` and `config.json` are `0.0.0.0` again; the installer task `lanaccess` became the unchecked `thispconly` ("This PC only"), which skips the firewall rule (private/domain only otherwise, never public) and writes `{"host": "127.0.0.1"}` only when no `config.json` exists. All other B2/B3 hardening stays (fail-closed `allowed_networks`, data-folder ACL, plain-http warning). CI now asserts the rule exists and is private/domain only after the default install, and that `/TASKS=thispconly` leaves no rule.
**Lesson / caution:** `load_config` writes the full default file when none exists, so a PC that already ran a 1.1.0 build with the loopback default has `"host": "127.0.0.1"` in its `config.json` and stays this-PC-only after an update (an explicit config is always respected). Such an office must change `host` to `0.0.0.0` by hand. The this-PC-only setting is written before the program is started (`ssInstall`), so the first start cannot write the default over it.

## Factory parity: close the 2026-10-11 review (branch `feat/factory-parity-20261011`)

**Why:** `docs/YOUSEF_REVIEW.md` found 6 blockers and 11 important gaps against the factory rules and Store's level. **What (in commit order):**
B1 `/api/state` filtered by read permissions; B2/B3 fail-closed allowlist, restricted data-folder ACL, private/domain-only firewall rule (the loopback default of this commit was reverted on 2026-10-11, see above); B4 a rate of 0 is a rate
(`pricing.is_set`); B5/I6 coherent backup snapshot + photo inventory in the manifest + explicit "incomplete" on verify/restore; I7-I9 error keys (`server/errkeys.py`), calm 400 for junk
JSON, incident number on 500, CSP-safe retry button; I1-I5 vendored the factory guide/consent/telemetry/licence parts, `server/assist.py` + `server/licence.py`, six role courses
(`guide/`), privacy and licence tabs, report dialog with exact preview, crash capture, online activation against the hub; B6 CI runs every test module and exercises the installed product
(`tools/journey_exe.py`); I10 `cryptography` for signing + authenticated key file; I11 axe/speed fixes and `tools/ui_lab.py`.
**Mistakes / lessons:** (1) the vendor script for the licence parts would have overwritten Trip Orders' own `server/ed25519.py` (it also signs the history) - only `afcodes.py` is vendored.
(2) The first-sign-in consent card covers the page: every screen test must answer it first (`make_authority(consent=...)`). (3) The factory guide button sat over the Save button of side panels
(z-index); it now sits under panels and dialogs. (4) A licence request and a code pasted in the same second looked "superseded"; the online path no longer counts as a manual paste.
(5) `aria-pressed` is not allowed on `role=tab`: the tab bars are toggle-button groups. (6) Never copy `node_modules` into the read-only factory checkout (done once, removed at once);
the UI lab now works in its own folder. **Not provable here:** Windows installer run, a real hub round trip, the Arabic reading pass by a non-developer, branch protection (see `docs/YOUSEF_REVIEW_STATUS.md`).

---

## Review follow-up on PR #7 - four findings of the Codex review, all verified and fixed (2026-10-06)

Each finding was reproduced with a failing test first (`test_time` k, `gateway.test.js` x3, `test_backup` m-p), then fixed. **Gate:** the same gates as the slices they touch (L2 money/time, L4 recovery, driver lane).
1. **P1 time (F11), real but narrow:** only the hour that happens twice (clocks go back, 29 Oct 2026 23:00-24:00) lost information: two phone events one real hour apart both became naive `23:30`, so the trip showed 0 h. (The spring case in the review is already right: `duration` localizes wall times.)
   Fix: `domain.business_text` - a phone/receive time that falls in the repeated hour keeps its Cairo offset (`...23:30:00+03:00` vs `+02:00`); every other time stays plain wall-clock text so screens, Excel and old data are unchanged. `drift_minutes` now uses instants.
2. **P1 revocation lifetime (F05), real:** the 60-day tombstone could be shorter than the life of a link (a trip planned months ahead), so a PC that was off long enough could bring a still-valid revoked link back. Now `revoked.until` = the card's expiry + 7 days (90 days when the card is unknown, for ever when the link never expires), never shortened by a second removal; the cleanup deletes by `until`; a table made by the first version is upgraded in place.
3. **P2 restore-set (F13), real:** it moved the current files aside before copying, so a full disk mid-copy left an empty data folder. Now the whole set is staged next to the data first, then the swap, with an `undo()` that puts everything back; tested with a copy failure and a placement failure (the data folder is byte-for-byte as before, no leftovers).
4. **P1 photo copies (F13), real:** a same-size corrupted copy was trusted for ever. Photos are named after their SHA-256, so every new copy is checked, every run re-checks the next 300 existing copies (a rolling cursor, so a large folder is covered over time without re-reading everything each run) and repairs a bad copy from the original - only when the original still matches its name; a damaged original is never copied over anything and is reported. `restore-set` now checks every photo against its name and refuses to bring back a damaged one (it says how many).
**Lesson:** "size is the same" is not proof; where the data names its own checksum, use it. And a restore must be staged before it touches what exists.

---

## Commercial readiness slice 7 - receipts and photo durability (F09) (2026-10-06)

**Gate (LAUNCH_SCOPE.md): driver-lane precondition "phone/mailbox/office receipts distinguish durability, photos survive agreed outages" (next-release lane, not a first-pilot dependency).** Branch ccr-a760379a-lzybk5 from 42d0e7b.
**Checks:** `gateway.test.js` 21 (+4), `test_e2e_driver` 8 (+1, and test_a now proves the three ticks and that the photo blob stays until the office receipt), `test_gateway_client` +2; Linux, node 22, Chromium 1194. **Not run:** a real Cloudflare account, a phone with real storage limits.
**Reproduced from the code (F09):** the phone deleted its photo and printed "Received by the office" as soon as the *mailbox* answered ok; the mailbox deletes unacknowledged items after 30 days (`scheduled`) - with the office off for a month the only copy of an odometer photo was silently gone and the phone had already said it was safe.
**Design:** `receipts(uuid, at)` in the gateway, written by `/office/ack` (one multi-row INSERT per 40 ids, DELETEs per 90 ids - far fewer statements than one per item), kept 60 days, created lazily for mailboxes deployed with the old schema.
`POST /api/receipts/<token>` {uuids<=100} -> {office, mailbox}; an id in neither list is *unknown* (never stored, or dropped by retention). The phone (`outbox.js`) keeps photo blobs until `officeAt`; unknown items are marked unsent and go out again with the same uuid (the gateway and the office both de-duplicate by uuid, the office also checks its own tables); items are tidied 7 days after the office receipt and after 120 days regardless.
UI: ✓ saved on phone, ✓✓ in the mailbox, ✓✓✓ stored by the office; driver guide and strings in both languages. Office: `oldest_waiting_seconds()`, `late` after 3 days, a warning card in Settings > Mailbox. Service worker cache name bumped so phones fetch the new page (F14 still open: a page that is open keeps running the old script until reloaded).
**Mistakes:** my first bulk-ack test hit the per-link rate limit (60/10 min) - the Worker was right, the test inserted the rows directly instead; `test_a` fetched a photo after acknowledging it (acknowledging deletes it) - order fixed.
**Next:** the Windows/field gates (L1 candidate, L3 clean install, L4 drill) need real hardware; software side left: F10 (D1 statement budget of the other routes), F14 (safe page update), F15 (installer/CI hardening), F17-F20 (admin separation, validation, docs, developer support).

---

## Commercial readiness slice 6 - import error contract (F16) (2026-10-06)

**Gate (LAUNCH_SCOPE.md): core import path ("native Excel/CSV import with preview"); protected/Office formats are an allowed exclusion, so this slice only makes their refusal predictable.** Branch ccr-a760379a-lzybk5 from 20c0f1e.
**Checks:** `test_import_errors` 6 (all layers, Office codes with a pretend PowerShell, the API answer, no data change, no content repeated), `test_formats`, `test_excel_io`, `test_word_io`; Linux, Python 3.13. **Not run:** Windows with Office (the two known failures should now pass there; to confirm).
**Root cause (reproduced here by pretending Office is present and automation fails):** the two tests expected the built-in readers' plain refusal, but on a PC where Office is *registered* a DRM-looking file is sent to Office and the answer is Office's/the environment's (`officeFailed` here). It was a test/product-path mismatch, not a defect in either route.
**Contract:** each failure has a stable code - `FormatError(msg, code)` (default derived from the standard message), carried by `ImportError_`, `WordError`, `OfficeError` and `BadRequest` into the API as `{error, code}`; `js/views/excel.js` picks the dictionary text by code (`CODE_KEY`), the English-substring map stays only as the fallback for old messages.
Codes: drm encrypted pdf image xlsb old empty unknown big damaged wordGiven sheetGiven noTable | officeMissing officeTimeout officePassword officeFailed | noColumns noTrips previewExpired nothingToImport noForm needCategory.
**Tests no longer depend on the host:** the refusal tests switch Office off (`_no_office`), Office has its own tests; harness `ApiError` now keeps the JSON answer. **Not done:** formula-injection check of exports, a real Office run.
**Next:** F09 (receipts and photo durability of the driver lane), then the Windows field drills (L1/L3/L4) which need real hardware.

---

## Commercial readiness slice 5 - one time contract (F11) (2026-10-06)

**Gate (LAUNCH_SCOPE.md): L2 core journey / money - "time/duration" precondition of any monetary report.** Branch ccr-a760379a-lzybk5 from 4f57d6d. **Checks:** `test_time` 10 (+1 in `test_gateway_client`), neighbours
`test_domain`, `test_trips_api`, `test_pricing`, `test_design`; Linux, Python 3.13 (a real tz database present). **Not run:** Windows (where there is no tz database: the installed program uses the built-in rules - proven equal to the database here, not run there).
**Reproduced:** `duration('2026-10-01T08:00:00+03:00', '2026-10-01T08:00:00Z')` was 0 h (`parse_dt` cut the offset), `_epoch` read a naive expiry as UTC while it was written in the office PC's local time (links expired 3 h late, and differently on a PC with another zone setting).
**Contract (new `server/tz.py`, `domain.py`):** a time with a zone = exact instant; without = Cairo wall time. `duration` = elapsed time between instants (Egypt's two clock-change nights are right: 3 h not 4 on 23->24 April, 6 h not 5 on 29->30 October 2026);
`parse_dt` = naive Cairo time (what screens, reports, Excel and calendar grouping use); `business_now()` replaces `datetime.now()` where a business date/time is meant (new trip date, amendment time, rate-history date, open-too-long check);
`link_expiry()` returns an aware UTC time; `gateway_client.local_pair` converts the phone's time and the receive time to Cairo (a phone set to UTC/any zone is corrected; drift stays the true difference); the stored event keeps the phone's original text with offset and the exact UTC receive time (`payload.phoneAt/recvAt`).
`Y_TIME_UNCLEAR` (yellow) marks a trip whose start/end falls in the repeated or skipped hour. `EgyptRules` (tzinfo) is used when `zoneinfo` has no data; the test sweeps every half hour 2023-2030 in both directions (instant->wall, wall->offset incl. both folds) against the database.
**Decisions:** business zone fixed to Africa/Cairo (one-company pilot); ambiguous wall times take the first occurrence (fold=0) and are flagged, not guessed; old naive `linkExpiry` values are read as Cairo (the office PCs were in Cairo). **Lesson:** a phone's clock is evidence, not truth - keep its text, show business time.
**Next:** F16, then F09 (the driver-phone lane: receipts and photo durability).

---

## Commercial readiness slice 4 - backups (F13) (2026-10-06)

**Gate (LAUNCH_SCOPE.md): L4 Recovery** - branch ccr-a760379a-lzybk5 from 312544a (+ the owner's docs commits cda804a merged). **Checks:** `test_backup` 15 (engine, tool through a subprocess, real Chrome banner) and the earlier suites; Linux, Python 3.13. **Not done:** the field drill on a real second Windows PC (L4 stays PENDING until it is run with the real installer); mixed-version restore. **Next step:** F11 (time/duration), then F09, F16.

**Reproduced first (`tests/test_backup.py`, engine only):** 8 simultaneous `create()` calls -> `FileNotFoundError` / `disk I/O error` (one shared `.tmp` per name); two backups in the same second -> the second
`os.replace` overwrote the first; a photo copy cut short by a power failure was trusted because its name existed; nothing proved that data, accounts and history belong together; an account-only change never made
a backup due (the scheduler watched `store.version()` only).
**What changed (`server/backup.py`, small edits in `auth.py`, `app.py`, `datatab.js`):** a lock (one run at a time); a free name (a taken second moves to the next); every part is snapshotted into a uniquely tagged temporary
file, checked (SQLite integrity, size, SHA-256) and renamed - auth, history, manifest, and the data file LAST, because the data file is what makes a set visible/restorable; any failure removes the temporary files and the
parts already placed, keeps the last good set and sets `last_error` (shown in Settings > Data as a red note; "overdue" as an amber one, counted from the last good backup or from program start so a new installation never warns);
disk space is checked first (plain message); the manifest `to_<time>_<kind>.json` lists sizes, checksums, history watermark (`journal.vv()`), data version and app version; `verify()` is used by `restore()` (a legacy set without a manifest
still restores, checked by SQLite only); the scheduler uses the watermark (data version + history), which also covers accounts because account changes are history entries; the second folder gets the same set file by file, data last;
photos are mirrored one file at a time under a temporary name and re-copied when the size differs (a failed photo is counted and reported, it does not stop the database backup). Backup copies are plain single files now
(`journal_mode=DELETE` on the copy; before, `-wal`/`-shm` files stayed next to every renamed copy).
**Drill result (important for the owner's guide):** a clean PC given ONLY a set (data, accounts, history, photos) comes back with all business data, working logins and photos, but the program starts as a new device and keeps the old history
as `journal.incomplete-*.db`: the PC's secret keys (`data/node`) and the mailbox secrets (`gateway.json`) are deliberately not in a set. Putting them in plain files on USB drives would be a key leak, and encrypting them needs a
cipher the standard library does not have, so a restore is data level. (Correction: `nodectl export-authority` already seals the administrator key with a passphrase - scrypt + HMAC stream, written earlier in the project - so the administrator identity can be kept separately by the operator; a general key package inside every backup is still not done.)
**New tool:** `TripOrders.exe tool restore-set <backup folder> [set]` (`nodectl.cmd_restore_set`): picks the newest set that passes `verify_set`, skips damaged ones with the reason, moves what was in the data folder (and `node/`) to `data/replaced-<time>/`, places data/accounts/history, copies photos whole, refuses safely (everything put back) if the program still runs. Tested through a real subprocess: the L4 drill is one command instead of file copying.
**Mistakes:** my first UI strings used double quotes inside double quotes - `JsSyntaxTest` (added last slice) caught it at once; the first "overdue" rule warned on a new installation (found by the browser test).

---

## Commercial readiness slice 3 - rates by trip date (F07), web address check (F04) (2026-10-06)

**F07 (reproduced in the plan, rebuilt as tests):** reports read the category's CURRENT rate, so raising the rate re-priced every old month. New `server/pricing.py`:
`tripCategories.rateHistory` holds the superseded rates as `{until, ratePerKm, ratePerOtHour}`; a trip dated before `until` uses that entry, later trips the next one, finally the current
rate. The server writes the history when a category is saved (`tripsvc.normalize_ops`): the client's copy is ignored, a change on the same day as the last one is a correction (no new entry),
a rate that was never set is not history (the first value applies to every trip, as before - nothing invented), and `force` (full restore / sample data, needs `data.import`) keeps a history as given.
Reconciliation money is now added trip by trip with each trip's own rate (before: whole month x one rate). The history is hidden from users without a money permission like the rates.
The category screen explains the rule in one sentence (EN/AR). **Deliberate simplification:** the effective date is always "the day you save"; retro-corrections and a date picker are not built.
**F04:** reproduced - through `Host: evil.example.com` the first administrator was created on a fresh server (`/api/auth/setup` only checks that the peer IP is local; a browser that was
tricked into talking to 127.0.0.1 under an attacker's name is local). Now every request needs a Host that is an IP address, `localhost`, a one-word computer name, `*.local`, the PC's own full
name or an `allowed_hosts` entry. Also: idle timeout 120 -> 60 s (`idle_timeout_seconds`), `max_connections` (128) with a 503, and a damaged `Content-Length` no longer drops the connection without an answer
(`send` called `int()` on it - found by the new test).
**Mistakes:** (1) my first English help text had an apostrophe inside a single-quoted JS string - the whole language file broke and every label showed as a raw key; `test_design` (regex based) did not notice,
the real-Chrome test did. Added `JsSyntaxTest` (node --check on every page script). (2) first `stamp` call site sat inside an `elif` chain and would have been a syntax error - caught by reading the diff before running.
**Owner decision (asked after the slice, answered 2026-10-06):** staff open the program from other PCs on the same network and from other networks (branches). So the plan's "loopback by default" is NOT applied.
Instead `server/netpolicy.py` (pure functions, unit-tested) makes the program answer only this PC and private networks (RFC 1918, link-local, 100.64/10 for VPNs, IPv6 ULA/link-local): the "never reachable from the
internet" rule now holds inside the application even if a router or the firewall lets a public address through. `allowed_networks` in `config.json` replaces the default list (this PC is always allowed); a list with nothing usable
falls back to the default instead of locking everybody out. Refusal is tested end to end with a client bound to 127.0.0.2 against a server whose list names other networks (a real public source address cannot be created in this sandbox).
**Still open (needs Windows or a certificate decision):** plain HTTP crosses the company network, so credentials are readable by anyone on a hostile WAN segment unless the VPN encrypts it; HTTPS for the web port needs a certificate
people can trust without a browser warning. The installer rule `profile=any` stays: a `remoteip=` rule with the private ranges would be the next step, but a silently failing `netsh` line would block the program on the customer's PC and I cannot run it here.

---

## Commercial readiness slice 2 - driver events in any order, replaced links really die (2026-10-06)

**Plan:** findings F08 and F05 (tasks T10/T11 first slices). Reproduced both before touching code.
**F08 (reproduced):** `apply_event` gated on status rank only, so an `end` that arrived first set `finished` and a later valid `start` was dropped - the trip kept
no start odometer/time. It is now an order-independent reducer: first start and first end win, a start after an end fills only what is still empty (an
odometer the office already typed is kept), closed/cancelled/unknown status is never touched, malformed bodies (`data` not an object, non-text route) change nothing
instead of raising. Also `pull()` now isolates each trip and photo: one that cannot be applied no longer stops the acknowledgement of the others (before, one
poison message made every round fail and nothing was acknowledged); the office sees the reason in the mailbox status.
**F05 (confirmed by the existing test comment "the old token's card is still on the gateway until it expires"):** replacing a link only changed the hash on the trip;
the old card stayed live and its phone could still post events as the current trip. Now `make_link(replace)` stores the replaced hash in the new `trips.oldLinks`
(hashes only, last five, replicated like any trip field so any PC can deliver it), `push_cards` sends `remove` for them before the new card, and the Worker keeps a
`revoked` tombstone table (60 days) so a stale PC that still publishes the old card cannot bring it back (`INSERT ... WHERE NOT EXISTS`). The Worker creates the table
on first use, so a mailbox deployed from the old `schema.sql` keeps working after a Worker-only update. Evidence the old phone had already delivered stays in the mailbox and is applied.
**Tests:** Python unit f-h (all 24 arrival orders of start/end/retries give the same trip; closed/cancelled/filled; malformed), integration f (end pulled first, start next round)
and d (old link 404, old phone's event 404, stale PC republish stays 404, three replacements), gateway.test.js +2 (tombstone, table made on first use and cleaned).
**Mistake found on the way:** the CI command did not list `test_permissions`, so slice 1's tests would never have run in CI. Added.
**Lesson:** the integration test must fail on the old code - the first F08 end-to-end assertion read a missing key, so it failed for the right reason but with an unhelpful message; assert with `.get`.
**Not done (still open):** durable device-release intent (still an in-memory set), D1 statement budget per request (F10, removals use batches of 20 to stay modest), Worker-side event schema, durable office receipt (F09).

---

## Commercial readiness slice 1 - real permissions on read and write, Windows rebuild (2026-10-05)

**Plan:** `COMMERCIAL_READINESS_EXECUTION_PLAN.md`, findings F01, F02, F03, F06, F12 (tasks T03-T06 first slices).
**What:** (1) `nodectl rebuild` closes its SQLite handle before renaming (Windows `WinError 32`) and, if the app still holds the file, puts every
file back and says so in plain words. (2) `/api/state` is filtered by `app.project_state`: rates need a money permission, driver/people mobile numbers
need the page that shows them. `/api/reports` and the clean Excel/Word exports leave out vendor reconciliation and cost allocation without
`finance.view` (the Reports page hides those cards). (3) A plain save (`/api/commit`) can no longer set approval, status, link, lock or number fields,
edit a locked trip, create an approved/linked trip or write an amendment by hand; the dedicated trip routes use `commit_guard(internal=True)` (they check
their own permission and keep the category limits). Dispatcher cancel now works (it needed `trips.amend` before); cancelling a closed trip needs
`trips.amend` or `trips.review`. (4) Trip photos follow their trip: `files.download` plus the user's categories (404 for other categories), served
`private, no-cache` instead of one year `immutable`.
**Tests:** `tests/test_permissions.py` (11, direct API calls); `test_unit` rebuild + refusal; `test_trips_api` insights now uses the amend route;
`test_e2e_browser.ReportsPageTest` gained a reviewer without the Money permission (real Chrome, `TO_CHROMIUM` set). Run on Windows, Python 3.12.10:
152 tests, 147 pass, 3 skipped, 2 fail (the known Office-COM refusals, F16). `test_multinode` could not be used as evidence on Windows (harness sends
`SIGINT`; same 10 `setUpClass` errors on the untouched commit); I only edited the one multi-PC test that renumbered a trip through a plain save.
**Mistakes:** my first refusal test compared whole folder listings - the tool itself creates `program.lock`; compare the database files only.
`test_g_insights` had been setting `status` through a plain save, i.e. it relied on the very bypass that is now closed.
**Not done yet (still open in the plan):** F04 LAN/HTTP exposure, F05/F08-F11 gateway protocol and time, F07 historical rates, F13 backups, F16 the two
Office-COM Windows test failures (`test_formats` refusals), everything from T19 on (administration/support/installer).

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
