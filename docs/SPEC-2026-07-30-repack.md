# SPEC: `repack` — mid-session harness reconfiguration

Status: design approved, not yet implemented
Date: 2026-07-30
Related: `skills/kit-selector`, `bin/kit` (`cmd_save`, `cmd_launch`), `decisions/`, `lib/context-est.py`

## Problem

kogitsune makes you choose the pack **before** the session starts. `kit-selector` picks from a
one-line task description — a guess made at the moment you know least about the task.

Two failure modes follow:

1. **Under-packed.** The task turns out to need a skill or MCP server you didn't pack. Today the
   only remedy is to notice, abandon, and relaunch by hand.
2. **Accretion.** A long session drifts. What you packed for the first hour is dead weight by the
   third, and there is no way to shed it.

`repack` closes both: at any point, the user asks the session to re-derive the optimal pack for
what is *actually* happening, and relaunch into it.

## Constraints (established empirically, 2026-07-30)

Measured in a live session, not assumed:

| Layer | Changes mid-session? | Note |
|---|---|---|
| Skills — **add** | Yes, ~1 turn lag | Symlink into live `$CLAUDE_CONFIG_DIR/skills/`; roster re-scans |
| Skills — **edit in place** | No | Body is cached from first scan; a rewritten `SKILL.md` serves stale content |
| MCP | Yes | `kitsune` gateway (`connect`/`shapeshift`/`release`) — already in use |
| Model, `CLAUDE.md`, hooks | No | Fixed at process start |

Skill hot-add works, but is **deliberately not used** in this design. A restart is required
anyway for model/CLAUDE.md/hooks, and taking the restart uniformly avoids both the one-turn lag
and the stale-body trap. Hot-add is retained as a possible future fast path for skills-only
additions (see Deferred).

## Design

### Trigger

User-invoked only. No hooks, no auto-trigger.

```
/repack                 # re-derive from what we are currently working on
/repack vue supabase    # steer it explicitly
```

### Flow

1. **Read the current pack** — from `KOGITSUNE_KIT` and friends (see Build item 2).
2. **Read the need** — task signals from the conversation, plus any hint argument.
3. **Derive the target pack** (below).
4. **Render the diff** — additions, sheds, model change, weight delta.
5. **Confirm with the user.** Nothing is written before this point.
6. On confirm — write handoff, `kit save`, print the relaunch command.

### Pack derivation

Reuses the existing selector spine. No new decision machinery.

1. Normalize conversation signals using the same canonical normalization the decider already
   applies (`decisions/SCHEMA.md`).
2. **Hot path** — match signals against the learned router (`decisions/router.v3.json`). On a
   confident match, propose that pack directly. No model call.
3. **Cold path** — match against `kits.yaml` (catalog + named kits) and
   `docs/ecc-skills-descriptions.tsv` (277 lines: name + one-liner, small enough to reason over
   in-context). Fall back to a haiku one-shot only if in-context matching is inconclusive, as
   `kit for` already does.
4. Diff target against current. Compute the weight delta via `lib/context-est.py`.

**Shedding is first-class.** The proposal always includes what to drop, not only what to add.
Add-only is what produces the heavy session the tool exists to prevent.

### Restart and handoff

No new launcher code — `kit save` and `kit <name> -- ARGS` already cover it:

```bash
kit save _repack --skills … --mcp … --model …
kit _repack -- "$(cat .kogitsune/handoff.md)"
```

Handoff is two layers:

- **claude-mem is pinned to every session**, so cross-session memory carries over for free.
- The skill writes `.kogitsune/handoff.md` — a short note on exactly where the work stands — and
  passes it as the opening prompt of the new session.

`_repack` is a reserved scratch kit name, overwritten on each repack. Users who want to keep a
derived pack run `kit save <realname>` themselves.

### Decision logging

Every confirmed repack appends to `decisions/decisions.jsonl` with `source: "repack"`, alongside
the existing `kit for` entries.

Repack decisions are **better training data than up-front picks**: they are labelled by real felt
need mid-task rather than by a guess from a one-line description. The `source` field lets the
distill step weight them accordingly.

## Interface

Confirmation prompt (stderr; nothing written until the user answers):

```
repack: task looks like Vue + Postgres

  + vue-patterns, vue-reviewer, supabase      +2.1k
  − n8n-*, html-email, interview-prep         −4.8k
  model: sonnet → opus

  net −2.7k   ·   14.2k → 11.5k

restart to apply? [y/N]
```

On yes, the skill prints the relaunch command rather than executing it. The user runs it. This
keeps the user in control of when the session dies and makes the step trivially abortable.
Auto-exec is deferred until the print flow is proven (see Deferred).

## Build

| # | Item | Kind |
|---|---|---|
| 1 | `skills/repack/SKILL.md` — the procedure | new |
| 2 | Export `KOGITSUNE_KIT` + packed skills/MCP in `launch_from_manifest` (`bin/kit`) | ~8 lines |
| 3 | `lib/pack-diff.py` — current manifest vs target → add/shed/weight delta | new, small |
| 4 | `source` field in the decision record + distill weighting | `decisions/SCHEMA.md` bump |
| 5 | Handoff writer | no code — plain `Write` inside the skill procedure |
| 6 | Publish `repack` to `~/.claude/skills/`, as `kit-selector` was | install step |

Reused unchanged: `kit save`, `kit <name> -- ARGS`, `kits.yaml`, `docs/ecc-skills-descriptions.tsv`,
`decisions/` + learned router, pinned claude-mem, `kitsune` for MCP, `lib/context-est.py`.

Item 2 is required because kogitsune currently exports no pack identity into the session.
`remember_kit` writes a global last-launched state file, which is not per-session and cannot be
trusted when several sessions run concurrently.

## Testing

TDD, matching the existing suite (`tests/`, `make lint`):

- `pack-diff` unit tests: add-only, shed-only, mixed, no-op, model change, weight arithmetic.
- Launcher test: `KOGITSUNE_KIT` and the packed lists are exported and match the manifest.
- Decision-log test: a repack entry round-trips with `source: "repack"` and is picked up by
  distill with the intended weight.
- End-to-end: launch `lean`, repack toward a target, assert the saved `_repack` kit resolves to
  the expected skills/MCP/model.

## Non-goals

- Hooks or auto-triggered repacking.
- Skill hot-add (deliberately unused — see Constraints).
- Voice, or any UI beyond the confirmation prompt.
- Editing skills in place (broken mid-session by the content cache).
- Grok parity — see `docs/NOTE-grok-build.md`.

## Deferred

- **Auto-exec the relaunch.** Add once the print flow is proven in daily use.
- **Skills-only fast path via hot-add.** When a repack requires *only* added skills — no shed, no
  model change, no MCP — it could symlink them into the live config dir and skip the restart
  entirely, at the cost of a one-turn lag. Worth revisiting once we see how often that case occurs
  in the decision log.
