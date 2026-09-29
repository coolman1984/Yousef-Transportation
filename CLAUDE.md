# Trip Orders – rules for every change

Owner: Mohamed. Users are dispatchers, GA staff, finance and drivers who are **not technical**.
Sibling of BAMS (`coolman1984/Mr.Ayman-HR`): same engine, same discipline. Start with `docs/PLAN.md`,
`docs/DESIGN.md`, `docs/REFERENCE_STUDY.md`.

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
