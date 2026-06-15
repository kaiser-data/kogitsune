# kogitsune 🦊

> **kogitsune** (小狐 · "little fox") — *the lean little sibling of [kitsune](#).*
> Pack only the skills + MCP your Claude Code session needs. Start light, spend fewer tokens.

`kogitsune` is a session launcher for [Claude Code](https://code.claude.com). Before a session you
choose a **kit** — a pre-tuned set of *skills + MCP servers* — and the little fox starts `claude`
carrying exactly that, and nothing else. Memory (claude-mem) always rides along.

The whole point is **lean sessions**: stop front-loading everything into every conversation, pack only
what the task needs, and save the tokens you'd otherwise burn on context you never use.

**Command:** `kit` — pack your kit before the trip. `kit`, `kit db`, `kit n8n`.
**Status:** 🚧 early / scaffolding. MVP = interactive `fzf` picker + saveable kits.

---

## Why this exists

Claude Code **front-loads** everything into every session — big `CLAUDE.md` imports, every installed
skill's description, every MCP server's tool schemas. You pay that token cost on a "hello" the same as
on a refactor, and the model half-reads instructions it doesn't need.

The fix is **on-demand context** — load capability only when a task calls for it. Two gaps remain that
the little fox closes:

1. **Skills can't be selected per session.** Everything in `.claude/skills/` (and enabled plugins) loads
   into *every* conversation — an open, unresolved Claude Code feature request
   ([#39749](https://github.com/anthropics/claude-code/issues/39749),
   [#26838](https://github.com/anthropics/claude-code/issues/26838),
   [#39686](https://github.com/anthropics/claude-code/issues/39686)).
2. **No unified picker** selects skills *and* MCP *and* pins memory in one pre-launch step.
   (Per-session MCP toggling already exists — `mcp-switch`, henkisdabro's fzf selector — so we don't
   rebuild it; our value is the *unified* skills+MCP kit with memory pinned.)

## What it looks like

```
╭──────────────────────────────────────────────────────────────────────╮
│  🦊 kogitsune · pack your kit                       📁 ~/cerpro        │
├──────────────────────────────────────────────────────────────────────┤
│  ALWAYS RIDES ALONG (pinned)                                           │
│   ✔ 🧠 memory (claude-mem)            ── default, not removable        │
│   ✔ 🛡 guardrails (RULES.md)          ── default                       │
│   ✔ 🕸 graphify                       ── default                       │
│                                                                        │
│  ── KITS ────────────────────────────────────────────────────────     │
│   ( ) Lean        memory only            ~1K ctx                       │
│   (•) DB work     + supabase + postgres  ~12K ctx   ◀ selected         │
│   ( ) n8n         + n8n-mcp + n8n skills ~18K ctx                      │
│   ( ) Frontend    + frontend-design      ~2K ctx                       │
│   ( ) Research    + notion + context7    ~6K ctx                       │
│                                                                        │
│  ── À LA CARTE ──────────────────────────────────────────────────     │
│   MCP servers                      Skill bundles                       │
│   [x] supabase        🔴 ~10K      [x] postgres-bp      🟡 ~2K         │
│   [ ] n8n-mcp         🔴 ~12K      [ ] n8n (7 skills)   🟡 ~4K         │
│   [ ] notion          🟠 ~4K       [ ] frontend-design  🟢 ~1K         │
│   [ ] dify-superclaude 🟠 ~3K      [ ] sc:* commands    🟡 ~4K         │
│                                                                        │
│   pack weight:  ~12K tokens  ▓▓▓░░░░░░░  (lean = ~1K)                  │
│         [ ↵ Go ]      [ s Save kit ]      [ q Lean ]                   │
╰──────────────────────────────────────────────────────────────────────╯
   ↑↓ move   space toggle   1-5 pick kit   tab switch column
```

```
 run `kit` → read kits.yaml + ~/.claude/mcp-on-demand.json → pick a kit / toggle à la carte
           → build temp --mcp-config + session-scoped skills → launch claude
           → memory + guardrails always ride along, + only your selections 🦊✨
```

## Design principles

- **Memory rides along** (claude-mem + a tiny guardrails file). Never a toggle.
- **Config-driven** — one `kits.yaml` (kits + catalog); reads servers from `~/.claude/mcp-on-demand.json`.
- **Non-destructive** — never edits global config in place; generates a session config, restores on exit.
- **Show the pack weight** — per-item context-cost estimate + live total bar.
- **Kits first, picker second** — `kit db` / `kit n8n` for the 90% path; the `fzf` TUI for ad-hoc.

## Quickstart (planned)

```bash
git clone <repo> && cd kogitsune
./install.sh                 # symlinks bin/* into PATH, sets the `kit` command
cp examples/kits.example.yaml kits.yaml   # then edit to taste

kit            # interactive picker
kit db         # send the fox off with a saved kit
```

Requires: `claude` CLI, `fzf`, `jq`, `python3`.

---

## 🛠 Build prompt (paste into a fresh Claude Code session in this folder)

````text
Build `kogitsune` (command: `kit`), a session launcher for Claude Code. Before a session, the user packs
a "kit" — a reusable named set of which skills and MCP servers to load — and the tool launches `claude`
with exactly that. Memory (the claude-mem plugin) and a small guardrails file are ALWAYS loaded ("ride
along") and are not toggleable. Theme: a little fox (kogitsune = "little fox") that packs light to save
tokens.

Context / why: Claude Code loads every installed skill description and every configured MCP server's
tool schemas into every session, wasting tokens. Per-session SKILL selection does not exist natively
(open feature requests #39749 / #26838; disabled plugins still leak context per #39686 / #35713).
Per-session MCP selection already exists in other tools (mcp-switch, henkisdabro's fzf selector) — do
NOT rebuild generic MCP toggling; our value is the UNIFIED skills+MCP kit with memory pinned, so each
session runs lean.

Requirements:
1. Config: a `kits.yaml` defining
   - `pinned`: memory + guardrails + graphify (always on)
   - `catalog.mcp`: selectable MCP servers, each with a context-weight hint (tokens) + color tag
   - `catalog.skills`: selectable skill bundles (plugin name, local dir glob, or sc:* prefix) + weights
   - `kits`: named sets (lean, db, n8n, frontend, research) listing mcp[] and skills[]
   Ship `examples/kits.example.yaml`; load the user's real MCP servers from
   `~/.claude/mcp-on-demand.json` by name.
2. `lib/build-config.py`: given a selection (kit name or explicit mcp/skills lists), emit a temp
   `--mcp-config` JSON containing ONLY the chosen servers (merged from mcp-on-demand.json). Pure,
   testable, no side effects beyond writing the temp file. Print the path.
3. Per-session SKILLS isolation: generate a session-scoped `.claude/skills/` (symlink only the chosen
   local skill folders) so unselected skills don't load. Spike the cleanest reversible mechanism first
   (symlinked skills dir vs. skill-listing-budget tuning); document the tradeoff. Restore on exit.
4. `lib/context-est.py`: sum weights of the current selection ("pack weight"); render a total + an
   ASCII progress bar relative to a "lean" baseline.
5. `bin/kit`: an interactive `fzf`-based multi-select TUI matching the mockup above — pinned items shown
   but locked, kits selectable by number, à la carte MCP + skills toggled with space, live pack-weight
   estimate, then Go (launch). Requires fzf + jq + python3.
6. Direct kit launch: `kit <name>` (e.g. `kit lean|db|n8n|frontend|research`) skips the TUI and launches
   the named kit. Implement as a thin path over the core.
7. `install.sh`: symlink `bin/*` into PATH and set up the `kit` command; idempotent; prints next steps.
8. Launch step: exec `claude --mcp-config <temp>.json` with the session skills dir in scope; pass
   through any extra args (e.g. a prompt) to `claude`.
9. Tests for build-config.py and context-est.py. A README with usage. MIT license.
10. Remember the last kit per working directory (small JSON state file under the repo or XDG dir).

Constraints: non-destructive (never edit ~/.claude.json or global mcp.json in place); reversible;
clear errors if fzf/jq/claude missing; keep memory + guardrails pinned in every generated config.

Deliverables: working `kit` picker + direct kit launch, kits.example.yaml, build-config.py +
context-est.py with tests, install.sh, README. Start with the skills-isolation spike (step 3) to
de-risk the design, then build the core (step 2), then the TUI (step 5).
````

---

## Family

`kogitsune` is the little sibling of **kitsune**, the lean MCP. Same fox spirit (狐), one packs light. 🦊

See [`docs/PRIOR-ART.md`](docs/PRIOR-ART.md) for the competitive landscape and where this fits.

## License

MIT (planned).
