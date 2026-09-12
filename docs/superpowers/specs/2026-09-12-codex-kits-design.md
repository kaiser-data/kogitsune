# Codex skill kits

Status: CLI-first design approved by the user on 2026-09-12.

## Problem and outcome

Kogitsune currently launches Claude Code with a selected kit. The user's Codex
installation also carries large skill bundles, including ECC and Superpowers.
Codex's initial skill catalog has a context budget; large installations can cause
descriptions to be shortened and skills to be omitted. A kit should select the
useful skills before that catalog is built.

The first release adds a Codex CLI entry point, named presets, and a picker for
individual installed skills. Claude's existing commands retain their behavior.

## Approaches

1. **Per-launch Codex overrides (recommended).** Discover skills through Codex's
   app-server protocol and launch the CLI with explicit skill enablement overrides.
   Retain the real Codex home, authentication, instructions, and session history.
   Concurrent CLI sessions can carry different selections.
2. **A temporary Codex home.** Similar to the Claude adapter, but Codex also
   discovers user/repository skills outside that home. This requires additional
   filtering and careful treatment of credentials, plugins, and session storage.
3. **Persist an active kit for the desktop app.** Update Codex's skill settings
   with a backup and restore command. This affects shared settings and requires
   a restart according to the documented skill configuration workflow. It is a
   separate mode, not equivalent to per-session CLI selection.

## Proposed CLI

```sh
kit codex                         # pick a preset or individual skills
kit codex lean                    # launch a named preset
kit codex tune python             # adjust a preset before launch
kit codex ls                      # list presets and discovered skills
kit codex show python             # inspect the resolved selection
kit codex python --dry-run        # inspect the launch without starting a turn
kit codex python -- "fix this"    # forward a prompt to Codex
```

Codex settings live under a separate `codex:` section in `kits.yaml`, also
supported by the existing project overlay. Reuse kit inheritance and additive /
subtractive membership where practical. Do not implicitly translate Claude model
names, plugins, hooks, MCP definitions, or built-in tool denials into Codex options.

The Codex picker uses installed skill names and descriptions instead of requiring
the user to hand-catalog hundreds of files. Stable selectors use plugin-qualified
names where available. Duplicate names must be disambiguated, never selected
arbitrarily. Resolve paths anew at launch so plugin version updates do not leave
saved presets tied to stale cache paths.

## Discovery and selection

Use the installed CLI's `skills/list` protocol, which reports each skill's name,
description, path, enabled state, scope, and optional plugin ownership. Query the
actual launch working directory so repository skills are accounted for. Inventory
operations do not create a model turn or send a prompt.

Keep system/admin and project skills by default; the primary selection target is
the personal and plugin catalog. Allow a small explicit pinned selection. Show
all retained skills in the resolved manifest, including those outside the kit.
Unknown selectors and failed discovery prevent launch with an actionable error.

Generate per-launch `skills.config` overrides for the discovered inventory. Carry
forward unrelated settings and existing disabled entries. An explicitly selected
skill may be enabled for this invocation. Verify individual plugin-skill filtering
against the installed Codex version before treating this mechanism as supported.
If that check fails, report the incompatibility rather than claiming isolation.

Show selected and excluded counts. A catalog-size estimate, if included, must be
labelled as approximate; Claude's measured token weights do not apply to Codex.
Do not increase Codex's skill budget to conceal an oversized selection.

## Boundaries and implementation

Keep Codex discovery, selection, and launch logic in a dedicated Python module,
with a small dispatch branch in `bin/kit`. Reuse existing YAML loading, project
overlay merge, and kit inheritance functions where their semantics match.
Update help, completions, examples, and README with the new entry point.

The first release manages skills. Existing Codex MCP, connector, approval, sandbox,
instruction, and authentication settings remain under Codex's normal controls.
It does not claim Claude-style whole-session isolation. Desktop activation is a
separate follow-up unless the user selects it as the first target.

Honor supported forwarded launch arguments, especially working directory and
profile, during discovery as well as launch. Reject combinations that cannot
preserve the advertised selection rather than silently inspecting one environment
and launching another. Preserve Codex's exit status and signal handling.

## Verification

- Resolver tests: inheritance, pins, duplicate names, unknown selections, plugin
  updates, and independent Claude/Codex configuration.
- Fake-CLI integration tests: discovery responses, picker selection, dry run,
  argument quoting, working directory, launch overrides, and exit status.
- Local protocol smoke check: enumerate skills before and after overrides and
  confirm that excluded standalone and plugin skills report disabled, without
  starting a model turn or changing global configuration.
- Existing Python and shell tests and shell lint continue to pass.

## Evidence

- Local CLI inspected: `codex-cli 0.154.0`.
- Locally generated app-server schemas include `skills/list` with `pluginId`,
  `enabled`, `scope`, and `path` fields.
- [Official skills documentation](https://developers.openai.com/codex/skills)
  describes catalog truncation, skill discovery, and `skills.config` enablement.
- [Official configuration reference](https://developers.openai.com/codex/config-reference)
  documents skill overrides and catalog budgets. Its path description differs
  from the skills guide's example (directory versus `SKILL.md`), so the local
  protocol smoke check must establish the accepted path form.

## Verified implementation constraints

The local smoke check established that `SKILL.md` file paths disable both plugin
and standalone skills. Directory paths are silently ineffective. Each launch
therefore verifies all enabled states through a second inventory request.

Codex 0.154.0 explicitly rejects native `--profile` for `app-server`; attempting
the equivalent `-c profile=...` fails because that legacy setting is retired.
The first adapter consequently rejects profile selection with an actionable error,
as allowed by the design's requirement to reject unsupported launch environments.
`--cd` and ordinary CLI config overrides are supported for both discovery and launch.
