<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Build and release (commercial safeguards)

Every push and pull request runs all tests, including the offline licensing and installed Windows journey. Automated Windows builds now contain **ephemeral CI test verification keys**. The resulting installers are labelled **CI TEST / NOT FOR CUSTOMERS**, and the CI workflow **does not publish these installers as customer releases**.

For an actual customer build:
1. Keep the vendor's Ed25519 PRIVATE signing key exclusively on the vendor's secure Licence Studio machine, never in GitHub, Cloudflare, the source, the customer installer or the CI workflow.
2. Supply one or more REAL **public verification keys** as the environment variable `TO_RELEASE_PUBLIC_KEYS` (comma-separated 43-character unpadded base64url encodings of the 32-byte Ed25519 keys); unset `TO_BUILD_CHANNEL` or use `commercial`.
3. On a trusted Windows builder with Python, Nuitka, the required libraries, Inno Setup and Node installed, run `python tools/build_windows.py`. This fails immediately if the public keys are missing, malformed, duplicate or all-zero. Its temporary `_release_policy.py` is removed after compilation; the customer app pins only the public keys.
4. Issue the signed offline trial, monthly or permanent licence separately for the customer PC's shown device code. Verify the licence accepts valid codes, rejects forged/other-device codes, works offline and preserves read/export/backup when expired.
5. Confirm installer/upgrade/disaster-recovery acceptance on the exact binary, sign/hash and archive that binary securely. Only explicitly approved, verified builds may be sent to a customer. There is currently **no automated commercial publishing**.

A compiled application is harder to inspect but **not impossible** to reverse-engineer on a client-controlled computer. The repo is public until its owner changes visibility, and prior public clones cannot be recalled. **Data at rest stays unencrypted unless `TRIPORDERS_ENCRYPT=1`.** That flag is off by default. `sqlcipher3` is an optional package and is not required for a normal build. The plan, recovery-key rules, and the two-backup migration gate are in `docs/OFFLINE_SECURITY_AND_RECOVERY.md`.

The installed program keeps data under `%ProgramData%\\TripOrders`; updates replace program files rather than intentionally deleting customer records.
