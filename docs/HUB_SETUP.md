# Factory hub: crash reports, problem reports and online licence activation

Trip Orders can use **two different Cloudflare Workers** (different URLs). They are not interchangeable.

| Worker | Role | Typical URL config |
|---|---|---|
| **Telemetry relay** (`Apps-Factory/templates/telemetry-relay`) | Problem reports (`/ingest`), usage counts, crash fingerprints | `hub_url` / `FACTORY_HUB_URL` (Settings → Privacy & help) |
| **Licence hub** (`licence-hub/` in this repository) | Online trial requests (`/licence/request`, `/licence/status`, `/licence/ack`) and the owner approval UI | `licence_hub_url` / `FACTORY_LICENCE_HUB_URL` (or the same `hub_url` only when telemetry is disabled) |

Nothing is set up by default and **nothing leaves the PC** until the office agrees (Settings → Privacy & help) and an address (+ token for telemetry) is configured.

## What goes to the hub
| What | When | Needs |
|---|---|---|
| Problem report (`/ingest`) | the person wrote it and pressed send after the preview | telemetry relay address and the install token |
| Usage counts, error fingerprints, backup/sync results (`/ingest`) | only after the **office and the person** agreed | telemetry relay address and the install token |
| Licence request (`/licence/request`, `/licence/status`, `/licence/ack`) | the administrator pressed "Activate" for an online trial | **licence hub** address (`licence_hub_url` / `FACTORY_LICENCE_HUB_URL`, or `hub_url` when telemetry is off) |

Never sent: passwords, phone numbers, trips, vehicles, drivers, amounts, screenshots. A licence request may include the **organisation name** you type on the Licence tab (`shop`, up to 60 characters; if left blank the program sends the site name from settings). That name is not part of the signed activation code. Other typed text is not sent. Telemetry uses only the factory taxonomy `server/aftelemetry_events.json` (byte-identical to the factory copy).

## Configure (nothing is committed to the repository)
- **Telemetry relay address:** environment variable `FACTORY_HUB_URL` or `"hub_url"` in `config.json`, or Settings → Privacy & help → Help service. It must be `https://`.
- **Licence hub address:** environment variable `FACTORY_LICENCE_HUB_URL` or `"licence_hub_url"` in `config.json`. When omitted, the program falls back to `hub_url` for online trial activation only.
- **Mutually exclusive on one URL:** if `hub_url` points at the licence hub, problem reports and usage counts will not reach a telemetry relay (that Worker has no `/ingest`). Either disable telemetry for that installation or configure **two** addresses as above.
- **Install token** (given by the factory control centre for telemetry): typed once in Settings → Privacy & help → Help service, or `TO_HUB_TOKEN`. It is kept only in `data/assist.db` on this PC, never shown again, never logged, never written to the backups.
- **Licence public keys (contract / source installs):** one or more `kid:key` lines in `licence_keys.txt` next to `config.json` (or `TO_LICENCE_KEYS`, or `"licence_keys"` in `config.json`). With no key the program is "licence by contract" and nothing is enforced.
- **Commercial installers:** trusted public keys and which keys are **trial-only** are compiled into the program at build time (`TO_RELEASE_PUBLIC_KEYS` with `trial-hub:` and `studio:` kids). Customer `licence_keys.txt` cannot change that policy.

### Trial-only hub signing key (separate from Licence Studio)

The licence hub must **not** use the same private key as Licence Studio. Generate a dedicated Ed25519 pair for trials only:

```bash
# Example — run on the owner's PC; never commit the PEM or paste it in chat
openssl genpkey -algorithm ED25519 -out trial-hub.pem
openssl pkey -in trial-hub.pem -pubout -outform DER | tail -c 32 | base64 -w0
```

1. Deploy **licence hub** with `npx wrangler secret put LICENCE_SIGNING_KEY` ← PKCS#8 PEM of **trial-hub.pem** only.
2. Customer **commercial** builds embed `trial-hub:<public>` and `studio:<public>` via `TO_RELEASE_PUBLIC_KEYS` at build time (not via `licence_keys.txt`).
3. Keep the Licence Studio **paid** private key off Cloudflare. Monthly/permanent codes stay Studio-only; the office refuses codes from the `trial-hub` kid unless they are **trial** edition and at most **14 days**.

The program enforces that rule in `server/afcodes.py` / `server/licence.py`, so a leaked Worker secret cannot mint monthly or perpetual licences customers will accept.

## Register the product (owner's PC / hub, once)
1. **Licence hub** (`licence-hub/`): deploy the Worker with `LICENCE_PRODUCTS` including `trip-orders` (`wrangler.toml` vars). Set `LICENCE_SIGNING_KEY` as above. Owner login secrets (`SESSION_SECRET`, `OWNER_PASSWORD_HASH`) and optional Telegram vars.
2. **Telemetry relay** (factory template): register the installation (`install_id` is shown in Settings → Privacy & help) and give the install token for problem reports and usage counts.
3. Licence Studio (owner's trusted PC): register the product id `trip-orders` for monthly/permanent and manual paste codes (Studio key, different kid).
4. Put the **trial-hub** and Studio **public** keys in the build's `TO_RELEASE_PUBLIC_KEYS` list (commercial) or in `licence_keys.txt` (contract/source).

## التفعيل البسيط (Simple activation)

Two paths use the **same** signed codes and rules; nothing new is invented.

| Path | What the administrator does |
|---|---|
| **Online (hub configured)** | Settings → **Licence** → enter the organisation name if needed → press **Activate**. The program sends a **trial** request to the hub (`/licence/request`), shows *waiting for company approval*, keeps the **device code** visible, and polls until the signed code arrives and activates automatically. |
| **Manual (offline, no hub, or hub failed)** | On the same screen: copy the **short device code**, send it to the company (WhatsApp, phone, …), paste the **activation code** from Licence Studio, press **Activate** (`/api/licence/activate`). |

**Owner one-time setup** (not done from this repository; do not deploy from a customer PC):

1. **Licence hub** (`licence-hub/`): deploy the Worker, set `LICENCE_SIGNING_KEY` (trial-only private key) and owner login secrets; trials are signed here.
2. **Licence Studio** on the owner's trusted PC: monthly/permanent and manual codes for the device code the customer sends.
3. Embed `trial-hub:<public>` and `studio:<public>` in commercial builds, or use `licence_keys.txt` on contract installs.
4. Set `licence_hub_url` / `FACTORY_LICENCE_HUB_URL` to the licence hub URL. Set `hub_url` / `FACTORY_HUB_URL` to the telemetry relay when help telemetry should stay enabled.

Advanced options (monthly/permanent requests, field preview) stay under **Details** on the Licence tab.

## Proof still needed (not provable from the repository)
Deployed Worker + a real ingest/ack round trip, a real trial from a clean Windows PC, and the Studio's signature on a real device code. The code is tested against a local stand-in of the Worker's URLs (`tests/test_assist.py`).
