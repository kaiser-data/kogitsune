#!/usr/bin/env bash
# Spike re-run: fix variadic --mcp-config swallowing the prompt; capture per-probe stderr.
set -uo pipefail
REAL_HOME_CFG="$HOME/.claude"; REAL_DOTJSON="$HOME/.claude.json"
PROMPT='Reply with exactly the single token: PONG'; MODEL="haiku"
HR(){ printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ctx(){ jq -r '(.usage//{})|((.input_tokens//0)+(.cache_creation_input_tokens//0)+(.cache_read_input_tokens//0))' 2>/dev/null; }

# IMPORTANT: prompt FIRST, then flags — so variadic --mcp-config can't eat the prompt.
run(){ local label="$1"; shift
  local out; out="$(claude -p --output-format=json --model "$MODEL" "$PROMPT" "$@" 2>"/tmp/kog_${label}.err")"; local rc=$?
  echo "$out">"/tmp/kog_${label}.json"
  if [[ $rc -ne 0 || -z "$out" ]]; then echo "  [$label] FAILED rc=$rc"; sed 's/^/    /' "/tmp/kog_${label}.err"|head -10; return 1; fi
  if echo "$out"|jq -e '(.is_error|not) and (.result!=null)'>/dev/null 2>&1; then
    echo "  [$label] OK  ctx=$(echo "$out"|ctx) tokens  result=$(echo "$out"|jq -r .result|head -c 30)"
  else echo "  [$label] is_error:"; echo "$out"|jq -r '{is_error,subtype,result}' 2>/dev/null|sed 's/^/    /'; fi; }

HR "Q1a  empty CLAUDE_CONFIG_DIR (real error this time)"
EMPTY="$(mktemp -d /tmp/kog_empty.XXXXXX)"; ( export CLAUDE_CONFIG_DIR="$EMPTY"; run empty )

HR "Q1b+Q3  curated mirror, prompt-first ordering"
MIRROR="$(mktemp -d /tmp/kog_mirror.XXXXXX)"
for e in "$REAL_HOME_CFG"/* "$REAL_HOME_CFG"/.[!.]*; do [[ -e "$e" ]]||continue; b="$(basename "$e")"
  case "$b" in skills|settings.json) continue;; *) ln -s "$e" "$MIRROR/$b";; esac; done
[[ -e "$REAL_DOTJSON" ]] && ln -s "$REAL_DOTJSON" "$MIRROR/.claude.json"
mkdir -p "$MIRROR/skills"; [[ -e "$REAL_HOME_CFG/skills/graphify" ]] && ln -s "$REAL_HOME_CFG/skills/graphify" "$MIRROR/skills/graphify"
jq '(.enabledPlugins//{}) as $ep|.enabledPlugins=($ep|to_entries|map(select(.key|test("claude-mem";"i")))|from_entries)' \
   "$REAL_HOME_CFG/settings.json">"$MIRROR/settings.json"
echo "  mirror=$MIRROR  plugins=$(jq -c .enabledPlugins "$MIRROR/settings.json")  skills=$(ls "$MIRROR/skills"|tr '\n' ' ')"
( export CLAUDE_CONFIG_DIR="$MIRROR"; run mirror --strict-mcp-config --mcp-config '{"mcpServers":{}}' )

HR "SUMMARY"
b=24154; m=$(ctx</tmp/kog_mirror.json 2>/dev/null); m=${m:-?}
echo "  baseline=$b  mirror=$m"
[[ "$m" =~ ^[0-9]+$ ]] && echo "  savings=$((b-m)) tokens ($(( (b-m)*100/b ))%)"
echo "  mirror dir: $MIRROR  empty dir: $EMPTY"
