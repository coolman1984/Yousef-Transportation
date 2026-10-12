# Commercial upgrade runbook (contract → signed licence)

Use this when an office that ran the **contract** build (full edit, no licence codes) moves to the **commercial** installer.

## Before you upgrade their live PC

1. **Copy their data folder** (`%ProgramData%\TripOrders` on Windows) to a safe test machine or VM. Never experiment on the only copy.
2. On the **old** build, open **Settings → Licence** and note every **device number** shown (one per office PC). Collect them for the vendor.
3. Confirm the vendor will sign codes with the **same public keys** that are baked into the new installer (`TO_RELEASE_PUBLIC_KEYS` at build time). If keys change, old trial codes will not work.
4. Run the **commercial** installer on the **data copy** first. Confirm trips open, edits work during the one-time **upgrade grace** (about 30 days), and that activating a test code unlocks edits after grace ends.
5. Plan licence codes for **each PC** before grace expires.

## On the live PC

1. Install the **commercial** `TripOrders-Setup-*.exe` (not a CI-test build).
2. Tell staff they may see **upgrade grace** in licence status: full editing for a limited period while codes are prepared.
3. Paste device-bound codes on each PC as they arrive.

## Never do this

- Do **not** ship or install **CI-test** installers (`TripOrders-Setup-*-CI-TEST-NOT-FOR-CUSTOMERS.exe`). They use a separate AppId, install folder (`TripOrders-CITest`), and ephemeral signing keys.
- Do **not** copy database files between unrelated PCs (normal replication rules still apply).
- Do **not** publish CI workflow artifacts as customer downloads.
