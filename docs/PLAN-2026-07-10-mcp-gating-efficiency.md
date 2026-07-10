# Plan — plugin-MCP gating + gateway-first efficiency (2026-07-10)

Status: **proposed** (not yet implemented). Author: maintainer session 2026-07-10.
Companion to `HANDOFF-2026-07-09-ecc-superclaude.md` (all seven duties there are done;
this plan is the follow-up work discovered afterwards).

## Trigger

The ECC plugin bundles an MCP server (`plugins/marketplaces/ecc/.mcp.json` →
`npx -y chrome-devtools-mcp@latest`, **29 tools**). Kit sessions were assumed to
isolate MCP via `--strict-mcp-config`, but that flag only filters mcp-config-file
servers — plugin-bundled servers ride in with `enabledPlugins`.

## Confirmed findings (evidence, 2026-07-10)

1. **Plugin MCP servers bypass kit isolation.** Process-level proof: a
   `kit ecc --model haiku -p …` probe launched at 14:23 spawned
   `npm exec chrome-devtools-mcp@latest` → `chrome-devtools-mcp` → telemetry
   watchdog under its own process tree, despite `--strict-mcp-config`.
   Cost per `ecc`/`deep` session: npx fetch + server + watchdog processes and
   seconds of startup latency. Token cost today is ~0: the same probe answered
   "NONE" when asked to list `mcp__` tools, so under current tool deferral the
   29 schemas don't reach the model unrequested — but they would cost
   **10–15K tokens if schemas load fully** (deferral off / older CC), so the
   gate is latency/process hygiene now and token insurance later.
2. **Kitsune MCP is the right-sized alternative for ad-hoc needs.**
   `kitsune-mcp` v0.20.8 (own project, `~/claude-projects/KitsuneMCP`) exposes a
   6-tool lean profile — `status, search, auth, shapeshift, call, auto` — ~2K
   standing, and can shapeshift into any registry MCP server at runtime.
3. **Baseline numbers** (measured, one-shot haiku probe methodology):
   floor 26.8K · `lean` +2.2K (~29K) · `ecc` +10.6K (~37K) · kitchen-sink ~79K.

## Phase 1 — Gate plugin-bundled MCPs in the mirror

Code change in `lib/session-env.sh` + `lib/build-config.py`, TDD.

- **Mirror:** `kog_build_mirror` currently symlinks `plugins/` wholesale
  (session-env.sh step 1). For plugins the manifest marks as MCP-gated,
  selectively mirror `plugins/marketplaces/<name>/`: per-entry symlinks (same
  pattern as the top-level mirror), with `.mcp.json` materialized as `{}`.
  One extra directory level; no file copying. Never touch the real `~/.claude`.
- **Catalog syntax:** `ecc: { plugin: "ecc@ecc", weight: 4200, gate_mcp: true }`
  → new manifest field (e.g. `plugin_mcp_exclude: ["ecc@ecc"]`) → mirror behavior.
  Default the `ecc` and `deep` kits to gated.
- **Opt-in re-exposure:** add `chrome-devtools` as an inline-def catalog MCP item
  (`def: { command: npx, args: [-y, chrome-devtools-mcp@latest] }`) flowing
  through the normal `--mcp-config` path, plus a kit:
  `qa: { extends: ecc, mcp: ["+chrome-devtools"] }`.
- **Tests:** launcher test asserting the gated plugin's `.mcp.json` is empty in
  the mirror and everything else in the plugin dir still resolves; pytest for the
  manifest field; both-direction process probe (`kit ecc` → no chrome-devtools
  processes; `kit qa` → present). `kit doctor` green; `kit measure` before/after
  and write measured weights into the catalog.

## Phase 2 — Kitsune gateway + a well-defined skill

Config + one skill file; no lib code.

- Add `kitsune` (2K) to kits where occasional, unpredictable MCP access is
  useful, instead of stacking heavy servers "just in case."
- Write `mcp-via-kitsune/SKILL.md` with a crisp trigger: *when a task needs an
  MCP server that isn't loaded (browser automation, Notion, any registry
  server), use kitsune: `search` the registry → `shapeshift` into the server →
  `call` its tools.* Standing cost: one line in the skills list.
- Encode the trade-off rule in the skill: the gateway adds a hop per call, so it
  wins for **occasional** use; a session that will hammer one server (long
  browser-QA run, heavy Supabase work) should launch the dedicated kit instead.
- Browser-work default is not an MCP at all: ECC's `browser-qa` skill and
  `e2e-runner` agent drive Playwright via CLI at zero standing schema cost.
  Reserve the chrome-devtools MCP (`qa` kit) for interactive DevTools work —
  performance traces, heap snapshots, console spelunking.

## Phase 3 — Standing policy + measurement loop

- **Rule: no MCP server rides along unless the session is about it.**
  Supabase (10K) and n8n (12K) already follow this via their kits; kitsune
  covers the ad-hoc tail everywhere else.
- After any catalog/mirror change: `kit measure <kit>`, write the **measured**
  number into the catalog, keep doctor green. Weights are hints; measurements
  are truth (the ECC 25K→4.2K correction proved why).

## Expected numbers

| Session                      | Startup context | Notes                                          |
|------------------------------|-----------------|------------------------------------------------|
| Kitchen-sink (no kit)        | ~79K            | floor 26.8K + full catalog                     |
| `kit ecc` today              | ~37K            | + chrome-devtools spawn + tool surface         |
| `kit ecc` after Phase 1      | ~36K            | −~1K tokens, −npx/Chrome spawn, −watchdog; insurance vs the 10–15K full-schema case |
| `kit lean` + kitsune skill   | ~31K            | ad-hoc access to any MCP for +2K               |

## Real workflows (kit → flow)

- **Everyday edits, questions, scripts** → `kit lean`. mem-search before
  re-deriving; graphify for architecture questions.
- **Feature work (TS/Py)** → `kit ecc` + matching rules pack → `/ecc:plan` →
  TDD → `/ecc:code-review` → commit. Quality hooks (GateGuard etc.) stay on
  here — this is where their per-action overhead earns its keep.
- **Bug fix** → `kit ecc` → `/ecc:orch-fix-defect` (failing repro test → fix →
  review → gated commit).
- **Database / n8n / research** → `kit db` / `kit n8n` / `kit research` —
  heavy MCPs only in their own lanes.
- **Browser QA** → `browser-qa` skill inside `kit ecc` by default; `kit qa`
  (new, Phase 1) when real DevTools access is needed.
- **"I suddenly need Notion/X/whatever"** → don't relaunch: kitsune
  `search → shapeshift → call`.

## Constraints (inherited)

- Never touch the real `~/.claude` from inside a mirrored session.
- Catalog weights are hints; prefer measured numbers.
- `kit doctor` must stay green after every config change.
