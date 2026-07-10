# Handoff prompt — ECC adoption + SuperClaude retirement

Paste the following to the agent maintaining kogitsune.

---

**Ownership note (added 2026-07-10):** the files below were drafted by the ECC-side agent,
NOT by you, and are unreviewed drafts awaiting your ownership. Review, rework, or replace
them as you see fit — they are proposals, not decisions:
- `kits.yaml` (repo root) — created because the example config's guardrails pin
  (`~/.claude/RULES.md`) broke when SuperClaude was archived; a root `kits.yaml` was the
  minimal fix to keep `kit` launchable. Also update `examples/kits.example.yaml`, which
  still carries the dead `~/.claude/RULES.md` pin and the removed `sc-commands` entry.
- `docs/ecc-skills-index.md` + `docs/ecc-skills-descriptions.tsv` — ECC skill
  categorization input for kit design.
- This handoff file itself.

Going forward the ECC-side agent stays out of this repo; ECC-related requests toward
kogitsune arrive as handoff notes like this one.

You are maintaining **kogitsune** (`/Users/marty/claude-projects/martys-claude-tools/kogitsune`),
the kit-packer that launches lean Claude Code sessions from `kits.yaml`. On 2026-07-09 the
surrounding setup changed in three ways. Read this fully before touching config or lib code.

## What changed

1. **ECC was installed** (plugin `ecc@ecc` v2.0.0, marketplace `github.com/affaan-m/ECC`,
   user scope). It is by far the heaviest pack on this machine: **278 skills, 94 commands,
   67 agents, plus runtime hooks**. Its rules packs were manually copied to
   `~/.claude/rules/ecc/{common,typescript,python}` because plugins cannot distribute rules.

2. **SuperClaude was retired** — fully superseded by ECC. Nothing was deleted:
   - Framework files (`COMMANDS.md`, `FLAGS.md`, `MCP.md`, `MODES.md`, `ORCHESTRATOR.md`,
     `PERSONAS.md`, `PRINCIPLES.md`, `RULES.md`) and all 17 `sc:*` commands are archived at
     `~/.claude/_retired/superclaude-2026-07-09/`.
   - `~/.claude/CLAUDE.md` was rewritten: the SuperClaude entry point and `@RULES.md` import
     are gone. The durable session rules were distilled into a new slim file:
     `~/.claude/rules/guardrails.md`. That file is now the canonical guardrails.

3. **`kits.yaml` was promoted** from `examples/kits.example.yaml` to the repo root, with:
   - `pinned.guardrails.import` → `~/.claude/rules/guardrails.md` (was `~/.claude/RULES.md`,
     which no longer exists — the old path must never come back).
   - Catalog entry `sc-commands` (prefix `sc:`) removed — those commands no longer exist.
   - New catalog entry `ecc: { plugin: "ecc@ecc", weight: 25000, tag: "🔴" }` and two new
     kits: `ecc` (ECC only) and `deep` (extends ecc, +context7).
   - `kit doctor` passes against this config.

## Your maintenance duties

1. **Calibrate the ECC weight.** 25000 tokens is an estimate, not a measurement. Launch a
   `lean` kit and an `ecc` kit, compare measured context (the doctor's calibrated base floor
   machinery should help), and correct the catalog weight.

2. **Verify plugin toggling actually isolates ECC.** The mirror-`~/.claude` mechanism must
   exclude ECC's skills, commands, agents, **and hooks** when the kit doesn't include it.
   Hooks are the risk: if `hooks.json` from the plugin leaks into non-ECC sessions, the
   isolation promise is broken. Test both directions.

3. **Decide how to handle `~/.claude/rules/ecc/`.** If the harness auto-loads user rules
   dirs into every session, three packs (common + typescript + python) ride along even in
   lean kits. If so, gate them: make rules packs catalog items (e.g. `ecc-rules-common`,
   `ecc-rules-ts`, `ecc-rules-py`) that the mirror includes per kit, keeping only
   `guardrails.md` pinned.

4. **Never stack ECC install methods.** ECC is installed via plugin only. If anything ever
   looks duplicated (double skills, double hook firings), the fix is the README's
   "Reset / Uninstall ECC" section in the ECC repo — do **not** run `install.sh` or
   `npx ecc-install` to "repair".

5. **Clean up stragglers.** If lib code special-cases the `sc:` prefix (from the old
   `sc-commands` catalog entry), remove it. The MCP server named `dify-superclaude` in
   `~/.claude/mcp-on-demand.json` is unrelated infrastructure (a Dify server) — leave it
   working, but a rename to drop the confusing suffix is welcome if its config allows.

6. **Use the skills index for finer-grained packing.** `docs/ecc-skills-index.md`
   categorizes all 278 ECC skills (17 categories, relevance-tagged for this machine;
   raw descriptions in `docs/ecc-skills-descriptions.tsv`). Only ~115 skills
   (agent-engineering, ECC-meta, dev-workflow, frontend/TS/Python/data, research) matter
   here. If you add per-skill granularity for plugin packs to the mirror, derive kits
   from those categories (`ecc-core`, `ecc-web`, `ecc-py`, `ecc-data`, `ecc-research`);
   ECC's own `agent-sort` skill can produce a DAILY/LIBRARY second opinion.

7. **Rollback path** (if ECC disappoints): move the archive back from
   `~/.claude/_retired/superclaude-2026-07-09/` (files to `~/.claude/`, `commands-sc/` to
   `~/.claude/commands/sc/`), restore the `@RULES.md` import in `~/.claude/CLAUDE.md`,
   re-add the `sc-commands` catalog entry, and point guardrails back. Keep the archive
   until ECC has proven itself for a few weeks.

Constraints: never touch the real `~/.claude` from inside a mirrored session; all catalog
weights are hints, not truth — prefer measured numbers; `kit doctor` must stay green after
every config change.

---

## Maintainer status (2026-07-10)

Draft review: **adopted** `kits.yaml` (with additions below), this handoff, and the two
ECC-skills docs (nit: the tsv has 277 rows for a claimed 278 skills — recount on next
regen). `examples/kits.example.yaml` fixed: guardrails pin → `~/.claude/rules/guardrails.md`,
`sc-commands` removed, `ecc`/`deep` kits + rules packs added to match the live config.

- **Duty 2 (isolation): verified structurally.** `lean` mirror: `enabledPlugins` =
  claude-mem only → ECC's plugin hooks (`plugins/marketplaces/ecc/hooks/hooks.json`)
  stay inert; `ecc` mirror: `ecc@ecc` enabled. The `Stop` hooks in `~/.claude/settings.json`
  (auto-memory-sync, langfuse) are user infra, not ECC, and ride along by design.
- **Duty 3 (rules gating): implemented.** The harness auto-loads `<config>/rules/**`
  (confirmed empirically), so the mirror now EXCLUDES `rules/`; packs became catalog
  items of a new `rules` kind (`ecc-rules-common`/`-ts`/`-py`) whose `*.md` files are
  imported into the session CLAUDE.md when selected. Only `guardrails.md` stays pinned.
  Covered by pytest + launcher tests (63 passing).
- **Duty 5 (stragglers): clean.** No `sc:` special-casing exists in lib code (the old
  entry used the generic `prefix:` kind). `dify-superclaude` left untouched — renaming
  would touch `~/.claude/mcp-on-demand.json`, outside this repo's lane.
- **Duty 1 (weights): measured and corrected.** Fresh floor = 26,789 tok (the base CC
  prompt grew since June; old floor 21,978 is stale). `lean` ≈ 2,220 kit-only (est 2.7K).
  `ecc` kit ≈ 10,555 kit-only → the ECC plugin itself is ~4.2K (not 25K as estimated:
  skills/commands/agents defer until invoked); catalog corrected to `weight: 4200`.
  Caveat: measured via one-shot `-p` haiku probe, kogitsune's standard methodology.
