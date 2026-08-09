# Payload attribution: what a kit actually costs

**Date:** 2026-08-09 · **Tooling:** `kit measure --proxy`, `lib/weight-sweep.sh`
**Probe:** haiku, `-p` one-shot, marginal vs an empty selection. No API calls.

Prompted by [aihero.dev — *How to kill the bloat in Claude Code's system prompt*](https://www.aihero.dev/how-to-kill-the-bloat-in-claude-codes-system-prompt).
That article measures with a forwarding proxy and cuts with `settings.json`. We took the
measurement idea and skipped the forwarding: `lib/measure-proxy.py` answers the probe
itself, so a sweep is free, offline, and unbillable.

## 1. The floor dwarfs the catalog

A `lean` session measures **~41.0K tokens** before a single catalog item is picked.
`LEAN_BASELINE` in `lib/context-est.py` claims 2,785 — it models only the pinned set and
was never wrong about that, but the bar it feeds implies a lean session is ~2.8K.

```
lean, haiku probe          ~41.0K total
  builtin tools (32)       ~27.6K   ← never modelled anywhere
  messages                  ~9.4K
  system prompt             ~3.8K
  mcp:kitsune (9 tools)     ~1.8K   ← the only part the catalog priced
```

Biggest single tools: `Workflow` 5,466 · `Bash` 2,947 · `DesignSync` 2,331 ·
`Agent` 2,171 · `Monitor` 1,915.

**Contra the article's framing for our case:** those tools are *not* deferred in a kit
session. An interactive Opus session defers most schemas; the haiku `-p` probe loads 41
eagerly. So `permissions.deny` on unused built-ins pays here — roughly **9.7K** for
Workflow + DesignSync + Monitor alone. This is the single largest available cut, and it
is the one axis kogitsune does not currently control.

## 2. A rules-gating leak (the important one)

`lib/session-env.sh` deliberately excludes `rules/` from the mirror and writes a minimal
session `CLAUDE.md`. Both work. The gating still leaks, because the harness walks *up from
cwd* collecting `CLAUDE.md` files, and that path is outside the mirror's control.

Same mirror, same manifest, only cwd differs:

| cwd | claudeMd block |
|---|---|
| `/tmp` | **2,401 B** — mirror CLAUDE.md + guardrails, exactly as designed |
| `~/claude-projects/…/kogitsune` | **21,472 B** |

The extra ~19.1 KB (**~4.8K tokens**) is `/Users/marty/CLAUDE.md`, `~/.claude/CLAUDE.md`,
and all ten `~/.claude/rules/ecc/common/*.md` files — riding into *every* kit session,
`lean` included, for any project under `$HOME` when `$HOME/CLAUDE.md` exists.

Not fixable inside `kog_build_mirror`: the ancestor walk starts at cwd, not at
`CLAUDE_CONFIG_DIR`. Needs its own decision.

**Sandbox probe — three independent sources.** Removing the top `CLAUDE.md` fixes only
the smallest:

| ancestor artifact | after removing `<ancestor>/CLAUDE.md` |
|---|---|
| `<ancestor>/CLAUDE.md` | fixed |
| `<ancestor>/.claude/CLAUDE.md` | still loads |
| `<ancestor>/.claude/rules/**` | still loads |

So there is no partial remedy: while `$HOME/.claude` sits on the ancestor path, its
`CLAUDE.md` and `rules/` re-enter every session. Only *some* of a rules tree loads —
here 11 of 22 files (`ecc/common/*` + `guardrails.md`); `ecc/typescript` and `ecc/python`
did not. Mechanism for that subset is not established.

`kit doctor` now reports this (`lib/leak-scan.py`) as an **upper bound**, since it cannot
know which subset loads — `kit measure --proxy lean` gives the real figure.

This also explains why `ecc-rules-common` sweeps at ~140 instead of ~4,100 — its content
is already present at the floor, so only the `@import` lines are marginal. Its declared
4,100 (≈ the files' 16.4 KB) is right; the sweep number is the artifact.

## 3. Measured vs declared catalog weights

Guesses, several off by 3–17×. Applied to `kits.yaml`.

| item | kind | declared | measured | note |
|---|---|---:|---:|---|
| n8n-mcp | mcp | 12,000 | **693** | 17× overstated |
| supabase | mcp | 10,000 | **3,261** | 3× overstated |
| dify-superclaude | mcp | 3,000 | **124** | 24× overstated |
| chrome-devtools | mcp | 1,000 | **5,479** | 5.5× *under*stated |
| kitsune-forge | mcp | 2,000 | **4,214** | 2× understated |
| kitsune | mcp | 700 | **2,345** | 3× understated |
| ecc | skills | 4,200 | **6,438** | |
| ecc-rules-ts | skills | 1,700 | **1,829** | accurate |
| ecc-rules-py | skills | 1,200 | **1,379** | accurate |
| superpowers | skills | 3,000 | **831** | its SessionStart hook, not the skills |
| context7, notion | mcp | 1,000 / 4,000 | *unresolved* | not installed — left as guesses |

## 4. Why skill items measure near zero

`n8n` (7 skills) sweeps at 7 tokens. Curation is *not* broken — the mirror lists 33 skills
at floor and 40 with `n8n` selected, the 7 correctly among them. The skills block is
**budgeted**: as the list grows the harness drops descriptions, so +7 names (~160 B) minus
dropped descriptions (~134 B) nets +26 B.

Consequence: skill cost is sublinear and self-limiting, so the per-skill weights in the
catalog overstate what toggling one actually saves. It also means the probe under-measures
relative to an interactive session, which carries far more descriptions.

## 5. Fidelity limits — read before trusting a number

- **Probe ≠ session.** haiku `-p` differs from interactive Opus in tool set (41 vs 42
  tools, 29.4K vs 25.0K tool tokens) and in skill-description density. Use
  `--probe-model opus` to compare like with like; never mix models in one sweep.
- **Marginals only.** Every number is *this item against this floor*. Two items that both
  pull the same dependency will each claim it.
- **Bytes ÷ 4.** No tokenizer. Fine for ranking and sizing, not for billing.
- **Uninstalled ≠ free.** The sweep marks unresolved items rather than scoring them 0.

## 6. The harness axis — shipped, and measured

`kits.yaml` gained a `harness:` catalog of 11 tool groups. A kit opts in with
`harness: [group, ...]` — an **allowlist**: groups named are kept, the rest are denied via
`permissions.deny` in the mirror's `settings.json`, which strips their schemas from the
payload. Omitting the key denies nothing, so kits written before the axis are unaffected.

`lean` (`harness: [web]`), measured before and after:

| | before | after |
|---|---:|---:|
| tools in payload | 41 | **19** |
| builtin tools | ~27,551 tok | **~6,654 tok** |
| session total | ~42,618 tok | **~22,091 tok** |

**~20.5K saved — 48% of the whole session.** Bigger than the entire catalog combined.

Guards, both tested: `ESSENTIAL_TOOLS` (Bash/Read/Edit/Write/Skill/ToolSearch/
AskUserQuestion/TaskOutput/TaskStop) can never be denied whatever a group lists; and an
unknown group name warns rather than silently denying more.

Kits wired so far: `lean` and `db` → `[web]`; `build` → `[agents, tasks, web, review,
worktrees]`. Every other kit is untouched.

## Open, in priority order

1. ~~**Fix the cwd leak**~~ (§2) — **partially fixed.** Moving the ECC packs to a
   `rules_root:` outside `.claude` removes ~4,093 tok. **~719 tok still leak** and are not
   fixable this way: `guardrails.md` (~380, wanted anyway, but double-loaded in kit
   sessions) and the two `CLAUDE.md` files (~339, only removable by moving projects off
   `$HOME`). `kit doctor` keeps reporting the residual.
2. **Wire the remaining kits** to the harness axis (§6) — each is a ~20K decision, and
   only `lean`/`db`/`build` have been made deliberately.
3. ~~**Re-baseline the bar.**~~ **Done.** `context-est.py` now models a whole session:
   `BASE_FLOOR` 35,700 (measured with no items and no denials) + items − `harness_saved`,
   scaled from `MIN_SESSION` 13,500 to `BAR_FULL_AT` 50,000. Modelled vs measured: `lean`
   16.8K/16.4K, `ecc` 38.7K/39.6K — within ~2.5%. Re-measure `BASE_FLOOR` after a Claude
   Code upgrade; the built-in tool set is its largest term.
4. **Expose harness in the picker.** It is config-only today; the fzf picker has no
   third column for it.
