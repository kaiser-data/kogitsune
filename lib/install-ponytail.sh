#!/usr/bin/env bash
# kogitsune 🦊 — install DietrichGebert/ponytail for use in kits.
#
# ponytail is a "lazy senior dev" nudge: YAGNI, stdlib first, no unrequested
# abstractions — it biases the agent toward the smallest change that works.
#
# Unlike a defer-until-invoked skill, ponytail ships three always-on Node
# lifecycle hooks (SessionStart / SubagentStart / UserPromptSubmit) that inject
# their instructions every session AND into every subagent. That makes it a
# standing cost (measured ~1,450 tok, all hook output), so kogitsune keeps it
# OFF globally and lets kits opt in — see `install_kit_only` below and the
# `ponytail` catalog entry in kits.yaml (used by the `build`/`feature` kits).
#
# Usage: bash lib/install-ponytail.sh [plugin|kit-only|all]   (default: all)
set -euo pipefail

MODE="${1:-all}"
MARKET="DietrichGebert/ponytail"       # `claude plugin marketplace add` source
PLUGIN="ponytail@ponytail"             # plugin@marketplace id
SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"

die() { echo "install-ponytail: $*" >&2; exit 1; }

install_plugin() {
  command -v claude >/dev/null 2>&1 || die "missing dependency: claude"
  # NOTE: brace every expansion followed by a multi-byte char (…, →). Under bash 3.2
  # the ellipsis bytes get parsed into the identifier -> "PLUGIN…: unbound variable".
  echo "🦊 installing ${PLUGIN} (marketplace ${MARKET})…"
  # marketplace add is idempotent-ish; tolerate an 'already added' non-zero exit
  claude plugin marketplace add "$MARKET" || true
  claude plugin install "$PLUGIN"
  echo "  ✔ installed $PLUGIN — the 'ponytail' catalog entry now resolves"
}

# Flip the plugin off in the *global* settings so its hooks don't tax every
# session. Kit sessions override enabledPlugins with the kit's own plugin set,
# so `build`/`feature` still get it; everything else stops paying for it.
install_kit_only() {
  command -v python3 >/dev/null 2>&1 || die "missing dependency: python3"
  [[ -f "$SETTINGS" ]] || die "settings not found: $SETTINGS"
  PLUGIN="$PLUGIN" python3 - "$SETTINGS" <<'PY'
import json, os, sys
path, plugin = sys.argv[1], os.environ["PLUGIN"]
with open(path) as fh:
    settings = json.load(fh)
enabled = settings.setdefault("enabledPlugins", {})
if enabled.get(plugin) is False:
    print(f"  • {plugin} already kit-only (globally disabled)")
    sys.exit(0)
enabled[plugin] = False
with open(path, "w") as fh:
    json.dump(settings, fh, indent=2)
    fh.write("\n")
print(f"  ✔ {plugin} disabled globally — kits that list it still enable it")
PY
}

case "$MODE" in
  plugin)   install_plugin ;;
  kit-only) install_kit_only ;;
  all)      install_plugin; install_kit_only ;;
  *)        die "usage: $0 [plugin|kit-only|all]" ;;
esac
