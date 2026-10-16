# Licence hub (Cloudflare Worker template)

قالب Worker لاستقبال طلبات التفعيل عبر الإنترنت ولوحة موافقة للمالك. **لا يُنشر من هذا المستودع تلقائيًا** — املأ `wrangler.toml` وضَع الأسرار على Cloudflare فقط.

Template Cloudflare Worker for online licence requests and an owner approval dashboard. **Nothing here deploys from CI by default** — configure `wrangler.toml` and set secrets in Cloudflare only.

This worker is **not** the factory telemetry relay (`/ingest`). Deploy it on its own URL. In the office app set **`licence_hub_url`** / `FACTORY_LICENCE_HUB_URL` to this Worker for online trials. Keep **`hub_url`** for the telemetry relay unless telemetry is disabled.

## What it does / ماذا يفعل

- نفس بروتوكول البرنامج: `POST /licence/request`, `GET /licence/status`, `POST /licence/ack` (حقول `server/licence.py`, اختبار `tests/test_assist.py`).
- Same protocol as the office app (`server/licence.py`, exercised by `tests/test_assist.py`).
- لوحة المالك على `/owner` (عربي، RTL): موافقة على الطلبات (يُعرض الكود بعد الموافقة)، تفعيل يدوي برقم الجهاز، قائمة العملاء.
- Owner dashboard at `/owner` (Arabic, RTL): pending requests (issued code shown on approve), offline device entry, customer list.
- توقيع التجربة (kid `trial-hub`, `LICENCE_SIGNING_KEY`) والاشتراك المدفوع/الدائم (kid `paid`, `PAID_SIGNING_KEY`) من لوحة المالك — تجربة ١٤ يومًا، مدفوع حتى تاريخ (شهر/٣/٦/سنة أو تاريخ مخصص)، أو دائم. بدون `PAID_SIGNING_KEY` تُعطَّل خيارات المدفوع برسالة عربية واضحة.
- Signs trials (`trial-hub`, `LICENCE_SIGNING_KEY`) and paid/permanent hub codes (`paid`, `PAID_SIGNING_KEY`) from the owner panel — 14-day trial, paid-until-date presets, or permanent. If `PAID_SIGNING_KEY` is missing, paid options are disabled with a clear Arabic message (no crash).
- One trial per PC online: locks both the normalized device code and the stable `machine` hash the app sends. Pending requests expire after a short TTL so a squatted poll token cannot block the real customer forever.
- Public `GET /licence/time` (alias `GET /licence/clock` for Store clients) returns the business calendar day with **v1** signature (`sig` over `AF-LICENCE-HUB-TIME/1|<day>|<kid>`) plus **v2** freshness (`server_time`, `sig2` over `AF-LICENCE-HUB-TIME/2|<day>|<server_time>|<kid>` or with `|<nonce>` when the client sends `?nonce=`). Response also includes legacy `serverTime` (same unix seconds as `server_time`). Hub calendar time is signed only with the **global** `LICENCE_SIGNING_KEY` (kid `trial-hub`) or, if that is unset, the global `PAID_SIGNING_KEY` (kid `paid`) — not per-product signing overrides. Every product build must trust those global public keys in `TO_RELEASE_PUBLIC_KEYS` / `licence_keys.txt`. Per-product `LICENCE_SIGNING_KEY_*` / `PAID_SIGNING_KEY_*` secrets apply to **activation codes** only. When no global signing key is configured, the hub returns `signed: false` — clients **must ignore** `calendar_day` for expiry.
- **Hub time replay:** clients call `af_license.hub_time.verify_hub_time` on every `/licence/time` response (v2 required; v1 only with `allow_v1=True`, deprecated — never advances `sealed_day`). **Persist locally:** `last_server_time` = highest accepted v2 `server_time`; `sealed_day` (`licence_hub_sealed_calendar_max`) = highest business day applied when `sealable` is true. After each success, update from the returned `HubTimeVerifyResult`. **v2:** when `last_server_time` is known, `server_time` must be **strictly greater** in both nonce and no-nonce modes (nonce binds the response, it does not bypass replay checks); re-verifying the same `sig2` after persisting fails. Day is clamped to `[sealed_day, sealed_day + max_jump_days]` when sealed; no upper bound on the `server_time` gap (far-future `server_time` requires the hub private key). **Nonce mode (recommended):** fresh random `?nonce=` per request; response nonce must match. **No-nonce mode:** same strict `server_time` rule. v1 without a seal always rejects; v1 with a seal returns `sealed_day` when signed day ≥ seal else rejects. Regression: `packages/af-license/tests/test_hub_time.py`.
- Multi-product hub: set `LICENCE_PRODUCTS` (comma-separated ids, e.g. `trip-orders,al-store`). Each request may carry `product`; when omitted, the hub uses `LICENCE_DEFAULT_PRODUCT` or the **first** id in `LICENCE_PRODUCTS`. **Yousef Transportation** sets `LICENCE_DEFAULT_PRODUCT=trip-orders` (or lists `trip-orders` first) so legacy clients without `product` keep working. Codes are always signed with that product’s tag — cross-product unlock is impossible. Optional per-product secrets: `LICENCE_SIGNING_KEY_AL_STORE`, `PAID_SIGNING_KEY_AL_STORE`, etc.
- Owner UI labels: optional `LICENCE_PRODUCT_LABELS` JSON (`{"product-id":"Arabic label"}`) exposed on `GET /owner/api/products` with `labels` and `default_product`; the panel falls back to the raw product id when no label is set.
- Route prefixes: `/licence/*`, `/api/licence/*`, and `/licence-hub/licence/*` are equivalent.
- A dedicated, bounded in-memory limiter uses the existing 120-per-600-second IP pattern without D1 or secrets; excess requests return 429 and `Retry-After`. Limits are per Worker isolate (add a Cloudflare WAF or rate rule in front of the Worker for stronger protection).

**بديل التوقيع:** Licence Studio على جهاز المالك يبقى الطريقة الأكثر أمانًا للتوقيع؛ هذا القالب يوازن بين الراحة (موافقة من الهاتف) ومخاطر سر التوقيع على Cloudflare (انظر أدناه).

**Alternative signer:** Licence Studio on the owner PC remains the strongest option; this template trades convenience for signing-key exposure on Cloudflare (see tradeoff).

## Signing key tradeoff / مخاطر مفتاح التوقيع

| Convenience | Risk |
|---|---|
| `LICENCE_SIGNING_KEY` في Worker secret → موافقة من أي مكان | إذا اُخترق حساب Cloudflare يمكن إصدار أكواد |
| Mitigations: **kid منفصل** (`trial-hub`) — البرنامج يقبل من هذا المفتاح تجربة ≤14 يوم فقط؛ إزالة المفتاح العام من `licence_keys` في الإصدار التالي؛ كلمة مرور قوية + 2FA على Cloudflare؛ أو الإبقاء على التوقيع في Licence Studio فقط |

Never put the Licence Studio **paid** private key in `LICENCE_SIGNING_KEY`. Generate a dedicated trial key pair; customers trust only `trial-hub:<public>` for hub-signed trials.

## Setup (documented only) / الإعداد (توثيق فقط)

```bash
cd licence-hub
npx wrangler d1 create trip-orders-licence
# Put database_id in wrangler.toml (this repo: trip-orders-licence-hub / trip-orders-licence)
npx wrangler d1 execute trip-orders-licence --file=schema.sql
# Legacy DBs only (see migrations/README.md) — run migrations BEFORE deploy.
# Local SQLite: node scripts/apply-migrations.mjs [--default-product <id>] ./local.sqlite
# Remote D1 (substitute __DEFAULT_PRODUCT__ in 0002/0003 SQL if not using the script):
#   node scripts/apply-migrations.mjs --default-product my-product /path/to/export.sqlite
#   npx wrangler d1 execute my-licence --remote --file=migrations/0001_licence_tier_expiry.sql
#   (after substituting __DEFAULT_PRODUCT__ in 0002 and 0003, or use apply-migrations on a copy and upload)

# Trial-only Ed25519 key (example — run locally, do not commit trial-hub.pem):
openssl genpkey -algorithm ED25519 -out trial-hub.pem

# Hash the owner password (example — run locally, do not commit output):
# python3 -c "import hashlib,secrets; s=secrets.token_hex(16); print('pbkdf2-sha256:100000:'+s+':'+hashlib.pbkdf2_hmac('sha256', b'YOUR_PASSWORD', bytes.fromhex(s), 100000).hex())"

npx wrangler secret put LICENCE_SIGNING_KEY   # PKCS#8 PEM of trial-hub.pem ONLY
npx wrangler secret put PAID_SIGNING_KEY      # PKCS#8 PEM Ed25519, kid "paid" (hub monthly/permanent)
npx wrangler secret put SESSION_SECRET
npx wrangler secret put OWNER_PASSWORD_HASH
# Optional:
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID

npx wrangler deploy
```

للنسخ **التجارية**: ادمج المفتاح العام في `TO_RELEASE_PUBLIC_KEYS` عند البناء (`trial-hub:<public>` و `studio:<public>`) — لا يُقرأ `licence_keys.txt` في المثبّت المباع. لنسخ **المصدر/العقد** فقط: ضع `trial-hub:<public>` في `licence_keys.txt`. مفتاح Licence Studio يبقى kid مختلفًا للاشتراكات المدفوعة.

For **commercial** installers embed trusted keys at build time via `TO_RELEASE_PUBLIC_KEYS` (`trial-hub:<public>`, `paid:<public>`, and `studio:<public>`) — sold builds ignore `licence_keys.txt`. For **source/contract** installs only, put `trial-hub:<public>` and `paid:<public>` in `licence_keys.txt`. Licence Studio remains an alternative signer for paid editions.

This worker is **not** the factory telemetry relay (`/ingest`); deploy it on its own URL and point the office app’s `licence_hub_url` / `FACTORY_LICENCE_HUB_URL` here.

## API contract (office / Store)

| Route | Method | Purpose |
|-------|--------|---------|
| `/licence/request` | POST | Start activation. Fields: `product` (optional, default from `LICENCE_DEFAULT_PRODUCT` or first `LICENCE_PRODUCTS` entry), `kind` (`trial` \| `monthly` \| `permanent`), `device`, `machine`, `nonce`, `shop`, `ref`, `version`. Returns `id`, `poll_token`, `status`. |
| `/licence/status` | GET | Poll with `?id=` and `Authorization: Bearer <poll_token>`. Returns `status`, optional `code` when `issued`, signed calendar fields, `reason` when refused. |
| `/licence/ack` | POST | Client got the code; body `{ id }` + Bearer poll token. Clears stored code (`delivered`). |
| `/licence/time` or `/licence/clock` | GET | Business calendar (`calendar_day`, v1 `sig`, v2 `server_time`/`sig2`, `serverTime`, optional `?nonce=`). `signed: false` when no global key. No auth. |

Poll every few seconds while `pending`; stop on `issued`, `refused`, or `expired`.

### Adding a product

1. Add the id to `LICENCE_PRODUCTS` (e.g. `trip-orders,al-store,my-app`).
2. Embed the product’s public key tag in sold builds (`TO_RELEASE_PUBLIC_KEYS`) or `licence_keys.txt` for contract installs.
3. Optionally set `LICENCE_SIGNING_KEY_<PRODUCT>` / `PAID_SIGNING_KEY_<PRODUCT>` (uppercase, hyphens → underscores) to override the shared trial/paid keys for **codes** for that product only. Hub `/licence/time` still uses the global `LICENCE_SIGNING_KEY` / `PAID_SIGNING_KEY` pair.

## Trial grants ledger (`trial_grants`)

The `trial_grants` table is the authoritative, insert-only record of which device (`subject_kind = d`) or machine hash (`m`, always lowercased) has already received a trial window for a product. Application code uses `INSERT OR IGNORE` only; optional SQL triggers reject `UPDATE`/`DELETE`.

**Migration order (existing D1):** back up the database first, then apply pending migrations (`0001`–`0003` if still needed, then `0004_trial_grants.sql` **and** `0005_trial_grants_backfill_staging.sql`, or `node scripts/apply-migrations.mjs` on a SQLite export) **before** deploying a worker build that writes the ledger. Without `0005` the backfill progress/staging and `trial_issue_batch_sentinel` tables are missing and trial requests fail. Fresh installs: `schema.sql` already includes all of them. After deploy, call `POST /owner/api/backfill-trial-grants` (owner session; two steps per call) until it returns `complete: true`; that sets the `trial_grants_backfill_v1` marker. Until then trial signing answers `backfill_in_progress` (503, retryable). Calling `backfillTrialGrants` directly does **not** create the 0005 tables or set the marker.

**Resolver limits:** `resolveTrial` and `linkedSubjects` expand device↔machine links with a recursive SQL closure over `licence_requests`, capped at **256** nodes; above that they fail closed with `link_limit`. Each resolver keeps total D1 statements under **50** (closure seed chunks included). Each statement keeps bind count ≤ **90** (closure seeds are chunked; ledger/term lookups are chunked). `linkedSubjects` always returns `deviceCodes` as a plain array plus `link_limit`. Paid/permanent blocking follows customers plus `issued`/`delivered` requests only. Blank `licence_expiry` on a paid customer falls back to `last_day` like `NULL`.

**Legacy backfill (lenient):** `backfillTrialGrants` creates ledger rows only from (1) `licence_requests` still marked trial (`kind`/`licence_tier`) that were actually issued (`issued`/`delivered`, or `expired` except `pending_timeout`) with a valid `licence_expiry` window, (2) `customers` rows of trial kind/tier with `first_day`/`last_day` (not paid/permanent), and (3) `etw|` rows in `machine_trials`. **d:/h:/od: lock rows are not trial evidence** (paid issues write locks too). Windows are never invented from `created_at` or lock timestamps. **Accepted edge case:** a device that went trial→paid in the hub (request row overwritten) may receive one more online trial after paid expires; there is no separate historical trial row to backfill.

**Backfill I/O:** three reads (`etw|` locks, requests, customers) plus one batch insert; unnormalizable devices are skipped.

**Offline trial with blank machine:** a hub request with `machine = ''` backfills only a device (`d`) ledger row, not a machine (`m`) row. Another device code on the same physical PC can still resolve as `eligible` until PR B ties grants to the owner-confirmed machine hash for unseen devices. Device-only `trialGrantStatements` still propagate missing machine rows when callers pass linked hashes on a later grant.

**Grant batches (`trialGrantStatements`):** async; expands the same device↔machine closure as `resolveTrial` (50-query budget, `link_limit` when exceeded). Returns propagate `INSERT OR IGNORE` statements (closure subjects chunked, ≤ **90** binds each) plus a final **window guard** (`TRIAL_GRANT_WINDOW_GUARD_LAST`). The authoritative window is the earliest row (min `first_day`, tie min `last_day`) among **all** closure subjects; propagate inserts that window for every linked subject still missing a row (existing later rows on other subjects stay untouched). The guard fails the batch only when that authoritative window exists and differs from the requested window — callers re-run `resolveTrial`, sign that window, and retry. PR B runs the full returned array in **one** batch: propagate statements, guard, then the licence issue write.

## Tests / الاختبارات

```bash
node --check licence-hub/src/worker.js
cd licence-hub && npm test
cd tests && python3 -m unittest test_licence_hub_signer.py
```

No runtime npm dependencies — only Node built-ins and `node --test`.
