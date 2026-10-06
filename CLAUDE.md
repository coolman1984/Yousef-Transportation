<!-- first-sale-contract: 2026-10-06 -->
> **Owner decision — 6 October 2026:** Read [the first-sale contract](LAUNCH_SCOPE.md) before using this document. The limited pilot core and its launch gates take priority; extra features belong to later releases or separately accepted add-ons. Existing implementation/history below is preserved and is not a claim of first-sale acceptance.

# Trip Orders – rules for every change

Owner: Mohamed. Users are dispatchers, GA staff, finance and drivers who are **not technical**.
Sibling of BAMS (`coolman1984/Mr.Ayman-HR`): same engine, same discipline. Start with `docs/EXECUTION_PLAN.md`
(the playbook), then `TASKS.md` (where to continue), `docs/PLAN.md`, `docs/DESIGN.md`, `docs/REFERENCE_STUDY.md`.
Project skill: `.claude/skills/trip-orders/SKILL.md`.

## Always

1. Update in the same pull request: `DEVELOPMENT_HISTORY.md` (newest first: what, why, mistakes, lessons),
   `IDEAS.md` (once it exists), guides, `TASKS.md` test map, `docs/RELEASE_NOTES.md` for user-visible changes.
2. Test before every push; regression test for every bug.
3. Independent review for bigger changes; fix every verified finding.
4. Simplicity: one clear action per screen, plain words. UI in **English and Arabic** (all strings via i18n keys,
   RTL by logical CSS properties). Excel exports keep the original English headers.
5. Replies to the owner: simple Egyptian Arabic, conclusion first, then steps, then what he can decide next.

## Never

- Never lose data: soft delete only, restore is a new change, never roll back history.
- Never copy database files between PCs. Never make the office PC reachable from the internet.
- Never store or log link tokens, passwords or keys in clear (store hashes; the gateway keys cards by token hash).
- Never let a link carry administrator rights.
- Never put a company name, logo or law reference in code – only in `config.json` (`brand.*`, `form.legal_text`).
- Never push to `main` or force-push.
- This repository is **public**: never commit the owner's workbook, form, photos, secrets or real names
  (use `samples/private/`, gitignored).
