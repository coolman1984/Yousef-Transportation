<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Trip Orders — أوامر التشغيل

First paid pilot: one transport office records trips, drivers, vehicles, start/end times and kilometres, reviews corrections, and exports its monthly report. Arabic and English, light and dark. Backups and a tested restore procedure support recovery within the agreed deployment limits; no unconditional no-data-loss guarantee is offered. Driver phone links, photos and internet exchange are separately accepted later-release services, not part of the basic office-only offer.

- **No sign-in and training mode (owner, 17 October 2026):** the program opens without signing in and works as the built-in administrator; the real work starts empty. The big "Enter training mode" button opens a separate training copy (port + 10, data in `training/`) with sample trips, cars, drivers, people and places to practise on; its yellow bar has "Back to real work". There is no licence or activation. To ask for sign-in again set `"sign_in": true` in `config.json` (a new folder then asks for the first administrator).
- Start here: `docs/GUIDE_ADMIN.md`, `docs/GUIDE_DISPATCHER.md`, `docs/GUIDE_DRIVER.md`, `docs/GATEWAY_SETUP.md`.
- Pilot installation: obtain the exact reviewed candidate from the operator after the launch gates in `LAUNCH_SCOPE.md` pass. Historical Releases (including 1.0.2) predate recent fixes and must not be used as the current pilot installer. No general customer download is approved by this documentation change.
- For developers/agents: `CLAUDE.md`, `docs/EXECUTION_PLAN.md`, `TASKS.md`, `DEVELOPMENT_HISTORY.md`.
- Run from source: `python server/app.py` (Python 3.11, no packages required). Optional: `sqlcipher3` (`pip install sqlcipher3-binary`) only when `TRIPORDERS_ENCRYPT=1`; the app works without it while that flag is unset. Then open http://localhost:8090/. Tests: `cd tests && python -m unittest discover`; gateway: `cd gateway && node --test test/gateway.test.js`.

This repository is public: the owner's real workbook, forms, photos and secrets are never committed (`samples/private/` is git-ignored).
