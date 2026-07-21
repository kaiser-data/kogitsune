#!/usr/bin/env bash
# decider.sh — deterministic datastore + versioning spine for the kogitsune
# kit-scout / kit-selector / kit-builder skills. All judgment lives in the skills;
# this handles append-only logging, version resolution, and distillation only.
#
#   append-decision <json>   append a selector gold-label; prints its Dxxx id
#   append-build <json>      append a builder outcome; prints its Bxxx id
#   write-context <json>     write scout context snapshot; prints context.vN.json path
#   normalize <text>         canonical signal tokens for text, one per line
#   distill                  aggregate decisions.jsonl -> new router.vN.json; prints path
#   match <task>             best kit from the latest router (exit 1 = cold path)
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

# ---- canonical signal vocabulary -------------------------------------------
# Deciders phrase signals however they like ("auth/security-sensitive", "explicit
# tests -> TDD"). The router can only aggregate what it can compare, so every
# signal is folded onto this fixed vocabulary before it reaches a rule. This is a
# lookup table, not judgment: rows are "token|pattern|pattern|...", and patterns
# are plain substrings tested against the lowercased, punctuation-stripped,
# space-padded text. Wrap a pattern in spaces to force a whole-word match — " test"
# keeps "latest" from reading as a testing signal.
SIGNAL_VOCAB='auth| auth|authentic|jwt|oauth|login|credential|password
security|security|secure|vulnerab|crypto|secret|injection| xss | csrf |sanitiz
testing| test|tdd|coverage
docs| doc | docs |documentation|readme|changelog| comment
performance|perf|latency|optimi|throughput|bottleneck|profil| slow
refactor|refactor|clean up|cleanup|rename|restructure|dead code|simplif
bugfix| bug | fix |defect|broken|crash|regression
feature|feature|implement|add support|new endpoint
multi-file|multi file|multifile|cross file|project wide|multiple files|several files
single-file|single file|one file
trivial|trivial|typo|tiny|one liner| minor | nit
python|python| py |django|flask|fastapi|pytest
typescript|typescript| ts | tsx |react| node | npm |javascript| js |vue
go|golang| go |goroutine
rust|rust|cargo|clippy
shell|bash| shell |zsh|shellcheck'

normalize_text(){ # text -> canonical tokens, one per line, sorted + deduped
  local s row tok pats pat
  s="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' ' ' | tr -s ' ')"
  s=" $s "
  while IFS= read -r row; do
    [[ -n "$row" ]] || continue
    tok="${row%%|*}"; pats="${row#*|}"
    while [[ -n "$pats" ]]; do
      pat="${pats%%|*}"
      if [[ "$pats" == *"|"* ]]; then pats="${pats#*|}"; else pats=""; fi
      if [[ "$s" == *"$pat"* ]]; then echo "$tok"; break; fi
    done
  done <<< "$SIGNAL_VOCAB" | sort -u
}

tokens_json(){ # text -> compact JSON array of canonical tokens
  normalize_text "$1" | jq -R . | jq -s -c .
}

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

cmd_normalize(){ normalize_text "${1:-}"; }

cmd_distill(){
  need_jq
  [[ -s "$DEC" ]] || die "no decisions to distill"
  local v out tmp kit launch raw conf
  v="$(( $(highest_version router) + 1 ))"; out="$(kind_path router "$v")"
  tmp="$(mktemp "${TMPDIR:-/tmp}/decider.distill.XXXXXX")"
  # Canonicalize each decision's signals first, so rules key on the shared
  # vocabulary rather than on whatever phrasing the decider happened to use.
  # Decisions that never named a launchable kit (bespoke à-la-carte compositions,
  # architecture calls) are skipped — the router's job is to name a kit to launch.
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    kit="$(printf '%s' "$line" | jq -r '.decision.kit // empty')"
    launch="$(printf '%s' "$line" | jq -r '.decision.launch // empty')"
    [[ -n "$kit" && "$kit" != "custom" ]] || continue
    case "$launch" in n/a*) continue ;; esac
    raw="$(printf '%s' "$line" | jq -r '[.signals[]?] | join(" ")')"
    # an unstated or malformed confidence is treated as middling, never as certain
    conf="$(printf '%s' "$line" \
      | jq -r 'if (.confidence|type) == "number" then .confidence else 0.5 end')"
    jq -n -c --arg kit "$kit" --argjson sig "$(tokens_json "$raw")" --argjson conf "$conf" \
      '{kit:$kit, signals:$sig, confidence:$conf}' >> "$tmp"
  done < "$DEC"
  jq -s --argjson v "$v" '
    { version: $v,
      built_from: { decisions: length },
      rules: ( group_by(.kit)
        | map({ kit: .[0].kit,
                signals_any: ([ .[].signals[]? ] | unique),
                support: length,
                weight: ([ .[].confidence ] | add | . * 1000 | round / 1000) })
        | map(select(.signals_any | length > 0))
        | sort_by([-.weight, -.support]) )
    }' "$tmp" > "$out"
  rm -f "$tmp"
  echo "$out"
}

cmd_match(){ # task -> best kit from the latest router; exit 1 when nothing overlaps
  need_jq
  local task="${1:-}" router toks kit
  [[ -n "$task" ]] || die "usage: decider match \"<task>\""
  router="$(cmd_latest router)"
  [[ -n "$router" && -f "$router" ]] || return 1
  toks="$(tokens_json "$task")"
  [[ "$toks" != "[]" ]] || return 1
  # Most overlapping signals wins. Ties break on weight (summed confidence) rather
  # than raw count, so a stream of hesitant picks can't bury a confident one; then
  # on support, then kit name so the same task always routes the same way.
  # `.weight // .support` keeps pre-v3 routers, which had no weight, readable.
  kit="$(jq -r --argjson t "$toks" '
    [ .rules[]
      | { kit, support, weight: (.weight // .support // 0),
          overlap: ([ .signals_any[] | select(. as $s | $t | index($s)) ] | length) }
      | select(.overlap > 0) ]
    | sort_by([-.overlap, -.weight, -.support, .kit])
    | (.[0].kit // empty)' "$router")"
  [[ -n "$kit" ]] || return 1
  echo "$kit"
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
  normalize)       shift; cmd_normalize "${1:-}" ;;
  distill)         cmd_distill ;;
  match)           shift; cmd_match "${1:-}" ;;
  latest)          shift; cmd_latest "${1:-}" ;;
  next-version)    shift; echo "$(( $(highest_version "${1:-}") + 1 ))" ;;
  stats)           cmd_stats ;;
  *) die "usage: decider {append-decision|append-build|write-context|normalize|distill|match|latest KIND|next-version KIND|stats}" ;;
esac
