# Trip Orders — licence hub (Cloudflare Worker template)

قالب Worker لاستقبال طلبات التفعيل عبر الإنترنت ولوحة موافقة للمالك. **لا يُنشر من هذا المستودع تلقائيًا** — املأ `wrangler.toml` وضَع الأسرار على Cloudflare فقط.

Template Cloudflare Worker for online licence requests and an owner approval dashboard. **Nothing here deploys from CI by default** — configure `wrangler.toml` and set secrets in Cloudflare only.

## What it does / ماذا يفعل

- نفس بروتوكول البرنامج: `POST /licence/request`, `GET /licence/status`, `POST /licence/ack` (حقول `server/licence.py`, اختبار `tests/test_assist.py`).
- Same protocol as the office app (`server/licence.py`, exercised by `tests/test_assist.py`).
- لوحة المالك على `/owner` (عربي، RTL): موافقة على الطلبات، تفعيل يدوي برقم الجهاز، قائمة العملاء.
- Owner dashboard at `/owner` (Arabic, RTL): pending requests, offline device entry, customer list.
- توقيع كود تجربة 14 يومًا (منتج `trip-orders`) بـ Ed25519 في Worker — متوافق مع `server/afcodes.py`.
- Signs 14-day trial codes (`trip-orders`) with Ed25519 in the Worker — byte-compatible with `server/afcodes.py`.

**بديل التوقيع:** Licence Studio على جهاز المالك يبقى الطريقة الأكثر أمانًا للتوقيع؛ هذا القالب يوازن بين الراحة (موافقة من الهاتف) ومخاطر سر التوقيع على Cloudflare (انظر أدناه).

**Alternative signer:** Licence Studio on the owner PC remains the strongest option; this template trades convenience for signing-key exposure on Cloudflare (see tradeoff).

## Signing key tradeoff / مخاطر مفتاح التوقيع

| Convenience | Risk |
|---|---|
| `LICENCE_SIGNING_KEY` في Worker secret → موافقة من أي مكان | إذا اُخترق حساب Cloudflare يمكن إصدار أكواد |
| Mitigations: kid منفصل للمفتاح، إزالة المفتاح العام من `licence_keys` في الإصدار التالي، كلمة مرور قوية + 2FA على Cloudflare، أو الإبقاء على التوقيع في Licence Studio فقط والاكتفاء بنقل الأكواد الجاهزة |

## Setup (documented only) / الإعداد (توثيق فقط)

```bash
cd licence-hub
npx wrangler d1 create trip-orders-licence
# Put database_id in wrangler.toml
npx wrangler d1 execute trip-orders-licence --file=schema.sql

# Hash the owner password (example — run locally, do not commit output):
# python3 -c "import hashlib,secrets; s=secrets.token_hex(16); print('pbkdf2-sha256:100000:'+s+':'+hashlib.pbkdf2_hmac('sha256', b'YOUR_PASSWORD', bytes.fromhex(s), 100000).hex())"

npx wrangler secret put LICENCE_SIGNING_KEY   # PKCS#8 PEM Ed25519 private key
npx wrangler secret put SESSION_SECRET
npx wrangler secret put OWNER_PASSWORD_HASH
# Optional:
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID

npx wrangler deploy
```

ضع المفتاح **العام** المقابل في `licence_keys.txt` للنسخة التي تفرض الأكواد. يمكن أن يكون `kid` مختلفًا عن Licence Studio؛ أزل المفتاح العام من الإصدار لإلغاء مفتاح Worker.

Put the matching **public** key in `licence_keys.txt` for builds that enforce codes. Use a separate `kid` from Licence Studio; remove the public key in a release to revoke a Worker key.

## Tests / الاختبارات

```bash
node --check licence-hub/src/worker.js
cd licence-hub && npm test
cd tests && python3 -m unittest test_licence_hub_signer.py
```

No runtime npm dependencies — only Node built-ins and `node --test`.
