#!/usr/bin/env bash
# kogitsune — session mirror builder (sourced by bin/kit).
# Turns a build-config manifest into an ephemeral CLAUDE_CONFIG_DIR that carries
# ONLY the chosen skills + plugins + guardrails, with memory pinned, then cleans up.
#
# Strategy (validated in docs/spike/FINDINGS.md): symlink-mirror ~/.claude into a
# private temp dir, overriding skills/, rules/, settings.json and CLAUDE.md; isolate
# MCP via --strict-mcp-config; materialize credentials so auth survives the remapped dir.

# Build the mirror. Args: $1=manifest.json  $2=real config dir (~/.claude)
# Echoes the mirror path on stdout. Caller owns cleanup via kog_cleanup.
kog_build_mirror() {
  # source config dir overridable via $2 or KOGITSUNE_HOME_CONFIG (hermetic tests)
  local manifest="$1" rc="${2:-${KOGITSUNE_HOME_CONFIG:-$HOME/.claude}}"
  local dotjson="${KOGITSUNE_HOME_DOTJSON:-$HOME/.claude.json}"
  local mirror; mirror="$(mktemp -d "${TMPDIR:-/tmp}/kogitsune.XXXXXX")"
  chmod 700 "$mirror"

  # 1. symlink every ~/.claude entry except the ones we override.
  #    rules/ is EXCLUDED: the harness auto-loads <config>/rules/** into every
  #    session, so rules packs are gated instead — selected ones ride in as
  #    explicit session-CLAUDE.md imports (catalog kind: rules).
  local e b
  for e in "$rc"/* "$rc"/.[!.]*; do
    [[ -e "$e" ]] || continue
    b="$(basename "$e")"
    case "$b" in
      skills|settings.json|CLAUDE.md|rules|plugins) continue ;;
      *) ln -s "$e" "$mirror/$b" ;;
    esac
  done
  # 1b. plugins/: wholesale symlink unless the manifest gates a plugin's bundled
  #     MCP — plugin .mcp.json bypasses --strict-mcp-config, so gated plugins are
  #     mirrored per-entry with their .mcp.json dropped (skills/hooks still load).
  local gated
  gated="$(jq -r '.plugin_mcp_exclude[]? // empty' "$manifest" 2>/dev/null)"
  if [[ -d "$rc/plugins" ]]; then
    if [[ -z "$gated" ]]; then
      ln -s "$rc/plugins" "$mirror/plugins"
    else
      kog_mirror_plugins "$rc/plugins" "$mirror/plugins" "$gated"
    fi
  fi
  # ~/.claude.json lives at $HOME — relocate it into the mirror so projects/auth resolve
  [[ -e "$dotjson" ]] && ln -s "$dotjson" "$mirror/.claude.json"

  # 2. curated skills dir — symlink only the chosen sources
  mkdir -p "$mirror/skills"
  local s
  while IFS= read -r s; do
    [[ -n "$s" && -d "$s" ]] && ln -s "$s" "$mirror/skills/$(basename "$s")"
  done < <(jq -r '.skills[]?' "$manifest")

  # 3. settings.json with enabledPlugins replaced by the manifest's set + env merged
  local base_settings="$rc/settings.json"
  [[ -f "$base_settings" ]] || base_settings=<(echo '{}')
  jq --slurpfile m "$manifest" '
      .enabledPlugins = ($m[0].plugins)
    | .env = ((.env // {}) + ($m[0].env // {}))
  ' "$base_settings" > "$mirror/settings.json"

  # 4. session CLAUDE.md = the pinned guardrails imports (lean; not the full global one)
  : > "$mirror/CLAUDE.md"
  local imp
  while IFS= read -r imp; do
    [[ -n "$imp" && -f "$imp" ]] && printf '@%s\n' "$imp" >> "$mirror/CLAUDE.md"
  done < <(jq -r '.imports[]?' "$manifest")

  # 5. credentials so auth survives the remapped config dir
  kog_materialize_creds "$mirror"

  echo "$mirror"
}

# Mirror a plugins dir per-entry, dropping .mcp.json from gated marketplaces so
# a plugin's skills/commands/hooks load but its bundled MCP servers never spawn.
# Args: $1=real plugins dir  $2=mirror plugins dir  $3=newline-separated plugin
# ids (name@marketplace) whose marketplace .mcp.json must be excluded.
kog_mirror_plugins() {
  local src="$1" dst="$2" gated="$3"
  mkdir -p "$dst"
  local e b
  for e in "$src"/* "$src"/.[!.]*; do
    [[ -e "$e" ]] || continue
    b="$(basename "$e")"
    [[ "$b" == "marketplaces" ]] && continue
    ln -s "$e" "$dst/$b"
  done
  [[ -d "$src/marketplaces" ]] || return 0
  mkdir -p "$dst/marketplaces"
  local m mb id hit p pb
  for m in "$src/marketplaces"/*; do
    [[ -e "$m" ]] || continue
    mb="$(basename "$m")"
    hit=""
    while IFS= read -r id; do
      [[ -n "$id" && "${id##*@}" == "$mb" ]] && hit=1
    done <<< "$gated"
    if [[ -z "$hit" ]]; then
      ln -s "$m" "$dst/marketplaces/$mb"
      continue
    fi
    mkdir -p "$dst/marketplaces/$mb"
    for p in "$m"/* "$m"/.[!.]*; do
      [[ -e "$p" ]] || continue
      pb="$(basename "$p")"
      [[ "$pb" == ".mcp.json" ]] && continue
      ln -s "$p" "$dst/marketplaces/$mb/$pb"
    done
  done
}

# Materialize auth into the mirror. API-key fast-path skips the keychain entirely.
kog_materialize_creds() {
  local mirror="$1"
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    return 0   # API-key auth: nothing to copy
  fi
  ( umask 077
    if security find-generic-password -s "Claude Code-credentials" -w \
         > "$mirror/.credentials.json" 2>/dev/null; then
      chmod 600 "$mirror/.credentials.json"
    else
      rm -f "$mirror/.credentials.json"
      echo "kit: warning — could not read Claude credentials from keychain;" >&2
      echo "     set ANTHROPIC_API_KEY or run 'claude /login' first." >&2
    fi )
}

# Remove the mirror (and the creds within). Safe to call repeatedly.
kog_cleanup() {
  local mirror="$1"
  [[ -n "$mirror" && "$mirror" == */kogitsune.* && -d "$mirror" ]] && rm -rf "$mirror"
}
