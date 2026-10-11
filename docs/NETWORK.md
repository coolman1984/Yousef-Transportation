# Network and Windows access / الشبكة وصلاحيات ويندوز

**Default (the office LAN):** every PC of the office network can connect (`"host": "0.0.0.0"`). This is the 6 October 2026 owner decision, reconfirmed on 11 October 2026. The program still answers only this PC and private networks (`allowed_networks`, fail-closed), the installer adds the Windows firewall rule for private/domain networks only (never public Wi-Fi), and the data folder stays protected as below.

**This PC only:** tick "This PC only (other PCs of the office cannot connect)" in the installer, or set `"host": "127.0.0.1"` in `config.json`. Then the installer adds no firewall rule (and removes an older one), and nothing else can reach the program. An existing `config.json` is always respected: a PC set to `127.0.0.1` stays this-PC-only after an update.

**Folder access:** the installer limits `%ProgramData%\TripOrders` (databases and signing keys) to SYSTEM, the Windows administrators and **one operator account**: the person who runs the installer, or the account given as `TripOrders-Setup.exe /OPERATOR=DOMAIN\name`. Other Windows accounts on the same PC cannot read or change the data. Use one trusted Windows account on the office PC.

**More than one PC (the default):** other PCs open the address shown in Settings. Please note:
- the firewall rule exists for private/domain networks only, never public Wi-Fi;
- `allowed_networks` (for example `["192.168.1.0/24"]`) narrows who may connect. A list with no usable network allows this PC only - a typo never opens the program wider;
- the browser pages use plain `http`, so passwords cross the network unencrypted. Use it only on a trusted office network or behind a VPN/HTTPS front; behind HTTPS set `"secure_cookie": true`.

---

**الوضع الافتراضي (شبكة المكتب):** يمكن لأي جهاز في شبكة المكتب الدخول إلى البرنامج (قرار المالك بتاريخ 6 أكتوبر 2026، وتم تأكيده في 11 أكتوبر 2026). يضيف المثبّت قاعدة جدار الحماية للشبكات الخاصة فقط، ولا يقبل البرنامج إلا الشبكات الخاصة.

**هذا الجهاز فقط:** اختر «هذا الجهاز فقط (أجهزة المكتب الأخرى لا تستطيع الدخول)» عند التثبيت. عندها لا تُضاف قاعدة في جدار الحماية ولا يستطيع أي جهاز آخر الدخول. وإعداد موجود مسبقًا في `config.json` يُحترم دائمًا.

**حماية مجلد البيانات:** المثبّت يقصر الوصول لمجلد `%ProgramData%\TripOrders` (قواعد البيانات ومفاتيح التوقيع) على النظام والمسؤولين وحساب واحد مُشغِّل (من يشغّل المثبّت). باقي حسابات ويندوز على نفس الجهاز لا تقرأ ولا تعدّل البيانات.

**أكثر من جهاز (الوضع الافتراضي):** لا حاجة لخيار إضافي. الجدار يفتح للشبكات الخاصة فقط، والصفحات تعمل بـ http غير مشفّر، فاستخدمها داخل شبكة المكتب الموثوقة أو عبر VPN فقط.
