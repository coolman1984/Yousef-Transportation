# Factory hub: crash reports, problem reports and online licence activation

Trip Orders can use **two different Cloudflare Workers** (different URLs). They are not interchangeable.

| Worker | Role | Typical URL config |
|---|---|---|
| **Telemetry relay** (`Apps-Factory/templates/telemetry-relay`) | Problem reports (`/ingest`), usage counts, crash fingerprints | `hub_url` / `FACTORY_HUB_URL` (Settings → Privacy & help) |
| **Licence hub** (`licence-hub/` in this repository) | Online trial requests, licence calendar checks (`/licence/time`) and the owner approval UI | `licence_hub_url` / `FACTORY_LICENCE_HUB_URL`; default below |

The licence hub defaults to `https://trip-orders-licence-hub.mflma2040.workers.dev` only when no licence hub setting is saved or explicitly configured. Upgrades keep an existing setting. Telemetry has no default relay and requires office consent (Settings → Privacy & help), an address and a token. An enabled licence hub allows calendar checks; trial activation sends a request when the administrator presses **Activate**.

## What goes to the hub
| What | When | Needs |
|---|---|---|
| Problem report (`/ingest`) | the person wrote it and pressed send after the preview | telemetry relay address and the install token |
| Usage counts, error fingerprints, backup/sync results (`/ingest`) | only after the **office and the person** agreed | telemetry relay address and the install token |
| Licence request (`/licence/request`, `/licence/status`, `/licence/ack`) | the administrator pressed "Activate" for an online trial | **licence hub** address (explicit, saved, or default) |
| Calendar check (`GET /licence/time`) | every six hours after a valid response; failed checks retry after five minutes, doubling up to six hours; includes paid or expired licences; disabled in practice mode | licence hub address only; no activation code, device identifier or token is sent |

Never sent: passwords, phone numbers, trips, vehicles, drivers, amounts, screenshots. A licence request may include the **organisation name** you type on the Licence tab (`shop`, up to 60 characters; if left blank the program sends the site name from settings). That name is not part of the signed activation code. Other typed text is not sent. Telemetry uses only the factory taxonomy `server/aftelemetry_events.json` (byte-identical to the factory copy).

## Configure (nothing is committed to the repository)
- **Telemetry relay address:** environment variable `FACTORY_HUB_URL` or `"hub_url"` in `config.json`, or Settings → Privacy & help → Help service. It must be `https://`.
- **Licence hub address, highest priority first:** nonblank `FACTORY_LICENCE_HUB_URL` environment variable → an explicit `"licence_hub_url"` key in `config.json` → the `licence_hub_url` setting saved in `data/assist.db` → `https://trip-orders-licence-hub.mflma2040.workers.dev` when none is set. The default is resolved at use time, not written into `config.json` or the database. `hub_url` is only for telemetry and is never a licence fallback.
- **Override or disable:** set `FACTORY_LICENCE_HUB_URL` or `"licence_hub_url"` in `config.json` to another HTTPS address. To disable online activation and calendar checks, set `FACTORY_LICENCE_HUB_URL=off` (case-insensitive), or set `"licence_hub_url": ""` in `config.json` with no nonblank environment override. A saved database value of `""` or `off` also stays disabled when no higher-priority setting exists. A blank environment value means no override; removing the config key exposes the saved database setting or default. Restart the app after changing the environment or config file.
- **Mutually exclusive on one URL:** if `hub_url` points at the licence hub, problem reports and usage counts will not reach a telemetry relay (that Worker has no `/ingest`). Either disable telemetry for that installation or configure **two** addresses as above.
- **Install token** (given by the factory control centre for telemetry): typed once in Settings → Privacy & help → Help service, or `TO_HUB_TOKEN`. It is kept only in `data/assist.db` on this PC, never shown again, never logged, never written to the backups.
- **Licence public keys (contract / source installs):** one or more `kid:key` lines in `licence_keys.txt` next to `config.json` (or `TO_LICENCE_KEYS`, or `"licence_keys"` in `config.json`). With no key the program is "licence by contract" and nothing is enforced.
- **Commercial installers:** trusted public keys and which keys are **trial-only** are compiled into the program at build time (`TO_RELEASE_PUBLIC_KEYS` with `trial-hub:` and `studio:` kids). Customer `licence_keys.txt` cannot change that policy.

The calendar response uses `LICENCE_CALENDAR_TZ` (default `Africa/Cairo`), is **signed** (`calendar_day`, `kid` `trial-hub` or `paid`, `sig`), and only moves the effective licence day forward when the office trusts the signature. A sealed hub day in assist storage cannot be lowered by changing `licence_hub_url` to another hub. A paid licence past its last day plus its signed grace period becomes expired: editing stops, while reading, exporting and backing up remain available under existing permissions. Network failures leave the calendar unchanged. Redeploy the updated hub and rebuild the customer app to enable this protection.

Activation processing and calendar checking have separate failure boundaries. HTTP errors, truncated responses, non-object JSON and invalid dates leave the last good date intact and schedule a retry. The trial status watch still runs when the public calendar check fails. Retry timers only schedule requests; they do not measure usage or determine expiry.

### Public calendar route protection

`GET /licence/time` uses the existing fixed-window limiter pattern: **120 requests per IP per 600 seconds**, keyed by Cloudflare's `CF-Connecting-IP`. Its dedicated in-memory buckets avoid D1 reads/writes and need no session or signing secrets. Rejected requests return HTTP 429 with `Retry-After` until the next window; responses remain uncached. At most 5,000 IP buckets are held per window; when full, new IPs receive 429 until the next window. Normal office retries and offices sharing one IP have room within the limit.

This is best-effort protection per Worker isolate. A new isolate starts with empty buckets, so it is not a global quota guarantee and does not prevent Worker invocations. For a publicly advertised hub, the recommended deployment is a custom domain with a Cloudflare WAF rate-limiting rule before Worker execution: match GET and path `/licence/time`, count by IP, and block excess requests. Use the period supported by the account and a generous equivalent threshold for shared offices; keep the rule scoped to this route. Verify the deployed rule's allowed/blocked responses before relying on it for invocation-quota protection. See [Cloudflare rate-limiting rules](https://developers.cloudflare.com/waf/rate-limiting-rules/) and [Worker limits](https://developers.cloudflare.com/workers/platform/limits/). No edge settings or deployment are changed by this repository update.

Redeploying the Worker enables the built-in protection without new bindings. `cd licence-hub && npm test` exercises the real Worker handler: 120 allowed requests, throttling, separate IPs, window reset, bounded bucket storage, and no D1/secret access. The approval-race regression selects the actual loser rather than assuming an execution order.

### Trial-only hub signing key (separate from Licence Studio)

The licence hub must **not** use the same private key as Licence Studio. Generate a dedicated Ed25519 pair for trials only:

```bash
# Example — run on the owner's PC; never commit the PEM or paste it in chat
openssl genpkey -algorithm ED25519 -out trial-hub.pem
openssl pkey -in trial-hub.pem -pubout -outform DER | tail -c 32 | openssl base64 -A | tr '+/' '-_' | tr -d '='
```

1. Deploy **licence hub** with `npx wrangler secret put LICENCE_SIGNING_KEY` ← PKCS#8 PEM of **trial-hub.pem** only.
2. Customer **commercial** builds embed `trial-hub:<public>` and `studio:<public>` via `TO_RELEASE_PUBLIC_KEYS` at build time (not via `licence_keys.txt`).
3. Set `PAID_SIGNING_KEY` (kid `paid`) for hub-issued monthly/permanent codes, or keep paid signing in Licence Studio only. The office refuses codes from the `trial-hub` kid unless they are **trial** edition and at most **14 days**; `paid` is not trial-capped.

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
4. Fresh installs use the default licence hub above; set `licence_hub_url` / `FACTORY_LICENCE_HUB_URL` only to override or disable it. Set `hub_url` / `FACTORY_HUB_URL` to the telemetry relay when help telemetry should stay enabled.

Advanced options (monthly/permanent requests, field preview) stay under **Details** on the Licence tab.

## Proof still needed (not provable from the repository)
Deployed Worker + a real ingest/ack round trip, a real trial from a clean Windows PC, and the Studio's signature on a real device code. The code is tested against a local stand-in of the Worker's URLs (`tests/test_assist.py`).
