<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Unreleased (next version)

## Fixed
- **Rates and contact numbers are only sent to people who may see them.** A user with only "Trip orders list" no longer receives the rates per km / per overtime hour or the drivers' and people's mobile numbers. The clean Excel report, the Word report and the Reports page leave out vendor reconciliation and cost allocation unless the user has the "Money" permission.
- **Approval, status, driver link and lock can only be changed with their own buttons**, never by a plain edit of the trip. A locked (closed) trip can only be corrected with "Change this trip" and a written reason, so the old value is always kept.
- **Dispatchers can cancel a trip again** (it needed a reviewer permission by mistake). Cancelling a closed trip needs the reviewer or "change a locked trip" permission.
- **Trip photos follow their trip:** a user sees a photo only with the photo permission and for categories assigned to them, and the browser no longer keeps a copy for the next person on a shared PC.
- **A driver's "end" that reaches the office before the "start" no longer loses the start.** The trip now ends up the same whatever order the phone's messages arrive in: the start odometer and time fill in when the start message arrives, a closed or cancelled trip is never touched, and one damaged message can no longer block the others.
- **Replacing a driver link now really switches the old one off.** The old link stops opening on the phone and cannot send anything new as this trip, even if another office PC that was switched off still knew it. What the old phone had already sent is kept. (If the mailbox was set up with an earlier version, nothing needs to be done: it updates itself.)
- **Changing a rate no longer changes old reports.** Each trip is priced with the rate that was valid on its date. A new rate per km / per overtime hour counts from the day you save it; earlier trips (and last month's reports, Excel and Word) keep the old rate. The category screen says so. A month with two rates adds up trip by trip.
- **The program's web address is checked.** A web site on the internet can no longer make a browser on the office PC talk to the program under a different name (and, on a fresh PC, create the first administrator). The PC's own addresses - `localhost`, its IP address, its computer name - work as before; a company DNS name can be added with `"allowed_hosts"` in `config.json`.
- **The program only answers the office network.** Staff can open it from other PCs, other offices and a company VPN as before (any private address: 192.168.x.x, 10.x.x.x, 172.16-31.x.x), but a request from a public internet address is refused even if a router lets it through. `"allowed_networks"` in `config.json` narrows it to chosen networks, e.g. `["192.168.1.0/24", "10.20.0.0/16"]`.
- A browser connection that stays silent is closed after a minute, and more than 128 open connections at once get a polite "busy, try again" instead of slowing the PC down. A damaged request length now gets a clear error instead of a dropped connection.
- **Backups are safer and checked.** Two backups at the same moment (the automatic one and "Back up now") no longer break each other, and two in the same second no longer overwrite each other. Every backup is written under a temporary name, checked (file test, size, checksum) and only then becomes visible; a backup that fails leaves the last good one untouched and tells the administrator in Settings > Data. Photos are copied whole or not at all. A change to a user account alone (a new password) now also makes the next automatic backup due. A restore refuses a backup whose files were damaged. A full disk gives a plain message instead of a cut-off backup. Every backup has a small `.json` file next to it listing what it contains. New: `TripOrders.exe tool restore-set <backup folder>` puts the newest undamaged backup (data, accounts, photos) on a clean PC in one step and keeps whatever was there before aside; it is described in the administrator guide.
- **Times and durations follow one rule.** Every trip time is read and shown in Cairo time, whatever time zone the PC or the driver's phone is set to (a phone set to the wrong zone is corrected, and its original time stays in the trip's driver messages). Trip hours and overtime are real elapsed time, so the two nights a year when Egypt changes the clocks are counted right (one hour shorter in April, one hour longer in October). A trip whose start or end is in the hour the clocks change is marked yellow "check the time". A driver link now expires at the same moment on every PC, and no longer 3 hours late (older links made before this version are read as Cairo time).
- **Import problems are explained in your language, reliably.** Every reason a file cannot be imported (company-protected file, password, PDF or picture, empty or damaged file, Word given to the Excel door and the other way round, no trip columns, nothing to import, Office missing or too slow...) now has a fixed name inside the program, so the message on the screen is the Arabic or English text for that reason instead of a guess from the English words. A refused file changes no data and its contents are never repeated in the message.
- Rebuilding the data file from the history now works on Windows, and refuses safely (nothing changed) while the app is still running.

# Trip Orders 1.0.2

## New
- **Protected company files (DRM) can now be read through Microsoft Excel / Word.** On a Windows PC that has Office and the company's security program, a protected file is opened by Office itself (read-only, macros off, nothing saved) and only the cell values / text are taken. Nothing is decrypted or copied to disk, and no protection is bypassed: if Office cannot open the file, neither can Trip Orders.
- The same route reads anything Office can open (.xlsb, Excel/Word 95, .wps...). A switch on the import page forces Office for a file that looks wrong when read directly.
- The import page says whether Office was found on this PC.

## 1.0.1

## Fixed
- **Welcome slides** were blank after the first slide in Arabic (they slid the wrong way). Fixed, with a test for both languages.
- **Import now reads many more file types**, recognised by what is inside the file, not by its name:
  Excel `.xlsx .xlsm .xltx .xltm`, old Excel `.xls`, `.ods`, `.csv/.tsv/.txt` (any common separator, UTF-8, UTF-16 or Arabic Windows code page), web-page style `.xls`, Excel 2003 XML;
  Word `.docx .docm .dotx .dotm`, old Word `.doc`, `.odt`, `.rtf`, web-page style `.doc`.
- Files locked by a **company document-security (DRM) system** or a **password**, PDFs and pictures now get a plain message that says what to do (the program never tries to get around such protection).

## 1.0.0

أول إصدار كامل / First complete release.

## What you can do
- **Trip orders** for cars: create, print, send the driver a WhatsApp link, follow the trip live on the Today board.
- **Driver page** (no app to install): odometer photo, kilometres, times, route, photo of the signed paper. Works without network and sends by itself later.
- **Trust colours** (green / yellow / red) tell you which trips need a look. They never block a trip.
- **Excel both ways**: import your monthly workbook with a review step, export in the exact same three sheets and formulas, or as a clean report.
- **Word**: printable form (Arabic / English), read filled forms back, monthly report.
- **Reports**: per vehicle, driver, department; overtime; vendor reconciliation; cost per department; things to check; presentation mode.
- Arabic and English, light and dark themes, fonts and sizes you choose. Nothing is ever deleted: Recycle Bin, amendments with reasons, automatic backups.
- Several office PCs stay in sync by themselves.

## Setting up
1. Install `TripOrders-Setup-1.0.0.exe` on the office PC and create the administrator account.
2. To use driver links, follow `gateway\GATEWAY_SETUP.md` once (free Cloudflare account, about 20 minutes). Files: `trip-orders-gateway.js`, `schema.sql`.
3. Try it with the sample workbook from Excel -> Import.

## Known limits
- The Windows installer and the Cloudflare gateway were built and tested by automatic tests in a simulated environment; the first real run on your PC and your Cloudflare account is the final check (steps are in the setup guide).
