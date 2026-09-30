# Build and release

Every push and pull request runs all tests (`.github/workflows/build.yml`): gateway (node), office (unit, convergence, several PCs, trips, Excel, Word, gateway client) and the screen tests in a real browser.
When a new `VERSION` in `server/version.py` reaches `main`, the workflow builds `TripOrders.exe` with Nuitka (no readable source), wraps it in `TripOrders-Setup-<version>.exe` (Inno Setup), checks that the built program starts and serves its pages, and publishes the release `v<version>` with the installer plus `trip-orders-gateway.js`, `schema.sql` and `GATEWAY_SETUP.md`.

To release: raise `VERSION`, update `docs/RELEASE_NOTES.md`, merge to `main`. A release that already exists is never overwritten.
Local build on Windows: `python tools/build_windows.py` (needs Nuitka, Inno Setup 6, Node).
The installed program keeps data in `%ProgramData%\TripOrders`; updating replaces only the program.
