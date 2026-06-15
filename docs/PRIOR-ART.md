# Prior Art & Positioning

Research snapshot (June 2026). Goal: confirm whether a per-session "pick your skills + MCP" launcher
for Claude Code already exists, and define where `kogitsune` fits.

## TL;DR

- **MCP-server selection is a solved, crowded space** — several good tools already toggle MCP servers
  on/off and manage profiles.
- **Per-session *skills* selection does NOT exist** — it is an open, unresolved Claude Code feature
  request. All skills load into every session today.
- **Starter kits exist** but are content libraries (agents/skills/hooks to copy), not selectors.
- ➡️ **The gap `kogitsune` fills: a unified launcher that selects skills *and* MCP, pins memory, and
  works around the "skills always load" limitation — before the session starts.**

## Landscape

### MCP server toggling / selection (crowded — do NOT rebuild)

| Tool | What it does | Overlap |
|---|---|---|
| [henkisdabro · MCP Server Selector](https://lobehub.com/mcp/henkisdabro-claude-code-mcp-server-selector) | fzf+jq TUI to enable only the MCP servers you need, per session, with real-time context optimization | **High** — our "MCP column." Consider wrapping/crediting rather than duplicating. |
| [incu6us/mcp-switch](https://github.com/incu6us/mcp-switch) | Fast CLI to enable/disable MCP servers, manage profiles, target project or global config | Medium |
| [daveonkels/MCP-Toggle](https://github.com/daveonkels/MCP-Toggle) | Scripts to enable/disable MCP servers without losing config | Medium |
| [Raycast · Claude Code Config Switcher](https://www.raycast.com/lavatorywang/claude-code-config-switcher) | Raycast UI to switch CC configs | Low (macOS/Raycast) |
| Native `/mcp` command | In-session enable/disable of configured servers | Low (in-session, not pre-launch; no skills) |

### Per-session skills control (OPEN GAP — our wedge)

| Source | Finding |
|---|---|
| anthropics/claude-code [#39749](https://github.com/anthropics/claude-code/issues/39749) | Feature request: enable/disable individual skills per session or globally. **Unresolved.** |
| anthropics/claude-code [#26838](https://github.com/anthropics/claude-code/issues/26838) | Request to allow disabling built-in skills. |
| anthropics/claude-code [#39686](https://github.com/anthropics/claude-code/issues/39686) | Skills/plugins silently injected, ~6k tokens/session wasted, no opt-out. |
| anthropics/claude-code [#35713](https://github.com/anthropics/claude-code/issues/35713) | Even **disabled** plugins still inject context via SessionStart/UserPromptSubmit hooks. |
| vercel-labs/skills [#634](https://github.com/vercel-labs/skills/issues/634) | Request for skill enable/disable management parity. |
| [claudefa.st — skill listing budget](https://claudefa.st/blog/guide/mechanics/skill-listing-budget) | A hidden "skill budget" setting exists; a partial lever we can use. |

**Implication:** there is no native or third-party way to say *"load only these skills for this session."*
`kogitsune` can implement it by generating a **session-scoped `.claude/skills/`** (symlink only the
chosen skill folders) and/or tuning the skill-listing budget, then launching `claude` against it.

### Starter kits / boilerplates (adjacent, not competing)

| Tool | What it is |
|---|---|
| [rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit) | Huge curated library of agents/skills/commands/plugins/MCP configs. Content, not a selector. |
| [mp-web3/claude-starter-kit](https://github.com/mp-web3/claude-starter-kit) | `.claude/` config that "remembers you across sessions." Memory-focused, no per-session picker. |
| [TheDecipherist · mastery starter kit](https://github.com/TheDecipherist/claude-code-mastery-project-starter-kit) | Opinionated project starting point. No kit selection. |
| [shinpr/ai-coding-project-boilerplate](https://github.com/shinpr/ai-coding-project-boilerplate) | TypeScript agentic boilerplate w/ context engineering. Template, not a launcher. |

## Positioning statement

> **kogitsune is the only launcher that lets you pack your *skills* and *MCP servers* together, per
> session, with memory pinned — turning Claude Code's "everything always loads" default into a kit you
> choose.** It complements (and can wrap) existing MCP-only selectors, and closes the per-session skills
> gap that Claude Code itself has not yet shipped.

## Differentiators

1. **Skills + MCP in one picker** (others do MCP only).
2. **Memory rides along by default** — the one thing you always want, never a toggle.
3. **Per-session skills isolation** via generated session-scoped `.claude/skills/`.
4. **Pack-weight transparency** — context cost per item + live total bar.
5. **Kits + à la carte** from a single `kits.yaml`.

## Open questions / risks

- **Skills isolation mechanism:** symlinked session `.claude/skills/` vs. skill-budget tuning vs. moving
  folders — needs a spike to pick the cleanest, most reversible approach. (Disabled plugins still
  injecting context, #35713, may limit how clean this can be for *plugin* skills vs. local skills.)
- **Overlap with henkisdabro's selector:** decide wrap-and-credit vs. independent implementation.
- **Upstream may ship native skills toggling**, narrowing the wedge — keep the value in the *unified
  picker + kits + memory-pinning*, which survives even if skills toggling lands natively.

---

### Sources
- https://github.com/incu6us/mcp-switch
- https://lobehub.com/mcp/henkisdabro-claude-code-mcp-server-selector
- https://github.com/daveonkels/MCP-Toggle
- https://www.raycast.com/lavatorywang/claude-code-config-switcher
- https://github.com/anthropics/claude-code/issues/39749
- https://github.com/anthropics/claude-code/issues/26838
- https://github.com/anthropics/claude-code/issues/39686
- https://github.com/anthropics/claude-code/issues/35713
- https://github.com/vercel-labs/skills/issues/634
- https://claudefa.st/blog/guide/mechanics/skill-listing-budget
- https://github.com/rohitg00/awesome-claude-code-toolkit
- https://github.com/mp-web3/claude-starter-kit
- https://code.claude.com/docs/en/mcp
