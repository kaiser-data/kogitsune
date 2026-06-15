#!/usr/bin/env bash
# kogitsune spike — validate the "curated mirror" CLAUDE_CONFIG_DIR isolation strategy.
# Answers 3 questions, non-destructively, measuring real token deltas:
#   1. Does auth survive a remapped CLAUDE_CONFIG_DIR (keychain + ~/.claude.json)?
#   2. Does claude-mem (memory) still ride along under pruned enabledPlugins?
#   3. Do only chosen skills load, and does the lean kit measurably cut tokens?
#
# Uses --model haiku for cheap/fast probes. Reads usage from --output-format=json.
set -uo pipefail

REAL_HOME_CFG="$HOME/.claude"
REAL_DOTJSON="$HOME/.claude.json"
PROMPT='Reply with exactly the single token: PONG'
MODEL="haiku"
HR() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# Sum the context actually fed to the model: fresh input + cache create + cache read.
ctx_tokens() { # reads json on stdin
  jq -r '(.usage // {}) | ((.input_tokens//0)+(.cache_creation_input_tokens//0)+(.cache_read_input_tokens//0))' 2>/dev/null
}
result_ok() { jq -e '(.is_error|not) and (.result != null)' >/dev/null 2>&1; }

run_claude() { # $1=label  $@rest=extra args ; uses global CFG override via env if set
  local label="$1"; shift
  local out
  out="$(claude -p --output-format=json --model "$MODEL" "$@" "$PROMPT" 2>/tmp/kog_spike_err)"
  local rc=$?
  echo "$out" > "/tmp/kog_spike_${label}.json"
  if [[ $rc -ne 0 || -z "$out" ]]; then
    echo "  [$label] FAILED rc=$rc  stderr:"; sed 's/^/    /' /tmp/kog_spike_err | head -8
    return 1
  fi
  if echo "$out" | result_ok; then
    echo "  [$label] OK  ctx=$(echo "$out" | ctx_tokens) tokens  result=$(echo "$out" | jq -r '.result' | head -c 40)"
  else
    echo "  [$label] ran but is_error/empty:"; echo "$out" | jq -r '{is_error,subtype,result}' 2>/dev/null | sed 's/^/    /'
  fi
}

# ---------------------------------------------------------------------------
HR "Q0  baseline: normal launch (full config) — establishes the 'before' number"
run_claude baseline

# ---------------------------------------------------------------------------
HR "Q1a  empty CLAUDE_CONFIG_DIR — does auth survive with NOTHING carried over?"
EMPTY="$(mktemp -d /tmp/kog_empty.XXXXXX)"
( export CLAUDE_CONFIG_DIR="$EMPTY"; run_claude empty )
echo "  (if this failed with auth/onboarding, a clean slate needs auth reconstruction)"

# ---------------------------------------------------------------------------
HR "Q1b+Q3  curated mirror — symlink ~/.claude, override skills/ + settings.json"
MIRROR="$(mktemp -d /tmp/kog_mirror.XXXXXX)"
# symlink every ~/.claude entry except the two we override
for entry in "$REAL_HOME_CFG"/* "$REAL_HOME_CFG"/.[!.]*; do
  [[ -e "$entry" ]] || continue
  base="$(basename "$entry")"
  case "$base" in
    skills|settings.json) continue ;;
    *) ln -s "$entry" "$MIRROR/$base" ;;
  esac
done
# ~/.claude.json lives at $HOME — relocate via symlink into the mirror root
[[ -e "$REAL_DOTJSON" ]] && ln -s "$REAL_DOTJSON" "$MIRROR/.claude.json"
# curated skills dir: only the pinned 'graphify'
mkdir -p "$MIRROR/skills"
[[ -e "$REAL_HOME_CFG/skills/graphify" ]] && ln -s "$REAL_HOME_CFG/skills/graphify" "$MIRROR/skills/graphify"
# settings.json with enabledPlugins pruned to claude-mem only
if [[ -e "$REAL_HOME_CFG/settings.json" ]]; then
  jq '(.enabledPlugins // {}) as $ep
      | .enabledPlugins = ($ep | to_entries | map(select(.key|test("claude-mem";"i"))) | from_entries)' \
     "$REAL_HOME_CFG/settings.json" > "$MIRROR/settings.json"
fi
echo "  mirror at $MIRROR"
echo "  enabledPlugins after prune: $(jq -c '.enabledPlugins' "$MIRROR/settings.json" 2>/dev/null)"
echo "  skills visible in mirror:  $(ls "$MIRROR/skills" 2>/dev/null | tr '\n' ' ')"

# launch under mirror, with strict MCP = none, to measure the lean floor
( export CLAUDE_CONFIG_DIR="$MIRROR"
  run_claude mirror --strict-mcp-config --mcp-config '{"mcpServers":{}}' )

# ---------------------------------------------------------------------------
HR "Q2  did claude-mem hooks fire under the mirror? (look for memory SessionStart context)"
( export CLAUDE_CONFIG_DIR="$MIRROR"
  claude -p --model "$MODEL" --output-format=stream-json --include-hook-events --verbose \
    'reply: ok' 2>/dev/null | jq -rc 'select(.type=="system" or (.hook_event_name//empty)!="") | {t:.type, hook:.hook_event_name, sub:.subtype}' 2>/dev/null | head -20 ) \
  || echo "  (stream probe inconclusive — will verify memory round-trip manually)"

# ---------------------------------------------------------------------------
HR "SUMMARY"
b=$(ctx_tokens < /tmp/kog_spike_baseline.json 2>/dev/null); b=${b:-?}
m=$(ctx_tokens < /tmp/kog_spike_mirror.json 2>/dev/null); m=${m:-?}
echo "  baseline ctx tokens : $b"
echo "  lean mirror ctx     : $m"
if [[ "$b" =~ ^[0-9]+$ && "$m" =~ ^[0-9]+$ && "$b" -gt 0 ]]; then
  echo "  savings             : $(( b - m )) tokens  ($(( (b-m)*100/b ))%)"
fi
echo
echo "  artifacts: /tmp/kog_spike_*.json   mirror: $MIRROR   empty: $EMPTY"
echo "  (dirs left in /tmp for inspection; rm -rf them when done)"
