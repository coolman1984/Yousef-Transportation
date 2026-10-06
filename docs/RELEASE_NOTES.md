<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Unreleased (next version)

## Fixed
- **Rates and contact numbers are only sent to people who may see them.** A user with only "Trip orders list" no longer receives the rates per km / per overtime hour or the drivers' and people's mobile numbers. The clean Excel report, the Word report and the Reports page leave out vendor reconciliation and cost allocation unless the user has the "Money" permission.
- **Approval, status, driver link and lock can only be changed with their own buttons**, never by a plain edit of the trip. A locked (closed) trip can only be corrected with "Change this trip" and a written reason, so the old value is always kept.
- **Dispatchers can cancel a trip again** (it needed a reviewer permission by mistake). Cancelling a closed trip needs the reviewer or "change a locked trip" permission.
- **Trip photos follow their trip:** a user sees a photo only with the photo permission and for categories assigned to them, and the browser no longer keeps a copy for the next person on a shared PC.
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
