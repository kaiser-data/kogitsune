---
name: kit-selector
version: 0.1.0
description: Use when a task needs a kogitsune config/kit chosen before launch, when routing work to the leanest capable harness, or when deciding which model + MCP + skills a task warrants. Symptoms: "which kit for this?", unsure lean vs build, avoiding a full-harness model call for an obvious task.
---

# kit-selector

## Overview
Turns a task into a config decision using the **learned router first, model last**.
It reads the scout's context (the menu) and the distilled router (past experience),
answers instantly when a task matches a learned pattern, and only reasons from scratch
when it doesn't. Every decision is logged as a gold label so the router keeps improving.
Selects *for* `kit-builder`.

## When to Use
- Any "which kit / config should this task use?" moment
- Before `kit <name> -- "<task>"`, to justify the pick
- When you want to avoid a slow full-harness model classification for an obvious task

## How it works
1. Load inputs: `decider latest context` (menu) and `decider latest router` (learned rules).
2. **Hot path** — extract task signals (language, security surface, tests, triviality,
   domain). If they match a router rule with support, take that kit. No model call.
3. **Cold path** — no confident match: reason over the context to compose the config
   (kit *or* à-la-carte model+MCP+skills). This is the teacher step (opus-grade judgment).
4. Log it: `decider append-decision '<json>'` with `task`, `decision`, **`signals`**,
   `rationale`, `confidence`, `alternatives` (see `decisions/SCHEMA.md`).
5. Periodically `decider distill` → bumps `router.v<N+1>.json` from all decisions.

## Improve with experience
`signals → decision` pairs accumulate in `decisions.jsonl`; `distill` compiles them into
the next router version. More logged decisions ⇒ more tasks answered on the hot path ⇒
fewer model calls. `alternatives` supply contrastive negatives for future learning.

## Versioning
- Skill: frontmatter `version:`.
- Learned artifact: `decisions/router.v<N>.json`; current N in `decisions/VERSIONS.md`.

## Common Mistakes
- Skipping the router and always reasoning — defeats the speed-up. Check the hot path first.
- Logging without `signals` — the router can only learn from signals; a decision without
  them is a dead record.
- Picking a heavy kit for a trivial task — prefer the leanest capable config.
