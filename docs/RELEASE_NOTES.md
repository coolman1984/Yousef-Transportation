# Trip Orders 1.0.0

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
