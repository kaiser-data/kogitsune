# Spike findings — session isolation mechanism

Date: 2026-06-15 · Claude Code v2.1.177 · probes via `claude -p --output-format=json --model haiku`

## Goal
De-risk the core of kogitsune: can we launch `claude` with only a chosen subset of
skills + MCP, while memory (claude-mem) + guardrails ride along — non-destructively?

## What we tested
The **curated-mirror** strategy: a temp `CLAUDE_CONFIG_DIR` that symlinks everything from
`~/.claude` (and `~/.claude.json`) except it overrides:
- `skills/` → fresh dir, symlink only the pinned `graphify`
- `settings.json` → copy with `enabledPlugins` pruned to `claude-mem` only

MCP isolated separately via `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`.

## Results

| Probe | Result | Tokens |
|---|---|---|
| **Baseline** (normal launch, full config) | ✅ works | **24,154 ctx** |
| **Empty** `CLAUDE_CONFIG_DIR` (nothing carried) | ❌ `Not logged in · Please run /login` | 0 |
| **Curated mirror** (skills + plugins pruned) | ❌ `Not logged in · Please run /login` | 0 |

Plus two sub-findings from the mirror run:
- ✅ **`enabledPlugins` prune worked** → `{"claude-mem@thedotmack":true}` only.
- ✅ **skills override worked** → only `graphify` visible in the session skills dir.
- ✅ **claude-mem hooks fired under the mirror** (stream-json showed `hook_started` /
  `hook_response` ×3 then `init`) — memory machinery rides along once auth is solved.

## The blocker: auth does not survive `CLAUDE_CONFIG_DIR`
Both isolated launches failed auth — **including the mirror that symlinks `~/.claude.json`
(which contains `oauthAccount` + `userID`)**. Conclusion: the OAuth *token* is **not** in
`.claude.json`. On macOS it lives in the **keychain** (or a `.credentials.json`) that Claude
Code resolves relative to the *default* config dir. Remapping `CLAUDE_CONFIG_DIR` makes it
look for creds in the temp dir, finds none → "Not logged in".

This is the make-or-break dependency. The token math is great (mirror prunes to a lean floor;
baseline is ~24k), but it's worthless if the session can't authenticate.

## Options to fix auth (decision needed)
1. **Materialize credentials into the mirror** — read the keychain cred once and write
   `$MIRROR/.credentials.json` (mode 600), cleaned up on exit via `trap`. Works, but writes a
   secret to a temp file and requires a keychain read (sensitive — blocked by the auto-mode
   classifier in this session; needs explicit user opt-in / a Bash permission rule).
2. **`ANTHROPIC_API_KEY` env** — if the user has an API key, export it for the session;
   sidesteps keychain entirely. Cleanest when available, but not OAuth/subscription auth.
3. **Abandon `CLAUDE_CONFIG_DIR`; isolate skills a different way.** No good native lever exists
   for *user-scope* skills (the token-heavy ones) — `--strict-mcp-config` covers MCP cleanly,
   but skills would remain unsolved. This guts the headline feature.
4. **`--bare`** loads minimal context but also skips auto-memory/hooks → breaks "memory rides
   along". Not viable as the default.

## Recommendation
Pursue **option 1 (materialize creds into the mirror)** as the default, with **option 2
(`ANTHROPIC_API_KEY`)** as an automatic fast-path when the env var is present. Both keep the
curated-mirror architecture — which we proved works for skills + plugins + memory-hooks — and
only add a guarded, opt-in credential copy. Requires a one-time user consent / permission rule
for the keychain read. Confirm before building the launcher around it.

## Reproduce
`bash docs/spike/run-spike.sh` (full) or `docs/spike/rerun.sh` (auth-focused). Artifacts land
in `/tmp/kog_*.json`. Scripts read `~/.claude` at runtime and contain no secrets.
