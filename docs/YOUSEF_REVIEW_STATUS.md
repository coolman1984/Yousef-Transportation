# Status of the 2026-10-11 review items

Branch `feat/factory-parity-20261011`. "Fixed" = changed in code and covered by a test that ran green locally (Linux). **Nothing here is `field_accepted`;** Windows, customer and live-service evidence is listed under "Remaining".

| Item | Status | What changed | Proof |
|---|---|---|---|
| B1 state leaks | fixed | `project_state` empties trip lists without a trip-reading permission and lookup lists without any working permission | `test_permissions` l, m |
| B2 data-folder ACL | fixed in installer (Windows run pending) | `icacls` narrows `%ProgramData%\TripOrders` to SYSTEM, administrators, one operator | `test_network` e4 (script); CI step `icacls` on Windows |
| B3 one-PC boundary | fixed | loopback default, fail-closed allowlist, firewall rule only on request and private/domain only, `secure_cookie` option, plain-http warning, `docs/NETWORK.md` | `test_network` e, e2, e3 |
| B4 zero rates | fixed | `pricing.is_set`, history keeps every interval; report = Excel = Word | `test_pricing` g, h, i, c2 |
| B5 backup coherence | fixed | 5 attempts, abort on exhaustion, accounts inside the check | `test_backup` q, r |
| B6 installed candidate | **partly**: CI added, not run | CI runs every test module (+ access gate); Windows job: silent install, ACL + firewall check, installed journey, update over it, N-1 update, uninstall keeps data, release proof | `test_release_files`; journey ran on the source here |
| I1 guide | fixed (reading pass pending) | 6 role courses, progress on the server, guide language, "?", error button, F1 | `test_guide`, `test_e2e_guide`, factory `check --release` clean |
| I2 consent + telemetry | fixed | two agreements, withdraw purges, factory taxonomy, bounded outbox, off until consent + address + token | `test_assist`, `test_e2e_guide` |
| I3 report a problem | fixed | button on every page, redaction, exact preview + digest, queued/sent/retry state, works without consent | `test_assist` ReportTest, `test_e2e_guide` c |
| I4 crash reports | fixed in code; hub round trip pending | `crash_report` -> fingerprint only, incident number to the person, browser fingerprints | `test_assist` CrashTest |
| I5 licence/trial | fixed in code; real hub/Studio pending | device-bound codes, expiry-safe read/export/backup, preview, persisted polling/retry, manual fallback | `test_assist` LicenceTest |
| I6 backup photos | fixed | photo inventory + checksums in the manifest, `ok/restorable/complete`, restore + `restore-set` say "incomplete", second-folder failures shown | `test_backup` s-w, q2 |
| I7 Arabic errors/installer | fixed (reading pass pending) | `errkeys.py` + `err.*`/`autherr.*`/`lic.*` in both dictionaries, Arabic installer | `test_errors`, `test_network` e4 |
| I8 junk JSON | fixed | non-object bodies are a 400, junk values a calm 400 with an incident id, 500 shows no exception text | `test_errors` |
| I9 retry button | fixed | listener instead of `onclick` | `test_errors` f |
| I10 crypto | fixed for the installed program | `cryptography` for Ed25519 when installed; authenticated v2 key file, v1 still opens; pure-Python only as the portable fallback | `test_crypto` |
| I11 a11y/perf/style | fixed on the last run | axe serious/critical = 0 on 13 pages x 2 widths; all pages within budget on the last run (TBT is noisy: two runs each missed once); Settings in tokens/classes; gzip | `docs/ui-lab/REPORT.md`, `test_design` |
| N1 unfinished tabs | fixed | Organisation and Money tabs hidden | `test_e2e_guide` d |
| N2 maintainability | not started | by design (incremental) | - |

## Remaining (cannot be done or proven from this repository)
1. **Windows evidence (B6):** the new CI job has never run; branch protection is not visible here; clean second-PC restore, customer acceptance and the scope/support agreement are manual.
2. **Live hub:** deploy the Worker, register `trip-orders`, give the install token, prove ingest/ack and a real trial (`docs/HUB_SETUP.md`). Until then reports/crashes stay in the local outbox.
3. **Reading pass:** the Arabic of the guide, errors and installer needs a non-developer's pass (HELP-04); the factory lint is clean.
4. **I11 leftovers:** about 130 inline `style=` attributes remain in the other views, so CSP `style-src` still allows `'unsafe-inline'`; `heading-order` (moderate) findings; keyboard/screenshot inspection by a person.
5. **Decision for the owner:** the default changed from "every PC may connect" (2026-10-06) to "this PC only"; ticking one installer box restores it.
6. **Old backups** made before this version have no photo inventory and show as "cannot prove the photos" (still restorable).
7. N2.
