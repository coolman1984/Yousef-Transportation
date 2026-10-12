# Offline commercial security and recoverable storage

**Owner decision (12 October 2026):** Trip Orders must still work when the office is offline. A suspected attempt to modify, inspect or reverse-engineer the application MUST NEVER delete, corrupt, encrypt again, or ransom the customer's data. Treat detected tampering as a **recoverable security incident**, not as proof of malicious intent. This document is a design and a staged acceptance plan. An opt-in at-rest prototype exists and is **off by default**. It is experimental: recovery-key export, plaintext-to-encrypted migration, and second-PC restore are **not implemented**, so the flag must not be enabled for a real office until they are. It is not a claim that customer databases are encrypted, and cloud backup is not built.

## Current verified code (security branch)

- Customer Windows build fails unless `TO_RELEASE_PUBLIC_KEYS` contains a valid Ed25519 public verification key. The generated `_release_policy` is compiled into the executable; config/env/file overrides cannot replace it.
- The vendor's PRIVATE Ed25519 signing key is never included in the binary, source, installer or customer configuration. Codes are signed on the vendor's own trusted machine, including offline codes.
- Trial/monthly/perpetual signed licences already support binding to a machine and checking offline. When the code is missing, expired, for a different machine, or the clock has moved back too far, writes are blocked; reading, reporting, exporting and backing up remain available. No data gets deleted.
- CI generates an ephemeral signing key, exercises the customer-style build and labels it **CI TEST / NOT FOR CUSTOMERS**. CI must not publish this as a commercial release. The owner must provision a separate, genuine public verification key and test a controlled customer build.
- Existing protected storage: local SQLite databases and uploaded attachments, access-controlled Windows data folder, backups with SHA-256 checks. **Database files stay ordinary SQLite unless an operator sets `TRIPORDERS_ENCRYPT=1` for that process.** With the variable unset, storage and backups remain readable to a party who can access the raw files. There is no second, hidden switch.

## Desktop executable anti-reverse-engineering (implemented in build tools)
- The Python backend is compiled with Nuitka standalone; the build requests `no_docstrings` and supported automatic link-time optimization (LTO). The executable ships no readable Python source, bytecode, C source or common debug/map symbols: the build fails if those are found.
- Gateway deployment JavaScript and schema are placed in a separate `dist/operator-only-gateway` folder, **outside** the installer's source directory. Do not share that operator folder with customers.
- The browser user interface contains JavaScript that **must be delivered to the browser**, so it is still inspectable. No executable encryption, compression, obfuscation or packing can make a fully offline client impossible to reverse-engineer. Keep security-critical checks on the compiled server, with signed device licences and no private signing keys in any client artifact.
- Prefer ordinary code signing from the owner's trusted signing process for authenticity and antivirus reputation after commercial signing credentials are arranged. **Not implemented in this phase.** Avoid third-party executable packers, runtime self-decryptors and destructive anti-debug traps: they can produce antivirus warnings, slow startup and create misleading security guarantees.
- Commercial reverse-engineering deterrence additionally requires a **private GitHub repo**; existing public copies cannot be recalled. Any signed commercial installer must pass clean Windows builds and a user-focused smoke test.

## Opt-in at-rest encryption (off by default, experimental)

The flag is **experimental**. Recovery-key export, a plaintext-to-encrypted migration command, and second-PC restore are **not implemented**. Do not enable `TRIPORDERS_ENCRYPT=1` for a real office until those three exist. Do not advertise encrypted disks or a protected cloud restore.

### Feature flag

- The only switch is the environment variable `TRIPORDERS_ENCRYPT`. Encryption runs only when that value is exactly `1`.
- Unset, empty, `0`, or any other value: every database open is ordinary `sqlite3`, backup files stay ordinary SQLite, and no `atrest.key` file is written.
- There is no silent backdoor. No vendor key, no key in the source tree, the installer, or the executable, and no second variable that decrypts an office's data. `TRIPORDERS_ENCRYPT_BACKEND` cannot turn encryption off and cannot open a database that was sealed for a different key. After the flag is already on, the only supported engine is SQLCipher (`sqlcipher`, or leaving the variable unset). `TRIPORDERS_ENCRYPT_BACKEND=file` is refused. There is no whole-file fallback.
- An existing plaintext database is refused when the flag is on. The program does not quietly migrate it, quietly re-encrypt it, or quietly fall back to plaintext.

### Optional package

- `sqlcipher3` (install with `pip install sqlcipher3-binary`) is required only when the flag is on. It is **optional** while the flag is off.
- While the flag is off the program never imports `sqlcipher3`. A normal install works with the Python standard library if that package is missing.
- `cryptography` seals backup archives and the wrapped data key when the flag is on. It is already the library used for licence signing when it is installed.
- If the flag is on and `sqlcipher3` is missing, the program refuses to start. It does not open the databases and it does not write a plaintext work file. The same refusal happens when `TRIPORDERS_ENCRYPT_BACKEND=file`, even if `sqlcipher3` is installed. That setting is not a fallback and it is not encryption.

### Recovery-key handling

- Each data directory gets its own random 32-byte data key, created on first use when the flag is on and `sqlcipher3` is installed. The raw key is not written into source, logs, backups' file names, or the program.
- The raw key is stored only as `data/atrest.key`, wrapped (ChaCha20-Poly1305, file mode 0600). On a future Windows build the wrap should be Windows DPAPI for the current user. On Linux the wrap uses a per-user stand-in file, mode 0600, under `$XDG_CONFIG_HOME/triporders` (or `~/.config/triporders`), or the directory in `TRIPORDERS_DPAPI_DIR` when that variable is set for a test. The stand-in is not DPAPI. Any process of the same user can read it. Do not describe it as protection against a local administrator.
- The wrapped key travels inside a backup archive header. The header never contains the raw key. The wrap uses the local stand-in of the PC that created the archive. `unwrap_key_blob` decrypts only with that local stand-in, so a restore can open the archive on the **same** PC.
- **Recovery-key export is not implemented.** The program does not create, show, save, or accept a one-time recovery key. There is nothing for the office to write down that this program can later use. Do not tell an office that a paper recovery key will unlock the data. Losing the Windows user profile (or the Linux stand-in) means this program cannot unwrap `atrest.key`. Never invent a vendor master key to "get it back".
- Same-PC restarts use `atrest.key` plus the user wrap. A new PC does not become readable merely by copying the database files.

### Migration and second-PC restore — not implemented

**Plaintext-to-encrypted migration is not implemented.** There is no command that encrypts an existing data directory. `connect` refuses a plaintext database when the flag is on. Do not turn the flag on for an office that already has data.

**Second-PC restore is not implemented.** A backup archive header stores the data key wrapped to the PC that created the archive. Another PC unwraps that header with its own stand-in, fails, reports the backup as damaged, and the restore changes nothing. Copying an encrypted copy to a clean second PC and starting with `TRIPORDERS_ENCRYPT=1` does not restore the office.

Keep every verified plaintext backup. Never migrate in place. Never delete the only readable copy. Those rules match the code today.

#### Planned procedure (not implemented yet)

The steps below are the planned acceptance drill for a later version. This program cannot carry them out now. Do not enable the flag for a real office until recovery-key export, the migration command, and second-PC restore exist and this drill has passed.

1. Stop every writer (the office program on every PC, and any maintenance tool).
2. Make **two independent backups** on two different disks. Verify each one (checksums, open, row counts) **before** any file is encrypted. If either check fails, stop. The plaintext copies stay untouched.
3. **Planned, not implemented:** encrypt a **separate copy** of the data with a migration command. Compare row and entity counts, photo hashes, history, licensing, and permissions with the plaintext original. There is no such command in this version.
4. **Planned, not implemented:** copy that encrypted copy to a **second, clean PC** that has never held this office's files. Start the program there with `TRIPORDERS_ENCRYPT=1`, restore with the owner recovery procedure, restart, and confirm daily work (open trips, export, backup, restore). That second PC would be the acceptance test, not the office's only copy. Second-PC restore does not work in this version.
5. Only after that second PC succeeds, switch the office. Keep both verified plaintext backups until the office has taken a new encrypted backup and restored it once on purpose.
6. If any check fails, put the original plaintext data back and leave the flag unset. A failed test must not be the moment the only good copy disappears.

## Mandatory phased design for real encryption

1. **Inventory and threat model.** Enumerate `trips.db`, `auth.db`, `journal.db`, `assist.db`, other SQLite files, WAL/SHM/temp copies, photos and exports. Audit exact access from all source files and all Windows user accounts. Identify the legitimate office owner and consent / contract rights to restore their business data.
2. **Encryption at rest.** Evaluate a supported audited SQLite encryption engine (SQLCipher with 256-bit AES and page authentication) for **every** database connection, including migrations, tests, backup, restore and multi-PC replicas. For attachments and backup archives use authenticated encryption with independent random nonces, and authenticate metadata. Never fake encryption by compressing/obfuscating files.
3. **Offline keys and recovery.** Generate a random data-encryption key per installation. Protect the local key using Windows DPAPI / supported hardware protection, with an explicit recoverable wrapped copy encrypted for the owner-approved recovery workflow. Never store a decryption key or reusable passphrase in the executable or source repository. Document how a legitimate customer recovers on a new PC with owner consent. A device compromise with local running-app privileges can still expose decrypted data: never promise impossible resistance.
4. **Safe migration.** Stop all writers; make and VERIFY two independent readable backups; encrypt a separate copy; check full row/entity counts, hashes, photos, histories, licensing and permissions; open/restart/recover on a second clean Windows PC; only then atomically switch. Roll back to the original good data if the test fails. Never migrate in place or delete the sole readable copy.
5. **Detect but do not destroy.** On a failed authentication/integrity check: stop writes, capture a sanitized local incident record and checksums, show a clear recovery screen, and preserve original files. Ordinary power failures, corruption and unsupported version upgrades must not falsely mark an employee as a hacker. Never lock the customer out of their data as punishment for inspection.
6. **R2 off-site backup.** Back up encrypted, versioned snapshots when the connection returns, plus a second local/offline backup for the time without internet. Use Cloudflare R2 bucket-lock retention on the backup prefix and a write-only upload gateway; never store R2 delete/admin credentials on customer PCs. Separate customer namespaces, rate limits, quotas, signed manifests, scheduled restore drills and retention agreed in the contract. R2 retention rules are configurable by an authorized account operator: this is not infallible, irremovable storage.
7. **Offline reality.** If internet disappears before the latest backup uploads, the server does NOT have the unsent changes. Queue encrypted uploads without stopping office operations; show the exact timestamp of the last server-confirmed backup and offline outstanding count. Do not describe backup as complete until server receipt and restore verification.
8. **Privacy and consent.** Customer trips and personal records belong to the customer. Disclose where backups are stored, encryption/access policies, restore approvals, retention/deletion, and who can see data. Do not quietly collect company records merely to deter reverse engineering.

## Before a commercial handoff

- Make the **currently public GitHub repository private** (requires the owner's GitHub administrative action; this branch cannot change visibility). Assume any previously cloned source is already disclosed.
- Produce a genuinely customer-signed installer from the release process, not the ephemeral CI artifact.
- Verify offline licence activation and renewal, hardware change/recovery, upgrade from no-key installations, expired licence read/export/backup, negative-role tests and unauthorised access.
- Validate SQLCipher and offsite backup migration on an identical Windows installation with a real disaster-recovery drill. Until this gate passes, do not advertise encrypted on-disk databases or protected cloud restores.
- Perform an independent security review of application and network permissions and simulate an ordinary power cut and an unclean shutdown; neither scenario may erase data.

**Key distinction:** tamper-detection may help identify an integrity incident. It cannot reliably prove who inspected, copied, modified or reverse-engineered an executable on a fully controlled offline PC. A fully offline application necessarily has enough information to operate locally and can be patched by a sufficiently capable local administrator.
