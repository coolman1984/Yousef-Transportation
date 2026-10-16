---
name: trip-orders
description: Working memory for the Trip Orders project (vehicle trip orders, driver links on WhatsApp, odometer photos, Excel both ways, office brain + internet mailbox). Load it before any change in this repository; it tells you where to continue and how the owner wants the work done.
---

<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](../../../LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Trip Orders – how to continue exactly as before

1. Read `CLAUDE.md`, then `docs/EXECUTION_PLAN.md` (the playbook: Part A = how to work, Part C = tasks),
   then `TASKS.md` → continue with the first task not ticked.
2. Decisions live in `docs/PLAN.md` (DECIDED items are closed; OPEN items have defaults – use them, say so).
3. Design rules live in `docs/DESIGN.md` (tokens, themes, fonts, RTL, motion, shortcuts, panels, slides).
4. The reference engine is BAMS (`coolman1984/Mr.Ayman-HR`), cloned read-only to
   `/home/user/coolman1984/mr.ayman-hr` (command in EXECUTION_PLAN B1). What we reuse: `docs/REFERENCE_STUDY.md`.

## Non-negotiables (short)
- Office side: Python standard library only. Driver page / gateway: plain JS, no runtime packages.
- Never lose data; soft delete; restore = new change; random ids; trip numbers carry the PC letter.
- Every UI string through i18n keys in `en.js` and `ar.js`; logical CSS properties only; tokens for colours.
- Tokens/secrets only as hashes; never in logs, Excel or errors.
- **This repository is public:** never commit the owner's workbook, form, photos, secrets or real names.
  Real files go to `samples/private/` (gitignored).
- Test before every push; regression test per bug; docs + `TASKS.md` + `DEVELOPMENT_HISTORY.md` in the same change.
- Reply to the owner in simple Egyptian Arabic: الخلاصة → اللي اتعمل → محتاج منك (with defaults) → الخطوة الجاية.
- Branch + push only; never `main`, never force-push; merge only when the owner says so.

## Pitfalls
- Activity search may pass `fields` or `columns` on `GET /api/audit`, but only `id, ts, user, node, label, entity, op, entity_id`. No list means the full row, which still includes `node_name`. A projected row has exactly the requested names and does not gain `node_name`. Never add `changes`, `before`, `after` or `ip` to that whitelist.
- Permissions: a new permission, page or ready-made profile needs its words in both dictionaries (`perm.*`, `permgroup.*`, `prof.*`);
  `tests/test_access_gate.py` runs the factory gate (`server/afaccess.py`; update from Apps-Factory with `python scripts/vendor_access.py ../Yousef-Transportation`).
  Standard: `Apps-Factory/docs/ACCESS_AND_ADMINISTRATION_STANDARD.md`.
See `docs/EXECUTION_PLAN.md` Part F and add new ones there and here.

## Guides, courses and "Solve a problem" (2026-10-11)
- `js/views/guides.js` (shared with Hessa): `GUIDES` (steps `S(kind, page, selector)`), `SITUATIONS` + `SIT_GUIDE`, `PATHS` (lessons = guide + fact).
- Facts: `server/tripsvc.py` `GUIDE_FACTS` / `guide_facts()`, `GET /api/guide-facts`. Setup facts are office-wide; daily facts count the person's own rows. A new fact goes into both and into `test_guide_gate.GuideFactsApiTest`.
- Words: `gd.<id>.*`, `sit.<id>.q/a`, `path.<id>.t/d` in both dictionaries. Each sentence has at most 18 Arabic / 22 English words. Each step has one action. No street or stiff office words. `tests/test_guide_gate.py` runs the factory release lint.
- Update the checker with the factory's `scripts/vendor_guide.py`, copying only the server files (`afguide.py`, `afguide_ar_lexicon.json`).
