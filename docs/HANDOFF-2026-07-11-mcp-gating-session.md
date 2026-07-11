# Handoff — 2026-07-11 session (plugin-MCP gating, kitsune gateway, weights)

For the next agent maintaining **kogitsune** and the adjacent **marty-skills** repo.
Predecessor docs: `HANDOFF-2026-07-09-ecc-superclaude.md` (all duties done),
`PLAN-2026-07-10-mcp-gating-efficiency.md` (all three phases now delivered).

## What shipped this session (all pushed to main)

kogitsune (`kaiser-data/kogitsune`):
- `e16a229` docs: the efficiency plan (trigger: ECC's plugin-bundled chrome-devtools
  MCP, 29 tools, spawned in every ecc/deep session because plugin `.mcp.json`
  bypasses `--strict-mcp-config` — proven by process-tree probe).
- `501c311` feat: **`gate_mcp: true`** on plugin catalog items → manifest
  `plugin_mcp_exclude` → `kog_mirror_plugins()` mirrors `plugins/` per-entry and
  drops the gated marketplace's `.mcp.json` (skills/commands/hooks still load;
  ungated kits keep the zero-cost wholesale symlink). New **`qa` kit**
  (`extends: ecc, mcp: ["+chrome-devtools"]`) re-exposes the server as an
  inline-def catalog item through the strict `--mcp-config` path.
  Verified both directions with live process probes: `kit ecc` spawns 0
  chrome-devtools processes; `kit qa` spawns the npx/server/watchdog trio.
- `b851fab` chore: example config sync — `kitsune` gateway added to `lean` and
  `ecc` kits (deep/qa inherit), kitsune weight corrected 2000 → **700**.

marty-skills (`kaiser-data/marty-skills`):
- `3212ed4` **kitsune-gateway** skill (`skills/kitsune-gateway/SKILL.md`), also
  symlinked into `~/.claude/skills/`. Teaches the on-demand MCP pattern:
  `search → shapeshift(server, tools=[…]) → call → shapeshift()`, plus the
  CLI vs gateway vs dedicated-kit decision rule. forge validate: 5 skills clean.

## Current measured numbers (one-shot haiku probe, floor 26,789)

| Kit  | kit-only | session start |
|------|---------:|--------------:|
| lean (incl. kitsune) | 2,810  | ~29.6K |
| ecc  (incl. kitsune) | 11,335 | ~38.1K |

kitsune's standing cost under tool deferral: **~590–780 tok** (measured deltas),
independently corroborated at 656 tok (name+description only; full schemas 1,319).
Kitchen-sink no-kit baseline for comparison: ~79K.

## OPEN ITEMS (priority order)

1. **See `HANDOFF-2026-07-11-LOCAL.md`** (gitignored, this machine only) for the
   top-priority item — handle it before anything below.
2. **`${VAR}` expansion in server defs** (proposed, user not yet committed):
   resolve-time env substitution in `build-config.py` so `mcp-on-demand.json`
   can reference env-var names instead of inline values. Small: substitution
   in `resolve_item`'s mcp branch + tests. Config files become safe to display.
3. **`kit doctor` credential-hygiene check** (proposed): warn when
   `mcp-on-demand.json` server defs carry inline values rather than
   env-var references.
4. **kitsune-forge weight**: catalog hint 2000; measured 3,025 full / 1,364
   deferred. Correct to ~1400 if/when a kit actually selects it.
5. **`kit measure qa`** hasn't been run (expect ecc + ~1K for the deferred
   29-tool surface; more if deferral is off).

## Invariants (unchanged)

- Never touch the real `~/.claude` from a mirrored session.
- Catalog weights are hints; prefer measured (`kit measure <kit>`, results in
  `~/.local/state/kogitsune/measured.json`).
- `kit doctor` must stay green after every config change; suite: pytest 37,
  launcher 69, `make lint` (shellcheck severity=warning).
- `kits.yaml` at repo root is the live per-machine config and **gitignored**;
  `examples/kits.example.yaml` is the tracked template — keep them in sync.
- ECC is installed via plugin only; never "repair" with install.sh/npx.

## Session-start workflow reminder

The whole system only pays off when sessions start with `kit <name>` instead of
bare `claude`: lean (daily), ecc (quality-gated feature work + hooks), deep
(+context7), qa (+DevTools MCP), db/n8n/research (heavy servers in their lanes).
Mid-session one-off MCP needs: kitsune-gateway skill, no relaunch.
