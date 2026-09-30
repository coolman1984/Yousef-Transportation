---
name: trip-orders
description: Working memory for the Trip Orders project (vehicle trip orders, driver links on WhatsApp, odometer photos, Excel both ways, office brain + internet mailbox). Load it before any change in this repository; it tells you where to continue and how the owner wants the work done.
---

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
See `docs/EXECUTION_PLAN.md` Part F and add new ones there and here.
