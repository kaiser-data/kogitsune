#!/usr/bin/env bash
# kogitsune — measure every catalog item's real marginal weight.
#
# The `weight:` hints in kits.yaml were hand-entered estimates. This sweep replaces
# guesswork with measurement: probe the empty selection once for a floor, then probe
# the floor plus exactly one item, and report the difference. Nothing reaches the
# API — each probe is answered by lib/measure-proxy.py.
#
#   lib/weight-sweep.sh                  # every catalog item, on haiku
#   lib/weight-sweep.sh --probe-model opus
#   lib/weight-sweep.sh --only supabase,ecc
#
# Emits a table plus a `catalog-weights.json` for review before editing kits.yaml.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
KIT="$ROOT/bin/kit"
PROBE_MODEL="haiku"
ONLY=""
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --probe-model) PROBE_MODEL="${2:?}"; shift 2 ;;
    --only)        ONLY="${2:?}"; shift 2 ;;
    --out)         OUT="${2:?}"; shift 2 ;;
    -h|--help)     sed -n '2,14p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "weight-sweep: unknown arg $1" >&2; exit 2 ;;
  esac
done
[[ -n "$OUT" ]] || OUT="${XDG_STATE_HOME:-$HOME/.local/state}/kogitsune/catalog-weights.json"

# Total measured tokens for one selection. $1=--mcp|--skills $2=item.
# Called with no args for the floor — an explicitly empty selection, which still
# needs a selection flag so the launcher treats it as ad-hoc rather than no input.
probe_total() {
  local flag="${1:---mcp}" item="${2:-}"
  "$KIT" measure --proxy --probe-model "$PROBE_MODEL" --json "$flag" "$item" \
    2>/dev/null | jq -r '.totals.total_tokens // empty'
}

wanted() {  # $1=item -> 0 if it should be measured
  [[ -z "$ONLY" ]] && return 0
  case ",$ONLY," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}

# Does this selection resolve? An uninstalled item measures as 0 — indistinguishable
# from a genuinely free one, and copying that 0 into kits.yaml would be a real error.
# $1=--mcp|--skills $2=item
resolves() {
  local w
  w="$(python3 "$ROOT/lib/build-config.py" --config "${KOGITSUNE_CONFIG:-$ROOT/kits.yaml}" \
        --mcp-on-demand "${KOGITSUNE_MCP_ON_DEMAND:-$HOME/.claude/mcp-on-demand.json}" \
        "$1" "$2" --dry-run 2>/dev/null | jq -r '.warnings | length')"
  [[ "$w" == "0" ]]
}

echo "kit: sweeping catalog weights on '$PROBE_MODEL' (no API calls)…" >&2

# The floor is an empty selection: pinned set + base harness, no catalog item. Every
# item's weight is measured against this same floor so the numbers are comparable.
FLOOR="$(probe_total)"
[[ "$FLOOR" =~ ^[0-9]+$ ]] || { echo "weight-sweep: could not measure the floor" >&2; exit 1; }
echo "   floor (pinned + base harness) = ${FLOOR} tok" >&2
echo

catalog_json="$(python3 "$ROOT/lib/build-config.py" \
  --config "${KOGITSUNE_CONFIG:-$ROOT/kits.yaml}" \
  --mcp-on-demand "${KOGITSUNE_MCP_ON_DEMAND:-$HOME/.claude/mcp-on-demand.json}" --list)"

printf '%-20s %-8s %10s %10s %9s\n' ITEM KIND MEASURED DECLARED DELTA
printf '%s\n' "────────────────────────────────────────────────────────────"

results="[]"
for kind in mcp skills; do
  flag="--mcp"; [[ "$kind" == skills ]] && flag="--skills"
  while IFS= read -r item; do
    [[ -n "$item" ]] || continue
    wanted "$item" || continue
    declared="$(echo "$catalog_json" | jq -r --arg k "$kind" --arg i "$item" \
      '.[$k][$i].weight // 0')"
    if ! resolves "$flag" "$item"; then
      printf '%-20s %-8s %10s %10s %9s\n' "$item" "$kind" "n/a" "$declared" "unresolved"
      results="$(echo "$results" | jq --arg i "$item" --arg k "$kind" --argjson d "$declared" \
        '. + [{item:$i, kind:$k, measured:null, declared:$d, unresolved:true}]')"
      continue
    fi
    total="$(probe_total "$flag" "$item")"
    if ! [[ "$total" =~ ^[0-9]+$ ]]; then
      printf '%-20s %-8s %10s %10s %9s\n' "$item" "$kind" "ERR" "$declared" "-"
      continue
    fi
    measured=$((total - FLOOR)); ((measured < 0)) && measured=0
    delta=$((measured - declared))
    printf '%-20s %-8s %10s %10s %+9d\n' "$item" "$kind" "$measured" "$declared" "$delta"
    results="$(echo "$results" | jq --arg i "$item" --arg k "$kind" \
      --argjson m "$measured" --argjson d "$declared" \
      '. + [{item:$i, kind:$k, measured:$m, declared:$d}]')"
  done < <(echo "$catalog_json" | jq -r --arg k "$kind" '.[$k] // {} | keys[]')
done

mkdir -p "$(dirname "$OUT")"
echo "$results" | jq --argjson f "$FLOOR" --arg m "$PROBE_MODEL" \
  '{probe_model:$m, floor:$f, items:.}' > "$OUT"
echo
echo "wrote $OUT — review before editing kits.yaml weights." >&2
