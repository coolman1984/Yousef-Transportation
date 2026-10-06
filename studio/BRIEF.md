<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Film 1 – "أمر تشغيل واحد، من الطلب للتقرير" (One trip order, from request to report)

> Status: Phase 0 done, Phase 1 (the stage) done and dry-run end to end in ~50 s with every proof passing. **Waiting for the owner's OK before shooting (Phase 2).**
> The five input fields of the studio prompt were left empty, so these defaults are used (change any of them and the storyboard follows):

| Input | Default used |
|---|---|
| Product and process | Trip Orders: request → General-Affairs approval → driver link → odometer photos on the phone (start / end) → signed paper photo → office sees a green, proven trip → month report and Excel in the old layout |
| Viewer + pain | The management of a company that runs cars. Pain: *every trip lives on paper and is typed into Excel at month end, and nobody can prove the kilometres.* |
| The one action (end card) | **جرّبه على أسبوع واحد من مشاويرك** – try it on one week of your own trips |
| Language / length / brand | Arabic, right-to-left · about 120 s · navy `#13294B` + amber `#F2A900` (the program's own tokens) |
| Forbidden | invented results (savings, time saved, customers), real company or person names, real data. The sample company is invented and the film says so on the first frame and on the end card. |

## 1. The process, screen by screen (and the read that proves each step)

| # | Who / where | Screen | What happens | Proof read back (API) |
|---|---|---|---|---|
| 1 | Dispatcher, office PC | Trip orders → **New trip** dialog | category, car, driver, requester, destination → Save | `GET /api/state` → `trips[id]`: `no`, `status = draft` |
| 2 | General Affairs, office PC | Trip panel → **Approve** | GA approval recorded with name and time | `trips[id].gaApproved = yes`, `gaBy` |
| 3 | Dispatcher | Trip panel → **Copy link** (WhatsApp in real life) | a driver link is made; only its hash is stored | `trips[id].status = sent`, `linkHash` set; gateway `GET /api/card/<token>` = 200 |
| 4 | Driver, phone | Link opens the driver page: **Your trip** | the trip card (number, car, destination, passenger) | card fields = office fields |
| 5 | Driver, phone | **Start**: odometer photo + reading | event + photo saved on the phone, sent (✓ → ✓✓) | office pull → `status = started`, `startKm`, `startAt`; `tripPhotos` kind `start_odo` |
| 6 | Office | **Today board** | the trip card moves to "On the road" | same as 5 |
| 7 | Driver, phone | **End**: odometer photo + reading + route | | `status = finished`, `endKm`, `endAt`, `routeText`, locked |
| 8 | Driver, phone | **Paper**: photo of the signed paper | | `tripPhotos` kind `paper` |
| 9 | Office | Trip panel | green trust, km, hours, three photos | `GET /api/insights[id]` → `trust = green`, `km`, `hours` |
| 10 | Management | **Reports** (month) | the month's totals, per vehicle / department | `GET /api/reports?ym=` → totals |
| 11 | Finance | **Excel → Export, same as today** | the month in the exact old three-sheet layout, formulas included | the exported file read back: the trip's row in "All Car" with `End KM − Strat KM` formula |

## 2. What is provably true, what is staged, what is never claimed

**Provably true** (each figure on screen is read back from the program before the take ends; the render refuses to start if a figure in the cut differs):
- the trip number, car, driver and destination (`/api/state`)
- approval by, status after each step (`/api/state`)
- start and end readings, km = end − start, the times (`/api/state`, `/api/insights`)
- three photos arrived with their kinds (`/api/state.tripPhotos`)
- trust colour green and no reasons (`/api/insights`)
- month totals: trips, km (`/api/reports`)
- the exported workbook's sheet names and the trip's row (read back from the downloaded file)

**Staged, and the film says so:**
- *Studio clock:* the day and hour are fixed by the studio (Tuesday 6 Oct 2026, 09:30, Cairo). The office program, the mailbox and both browsers share it.
- *The office checks the mailbox when the studio asks* (in real use it checks by itself every minute). The two-hour drive is skipped by moving the studio clock forward; a caption says "بعد ساعتين (الوقت مضغوط في الفيلم)".
- *The odometer pictures* are drawn test images fed to the phone's camera, not a real dashboard (caption on the first photo).
- *WhatsApp* is not filmed: the dispatcher copies the link; a caption says it is sent on WhatsApp.
- *The company, people, cars and the September history* are invented sample data, loaded through the program's own Excel import before the film starts.
- *The internet mailbox* runs locally on the studio PC (same code as on Cloudflare).

**Never claimed:** money saved, time saved, error rates, customers, "used by".

## 3. Persistent actor

One trip order follows the whole film: **requested by منى سامي (المشتريات), car ن ج ع 4821, driver كريم فؤاد, المصنع ← المطار ← المصنع**.
Its card stays on screen in a corner; its chips fill in as each step is *proven*:
`طلب` → `موافقة` → `لينك` → `بداية <قراءة>` → `نهاية <قراءة>` → `الورقة` → `أخضر · 118 كم` → `في تقرير الشهر`.
The readings come from the sample history (the car's last recorded end reading: it stood at the office since then, so there is no gap), and are read back before the cut is written – never typed into the cut by hand.

## 4. Storyboard (≈ 120 s)

| Time | The viewer sees | Business job of the beat | Carries into the next beat |
|---|---|---|---|
| 0:00–0:06 | **Frame 0 is finished:** title "أمر تشغيل واحد — من الطلب للتقرير", subtitle "شركة وبيانات تجريبية · ساعة الاستوديو"; the program window already on the dark stage | Promise: one order, the whole way, real screens | the empty actor card slides into its corner |
| 0:06–0:22 | Trip orders list → New trip → fields filled by the visible cursor → Save. **Stamp:** the new trip number | The request is typed once, never again | chip `طلب ✓` + number |
| 0:22–0:31 | Trip panel opens → Approve → badge "موافق" with name and time | Approval is recorded, not a signature hunt | chip `موافقة ✓` |
| 0:31–0:41 | Copy link dialog → caption "بيتبعت للسائق على واتساب" (the token part of the link is blurred) | One link per trip, for that trip only | chip `لينك ✓`; the window leaves as the phone enters |
| 0:41–1:02 | **Phone frame** (driver page, Arabic): trip card → Start → camera shows the drawn odometer → capture → reading → Start → ✓ then ✓✓. Caption on the photo: "صورة عداد تجريبية". **Stamp:** `<start reading> · 09:30` | Proof at the source: photo + reading + time from the car | chip `بداية <start>` |
| 1:02–1:10 | Office **Today board**: the trip card moves to "في الطريق" (live elapsed time) | The office knows without calling | — |
| 1:10–1:28 | Caption "بعد ساعتين (الوقت مضغوط)" → phone: End → photo → end reading → route → End → Paper photo → Done ✓✓ | The end and the signed paper, proven | chips `نهاية <end>`, `الورقة ✓` |
| 1:28–1:42 | Office trip panel: green trust, km **118**, 2 h 05, three photos. **Stamp:** `118 كم · أخضر` (placed beside, not over, the details) | A trip that needs no checking | chip `أخضر · 118 كم` |
| 1:42–1:55 | Reports page for October: totals fill in; then Excel → Export → "زي اللي عندك دلوقتي" → file saved; **badge:** "نفس الشيت ونفس المعادلات" with the row read back | Month end is a click, in the layout finance already uses | chip `في تقرير الشهر ✓` |
| 1:55–2:02 | End card: **"جرّبه على أسبوع واحد من مشاويرك"** + "الفيلم بشركة وبيانات تجريبية" (one fade to end) | The one action | — |

### Self-check of the storyboard
- Chronology = the real process order (table §1), nothing out of order; the off-camera pull from the mailbox happens between phone beats and is shown by the board moving.
- Numbers: end − start = 118 km ✔ (dry run: 49,731 → 49,849); 09:30 → 11:35 = 2 h 05 ✔ (dry run read-back: 2.09 h). Only read-back values go into the cut.
- Compositions vary: office window (wide) · dialog close-up hold · phone frame centred · board (moving columns) · panel with stamp at the side · report counters · end card.
- No beat claims a saving; every stamp is a read-back figure.
