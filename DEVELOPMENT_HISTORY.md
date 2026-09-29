# Development History and Lessons Learned

Newest first. Every change adds an entry: what changed, why, mistakes, lessons.

---

## Phase 1a – engine fork (2026-09-29)

**What:** copied the BAMS engine (BAMS commit `5f5b3ce`, version 2.4.0), renamed everything to Trip Orders
(`TO-` hash domains and headers, `TO_HOME`, `trips.db`, `TripOrders.exe`, ports 8090/8453, new installer AppId),
replaced the break-area domain by the trip domain in `store.ENTITIES` (13 entities, `docs/EXECUTION_PLAN.md` P2.1),
new permission groups and 7 built-in profiles in `auth.py`, permission mapping and category scopes in `app.py`
(a person can be limited to trip categories; journal/audit column `scope_id`, user field `scopes`).

**Tests:** engine tests kept. In-process tests use a test-only break-area style domain (`tests/engine_domain.py`,
registered by `tests/cluster.py`, never shipped) so counters, `max`/`rank`/`follow` resolvers and restores stay
covered; the multi-PC tests were rewritten on trips (photos = `tripPhotos`, limited user = category scope).
Removed: the upgrade-from-version-1 tests (they rebuilt BAMS history from git).
Result: unit + convergence 32 OK, multi-PC 35 OK.

**Mistakes / lessons**
- A blind `sed s/bams_/to_/` shortened the backup file prefix from 5 to 3 characters and broke code that sliced
  file names by position (`name[4:]`, `n[5:20]`). Lesson: after a rename, grep for numeric slices of the renamed strings.
- `git rm --cached -r .` was run by mistake while cleaning up; it only changed the index (fixed by `git reset`).
  Lesson: never run index-wide commands as a side effect of a rename.
- Fields like `description` that tests used are not real trip fields; conflict resolution must use the real field
  name (`notes`).

## Phase 0b – playbook for every agent (2026-09-29)

**What:** `docs/EXECUTION_PLAN.md` (how to work, environment, every task with exact rules, data model, API,
gateway protocol, workbook layout, checks, pitfalls, owner answers), `TASKS.md` (tracker), project skill
`.claude/skills/trip-orders/SKILL.md`, `.gitignore` for `samples/private/`.

**Why:** the owner wants any later agent to continue without mistakes, the same way.

**Owner answer:** demo data = the real sheet. The repository is **public**, so the real workbook is loaded at first
start on the office PC and never committed; the repo gets a synthetic sample with the same shape.

**Lessons**
- Check repository visibility before committing anything derived from the owner's files.

## Phase 0 – study and plan (2026-09-29)

**What:** studied the BAMS reference repository, the paper trip order and the September workbook; wrote
`docs/REFERENCE_STUDY.md`, `docs/PLAN.md`, `docs/DESIGN.md`, `CLAUDE.md`. Removed the first idea note
`PROJECT_PLAN.md` (it proposed passenger QR confirmation, which the owner decided against for version 1).

**Why:** the owner's master prompt asks for Phase 0 first; the owner also added bilingual UI, light/dark themes,
motion, shortcuts, slides and full admin control.

**Mistakes / lessons**
- The master prompt's workbook numbers were close but not exact (drivers 42 vs 41, cars 46 vs 44, back-steps 13 vs
  12, destinations 87 vs 89/90) – the differences come from whitespace and case. Lesson: every count depends on
  normalisation; tests must state the normalisation they use.
- BAMS has no Excel reader, no i18n, no dark mode and no service worker – these are new work, not reuse.
