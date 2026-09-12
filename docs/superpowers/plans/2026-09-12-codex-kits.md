# Codex Skill Kits Implementation Plan

**Goal:** Select individual Codex skills with named kits before launching the CLI.

**Architecture:** Add a Python Codex adapter behind `kit codex`. Discover the
effective inventory through a short-lived app server, resolve a separate YAML
section, and pass per-launch overrides to the real CLI. Use fzf for selection.

**Tech stack:** Existing Bash launcher, Python 3 + PyYAML, Codex app-server JSON-RPC,
fzf, pytest, shellcheck.

**Spec:** `docs/superpowers/specs/2026-09-12-codex-kits-design.md`

## Constraints

- CLI first; existing Claude commands retain their behavior.
- Preserve Codex home, credentials, history, instructions, MCP and permissions.
- Keep enabled system/admin/repo skills by default and resolve plugin paths anew.
- Discovery and validation never create a model turn.
- No arbitrary selection on ambiguous names, missing skills, or discovery errors.

## Execution checklist

- [x] Implement `lib/codex-rpc.py`: bounded stdio JSON-RPC requests, initialize,
  skills/list, config/read, clear startup errors, process cleanup. Test with a
  fake executable that speaks the actual protocol.
- [x] Implement `lib/codex-kit.py`: shared YAML merge/inheritance, stable skill
  selectors, preserved disabled entries, retained scopes, per-launch overrides.
  Test duplicate names, pins, inheritance, changed plugin versions and bad input.
- [x] Verify the adapter against local Codex 0.154.0: disabled standalone and
  plugin skills must report disabled under generated overrides. Establish the
  accepted path form from actual results.
- [x] Add CLI and fzf flows, save selections, dry-run/show/list commands, launch
  argument validation, working directory/profile handling and exit propagation.
  Cover these through fake-CLI subprocess tests, including cancellation and paths
  with shell metacharacters.
- [x] Wire `bin/kit`, completions, example presets and README. Add focused Python
  and frontend kits to the local YAML so the new command is immediately useful.
- [x] Run focused tests, then `make check`; inspect the final diff and report the
  actual smoke-check results and supported limitations.

Execute inline under the user's existing authorization. Keep unrelated untracked
notes and the backup YAML intact. No publishing or global activation is needed.

## Results

- `make check`: 169 Python tests, 97 launcher checks, 26 router checks; shell lint
  passed. One existing launcher assertion was changed from a pipe to a here-string
  after an observed intermittent `grep -q`/SIGPIPE failure under `pipefail`.
- Real Codex 0.154.0 inventory: 354 enabled skills before selection, 6 for `lean`,
  8 each for `python`, `frontend`, and `debug`; all enabled states verified.
- SHA-256 of `~/.codex/config.toml` remained unchanged across the smoke checks.
- Real fzf 0.73.1 terminal checks: preset preselection, empty selection, and the
  save-name interaction passed. Added a regression test for nonseekable TTY input.
- Profiles are explicitly unsupported because the installed app server rejects
  both native profile selection and the retired `profile` config key.
