# Development History and Lessons Learned

Newest first. Every change adds an entry: what changed, why, mistakes, lessons.

---

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
