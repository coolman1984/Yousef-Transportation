<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Design System — Trip Orders (draft for Phase 1)

Owner's wishes (2026-09-29), all accepted: English **and** Arabic; light **and** dark; the light theme must not look
like a flat white page (depth, shadows, motion); animations; professional extras; use all our data so nothing looks
empty; the administrator controls everything; toolbars, slides, side panels; every page linked with shortcuts;
comfortable, clear settings; beautiful consistent fonts; choice of theme, font and font size; a guide for everything.

The 15-screen concept board (Overview … Passenger confirmation) is the layout reference. Screen 15 (passenger
confirmation) is **out of version 1** (DECIDED: passengers do nothing digital) and becomes "Paper photo check".

## 1. Principles

1. **Calm and precise** — a transport control room, not a marketing site. Boldness in one place: the live board.
2. **One action per screen**, plain words, empty states that say the next step.
3. **Depth without noise** — light theme uses layered surfaces (canvas → card → raised → overlay) with soft,
   tinted shadows; no gradient washes, no identical-card walls, no all-caps eyebrows.
4. **Motion explains** — things slide from where they come from; nothing moves just to move; `prefers-reduced-motion`
   and a setting switch all motion off.
5. **Colour means something** — green / amber / red are reserved for trust colours; the brand accent is separate.

## 2. Tokens (CSS custom properties on `:root`, overridden per theme)

| Token | Light "Daylight" | Dark "Night Road" | Use |
|---|---|---|---|
| `--canvas` | `#EEF1F6` | `#0B1220` | page background (never pure white) |
| `--surface` | `#FFFFFF` | `#121A2B` | cards |
| `--surface-2` | `#F7F9FC` | `#172136` | table stripes, inputs |
| `--raised` | `#FFFFFF` + shadow-2 | `#1B2640` | drawers, popovers |
| `--ink` | `#0F1B33` | `#E6ECF5` | main text |
| `--ink-2` | `#51607A` | `#9AA8BF` | secondary text |
| `--line` | `#DCE2EC` | `#26324A` | borders |
| `--brand` | `#13294B` (deep navy) | `#8FB2FF` | structure, sidebar, headings |
| `--signal` | `#F2A900` (road amber) | `#FFC23D` | the single accent: primary buttons, focus ring, live dot |
| `--ok` / `--warn` / `--bad` | `#1F9D55` / `#D98A00` / `#D64545` | `#3DD68C` / `#FFB547` / `#FF6B6B` | **trust colours only** |
| `--info` | `#2F6FDE` | `#6EA8FF` | information, links |
| shadow-1 | `0 1px 2px rgb(15 27 51/.06), 0 2px 6px rgb(15 27 51/.06)` | `0 1px 0 rgb(255 255 255/.04) inset` | cards |
| shadow-2 | `0 8px 24px rgb(15 27 51/.12)` | `0 8px 24px rgb(0 0 0/.45)` | drawers, menus |
| radius | 6 / 10 / 16 px | same | inputs / cards / sheets |

Extra themes (admin can allow/hide): **Asphalt** (graphite + amber), **Highway** (navy + green signs), **High
contrast** (AA+ for outdoor/low-vision). All themes pass WCAG AA contrast; checked by a unit test on the token file.

## 3. Typography

- Bundled locally (office works offline): **IBM Plex Sans Arabic** + **IBM Plex Sans** (OFL) as default; options
  **Cairo**, **Tajawal**, **Noto Kufi Arabic** (all OFL), subset to Arabic + Latin + digits.
- Numbers: Western digits, `font-variant-numeric: tabular-nums` for km, times, money.
- Plates rendered like the physical plate: a two-part badge (letters | digits), letters spaced, RTL-safe.
- Scale (user setting **S / M / L / XL** = 13 / 14 / 15 / 17 px base) with a modular ratio 1.2; density setting
  **Comfortable / Compact**.

## 4. Language and direction

- UI strings in `js/i18n/en.js` and `js/i18n/ar.js`; a missing key falls back to English and is reported by a test.
- `<html dir>` switches with the language; layout uses logical properties (`margin-inline-start`, `inset-inline-end`)
  so RTL needs no second stylesheet. Icons with direction (arrows, chevrons) mirror.
- Per-user language; the driver page is Arabic by default with an English toggle.
- Excel headers stay in the original English (export fidelity).

## 5. Layout and navigation

- **Shell:** sidebar (collapsible to icons) · top bar · content · optional **side panel** (right in LTR, left in RTL).
- **Top toolbar per page:** title, context filters (date range, category, vehicle, driver), view switch
  (table / cards / timeline), and the page's one primary action.
- **Side panels (drawers):** open any trip, car, driver or person from anywhere without leaving the page; stackable
  (trip → its car → its driver), `Esc` closes one level. Every entity name in the app is a link to its panel.
- **Command palette** `Ctrl K`: search trips (by no., plate, driver, person), jump to any page, run actions
  ("new trip", "export month", "switch theme").
- **Shortcuts** (shown in tooltips and in `?` sheet): `N` new trip · `G` then `O/T/D/L/V/R/S` go to page ·
  `/` search · `[` `]` previous/next day · `J/K` next/previous row · `Enter` open · `E` export · `T` toggle theme ·
  `L` toggle language. Admin can disable shortcuts per profile.
- **Breadcrumbs + back** keep context; filters live in the URL so every view is shareable and bookmarkable.

## 6. Motion

| Pattern | Spec |
|---|---|
| Page change | content fades + rises 8 px, 180 ms, `cubic-bezier(.2,.8,.2,1)` |
| Side panel | slides from the inline-end edge, 240 ms, backdrop fades |
| Numbers on the board | count up on first view (600 ms), then change with a short tick |
| Live board | "on the road" rows have a pulsing amber dot; elapsed time ticks every second |
| Save | button shows ✓ morph; toast slides from the bottom |
| Skeletons | shimmer placeholders while loading, never a blank white page |
| Trust colour change | 1 s soft glow on the row |
All motion off with reduced-motion or the setting.

## 7. Slides and guided help

- **Welcome slides** (first start, and from Help): 6 short slides — what the system does, the trip journey, the
  driver link, trust colours, Excel, where to get help. Both languages, skippable.
- **Presentation mode** for management: full-screen slides generated from live data (month in numbers, km by
  department, overtime, vendor difference, anomalies) with keyboard arrows; exportable to PDF via print.
- **Guided tours** per page (spotlight + 3–5 steps) and a **Help centre** with search, Q&A per topic (BAMS pattern),
  admin topics hidden from others. Every empty state links to its guide.
- Contextual **ⓘ hints** next to fields that are often wrong (km, times, category).

## 8. Settings (clear and comfortable)

Grouped cards with a live preview:
- **Appearance** (per user): theme, font family, font size, density, motion on/off, language.
- **Organisation** (admin): brand name, short name, logo, colours (with contrast check), paper form legal text,
  trip number format, working week.
- **Trips & rules** (admin): categories and their export sheet, OT threshold (12 h), time drift limit, open-trip
  limit per category, link lifetime, required photos, "unusual km" tolerance.
- **Money** (admin/finance): rates per km and per OT hour per category/vendor, currency.
- **Lists** (admin): vehicles, drivers, departments, people, places + aliases, routes.
- **Gateway** (admin): address, secret, poll interval, retention, status and last contact.
- **Users & permissions**, **Backups**, **Devices & sync**, **Recycle bin**, **Activity log** (BAMS pattern).
Admin can lock any appearance option for everybody (e.g. force the brand theme).

## 9. Using the data so nothing looks empty

First start offers **"Try with the September sample"**: the real workbook imported as demo data (232 trips, all
lists), with generated demo photos and times, clearly badged "Sample" and removable in one step (BAMS pattern).
Every page then shows real patterns: busiest routes, the 12 back-steps, the 56 vendor differences, drivers' month.

## 10. Driver page (phone)

Arabic RTL, big 48 px targets, high-contrast outdoor mode automatic in bright light (option), one action per screen,
progress dots 1–5, ✓/✓✓ status always visible, works offline. Budget < 150 KB compressed excluding the font subset.
