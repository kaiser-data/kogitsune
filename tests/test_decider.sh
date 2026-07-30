#!/usr/bin/env bash
# Tests for skills/lib/decider.sh — deterministic datastore + versioning spine
# behind kit-scout / kit-selector / kit-builder. Hermetic: throwaway dir per run.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DECIDER="$ROOT/skills/lib/decider.sh"
pass=0; fail=0
ok(){ printf '  \033[32mok\033[0m  %s\n' "$1"; pass=$((pass+1)); }
no(){ printf '  \033[31mFAIL\033[0m  %s\n    %s\n' "$1" "${2:-}"; fail=$((fail+1)); }
newdir(){ mktemp -d "${TMPDIR:-/tmp}/decider.XXXXXX"; }

echo "== decider: append-decision =="
D="$(newdir)"
id="$(KOG_DECIDER_DIR="$D" "$DECIDER" append-decision '{"task":"fix typo","decision":{"kit":"lean"},"signals":["typo","docs-only"]}' 2>/dev/null)"
[[ "$id" == D* ]] && ok "append-decision returns a Dxxx id" || no "append-decision returns a Dxxx id" "got: '$id'"
lines="$(wc -l < "$D/decisions.jsonl" 2>/dev/null | tr -d ' ')"
[[ "$lines" == "1" ]] && ok "decision appended as one jsonl line" || no "decision appended as one jsonl line" "lines: $lines"
KOG_DECIDER_DIR="$D" "$DECIDER" append-decision 'not json {{' >/dev/null 2>&1 \
  && no "invalid json is rejected" "exit 0 on garbage" || ok "invalid json is rejected"

echo "== decider: append-build =="
bid="$(KOG_DECIDER_DIR="$D" "$DECIDER" append-build '{"task":"fix typo","built":{"kit":"lean"},"success":true}' 2>/dev/null)"
[[ "$bid" == B* ]] && ok "append-build returns a Bxxx id" || no "append-build returns a Bxxx id" "got: '$bid'"

echo "== decider: distill -> versioned router =="
r1="$(KOG_DECIDER_DIR="$D" "$DECIDER" distill 2>/dev/null)"
[[ -f "$r1" && "$r1" == *router.v1.json ]] && ok "first distill writes router.v1.json" || no "first distill writes router.v1.json" "got: '$r1'"
KOG_DECIDER_DIR="$D" "$DECIDER" append-decision '{"task":"jwt auth tests","decision":{"kit":"build"},"signals":["auth","tests"]}' >/dev/null 2>&1
r2="$(KOG_DECIDER_DIR="$D" "$DECIDER" distill 2>/dev/null)"
[[ "$r2" == *router.v2.json ]] && ok "second distill bumps to router.v2.json" || no "second distill bumps to router.v2.json" "got: '$r2'"
if command -v jq >/dev/null 2>&1; then
  kit="$(jq -r '.rules[] | select(.signals_any | index("auth")) | .kit' "$r2" 2>/dev/null | head -1)"
  [[ "$kit" == "build" ]] && ok "router maps signal 'auth' -> build" || no "router maps signal 'auth' -> build" "got: '$kit'"
fi

echo "== decider: latest resolves highest version =="
latest="$(KOG_DECIDER_DIR="$D" "$DECIDER" latest router 2>/dev/null)"
[[ "$latest" == *router.v2.json ]] && ok "latest router = v2" || no "latest router = v2" "got: '$latest'"

echo "== decider: stats =="
st="$(KOG_DECIDER_DIR="$D" "$DECIDER" stats 2>/dev/null)"
case "$st" in *"decisions:"*) ok "stats reports decisions";; *) no "stats reports decisions" "$st";; esac

echo "== decider: normalize -> canonical signal vocabulary =="
norm(){ KOG_DECIDER_DIR="$D" "$DECIDER" normalize "$1" 2>/dev/null | tr '\n' ' '; }
has(){ case " $1 " in *" $2 "*) return 0;; *) return 1;; esac; }

n="$(norm 'auth/security-sensitive')"
{ has "$n" auth && has "$n" security; } \
  && ok "verbose phrase splits into canonical tokens" \
  || no "verbose phrase splits into canonical tokens" "got: '$n'"

n="$(norm 'explicit tests -> TDD')"
has "$n" testing && ok "'tests'/'TDD' collapse to one 'testing' token" \
  || no "'tests'/'TDD' collapse to one 'testing' token" "got: '$n'"

n="$(norm 'PYTHON')"
has "$n" python && ok "normalize is case-insensitive" || no "normalize is case-insensitive" "got: '$n'"

n="$(norm 'fix a typo in the README')"
{ has "$n" trivial && has "$n" docs; } \
  && ok "raw task text normalizes to signals" \
  || no "raw task text normalizes to signals" "got: '$n'"

n="$(norm 'the latest router version')"
has "$n" testing && no "no false 'testing' from the substring in 'latest'" "got: '$n'" \
  || ok "no false 'testing' from the substring in 'latest'"

n="$(norm 'zzzz qqqq')"
[[ -z "${n// /}" ]] && ok "unknown text yields no tokens" || no "unknown text yields no tokens" "got: '$n'"

echo "== decider: distill stores canonical signals =="
DN="$(newdir)"
KOG_DECIDER_DIR="$DN" "$DECIDER" append-decision \
  '{"task":"jwt refresh for the python auth service","decision":{"kit":"build"},"signals":["python","auth/security-sensitive","explicit tests -> TDD"]}' >/dev/null 2>&1
KOG_DECIDER_DIR="$DN" "$DECIDER" append-decision \
  '{"task":"fix a typo in the README","decision":{"kit":"lean"},"signals":["trivial edit","docs-only","single-file"]}' >/dev/null 2>&1
rn="$(KOG_DECIDER_DIR="$DN" "$DECIDER" distill 2>/dev/null)"
if command -v jq >/dev/null 2>&1; then
  sig="$(jq -r '.rules[] | select(.kit=="build") | .signals_any | join(" ")' "$rn" 2>/dev/null)"
  { has "$sig" auth && has "$sig" testing; } \
    && ok "router rule holds canonical tokens, not raw phrases" \
    || no "router rule holds canonical tokens, not raw phrases" "got: '$sig'"
  has "$sig" "auth/security-sensitive" \
    && no "raw verbose phrase is gone from the router" "still present: '$sig'" \
    || ok "raw verbose phrase is gone from the router"
fi

echo "== decider: match -> deterministic hot path =="
m="$(KOG_DECIDER_DIR="$DN" "$DECIDER" match 'add JWT refresh tokens to our Python auth service with tests' 2>/dev/null)"
[[ "$m" == "build" ]] && ok "unseen auth+python+tests task routes to build" \
  || no "unseen auth+python+tests task routes to build" "got: '$m'"

m="$(KOG_DECIDER_DIR="$DN" "$DECIDER" match 'correct a typo in the docs' 2>/dev/null)"
[[ "$m" == "lean" ]] && ok "unseen docs typo task routes to lean" \
  || no "unseen docs typo task routes to lean" "got: '$m'"

if KOG_DECIDER_DIR="$DN" "$DECIDER" match 'zzzz qqqq' >/dev/null 2>&1; then
  no "no-overlap task exits non-zero (cold path)" "exit 0 on unmatchable task"
else
  ok "no-overlap task exits non-zero (cold path)"
fi

echo "== decider: confidence outweighs raw support =="
# Two hesitant picks must not outvote one confident one — otherwise a stream of
# low-confidence `kit for` logs would slowly bury the opus gold labels.
DW="$(newdir)"
KOG_DECIDER_DIR="$DW" "$DECIDER" append-decision \
  '{"task":"a","decision":{"kit":"flow"},"signals":["docs-only"],"confidence":0.3}' >/dev/null 2>&1
KOG_DECIDER_DIR="$DW" "$DECIDER" append-decision \
  '{"task":"b","decision":{"kit":"flow"},"signals":["docs-only"],"confidence":0.3}' >/dev/null 2>&1
KOG_DECIDER_DIR="$DW" "$DECIDER" append-decision \
  '{"task":"c","decision":{"kit":"lean"},"signals":["docs-only"],"confidence":0.95}' >/dev/null 2>&1
rw="$(KOG_DECIDER_DIR="$DW" "$DECIDER" distill 2>/dev/null)"
if command -v jq >/dev/null 2>&1; then
  fw="$(jq -r '.rules[] | select(.kit=="flow") | .weight' "$rw" 2>/dev/null)"
  fs="$(jq -r '.rules[] | select(.kit=="flow") | .support' "$rw" 2>/dev/null)"
  [[ "$fs" == "2" && "$fw" == "0.6" ]] \
    && ok "rule carries both support (count) and weight (summed confidence)" \
    || no "rule carries both support and weight" "support=$fs weight=$fw"
fi
m="$(KOG_DECIDER_DIR="$DW" "$DECIDER" match 'update the readme docs' 2>/dev/null)"
[[ "$m" == "lean" ]] \
  && ok "one confident decision beats two hesitant ones" \
  || no "one confident decision beats two hesitant ones" "got: '$m'"

echo "== decider: repack decisions outweigh up-front guesses =="
# A repack label is written mid-task, when the need is actually felt, rather than
# guessed from a one-line description before any work happened. 0.4 from a repack must
# therefore beat 0.5 from an up-front pick.
SW="$(newdir)"
KOG_DECIDER_DIR="$SW" "$DECIDER" append-decision \
  '{"task":"a","decision":{"kit":"flow"},"signals":["auth"],"confidence":0.4,"source":"repack"}' >/dev/null 2>&1
KOG_DECIDER_DIR="$SW" "$DECIDER" append-decision \
  '{"task":"b","decision":{"kit":"lean"},"signals":["auth"],"confidence":0.5}' >/dev/null 2>&1
rs="$(KOG_DECIDER_DIR="$SW" "$DECIDER" distill 2>/dev/null)"
if command -v jq >/dev/null 2>&1; then
  rwt="$(jq -r '.rules[] | select(.kit=="flow") | .weight' "$rs" 2>/dev/null)"
  rsp="$(jq -r '.rules[] | select(.kit=="flow") | .support' "$rs" 2>/dev/null)"
  [[ "$rwt" == "0.6" ]] \
    && ok "source=repack scales weight (0.4 x 1.5 = 0.6)" \
    || no "source=repack scales weight" "weight=$rwt"
  [[ "$rsp" == "1" ]] \
    && ok "support stays a raw count, unscaled" \
    || no "support stays a raw count" "support=$rsp"
fi
m="$(KOG_DECIDER_DIR="$SW" "$DECIDER" match 'audit the login flow' 2>/dev/null)"
[[ "$m" == "flow" ]] \
  && ok "a repack label outranks a more confident up-front guess" \
  || no "a repack label outranks a more confident up-front guess" "got: '$m'"

echo "== decider: unknown and absent source stay neutral =="
SN="$(newdir)"
KOG_DECIDER_DIR="$SN" "$DECIDER" append-decision \
  '{"task":"a","decision":{"kit":"flow"},"signals":["auth"],"confidence":0.4,"source":"whatever"}' >/dev/null 2>&1
rn="$(KOG_DECIDER_DIR="$SN" "$DECIDER" distill 2>/dev/null)"
if command -v jq >/dev/null 2>&1; then
  nwt="$(jq -r '.rules[] | select(.kit=="flow") | .weight' "$rn" 2>/dev/null)"
  [[ "$nwt" == "0.4" ]] \
    && ok "unrecognised source leaves confidence untouched" \
    || no "unrecognised source leaves confidence untouched" "weight=$nwt"
fi

echo; echo "decider tests: $pass passed, $fail failed"
[[ "$fail" == 0 ]]
