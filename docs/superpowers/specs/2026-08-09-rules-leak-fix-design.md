# Design: close the ancestor rules leak

**Date:** 2026-08-09
**Status:** approved, not yet implemented
**Background:** [`docs/FINDINGS-2026-08-09-payload-attribution.md`](../../FINDINGS-2026-08-09-payload-attribution.md) §2

## Problem

kogitsune gates rules packs by excluding `rules/` from the session mirror and writing a
minimal session `CLAUDE.md`. Both work. The gating leaks anyway: the harness also walks up
from the working directory, and anything it finds there loads with real paths the mirror
never sees.

Measured 2026-08-09 (same mirror, same manifest, only cwd differs):

| cwd | claudeMd block |
|---|---|
| `/tmp` | 2,401 B — as designed |
| anywhere under `$HOME` | 21,472 B |

Because `$HOME/.claude` *is* the real config dir, every project under `$HOME` re-imports
the very rules the mirror gated out. The ~4.8K decomposes as:

| source | tokens |
|---|---:|
| `~/.claude/rules/ecc/common/*.md` (10 files) | ~4,093 |
| `~/.claude/rules/guardrails.md` | ~380 |
| `~/.claude/CLAUDE.md` + `~/CLAUDE.md` | ~339 |

**Goal:** `ecc-rules-common` becomes a genuine toggle — absent from `lean`, present only
when a kit selects it. Accepted consequence: plain `claude` sessions stop auto-loading the
ECC packs.

## Load-bearing facts (verified, not assumed)

1. Three ancestor artifacts load **independently** — removing `<ancestor>/CLAUDE.md` does
   not stop `<ancestor>/.claude/CLAUDE.md` or `<ancestor>/.claude/rules/**`. (Sandbox probe.)
2. A sibling directory **not** named `.claude` is not scanned. Verified with a positive
   control in the same run: `.claude/rules/y.md` leaked, `.claude-rules/ecc/common/x.md`
   did not. **The whole design rests on this.**
3. Only part of a rules tree loads — 11 of 22 files here (`ecc/common/*` + `guardrails.md`);
   `ecc/typescript` and `ecc/python` did not. Mechanism for that subset is not established,
   so the fix must not depend on it.
4. Blast radius is small: `KOGITSUNE_RULES_DIR` already exists as a seam
   (`build-config.py:43`); the only hard references are one pinned `guardrails` import in
   `kits.yaml` and in `examples/kits.example.yaml`, plus `@rules/guardrails.md` (line 3) and
   a prose mention (line 8) in `~/.claude/CLAUDE.md`. No other consumers.

## Design

### 1. What moves

```
~/.claude/rules/ecc/           →  ~/.claude-rules/ecc/
~/.claude/rules/guardrails.md  →  stays
```

`~/.claude/rules/` then holds only `guardrails.md`, so the ancestor auto-load still fires —
but now loads exactly the thing that is wanted in every session anyway. `@rules/guardrails.md`
in the global CLAUDE.md is untouched and keeps resolving, so **plain `claude` sessions keep
their guardrails by construction**, with no edit to that file.

Rejected: moving the whole tree. It saves a further ~380 but requires rewriting
`@rules/guardrails.md` to an absolute path; getting that wrong silently drops guardrails from
every non-kit session — a worse failure than the leak being fixed.

### 2. `rules_root:` config key

`rules_root()` reads only `KOGITSUNE_RULES_DIR` today. A shell env var makes `kits.yaml`
non-portable: a teammate cloning it gets silently wrong paths and no error. Add a top-level
key, precedence **`config > env > ~/.claude/rules`**:

```yaml
rules_root: "~/.claude-rules"
```

Implementation: thread the resolved root into `resolve_item()` as a parameter rather than
having it reach for the environment, consistent with the resolver's existing purity. The
`ecc-rules-*` catalog entries do **not** change — they are already relative (`rules: "ecc/common"`).
The pinned `guardrails` entry does not change either — it is an absolute `import:` path.

### 3. Migration: detect, don't automate

`kit doctor` gains a check for `ecc/` still at the old location, printing the exact `mv` and
the `rules_root:` line to add. The move itself stays manual.

Rationale: it is one `mv` of files outside the repo. Automating it responsibly means backup,
idempotence and rollback for a one-line operation the user can verify themselves. Detection
plus an exact instruction is the honest split, and `leak-scan` already provides the surface.

### 4. Documentation

- `~/.claude/CLAUDE.md` line 8 prose ("Rules packs live in `~/.claude/rules/ecc/`") — user-owned,
  flagged in the migration output, not edited by us.
- `kits.yaml` + `examples/kits.example.yaml`: comments describing the gating, plus the new
  `rules_root:` key in the example.
- README and the findings doc: corrected to describe a *partial* fix (see Residual).

## Residual — this fix is partial, and says so

**~719 tokens still reach every session** and are out of scope:

- `guardrails.md` ~380 — wanted anyway, but now loaded **twice** in a kit session (once via
  the mirror's `@import`, once via ancestry). Dropping the pinned import to deduplicate would
  make guardrails depend on an implicit harness behaviour; not worth it.
- `~/.claude/CLAUDE.md` + `~/CLAUDE.md` ~339 — only removable by moving projects off `$HOME`.

`kit doctor` keeps reporting the residual. Neither doc may imply the leak is closed.

## Testing

Acceptance test is the measurement, not the code:

| check | expectation |
|---|---|
| `kit measure --proxy lean` | ~22,091 → **≈18.0K** tok (−4,093, ± probe noise of a few hundred). If this does not move, the fix did not work. |
| `lib/leak-scan.py` | its **rules** hit drops from ~7,371 to ~380; the reported **total** becomes ~719, not zero |
| pytest: resolver | `ecc-rules-common` resolves from a configured `rules_root`, via the existing `KOGITSUNE_RULES_DIR` fixture seam in `conftest.py` |
| pytest: precedence | config beats env beats default |
| pytest: doctor residual | non-zero — must not claim victory |
| pytest: migration check | fires when `ecc/` is at the old path, silent when it is not |
| `make check` | 102 pytest + 92 launcher + 26 decider still green |

## Out of scope

Wiring the remaining kits to the harness axis; re-baselining the weight bar; exposing harness
in the picker. Each is tracked separately in the findings doc.
