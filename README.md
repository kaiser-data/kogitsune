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
  🦊 lean           ~0K   preset                 │ pack weight: ~14.7K tokens     │
▶ ✔ 🔴 supabase     ~10K  (mcp)   ← in pack      │  ▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░        │
  ○ 🟠 notion       ~4K   (mcp)   ← toggle on    │  (lean = ~2.7K)                │
  ✔ 🟡 postgres-bp  ~2K   (skill)                │ model:  opus  (ctrl-o cycles)  │
  ○ 🟢 frontend     ~1K   (skill)                │                                │
                                                 │ mcp:    supabase               │
                                                 │ skills: postgres-bp            │
 space/tab · 🦊 loads preset · ctrl-o model ·     │ pinned: memory · guardrails ·  │
 ctrl-p hide presets · enter · ctrl-s save        │         graphify               │
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
`prefix` · `mcp` · `import` · `env`), and kits compose:

```yaml
pinned:                                   # always on, never a toggle
  memory:     { plugin: "claude-mem@thedotmack" }
  guardrails: { import: "~/.claude/RULES.md" }
  graphify:   { skill: "graphify" }

catalog:
  mcp:
    supabase: { weight: 10000, tag: "🔴" }      # resolved from mcp-on-demand.json
    context7: { weight: 1000,  tag: "🟢" }
  skills:
    postgres-bp: { plugin: "postgres-best-practices@supabase-agent-skills", weight: 2000, tag: "🟡" }
    n8n:         { dir: "n8n-*", count: 7, weight: 4000, tag: "🟡" }

kits:
  lean:     { mcp: [],          skills: [] }
  db:       { model: opus, mcp: [supabase], skills: [postgres-bp] }   # per-kit model
  db-heavy: { extends: db, mcp: ["+context7"] }      # inherit db (incl. model), add one more
```

A kit's optional **`model:`** (`opus` · `sonnet` · `haiku`, or a full model id) sets the launch
model. It's inherited via `extends`, overridable live in the picker with **ctrl-o**, and always
beaten by an explicit `kit db -- --model <x>`. Omit it to use Claude Code's default.

## Status

🦊 **Working MVP core.** Resolver + manifest, pack-weight estimator, curated-mirror launcher,
`kit ls` / `show` / `doctor` / direct `kit <name>`, and the `fzf` tuning picker (seed, toggle,
preset-load) all work and are tested. `install.sh` rounds it out. See [`docs/spike/FINDINGS.md`](docs/spike/FINDINGS.md) for the validated
mechanism and [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md) for where this sits in the landscape.

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

## Family

`kogitsune` is the little sibling of **kitsune**, the lean MCP. Same fox spirit (狐), one packs light. 🦊

## License

MIT
