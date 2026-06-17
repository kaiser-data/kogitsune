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

echo "== model selection =="
# db declares model: opus in the fixture -> launcher passes --model opus to claude
"$ROOT/bin/kit" db >/dev/null 2>&1
grep -q -- "--model opus" "$TMP/claude.log" && ok "kit-declared model passed to claude" || no "model not passed: $(grep ARGS "$TMP/claude.log")"
# passthrough --model wins (kit model suppressed)
"$ROOT/bin/kit" db -- --model haiku >/dev/null 2>&1
grep -q -- "--model haiku" "$TMP/claude.log" && ! grep -q -- "--model opus --model haiku" "$TMP/claude.log" \
  && ok "passthrough --model overrides the kit model" || no "passthrough override: $(grep ARGS "$TMP/claude.log")"
# lean has no model -> no --model flag at all
"$ROOT/bin/kit" lean >/dev/null 2>&1
! grep -q -- "--model" "$TMP/claude.log" && ok "no --model when kit declares none" || no "spurious --model: $(grep ARGS "$TMP/claude.log")"
clean_tmp

# regression: --mcp-config is variadic, so it must come LAST or a stray passthrough
# word (e.g. `kit db tune`) gets eaten as a phantom second config path.
"$ROOT/bin/kit" db tune >/dev/null 2>&1
grep -qE -- "tune --strict-mcp-config --mcp-config [^ ]+$" "$TMP/claude.log" \
  && ok "stray passthrough can't poison --mcp-config (kit db tune)" || no "arg order: $(grep ARGS "$TMP/claude.log")"
clean_tmp

echo "== launch guards: never hand claude a bad mcp-config =="
# a build-config failure (malformed config) must die clearly and NOT invoke claude
printf 'kits: [this is not: valid yaml\n' > "$TMP/broken.yaml"
: > "$TMP/claude.log"
out="$(KOGITSUNE_CONFIG="$TMP/broken.yaml" "$ROOT/bin/kit" db 2>&1)"; rc=$?
[[ "$rc" -ne 0 ]] && echo "$out" | grep -qi "failed to resolve" && ok "broken config fails with a clear error" || no "broken config not caught: $out"
[[ ! -s "$TMP/claude.log" ]] && ok "claude not invoked on resolve failure" || no "claude ran despite bad config"
clean_tmp

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

echo "== picker: tune a pack (state-file model) =="
# fzf is stubbed: the picker's space/tab binds never fire, so the state file is
# the source of truth. A no-op stub (enter on the focused row) means "launch the
# pack as currently seeded". We exercise the seed + the internal toggle commands.
cat > "$BIN/fzf_noop" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null; echo ""   # consume rows; emit just the (blank=enter) --expect key
EOF
chmod +x "$BIN/fzf_noop"

# seed the picker from a kit -> launches that kit's resolved à la carte selection
out="$(KIT_DRY_RUN=1 KOGITSUNE_FZF="$BIN/fzf_noop" "$ROOT/bin/kit" tune db 2>&1)"
echo "$out" | grep -q "mcp=supabase" && ok "tune seeds the pack from a kit" || no "tune seed: $(echo "$out" | tail -1)"
echo "$out" | grep -q "postgres-best-practices" && ok "tune seed carries the kit's skills" || no "tune seed skills: $(echo "$out" | grep would)"
clean_tmp

# internal toggle/rows/preview transitions, driven on a hand-built tune dir
TD="$TMP/kogitsune.tune.t1"; mkdir -p "$TD"
KOGITSUNE_CONFIG="$FIX/kits.yaml" KOGITSUNE_MCP_ON_DEMAND="$FIX/mcp-on-demand.json" \
  python3 "$ROOT/lib/build-config.py" --config "$FIX/kits.yaml" \
  --mcp-on-demand "$FIX/mcp-on-demand.json" --list > "$TD/list.json" 2>/dev/null
echo '{"mcp":[],"skills":[]}' > "$TD/state.json"

# toggling a kit row loads its whole preset
"$ROOT/bin/kit" __tune_toggle "$TD" kit db
jq -e '.mcp==["supabase"] and .skills==["postgres-bp"]' "$TD/state.json" >/dev/null \
  && ok "toggling a 🦊 kit row loads its preset" || no "kit preset load: $(cat "$TD/state.json")"
# rows reflect membership with a ✔ glyph and the bar sums the in-pack weights
rows="$("$ROOT/bin/kit" __tune_rows "$TD" 2>/dev/null)"
printf '%s\n' "$rows" | grep -qE '^✔ .*supabase' && ok "in-pack item renders a ✔ glyph" || no "glyph: $(printf '%s' "$rows" | grep supabase)"
pv="$("$ROOT/bin/kit" __tune_preview "$TD" 2>/dev/null)"
printf '%s\n' "$pv" | grep -q "14.7K" && ok "preview bar sums tuned pack (+baseline)" || no "preview weight sum: $(printf '%s\n' "$pv" | grep -i token)"
# dropping a single item from the loaded preset
"$ROOT/bin/kit" __tune_toggle "$TD" mcp supabase
jq -e '.mcp==[] and .skills==["postgres-bp"]' "$TD/state.json" >/dev/null \
  && ok "toggling an item drops it from the pack" || no "item drop: $(cat "$TD/state.json")"
pv="$("$ROOT/bin/kit" __tune_preview "$TD" 2>/dev/null)"
printf '%s\n' "$pv" | grep -q "4.7K" && ok "bar updates after dropping an item" || no "bar after drop: $(printf '%s\n' "$pv" | grep -i token)"
# toggling the same item again re-adds it
"$ROOT/bin/kit" __tune_toggle "$TD" mcp supabase
jq -e '.mcp==["supabase"]' "$TD/state.json" >/dev/null && ok "re-toggling re-adds the item" || no "item re-add: $(cat "$TD/state.json")"
# the empty 'lean' preset acts as a reset-to-pinned button
"$ROOT/bin/kit" __tune_toggle "$TD" kit lean
jq -e '.mcp==[] and .skills==[]' "$TD/state.json" >/dev/null && ok "the lean preset resets the pack" || no "lean reset: $(cat "$TD/state.json")"
# 'lean' shows ✔ only when the pack is genuinely empty (not vacuously)
"$ROOT/bin/kit" __tune_toggle "$TD" mcp supabase
printf '%s\n' "$("$ROOT/bin/kit" __tune_rows "$TD" 2>/dev/null)" | grep -qE '^○ 🦊 lean' \
  && ok "lean shows ○ once the pack is non-empty" || no "lean glyph: $("$ROOT/bin/kit" __tune_rows "$TD" 2>/dev/null | grep lean)"
# ctrl-p hides/shows the 🦊 preset rows; items stay visible either way
echo 1 > "$TD/presets"
"$ROOT/bin/kit" __tune_presets "$TD"   # -> hidden
rows="$("$ROOT/bin/kit" __tune_rows "$TD" 2>/dev/null)"
! printf '%s\n' "$rows" | grep -q "preset" && ok "ctrl-p hides the 🦊 preset rows" || no "presets still shown: $(printf '%s\n' "$rows" | grep preset | head -1)"
printf '%s\n' "$rows" | grep -q "supabase" && ok "items stay visible when presets hidden" || no "items vanished with presets"
"$ROOT/bin/kit" __tune_presets "$TD"   # -> shown again
printf '%s\n' "$("$ROOT/bin/kit" __tune_rows "$TD" 2>/dev/null)" | grep -q "preset" && ok "ctrl-p shows presets again" || no "presets did not return"
# ctrl-o cycles the model override: default -> sonnet -> opus -> haiku -> default
: > "$TD/model"
"$ROOT/bin/kit" __tune_model "$TD"; [[ "$(cat "$TD/model")" == "sonnet" ]] && ok "ctrl-o: default→sonnet" || no "cycle1: $(cat "$TD/model")"
"$ROOT/bin/kit" __tune_model "$TD"; "$ROOT/bin/kit" __tune_model "$TD"
[[ "$(cat "$TD/model")" == "haiku" ]] && ok "ctrl-o: sonnet→opus→haiku" || no "cycle3: $(cat "$TD/model")"
"$ROOT/bin/kit" __tune_model "$TD"; [[ -z "$(cat "$TD/model")" ]] && ok "ctrl-o: haiku→default wraps" || no "cycle wrap: $(cat "$TD/model")"
printf '%s\n' "$("$ROOT/bin/kit" __tune_preview "$TD" 2>/dev/null)" | grep -q "model:  default" && ok "preview shows the model" || no "preview model line missing"
rm -rf "$TD"

# preset model adoption: loading a 🦊 preset adopts its model UNLESS the user cycled (ctrl-o)
TD="$TMP/kogitsune.tune.m"; mkdir -p "$TD"
KOGITSUNE_CONFIG="$FIX/kits.yaml" KOGITSUNE_MCP_ON_DEMAND="$FIX/mcp-on-demand.json" \
  python3 "$ROOT/lib/build-config.py" --config "$FIX/kits.yaml" \
  --mcp-on-demand "$FIX/mcp-on-demand.json" --list > "$TD/list.json" 2>/dev/null
# (a) unlocked: toggling db on adopts db's model (opus)
echo '{"mcp":[],"skills":[]}' > "$TD/state.json"; : > "$TD/model"
"$ROOT/bin/kit" __tune_toggle "$TD" kit db
[[ "$(cat "$TD/model")" == "opus" ]] && ok "loading a preset adopts its model" || no "preset model: $(cat "$TD/model")"
# (b) dropping that preset back off leaves the model alone (no clobber to default)
"$ROOT/bin/kit" __tune_toggle "$TD" kit db
[[ "$(cat "$TD/model")" == "opus" ]] && ok "dropping a preset keeps the model" || no "drop model: $(cat "$TD/model")"
# (c) locked: after ctrl-o, loading a preset must NOT overwrite the user's choice
echo '{"mcp":[],"skills":[]}' > "$TD/state.json"; : > "$TD/model"; rm -f "$TD/model_locked"
"$ROOT/bin/kit" __tune_model "$TD"   # ctrl-o -> sonnet, and locks
"$ROOT/bin/kit" __tune_toggle "$TD" kit db   # db is opus, but we chose sonnet
[[ "$(cat "$TD/model")" == "sonnet" ]] && ok "ctrl-o choice survives a preset load" || no "lock failed: $(cat "$TD/model")"
rm -rf "$TD"

# picker seeds the model from the base kit and carries it into the launch
out="$(KIT_DRY_RUN=1 KOGITSUNE_FZF="$BIN/fzf_noop" "$ROOT/bin/kit" tune db 2>&1)"
echo "$out" | grep -q -- "--model opus" && ok "tune seeds + launches with the kit's model" || no "tune model: $(echo "$out" | grep would)"
clean_tmp

echo "== measured weight: floor calibration math =="
SD="$TMP/state/kogitsune"; mkdir -p "$SD"
echo '{"db":25000}' > "$SD/measured.json"
# uncalibrated: ls/show report the raw total
"$ROOT/bin/kit" ls 2>/dev/null | grep -q "measured ~25000 tok total" && ok "ls shows raw total when uncalibrated" || no "ls raw: $("$ROOT/bin/kit" ls 2>/dev/null | grep db)"
# calibrated: measured tag becomes kit-only (total − floor)
echo 22000 > "$SD/floor"
"$ROOT/bin/kit" ls 2>/dev/null | grep -q "measured ≈3000 tok" && ok "ls subtracts floor (kit-only)" || no "ls marginal: $("$ROOT/bin/kit" ls 2>/dev/null | grep db)"
"$ROOT/bin/kit" show db 2>&1 >/dev/null | grep -q "measured ≈ 3000 tok (kit-only)" && ok "show reports kit-only weight" || no "show marginal: $("$ROOT/bin/kit" show db 2>&1 >/dev/null | tail -1)"
# floor larger than a measurement clamps to 0, never negative
echo '{"db":21000}' > "$SD/measured.json"
"$ROOT/bin/kit" ls 2>/dev/null | grep -q "measured ≈0 tok" && ok "marginal clamps at 0" || no "clamp: $("$ROOT/bin/kit" ls 2>/dev/null | grep db)"
# doctor surfaces the calibrated floor
"$ROOT/bin/kit" doctor 2>/dev/null | grep -q "base floor: ~22000 tok" && ok "doctor shows calibrated floor" || no "doctor floor: $("$ROOT/bin/kit" doctor 2>/dev/null | grep -i floor)"
rm -rf "$SD"
# measure --calibrate routes to the calibrator (fake claude → graceful failure, no crash)
out="$("$ROOT/bin/kit" measure --calibrate 2>&1)"; rc=$?
echo "$out" | grep -q "calibrating base floor" && ok "measure --calibrate routes to calibrator" || no "calibrate route: $out"
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
