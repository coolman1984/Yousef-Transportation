# Trip Orders — أوامر التشغيل

Vehicle trip orders without the paper chase: the dispatcher prepares a trip, the driver gets a WhatsApp link and fills it on the phone (odometer photos, times, signed-paper photo), the office sees it live, and Excel/Word work in and out in your existing layout. Arabic and English, light and dark. Nothing is ever lost.

- Start here: `docs/GUIDE_ADMIN.md`, `docs/GUIDE_DISPATCHER.md`, `docs/GUIDE_DRIVER.md`, `docs/GATEWAY_SETUP.md`.
- Install: download `TripOrders-Setup-<version>.exe` from **Releases**.
- For developers/agents: `CLAUDE.md`, `docs/EXECUTION_PLAN.md`, `TASKS.md`, `DEVELOPMENT_HISTORY.md`.
- Run from source: `python server/app.py` (Python 3.11, no packages). Tests: `cd tests && python -m unittest discover`; gateway: `cd gateway && node --test test/gateway.test.js`.

This repository is public: the owner's real workbook, forms, photos and secrets are never committed (`samples/private/` is git-ignored).
