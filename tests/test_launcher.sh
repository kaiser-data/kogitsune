#!/usr/bin/env bash
# Hermetic integration tests for the bash launcher (bin/kit + lib/session-env.sh).
# No real claude / keychain / ~/.claude: everything is faked via PATH + env seams.
# Run: bash tests/test_launcher.sh   (exits non-zero if any assertion fails)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIX="$ROOT/tests/fixtures"
cd "$ROOT" || exit 1   # so the fixture's relative import path resolves
PASS=0; FAIL=0
ok(){ printf '  \033[32mok\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
no(){ printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
# GNU stat (-c) first: BSD/macOS stat rejects -c cleanly so the fallback runs;
# the reverse order is wrong because GNU `stat -f` *succeeds* with filesystem info.
perms(){ stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null; }
mirrors(){ find "$TMP" -maxdepth 1 -type d -name 'kogitsune.*' ! -name 'kogitsune.sel.*'; }
seldirs(){ find "$TMP" -maxdepth 1 -type d -name 'kogitsune.sel.*'; }
clean_tmp(){ find "$TMP" -maxdepth 1 -type d -name 'kogitsune.*' -exec rm -rf {} + 2>/dev/null; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"; mkdir -p "$BIN"
make_claude(){ # $1 = exit code
  cat > "$BIN/claude" <<EOF
#!/usr/bin/env bash
{ echo "CLAUDE_CONFIG_DIR=\${CLAUDE_CONFIG_DIR:-}"; echo "ARGS: \$*"; } > "$TMP/claude.log"
exit ${1:-0}
EOF
  chmod +x "$BIN/claude"; }
make_claude 0
cat > "$BIN/security" <<'EOF'
#!/usr/bin/env bash
echo '{"fake":"oauth-token"}'   # mimic keychain read
EOF
chmod +x "$BIN/security"

# fake ~/.claude with a stale plugin + env + skills we will override/preserve
HC="$TMP/home"; mkdir -p "$HC/skills" "$HC/plugins"
printf '{"enabledPlugins":{"stale@x":true},"permissions":{"allow":[]},"env":{"KEEPME":"1"}}\n' > "$HC/settings.json"
printf '@should-not-appear\n' > "$HC/CLAUDE.md"
printf '{"oauthAccount":{}}\n' > "$TMP/dotjson.json"

export PATH="$BIN:$PATH"
export KOGITSUNE_CONFIG="$FIX/kits.yaml"
export KOGITSUNE_MCP_ON_DEMAND="$FIX/mcp-on-demand.json"
export KOGITSUNE_SKILLS_DIR="$FIX/skills"
export KOGITSUNE_HOME_CONFIG="$HC"
export KOGITSUNE_HOME_DOTJSON="$TMP/dotjson.json"
export XDG_STATE_HOME="$TMP/state"
export TMPDIR="$TMP"

echo "== launch contract + cleanup =="
"$ROOT/bin/kit" db -- --model haiku "hi" >/dev/null 2>&1
grep -q "CLAUDE_CONFIG_DIR=$TMP/kogitsune" "$TMP/claude.log" && ok "CLAUDE_CONFIG_DIR points at a mirror" || no "CLAUDE_CONFIG_DIR not a mirror"
grep -q -- "--strict-mcp-config --mcp-config" "$TMP/claude.log" && ok "passes --strict-mcp-config --mcp-config" || no "missing strict mcp args"
grep -q -- "--model haiku hi" "$TMP/claude.log" && ok "forwards passthrough args" || no "passthrough args dropped"
[[ -z "$(mirrors)" ]] && ok "mirror cleaned up after launch (no exec leak)" || no "mirror LEAKED: $(mirrors)"
[[ -z "$(seldirs)" ]] && ok "selection dir cleaned up" || no "sel dir leaked: $(seldirs)"

echo "== mirror structure (inspect via KIT_DEBUG kept mirror) =="
KIT_DEBUG=1 "$ROOT/bin/kit" db >/dev/null 2>&1
MIR="$(mirrors | head -1)"
[[ -n "$MIR" ]] && ok "KIT_DEBUG keeps the mirror" || no "KIT_DEBUG should keep mirror"
[[ -L "$MIR/skills/graphify" ]] && ok "chosen skill symlinked (graphify)" || no "graphify not symlinked"
[[ $(ls "$MIR/skills" | wc -l) -eq 1 ]] && ok "only chosen skills present" || no "unexpected skills: $(ls "$MIR/skills")"
jq -e '.enabledPlugins["claude-mem@thedotmack"]==true' "$MIR/settings.json" >/dev/null && ok "memory plugin pinned" || no "memory plugin missing"
jq -e '.enabledPlugins["stale@x"]==null' "$MIR/settings.json" >/dev/null && ok "stale global plugin pruned" || no "stale plugin leaked"
jq -e '.env.KEEPME=="1"' "$MIR/settings.json" >/dev/null && ok "infra env preserved" || no "env not preserved"
grep -q "RULES.md" "$MIR/CLAUDE.md" && ok "guardrails import written to session CLAUDE.md" || no "guardrails missing"
! grep -q "should-not-appear" "$MIR/CLAUDE.md" && ok "global CLAUDE.md NOT carried (lean)" || no "global CLAUDE.md leaked"
[[ -f "$MIR/.credentials.json" ]] && ok "creds materialized (fake keychain)" || no "creds not written"
[[ "$(perms "$MIR/.credentials.json")" == "600" ]] && ok "creds file is mode 600" || no "creds perms = $(perms "$MIR/.credentials.json")"
[[ -L "$MIR/.claude.json" ]] && ok ".claude.json relocated into mirror" || no ".claude.json missing"
clean_tmp

echo "== ANTHROPIC_API_KEY fast-path skips creds =="
( export ANTHROPIC_API_KEY=test-key; KIT_DEBUG=1 "$ROOT/bin/kit" lean >/dev/null 2>&1 )
MIR="$(mirrors | head -1)"
[[ -n "$MIR" && ! -f "$MIR/.credentials.json" ]] && ok "no creds file when API key set" || no "creds written despite API key"
clean_tmp

echo "== exit-code propagation =="
make_claude 7
"$ROOT/bin/kit" lean >/dev/null 2>&1; rc=$?
[[ "$rc" -eq 7 ]] && ok "claude exit code propagated ($rc)" || no "exit code = $rc, expected 7"
make_claude 0
clean_tmp

echo "== completion helpers =="
ln -sf "$ROOT/bin/kit" "$BIN/kit"   # so completion's `kit __kits` resolves on PATH
"$BIN/kit" __kits 2>/dev/null | grep -qx "db" && ok "__kits lists kit names" || no "__kits missing 'db'"
# bash-completion smoke test: source the script and drive _kit
# shellcheck disable=SC1091
source "$ROOT/completions/kit.bash"
COMP_WORDS=(kit d); COMP_CWORD=1
_kit 2>/dev/null
printf '%s\n' "${COMPREPLY[@]:-}" | grep -qx "db" && ok "bash completion offers kit names" || no "completion missing 'db'"
COMP_WORDS=(kit db --); COMP_CWORD=2
_kit 2>/dev/null
printf '%s\n' "${COMPREPLY[@]:-}" | grep -qx -- "--strict" && ok "bash completion offers launch flags" || no "completion missing --strict"

echo "== kog_cleanup path safety =="
# shellcheck source=lib/session-env.sh
source "$ROOT/lib/session-env.sh"
mkdir -p "$TMP/not-a-mirror"
kog_cleanup "$TMP/not-a-mirror"
[[ -d "$TMP/not-a-mirror" ]] && ok "cleanup refuses a non-kogitsune path" || no "cleanup DELETED a non-mirror path!"

echo
echo "launcher tests: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
