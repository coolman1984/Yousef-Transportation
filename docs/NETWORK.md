# Network and Windows access / الشبكة وصلاحيات ويندوز

**Default (one-PC pilot):** Trip Orders listens on this PC only (`"host": "127.0.0.1"` in `config.json`). Nothing else can reach it, the Windows firewall gets no rule, and the replication port is closed.

**Folder access:** the installer limits `%ProgramData%\TripOrders` (databases and signing keys) to SYSTEM, the Windows administrators and **one operator account**: the person who runs the installer, or the account given as `TripOrders-Setup.exe /OPERATOR=DOMAIN\name`. Other Windows accounts on the same PC cannot read or change the data. Use one trusted Windows account on the office PC.

**More than one PC:** tick "Let the other PCs of the office connect" in the installer (or set `"host": "0.0.0.0"` in `config.json`). Then:
- the firewall rule exists for private/domain networks only, never public Wi-Fi;
- `allowed_networks` (for example `["192.168.1.0/24"]`) narrows who may connect. A list with no usable network allows this PC only - a typo never opens the program wider;
- the browser pages use plain `http`, so passwords cross the network unencrypted. Use it only on a trusted office network or behind a VPN/HTTPS front; behind HTTPS set `"secure_cookie": true`.

---

**الوضع الافتراضي (تجربة جهاز واحد):** البرنامج يعمل على هذا الجهاز فقط ولا يفتح أي منفذ للشبكة ولا يضيف قاعدة في جدار الحماية.

**حماية مجلد البيانات:** المثبّت يقصر الوصول لمجلد `%ProgramData%\TripOrders` (قواعد البيانات ومفاتيح التوقيع) على النظام والمسؤولين وحساب واحد مُشغِّل (من يشغّل المثبّت). باقي حسابات ويندوز على نفس الجهاز لا تقرأ ولا تعدّل البيانات.

**أكثر من جهاز:** فعّل خيار «السماح لأجهزة المكتب الأخرى» عند التثبيت. الجدار يفتح للشبكات الخاصة فقط، والصفحات تعمل بـ http غير مشفّر، فاستخدمها داخل شبكة المكتب الموثوقة أو عبر VPN فقط.
