#!/usr/bin/env bash
# decider.sh — deterministic datastore + versioning spine for the kogitsune
# kit-scout / kit-selector / kit-builder skills. All judgment lives in the skills;
# this handles append-only logging, version resolution, and distillation only.
#
#   append-decision <json>   append a selector gold-label; prints its Dxxx id
#   append-build <json>      append a builder outcome; prints its Bxxx id
#   write-context <json>     write scout context snapshot; prints context.vN.json path
#   distill                  aggregate decisions.jsonl -> new router.vN.json; prints path
#   latest {router|context}  print path of highest existing version (empty if none)
#   next-version {router|context}  print the next integer version
#   stats                    counts + current versions
#
# Datastore dir: $KOG_DECIDER_DIR (default: <repo>/decisions).
set -euo pipefail

DIR="${KOG_DECIDER_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/decisions}"
mkdir -p "$DIR" "$DIR/context"
DEC="$DIR/decisions.jsonl"
BLD="$DIR/builds.jsonl"

die(){ echo "decider: $*" >&2; exit 1; }
need_jq(){ command -v jq >/dev/null 2>&1 || die "jq required"; }

kind_path(){ # kind version -> path
  case "$1" in
    router)  echo "$DIR/router.v$2.json" ;;
    context) echo "$DIR/context/context.v$2.json" ;;
    *) die "unknown kind: $1" ;;
  esac
}

highest_version(){ # kind -> highest integer version present (0 if none)
  local kind="$1" max=0 f n
  case "$kind" in
    router)  set -- "$DIR"/router.v*.json ;;
    context) set -- "$DIR"/context/context.v*.json ;;
    *) die "unknown kind: $kind" ;;
  esac
  for f in "$@"; do
    [[ -e "$f" ]] || continue
    n="${f##*.v}"; n="${n%.json}"
    [[ "$n" =~ ^[0-9]+$ ]] && (( n > max )) && max=$n
  done
  echo "$max"
}

next_id(){ # prefix file -> zero-padded next id
  local n=0
  [[ -f "$2" ]] && n=$(wc -l < "$2" | tr -d ' ')
  printf '%s%03d' "$1" "$((n+1))"
}

cmd_append_decision(){
  need_jq
  local json="${1:-}"
  printf '%s' "$json" | jq -e . >/dev/null 2>&1 || die "invalid json"
  local given id
  given="$(printf '%s' "$json" | jq -r '.id // empty')"
  id="${given:-$(next_id D "$DEC")}"
  printf '%s' "$json" | jq -c --arg id "$id" '.id = $id' >> "$DEC"
  echo "$id"
}

cmd_append_build(){
  need_jq
  local json="${1:-}"
  printf '%s' "$json" | jq -e . >/dev/null 2>&1 || die "invalid json"
  local given id
  given="$(printf '%s' "$json" | jq -r '.id // empty')"
  id="${given:-$(next_id B "$BLD")}"
  printf '%s' "$json" | jq -c --arg id "$id" '.id = $id' >> "$BLD"
  echo "$id"
}

cmd_write_context(){
  need_jq
  local json="${1:-}"
  printf '%s' "$json" | jq -e . >/dev/null 2>&1 || die "invalid json"
  local v out; v="$(( $(highest_version context) + 1 ))"; out="$(kind_path context "$v")"
  printf '%s' "$json" | jq -c --argjson v "$v" '.version = $v' > "$out"
  echo "$out"
}

cmd_distill(){
  need_jq
  [[ -s "$DEC" ]] || die "no decisions to distill"
  local v out; v="$(( $(highest_version router) + 1 ))"; out="$(kind_path router "$v")"
  jq -s --argjson v "$v" '
    { version: $v,
      built_from: { decisions: length },
      rules: ( group_by(.decision.kit)
        | map({ kit: .[0].decision.kit,
                signals_any: ([ .[].signals[]? ] | unique),
                support: length })
        | sort_by(-.support) )
    }' "$DEC" > "$out"
  echo "$out"
}

cmd_latest(){ # kind
  local v; v="$(highest_version "$1")"
  [[ "$v" == 0 ]] && return 0
  kind_path "$1" "$v"
}

cmd_stats(){
  local dn=0 bn=0
  [[ -f "$DEC" ]] && dn=$(wc -l < "$DEC" | tr -d ' ')
  [[ -f "$BLD" ]] && bn=$(wc -l < "$BLD" | tr -d ' ')
  echo "decisions: $dn"
  echo "builds:    $bn"
  echo "router:    v$(highest_version router)"
  echo "context:   v$(highest_version context)"
}

case "${1:-}" in
  append-decision) shift; cmd_append_decision "${1:-}" ;;
  append-build)    shift; cmd_append_build "${1:-}" ;;
  write-context)   shift; cmd_write_context "${1:-}" ;;
  distill)         cmd_distill ;;
  latest)          shift; cmd_latest "${1:-}" ;;
  next-version)    shift; echo "$(( $(highest_version "${1:-}") + 1 ))" ;;
  stats)           cmd_stats ;;
  *) die "usage: decider {append-decision|append-build|write-context|distill|latest KIND|next-version KIND|stats}" ;;
esac
