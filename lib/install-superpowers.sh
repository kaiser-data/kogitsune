#!/usr/bin/env bash
# kogitsune 🦊 — install obra/superpowers for use in kits, in either (or both) mode:
#
#   plugin  — Mode A: add the marketplace + install the plugin. Full methodology PLUS
#             its SessionStart dispatcher hook (an always-on nudge). Used by the `build`
#             kit via the `superpowers` catalog entry (plugin: superpowers@superpowers-dev).
#   skills  — Mode B: git clone the repo into the vendor dir. The `sp` catalog entry then
#             pulls skills/* by dir glob — same skills, WITHOUT the hook, triggered on
#             demand. Leaner. Used by the `flow` and `feature` kits.
#
# Usage: bash lib/install-superpowers.sh [plugin|skills|all]   (default: all)
set -euo pipefail

MODE="${1:-all}"
REPO_URL="https://github.com/obra/superpowers"
MARKET="obra/superpowers"                       # `claude plugin marketplace add` source
PLUGIN="superpowers@superpowers-dev"            # plugin@marketplace id
VENDOR="${KOGITSUNE_VENDOR:-$HOME/.claude/_vendor}/superpowers"

die() { echo "install-superpowers: $*" >&2; exit 1; }

install_plugin() {
  command -v claude >/dev/null 2>&1 || die "missing dependency: claude"
  # NOTE: brace every expansion followed by a multi-byte char (…, →). Under bash 3.2
  # the ellipsis bytes get parsed into the identifier -> "PLUGIN…: unbound variable".
  echo "🦊 Mode A (plugin): adding marketplace + installing ${PLUGIN}…"
  # marketplace add is idempotent-ish; tolerate an 'already added' non-zero exit
  claude plugin marketplace add "$MARKET" || true
  claude plugin install "$PLUGIN"
  echo "  ✔ installed $PLUGIN — the 'build' kit's superpowers entry now resolves"
}

install_skills() {
  command -v git >/dev/null 2>&1 || die "missing dependency: git"
  if [[ -d "$VENDOR/.git" ]]; then
    echo "🦊 Mode B (skills): updating ${VENDOR}…"
    git -C "$VENDOR" pull --ff-only -q || echo "  • pull skipped (local changes?) — using existing clone"
  else
    echo "🦊 Mode B (skills): cloning ${REPO_URL} → ${VENDOR}…"
    mkdir -p "$(dirname "$VENDOR")"
    git clone --depth 1 "$REPO_URL" "$VENDOR"
  fi
  local n
  n="$(find "$VENDOR/skills" -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$n" -gt 0 ]] || die "no skills found under $VENDOR/skills — repo layout changed?"
  echo "  ✔ $n superpowers skills available via the 'sp' catalog entry (flow / feature kits)"
}

case "$MODE" in
  plugin) install_plugin ;;
  skills) install_skills ;;
  all)    install_plugin; install_skills ;;
  *)      die "usage: $0 [plugin|skills|all]" ;;
esac
