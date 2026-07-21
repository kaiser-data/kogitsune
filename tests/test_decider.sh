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

echo; echo "decider tests: $pass passed, $fail failed"
[[ "$fail" == 0 ]]
