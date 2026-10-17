<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Build and release

**17 October 2026 (owner):** the program has no licence or activation any more and opens without sign-in (`"sign_in"` in `config.json`); sample data lives only in the training copy that the "Training mode" button starts (`server/training.py`). The licence hub, the signing keys, `tools/release_policy.py` and the `Customer release build` workflow were removed.

Every push and pull request runs all tests and the installed Windows journey (`tools/journey_exe.py`). The resulting installers are labelled **CI TEST / NOT FOR CUSTOMERS**, and the CI workflow **does not publish them as customer releases**.

For an actual customer build:
1. On a trusted Windows builder with Python, Nuitka, the required libraries, Inno Setup and Node installed, run `python tools/build_windows.py`.
2. Confirm installer/upgrade/disaster-recovery acceptance on the exact binary, hash and archive that binary. Only explicitly approved, verified builds may be sent to a customer. There is **no automated publishing**.

A compiled application is harder to inspect but **not impossible** to reverse-engineer on a client-controlled computer. The repo is public until its owner changes visibility, and prior public clones cannot be recalled. **Data at rest stays unencrypted unless `TRIPORDERS_ENCRYPT=1`.** That flag is off by default. `sqlcipher3` is an optional package and is not required for a normal build. The plan, recovery-key rules, and the two-backup migration gate are in `docs/OFFLINE_SECURITY_AND_RECOVERY.md`.

The installed program keeps data under `%ProgramData%\\TripOrders`; updates replace program files rather than intentionally deleting customer records.
