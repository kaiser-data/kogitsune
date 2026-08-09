<div align="center">

```
       /\___/\        k o g i t s u n e
      ( o   o )       ┌─────────────────────────────┐
      (  =^=  )       │  小狐 · the little fox that  │
       )     (        │  packs light to save tokens │
      (       )       └─────────────────────────────┘
     ( (  )  ( )
    (__(__)_(__)__)        pick a kit · start lean · spend fewer tokens
```

# kogitsune 🦊

### Start every [Claude Code](https://code.claude.com) session lean — then pack in *exactly* the skills + MCP your task needs.

One keystroke. Memory always rides along. Everything else is a choice.

```bash
kit db      # 🦊 off you go: memory + guardrails + supabase + postgres — nothing else
kit         # …or open the picker, toggle what you want, watch the token cost live
```

</div>

---

## Why you'll love it

- ⚡ **Lighter sessions, more room to work.** Stop paying for every installed skill and MCP schema on a
  *"hello"*. Pack a focused kit and keep the context window for the actual task.
- 🎯 **A sharper model.** Fewer competing instructions in context means Claude stays on-task instead of
  wading through tools it'll never call. Less noise in → better answers out.
- 🦊 **Memory never leaves your side.** claude-mem and your guardrails are pinned to *every* session — the
  things you always want are never a toggle, never a tax.
- 🎛️ **One picker for skills *and* MCP.** Toggle items, watch the pack weight re-total live, pick your
  model, hit enter. There's no native Claude Code feature that does this.
- 💾 **Build a muscle-memory of kits.** `kit db` for the 90% path; tune-and-save your own in seconds.
  Commit a `kits.yaml` and your whole team launches the same way.
- ♻️ **Zero risk to your setup.** Your real `~/.claude` is never touched. Every session runs in a
  throwaway mirror that's wiped on exit — credentials and all.

```
   a normal "hello" session                    the same session, packed by the fox 🦊
   ┌───────────────────────────────┐           ┌───────────────────────────────┐
   │ base · ALL skills · ALL MCP ·  │           │ base · memory · guardrails ·   │
   │ full CLAUDE.md                 │           │ + only what you picked         │
   │ ████████████████████  heavy    │   ──▶     │ ██████░░░░░░░░░░░░░░  lean      │
   └───────────────────────────────┘           └───────────────────────────────┘
```

## Pack a kit, send the fox off

A **kit** is a reusable, named set of *skills + MCP servers*. Pick one — `lean`, `db`, `n8n`,
`frontend`, `research`, or your own — and the fox starts `claude` carrying **exactly that, and nothing
else**. Memory (claude-mem) and a small guardrails file are pinned and never toggle off.

```bash
kit            # interactive picker (fzf) — tune a pack from scratch
kit tune db    # open the picker pre-loaded with the DB kit, then add/drop items
kit db tune    # same thing, object-first (alias for `kit tune db`)
kit db         # send the fox off with the DB kit: +supabase +postgres-best-practices
kit lean       # memory + guardrails only — the leanest possible start
kit db -- --model opus "optimize this query"   # forward args straight to claude
```

### Tune it in the picker

A live two-pane `fzf` view. Every item shows a `✔`/`○` glyph for whether it's in the pack; **space/tab**
toggles the focused one and the preview **re-totals the weight instantly**. A 🦊 **kit row loads its whole
preset** — start from `db`, drop `supabase`, add `context7`, and launch the tuned set (or **ctrl-s** to
save it as a new kit).

```
 pack › db                                     ┌─ preview ──────────────────────┐
  🦊 db             ~12K  preset                 │ 🦊 pack your kit               │
  🦊 db-heavy       ~16K  preset                 │                                │
  🦊 lean           ~0K   preset                 │ pack weight: ~14.8K tokens     │
▶ ✔ 🔴 supabase     ~10K  (mcp)   ← in pack      │  ▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░        │
  ○ 🟠 notion       ~4K   (mcp)   ← toggle on    │  (lean = ~2.8K)                │
  ✔ 🟡 postgres-bp  ~2K   (skill)                │ model:  opus  (ctrl-o cycles)  │
  ○ 🟢 frontend     ~1K   (skill)                │                                │
                                                 │ mcp:    supabase               │
                                                 │ skills: postgres-bp            │
 space/tab · 🦊 loads preset · ctrl-o model ·     │ pinned: memory · guardrails ·  │
 ctrl-p hide presets · enter · ctrl-s save        │         graphify · repack      │
                                                 └────────────────────────────────┘
```

| key | does |
|---|---|
| **space** / **tab** | toggle the focused item in/out of the pack |
| **🦊 kit row** | load that kit's whole preset (toggle again to drop it) |
| **ctrl-o** | cycle the model: default → sonnet → opus → haiku |
| **ctrl-p** | hide the preset rows to hand-pick items only |
| **ctrl-s** | save the tuned pack as a new named kit |
| **enter** | launch it 🦊 |

> Loading a preset adopts that kit's model too — unless you've already picked one with ctrl-o, which
> then sticks. (Pack membership lives in a state file, not fzf's multi-select — that's what lets kit
> rows act as loadable presets and items render pre-ticked and individually removable.)

### Know the cost before you launch

Every item carries a token-weight hint and the bar totals your pack live — so the trade-off is always
on screen. Want the real number? `kit measure db` probes the actual session. And `kit measure --calibrate`
records the fixed ~22K base Claude Code floor (system prompt + built-in tool schemas) once, so afterwards
**measured weights show a kit's *own* cost** — apples to apples with the estimate.

## The gap it fills

Claude Code **front-loads everything into every session** — every installed skill's description, every
configured MCP server's tool schemas, your whole `CLAUDE.md` — whether you're refactoring or just saying
hi. There's no native way to say *"load only these skills for this session"*: it's an open, unresolved
feature request ([#39749](https://github.com/anthropics/claude-code/issues/39749),
[#26838](https://github.com/anthropics/claude-code/issues/26838),
[#39686](https://github.com/anthropics/claude-code/issues/39686)). MCP toggling exists; **a unified
picker for skills *and* MCP, with memory pinned, does not.** That's kogitsune.

## Design principles

1. **Memory rides along.** claude-mem + a tiny guardrails file are pinned in every session.
2. **Config-driven.** One `kits.yaml` (kits + catalog). Adding a kit, server, or skill is a YAML edit —
   no code. Kits compose with `extends:` and `+`/`-` deltas.
3. **Non-destructive.** Never mutate global config in place. Generate an ephemeral session, restore on exit.
4. **Show the pack weight.** Per-item cost + a live total bar, so the trade-off is always visible.
5. **Kits first, picker second.** Named kits for muscle memory; the `fzf` TUI for one-off packing.

## How it works

```
 kit db ─▶ build-config.py  reads kits.yaml + ~/.claude/mcp-on-demand.json
        ─▶ resolves the kit  → a JSON manifest (skills, plugins, MCP, guardrails)
        ─▶ session-env.sh    builds an ephemeral CLAUDE_CONFIG_DIR that mirrors
                              ~/.claude but swaps in ONLY your picked skills +
                              memory, and isolates MCP with --strict-mcp-config
        ─▶ exec claude       memory + guardrails + your kit ride along 🦊✨
        ─▶ on exit           the mirror (and its copied credentials) are deleted
```

The isolation mechanism is a **curated mirror**: a private temp dir set as `CLAUDE_CONFIG_DIR`, symlinked
to your real `~/.claude` but overriding `skills/`, `settings.json`, and `CLAUDE.md` — so unselected
skills and plugins simply aren't there for the session. MCP is scoped separately via `--strict-mcp-config`.
The mechanism (and its caveats) is validated end-to-end in [`docs/spike/FINDINGS.md`](docs/spike/FINDINGS.md).

> **Honest note on savings.** How much you save depends on what you'd *otherwise* load. If your global
> config carries heavy MCP servers and many skills, a lean kit cuts them entirely. If you've already
> demoted MCP to on-demand, the marginal win is smaller — kogitsune is then the tool that lets you keep
> that lean default *and* pull heavy kits back in only when a task calls for it.

## Quickstart

```bash
git clone https://github.com/kaiser-data/kogitsune && cd kogitsune
./install.sh                              # symlinks bin/kit into your PATH
cp examples/kits.example.yaml kits.yaml   # then edit to taste

kit doctor        # check deps, config, auth
kit ls            # list kits + à la carte catalog
kit show db       # what would the db kit pack? (no launch)
kit db --dry-run  # resolve + print the exact claude command, launch nothing
kit measure --calibrate  # one-time: record the base Claude Code floor (~22K)
kit measure db    # probe the kit; reports kit-only weight (measured − floor)
kit save mine --mcp supabase,notion --skills postgres-bp   # save a reusable kit
kit db            # launch it
kit               # or pick interactively (fzf) — ctrl-s in the picker saves a kit
```

A repo can also ship a **project overlay**: drop a `.kogitsune.yaml` in the working directory and
the fox merges it over your global `kits.yaml` (CLI flags win last), so a project recommends its own
kit without touching your global config.

**Tab completion:** `install.sh` prints the one line to add to your `~/.zshrc` or `~/.bashrc`
(completes commands, kit names, and launch flags). Scripts live in `completions/`.

**Requires:** `claude` CLI, `python3` + `PyYAML`, `jq`, and `fzf` (for the picker only).
**Auth:** uses your existing Claude login — credentials are copied into the session mirror (mode `600`)
and deleted on exit, or set `ANTHROPIC_API_KEY` to skip the copy entirely.

## Defining a kit

`kits.yaml` is the single source of truth. Items are typed by one key (`plugin` · `skill` · `dir` ·
`prefix` · `mcp` · `import` · `rules` · `env`), and kits compose:

```yaml
pinned:                                   # always on, never a toggle
  memory:     { plugin: "claude-mem@thedotmack" }
  guardrails: { import: "~/.claude/rules/guardrails.md" }
  graphify:   { skill: "graphify" }
  repack:     { skill: "repack" }         # escape hatch — must predate the need

catalog:
  mcp:
    supabase: { weight: 3300, tag: "🔴" }       # resolved from mcp-on-demand.json
    context7: { weight: 1000,  tag: "🟢" }
  skills:
    postgres-bp: { plugin: "postgres-best-practices@supabase-agent-skills", weight: 2000, tag: "🟡" }
    n8n:         { dir: "n8n-*", count: 7, weight: 4000, tag: "🟡" }
    ecc:         { plugin: "ecc@ecc", weight: 6400, gate_mcp: true }   # see below
    ecc-rules:   { rules: "ecc/common", weight: 4100 }  # rules pack -> session CLAUDE.md imports

kits:
  lean:     { mcp: [],          skills: [] }
  db:       { model: opus, mcp: [supabase], skills: [postgres-bp] }   # per-kit model
  db-heavy: { extends: db, mcp: ["+context7"] }      # inherit db (incl. model), add one more
```

A kit's optional **`model:`** (`opus` · `sonnet` · `haiku`, or a full model id) sets the launch
model. It's inherited via `extends`, overridable live in the picker with **ctrl-o**, and always
beaten by an explicit `kit db -- --model <x>`. Omit it to use Claude Code's default.

### The harness axis — the built-in tools

Skills and MCP were only ever part of the bill. The **built-in tools** (`Workflow`, `Agent`,
`Monitor`, `DesignSync`, `Cron*`, …) are the largest single block in a session, and no kit
could touch them. A `permissions.deny` entry naming a bare tool **strips that tool's schema
from the request payload** — it doesn't merely block the call — so a kit can now decline what
it will never use:

```yaml
harness:                                  # groups, sized from real measurements
  agents:    { weight: 8653, tools: [Workflow, Agent, SendMessage, ListAgents] }
  cron:      { weight: 2062, tools: [CronCreate, CronDelete, CronList, ScheduleWakeup] }
  web:       { weight:  950, tools: [WebSearch, WebFetch] }
  # … design · watch · tasks · worktrees · remote · review · mcp-res · notebooks

kits:
  lean:  { mcp: [kitsune], skills: [], harness: [web] }      # allowlist: keep web, deny the rest
  build: { extends: ecc, harness: [agents, tasks, web, review, worktrees] }
```

`harness:` is an **allowlist** — groups you name are kept, every other group is denied. Omit
the key and nothing is denied, so kits written before this axis are unaffected. Measured on
`lean`: **41 tools → 19, ~42.6K → ~22.1K tokens per session.**

Two guards, because this axis is *not* symmetric with the others: `settings.json` is read once
at startup, so unlike a missing skill (recoverable with `repack`) a wrongly denied tool needs a
full restart.

- **Essentials are never deniable** — `Bash`, `Read`, `Edit`, `Write`, `Skill`, `ToolSearch`,
  `AskUserQuestion`, `TaskOutput`, `TaskStop` survive whatever a group lists.
- **Unknown group names warn** rather than silently denying more than you meant.

Deny groups a kit is *certain* not to need; when unsure, keep them.

### Measuring instead of guessing

Weights used to be hand-entered estimates. `kit measure --proxy` points the launcher at a
local capture proxy that **answers the probe itself** — no request reaches the API — and breaks
the captured payload down per tool, per MCP server, and per system/message block:

```bash
kit measure --proxy lean            # attribution for one kit (free, offline)
kit measure --proxy lean --probe-model opus
lib/weight-sweep.sh                 # every catalog item's marginal weight
```

The first sweep found declared weights off by 3–17× in both directions. See
[`docs/FINDINGS-2026-08-09-payload-attribution.md`](docs/FINDINGS-2026-08-09-payload-attribution.md)
for the numbers and the fidelity limits — the probe is a `-p` one-shot and differs from an
interactive session, so treat the figures as comparable-to-each-other, not as billing.

Two gating features close context leaks the harness would otherwise open:

- **`rules` packs** — the harness auto-loads `<config>/rules/**` into every session, so the
  mirror excludes `rules/` and selected packs ride in as explicit session-CLAUDE.md imports.
  It *also* walks up from the working directory and loads `<ancestor>/.claude/rules/**`,
  which no mirror can reach — so keep packs outside any `.claude` dir and point
  **`rules_root:`** at them. `kit doctor` detects the un-migrated case and prints the move.
- **`gate_mcp: true`** on a plugin — plugin-bundled MCP servers (the plugin's `.mcp.json`)
  bypass `--strict-mcp-config`; gating mirrors the plugin per-entry without its `.mcp.json`,
  so its skills/commands/hooks load but its MCP servers never spawn. Re-expose the server as
  an inline-def `mcp` catalog item in the kits that genuinely want it.

## Two layers: process (superpowers) × capability (ECC)

Two big harnesses plug into kogitsune, and they answer different questions — so you pack them as
*layers*, not alternatives:

- **superpowers** (`obra/superpowers`) — the **HOW**. ~14 methodology skills that choreograph a task:
  `brainstorming` → `writing-plans` → `using-git-worktrees` → `test-driven-development` →
  `requesting-code-review` → `verification-before-completion` → `finishing-a-development-branch`.
- **ECC** (`ecc@ecc`) — the **WHAT**. 278 skills / 94 commands / 67 agents of domain capability:
  language reviewers, build-resolvers, framework patterns, orchestration (`orch-*`).
- **guardrails** (pinned) — the non-negotiable floor beneath both.

**Precedence on overlap** (both ship TDD/review/planning): `guardrails > superpowers (owns the
*sequence*) > ECC (owns the *domain step*)`. Because skills defer until invoked, the cost of
combining them is at invocation, not at launch.

One wrinkle drives the design: **superpowers installs a SessionStart hook** that auto-injects its
dispatcher on every session where the plugin is enabled — a standing cost, unlike ECC's
defer-until-invoked skills. So kogitsune offers two integration modes:

| Mode | Catalog entry | Cost | Used by |
|---|---|---|---|
| **A — plugin** | `superpowers: { plugin: "superpowers@superpowers-dev" }` | full methodology **+ SessionStart hook** | `build` |
| **B — à la carte** | `sp: { dir: "~/.claude/_vendor/superpowers/skills/*" }` | same skills, **no hook**, trigger on demand | `flow`, `feature` |

Install one or both:

```bash
make superpowers          # both modes
make superpowers-plugin   # Mode A: marketplace add + plugin install (has the hook)
make superpowers-skills   # Mode B: git clone into ~/.claude/_vendor (à la carte, no hook)
```

The best-of-both kits:

```yaml
flow:    { mcp: [kitsune], skills: [sp] }                    # lean process discipline, no ECC
build:   { extends: ecc, model: opus, skills: ["+superpowers"] }  # ⭐ ECC capability + methodology
feature: { model: opus, mcp: [kitsune], skills: [sp, ecc-rules-ts] }  # process + one language
```

### From a task to a kit: `kit for`

Don't remember the matrix — let the fox pick. `kit for "<task>"` prints the leanest kit that
fits (add `--go` to launch it), and it answers from **learned experience first**:

```bash
$ kit for "add JWT refresh to the python auth service, TDD"
🦊 for: build  — learned router (no model call)
     run: kit build -- "add JWT refresh to the python auth service, TDD"

$ kit for --go "what does resolve_kit do?"      # trivial → lean, launched immediately
```

Two paths, and the cheap one is the default:

- **Hot path** — the task's canonical signals overlap a rule the router already learned, so
  the pick is a local lookup: no model, no harness startup. Instant.
- **Cold path** — nothing overlaps, so a haiku one-shot gets the task plus the resolved
  catalog. The pick is then **logged as a gold label** with normalized signals, so the same
  shape lands on the hot path next time. (Hot-path picks are deliberately *not* logged —
  re-recording what the router already knew would only inflate its own support counts.)

That loop is the point: model calls get **rarer**, not just cheaper.

```bash
skills/lib/decider.sh normalize "harden the login flow"   # → auth, security
skills/lib/decider.sh match     "harden the login flow"   # → build   (exit 1 = cold)
skills/lib/decider.sh distill                             # decisions.jsonl → router.v<N+1>
```

Signals are canonicalized before they reach a rule, so `"auth/security-sensitive"` and
`"needs a login audit"` reinforce the *same* rule instead of two unrelated ones — see
[`decisions/SCHEMA.md`](decisions/SCHEMA.md) for the vocabulary.

### When the pick was wrong: `repack`

`kit for` still picks *before* the session, from a one-line description — a guess made at the
moment you know least. The `repack` skill re-derives the pack **mid-flight**, from what the
work turned out to actually be:

```
repack: task looks like Vue + Postgres

  + vue-patterns, supabase
  - n8n, html-email
  model: sonnet -> opus

  net -2.7K   ·   14.2K -> 11.5K

restart to apply? [y/N]
```

On confirm it writes a handoff note, saves the derived pack as the reserved `_repack` kit, and
**prints** `kit _repack -- "$(cat .kogitsune/handoff.md)"` for you to run — it never kills the
session itself. A restart is required because model, `CLAUDE.md`, and hooks are fixed at
process start; MCP alone needs no restart (use `kitsune`).

**Shedding is first-class.** Every proposal names what to drop, not only what to add —
add-only repacking is what produces the heavy session kogitsune exists to prevent.

Repack decisions are logged with `source: "repack"` and count for more in `distill` than
up-front picks: they are labelled by felt need mid-task rather than by prediction.

## Status

🦊 **Working MVP core.** Resolver + manifest, pack-weight estimator, curated-mirror launcher,
`kit ls` / `show` / `doctor` / direct `kit <name>`, and the `fzf` tuning picker (seed, toggle,
preset-load) all work and are tested. `install.sh` rounds it out. See [`docs/spike/FINDINGS.md`](docs/spike/FINDINGS.md) for the validated
mechanism and [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md) for where this sits in the landscape.

**Grok Build:** the launcher is Claude-only today; skills already surface via Claude compat. For how to make kits useful in Grok (Tier 0–3), see [`docs/NOTE-grok-build.md`](docs/NOTE-grok-build.md).

## Development & testing

```bash
make check     # shellcheck + all tests (what CI runs)
make test      # pytest (pure logic) + launcher integration tests
make lint      # shellcheck the shell scripts
```

- **Pure logic** (`build-config.py`, `context-est.py`, kit save) — unit-tested with pytest.
- **The launcher** (`bin/kit` + `lib/session-env.sh`) — `tests/test_launcher.sh` runs it
  hermetically against a **fake `claude`/keychain** (env seams: `KOGITSUNE_HOME_CONFIG`,
  `KOGITSUNE_FZF`, …), asserting the launch contract, the mirror's structure, credential mode
  `600`, the `ANTHROPIC_API_KEY` fast-path, exit-code passthrough, and — critically — that the
  **session mirror is always deleted on exit** (no credential leak).
- **CI** runs the suite on Linux *and* macOS; the macOS job runs **bash 3.2**, guarding the
  portability floor.

## Credits

The **harness axis** and `kit measure --proxy` came out of
[**Matt Pocock**](https://www.aihero.dev)'s article
[*How to kill the bloat in Claude Code's system prompt*](https://www.aihero.dev/how-to-kill-the-bloat-in-claude-codes-system-prompt)
(aihero.dev). Two ideas of theirs are load-bearing here:

1. **Point Claude Code at a local proxy and read the request body.** Tool schemas and the
   system prompt are assembled client-side, so the request is the only place the real cost is
   visible. Their run: *69 tools · 154,946 tool bytes · 65,538 input tokens*.
2. **`permissions.deny` with a bare tool name strips the tool from the payload** rather than
   just blocking the call — the mechanism the whole harness axis rests on.

What we changed:

- **The proxy doesn't forward.** Theirs is a logging proxy in front of the real API. Ours
  (`lib/measure-proxy.py`) answers the probe with a synthetic reply and never calls upstream,
  so a full catalog sweep is free, offline, and impossible to bill.
- **Per-kit, not per-user.** They tune one global `settings.json`. kogitsune already builds a
  throwaway `settings.json` per session, so denials became a kit property — `lean` can be
  ruthless while `build` keeps its agents, in the same install.
- **Allowlist with an essentials floor.** Rather than adopting their deny list, groups are
  declared and kits keep what they name; `ESSENTIAL_TOOLS` can never be denied, because a
  denial costs a restart to undo.
- **We measured our own numbers instead of reusing theirs.** Per-tool sizes came out close
  (`Workflow` ~5.3K vs our 5,466), but the conclusion differed: in an interactive Opus session
  most schemas are deferred and denying them buys ~nothing, while in a kit's `-p` probe 41 load
  eagerly. Which tools are worth denying is install- and model-specific — hence the sweep.

We did **not** adopt their `disable*` flags (`disableBundledSkills`, `disableWorkflows`, …).
They're plausible and may well work, but we haven't verified them against this Claude Code
build, and an unverified key doesn't belong in a `kits.yaml` contract.

## Family

`kogitsune` is the little sibling of **kitsune**, the lean MCP. Same fox spirit (狐), one packs light. 🦊

## License

MIT
