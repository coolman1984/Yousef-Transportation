# Factory hub: crash reports, problem reports and online licence activation

Trip Orders talks to **one** address: the factory hub (the Cloudflare Worker of `Apps-Factory/templates/telemetry-relay`). Nothing is set up by default and **nothing leaves the PC** until you do both: the office agrees (Settings → Privacy & help) and an address (+ token for reports) is configured.

## What goes to the hub
| What | When | Needs |
|---|---|---|
| Problem report (`/ingest`) | the person wrote it and pressed send after the preview | the address and the install token |
| Usage counts, error fingerprints, backup/sync results (`/ingest`) | only after the **office and the person** agreed | the address and the install token |
| Licence request (`/licence/request`, `/licence/status`, `/licence/ack`) | the administrator pressed "Ask for a trial / licence" | the address only (no secret in the program) |

Never sent: passwords, typed text, names, phone numbers, trips, vehicles, drivers, amounts, screenshots. The list of allowed fields is the factory taxonomy `server/aftelemetry_events.json` (byte-identical to the factory copy).

## Configure (nothing is committed to the repository)
- **Address:** environment variable `FACTORY_HUB_URL` (for example in the service/installer), or `"hub_url"` in `config.json`, or Settings → Privacy & help → Help service. It must be `https://`.
- **Install token** (given by the factory control centre for this installation): typed once in Settings → Privacy & help → Help service, or `TO_HUB_TOKEN`. It is kept only in `data/assist.db` on this PC, never shown again, never logged, never written to the backups.
- **Licence public keys:** one or more `kid:key` lines in `licence_keys.txt` next to `config.json` (or `TO_LICENCE_KEYS`, or `"licence_keys"` in `config.json`). With no key the program is "licence by contract" and nothing is enforced.

## Register the product (owner's PC / hub, once)
1. Hub: add `trip-orders` to `LICENCE_PRODUCTS` of the Worker (`wrangler.toml` vars) and redeploy.
2. Licence Studio (owner's trusted PC, never the Worker): register the product id `trip-orders`; the Studio signs device-bound codes, the Worker only carries them.
3. Put the Studio's **public** key in `licence_keys.txt` of the build or installation.
4. Control centre: register the installation (`install_id` is shown in Settings → Privacy & help) and give the install token.

## التفعيل البسيط (Simple activation)

Two paths use the **same** signed codes and rules; nothing new is invented.

| Path | What the administrator does |
|---|---|
| **Online (hub configured)** | Settings → **Licence** → enter the organisation name if needed → press **Activate**. The program sends a **trial** request to the hub (`/licence/request`), shows *waiting for company approval*, keeps the **device code** visible, and polls until the signed code arrives and activates automatically. |
| **Manual (offline, no hub, or hub failed)** | On the same screen: copy the **short device code**, send it to the company (WhatsApp, phone, …), paste the **activation code** from Licence Studio, press **Activate** (`/api/licence/activate`). |

**Owner one-time setup** (not done from this repository; do not deploy from a customer PC):

1. **Licence Studio** on the owner's trusted PC: register product id `trip-orders`; sign codes for the device code the customer sends.
2. **Factory hub** (`templates/telemetry-relay`): add `trip-orders` to `LICENCE_PRODUCTS` in `wrangler.toml` and redeploy when you are ready.
3. Put the Studio **public** key in `licence_keys.txt` (or the build's embedded keys) for installations that enforce codes.
4. Optional: set `hub_url` / `FACTORY_HUB_URL` so the office can request a trial without typing a long code.

Advanced options (monthly/permanent requests, field preview) stay under **Details** on the Licence tab.

## Proof still needed (not provable from the repository)
Deployed Worker + a real ingest/ack round trip, a real trial from a clean Windows PC, and the Studio's signature on a real device code. The code is tested against a local stand-in of the Worker's URLs (`tests/test_assist.py`).
