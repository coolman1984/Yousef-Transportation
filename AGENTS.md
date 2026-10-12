<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Agent instructions

Read LAUNCH_SCOPE.md first, then CLAUDE.md and the execution plan. Prioritize launch gates over the old unchecked backlog.

## Cursor Cloud specific instructions

`python` on the Cloud Agent image is Python 3.11 (the version CI uses). Ubuntu's `python3` stays 3.12; do not use it for this program or its tests. The office server is the standard library only. Screen tests also need `playwright`, `xlwt`, and `cryptography`, and they launch Chromium from `/opt/pw-browsers/chromium` unless `TO_CHROMIUM` is set.

- Gateway (no npm install; Node 22.13+ for `node:sqlite`): `cd gateway && node --test --no-warnings test/gateway.test.js`
- Office tests, from `tests/`: the modules named in `.github/workflows/build.yml` (not `unittest discover`, which would also import helpers).
- On boot the office server listens on port 8090. Its data is `$HOME/trip-orders-home` (`TO_HOME`), with `open_browser` off, so the checkout stays clean. `python server/app.py` without `TO_HOME` uses the repo `config.json` and the same port; stop the boot server before starting that copy.
