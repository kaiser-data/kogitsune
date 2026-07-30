# `repack` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a running kogitsune session re-derive its optimal pack mid-flight and relaunch into it.

**Architecture:** Four small pieces bolted onto machinery that already exists. The launcher gains a pack-identity export so a session can read what it is running; a pure Python differ turns two manifests into an add/shed/weight report; the decision log gains a `source` field so repack labels outvote up-front guesses; and one new skill drives the procedure and writes the handoff. `kit save` + `kit <name> -- ARGS` provide the relaunch — no new launcher code.

**Tech Stack:** Bash 3.2 (macOS-safe), Python 3 stdlib only, `jq`, pytest, hand-rolled bash test harnesses.

**Source spec:** `docs/SPEC-2026-07-30-repack.md`

## Global Constraints

- **Bash 3.2 compatible** — no associative arrays, no `${var^^}`, no float arithmetic in bash (delegate math to `jq` or Python).
- **Python 3 stdlib only** — no new dependencies. `lib/*.py` files are hyphenated and loaded via `importlib`, never imported by name.
- **Pure where possible** — `lib/pack-diff.py` must be side-effect-free and importable, matching `lib/context-est.py`.
- **`shellcheck -x --severity=warning` must pass** on every script in the `Makefile` `SCRIPTS` list.
- **Never mutate the real `~/.claude`** — kogitsune's core safety property.
- **Tests are hermetic** — no real `claude`, no keychain, no `~/.claude`. Fake via `PATH` + the `KOGITSUNE_*` env seams.
- **Do not commit unless explicitly asked** (user guardrail). Steps below include `git commit` because the plan is TDD-structured; confirm with the user before the first commit.
- **Spec correction:** the spec's Build item 2 names `lib/session-env.sh`. `launch_from_manifest` actually lives in `bin/kit:120`. Task 1 fixes the spec text alongside the code.

---

### Task 1: Pack identity export

A session cannot repack what it cannot identify. `remember_kit` writes a *global* last-launched state file, which is wrong for concurrent sessions. Export the pack onto the `claude` process instead, where the session can read it via `Bash`.

**Files:**
- Modify: `bin/kit:120-165` (`launch_from_manifest`)
- Modify: `docs/SPEC-2026-07-30-repack.md:127` (fix the file reference)
- Test: `tests/test_launcher.sh`

**Interfaces:**
- Consumes: the build-config manifest, which already carries `.kit`, `.model`, and `.items[] = {name, kind, weight}` where `kind == "mcp"` marks MCP servers.
- Produces: four env vars on the launched session — `KOGITSUNE_KIT` (kit name, empty for à-la-carte), `KOGITSUNE_PACK_SKILLS` (comma-joined names), `KOGITSUNE_PACK_MCP` (comma-joined names), `KOGITSUNE_PACK_MODEL` (resolved model, empty if none). Task 4's skill reads all four.

- [ ] **Step 1: Make the test's fake `claude` record the environment**

In `tests/test_launcher.sh`, the `make_claude` helper currently logs only `CLAUDE_CONFIG_DIR` and args. Add the pack vars. Replace the `make_claude` function body:

```bash
make_claude(){ # $1 = exit code
  cat > "$BIN/claude" <<EOF
#!/usr/bin/env bash
{ echo "CLAUDE_CONFIG_DIR=\${CLAUDE_CONFIG_DIR:-}"
  echo "KOGITSUNE_KIT=\${KOGITSUNE_KIT:-}"
  echo "KOGITSUNE_PACK_SKILLS=\${KOGITSUNE_PACK_SKILLS:-}"
  echo "KOGITSUNE_PACK_MCP=\${KOGITSUNE_PACK_MCP:-}"
  echo "KOGITSUNE_PACK_MODEL=\${KOGITSUNE_PACK_MODEL:-}"
  echo "ARGS: \$*"; } > "$TMP/claude.log"
exit ${1:-0}
EOF
  chmod +x "$BIN/claude"; }
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_launcher.sh`, immediately after the `== model selection ==` block's final `clean_tmp`:

```bash
echo "== pack identity export =="
# A session cannot repack what it cannot identify. The global last-kits state file is
# not per-session, so the pack rides on the claude process env instead.
"$ROOT/bin/kit" db >/dev/null 2>&1
grep -q "^KOGITSUNE_KIT=db$" "$TMP/claude.log" \
  && ok "KOGITSUNE_KIT names the launched kit" \
  || no "KOGITSUNE_KIT not exported: $(grep KOGITSUNE_KIT "$TMP/claude.log")"
grep -q "^KOGITSUNE_PACK_MODEL=opus$" "$TMP/claude.log" \
  && ok "KOGITSUNE_PACK_MODEL carries the resolved model" \
  || no "KOGITSUNE_PACK_MODEL wrong: $(grep KOGITSUNE_PACK_MODEL "$TMP/claude.log")"
# the db fixture's items must show up split by kind, never mixed
skills_line="$(grep '^KOGITSUNE_PACK_SKILLS=' "$TMP/claude.log")"
mcp_line="$(grep '^KOGITSUNE_PACK_MCP=' "$TMP/claude.log")"
[[ "$skills_line" != "KOGITSUNE_PACK_SKILLS=" ]] \
  && ok "KOGITSUNE_PACK_SKILLS is populated" \
  || no "KOGITSUNE_PACK_SKILLS empty"
[[ -n "$mcp_line" ]] \
  && ok "KOGITSUNE_PACK_MCP is exported" \
  || no "KOGITSUNE_PACK_MCP missing from the log entirely"
# MCP names must not leak into the skills list
case "$skills_line" in
  *postgres*) no "MCP server leaked into KOGITSUNE_PACK_SKILLS: $skills_line" ;;
  *) ok "MCP names kept out of the skills list" ;;
esac
clean_tmp
```

Before running, confirm what the `db` fixture actually contains so the assertions match reality:

```bash
KOGITSUNE_CONFIG=tests/fixtures/kits.yaml KOGITSUNE_MCP_ON_DEMAND=tests/fixtures/mcp-on-demand.json \
  python3 lib/build-config.py db --config tests/fixtures/kits.yaml \
  --mcp-on-demand tests/fixtures/mcp-on-demand.json --dry-run \
  | jq '{kit, model, items: [.items[] | {name, kind}]}'
```

If the fixture's MCP server is not named `postgres`, substitute the real name in the leak check above.

- [ ] **Step 3: Run the test to verify it fails**

Run: `bash tests/test_launcher.sh 2>&1 | tail -25`
Expected: the four new assertions FAIL — `KOGITSUNE_KIT not exported:` with an empty value, because nothing exports it yet.

- [ ] **Step 4: Export the pack in `launch_from_manifest`**

In `bin/kit`, inside `launch_from_manifest`, after the model-resolution block (the `if [[ -n "$model" && -z "$user_model" ]]` block ending at the `fi` around line 140) and before the `KIT_DRY_RUN` check, insert:

```bash
  # Export the pack onto the session so a running session can read what it is
  # running — this is what `repack` reads. `remember_kit` writes a *global*
  # last-launched file, which is not per-session and lies when sessions overlap.
  local pack_skills pack_mcp
  pack_skills="$(jq -r '[.items[] | select(.kind != "mcp") | .name] | join(",")' "$manifest")"
  pack_mcp="$(jq -r '[.items[] | select(.kind == "mcp") | .name] | join(",")' "$manifest")"
  export KOGITSUNE_KIT="$(jq -r '.kit // ""' "$manifest")"
  export KOGITSUNE_PACK_SKILLS="$pack_skills"
  export KOGITSUNE_PACK_MCP="$pack_mcp"
  export KOGITSUNE_PACK_MODEL="$model"
```

`$model` is already set above from `.model // empty`, so it is the resolved kit model and empty when the kit declares none. These are plain `export`s on the launcher shell; `claude` runs as a child at line ~161 and inherits them.

- [ ] **Step 5: Run the test to verify it passes**

Run: `bash tests/test_launcher.sh 2>&1 | tail -25`
Expected: all pack-identity assertions PASS, and the pre-existing assertions still pass (final line reports 0 failed).

- [ ] **Step 6: Verify the env reaches a real session manually**

Run: `kit lean -- -p 'Run: echo "$KOGITSUNE_KIT / $KOGITSUNE_PACK_MODEL"'`
Expected: the session's Bash tool prints `lean / ` (empty model — `lean` declares none). This confirms the export survives into the session's tool subprocesses, which is the whole point of the task.

- [ ] **Step 7: Lint**

Run: `make lint`
Expected: no output, exit 0.

- [ ] **Step 8: Fix the spec's file reference**

In `docs/SPEC-2026-07-30-repack.md`, in the Build table, replace:

```
| 2 | Export `KOGITSUNE_KIT` + packed skills/MCP in `launch_from_manifest` (`lib/session-env.sh`) | ~1 line |
```

with:

```
| 2 | Export `KOGITSUNE_KIT` + packed skills/MCP in `launch_from_manifest` (`bin/kit`) | ~8 lines |
```

- [ ] **Step 9: Commit**

```bash
git add bin/kit tests/test_launcher.sh docs/SPEC-2026-07-30-repack.md
git commit -m "feat: export pack identity into the session for repack"
```

---

### Task 2: `lib/pack-diff.py`

**Files:**
- Create: `lib/pack-diff.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_pack_diff.py`

**Interfaces:**
- Consumes: two build-config manifests (dicts), each with `items[] = {name, kind, weight}`, `model`, and `weight`.
- Produces: `diff_packs(current: dict, target: dict) -> dict` returning
  `{"add": {"skills": [str], "mcp": [str]}, "shed": {"skills": [str], "mcp": [str]}, "model": {"from": str|None, "to": str|None} | None, "weight": {"current": int, "target": int, "delta": int}, "noop": bool}`,
  and `render(diff: dict) -> str` returning the human block. Task 4's skill calls the CLI, not the functions.

Number formatting reuses `human()` from `lib/context-est.py` so the two never drift. Signs are ASCII `+`/`-` (the spec mockup's `−` is U+2212; ASCII keeps shell round-tripping and test assertions clean).

- [ ] **Step 1: Add the conftest fixture**

In `tests/conftest.py`, after the `ctxest` fixture, add:

```python
@pytest.fixture(scope="session")
def packdiff():
    return _load("packdiff", "pack-diff.py")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_pack_diff.py`:

```python
"""Pack diffing: current manifest vs target -> add / shed / model / weight delta."""


def manifest(items, model=None, weight=None):
    """Build a minimal build-config-shaped manifest. items: [(name, kind, weight)]."""
    entries = [{"name": n, "kind": k, "weight": w} for n, k, w in items]
    return {
        "kit": "test",
        "model": model,
        "items": entries,
        "weight": weight if weight is not None else sum(w for _, _, w in items),
    }


def test_add_only(packdiff):
    cur = manifest([("guardrails", "skill", 1000)])
    tgt = manifest([("guardrails", "skill", 1000), ("vue-patterns", "skill", 2100)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == ["vue-patterns"]
    assert d["shed"]["skills"] == []
    assert d["weight"]["delta"] == 2100
    assert d["noop"] is False


def test_shed_only(packdiff):
    cur = manifest([("guardrails", "skill", 1000), ("html-email", "skill", 4800)])
    tgt = manifest([("guardrails", "skill", 1000)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == []
    assert d["shed"]["skills"] == ["html-email"]
    assert d["weight"]["delta"] == -4800


def test_mixed_add_and_shed_separates_mcp_from_skills(packdiff):
    cur = manifest([("n8n", "skill", 3000), ("postgres", "mcp", 1800)])
    tgt = manifest([("vue-patterns", "skill", 2100), ("supabase", "mcp", 900)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"] == {"skills": ["vue-patterns"], "mcp": ["supabase"]}
    assert d["shed"] == {"skills": ["n8n"], "mcp": ["postgres"]}
    assert d["weight"] == {"current": 4800, "target": 3000, "delta": -1800}


def test_noop_when_packs_match(packdiff):
    cur = manifest([("guardrails", "skill", 1000)], model="sonnet")
    d = packdiff.diff_packs(cur, dict(cur))
    assert d["noop"] is True
    assert d["model"] is None
    assert d["weight"]["delta"] == 0


def test_model_change_reported_and_is_not_a_noop(packdiff):
    cur = manifest([("guardrails", "skill", 1000)], model="sonnet")
    tgt = manifest([("guardrails", "skill", 1000)], model="opus")
    d = packdiff.diff_packs(cur, tgt)
    assert d["model"] == {"from": "sonnet", "to": "opus"}
    assert d["noop"] is False


def test_same_name_in_both_kinds_is_not_confused(packdiff):
    """A skill and an MCP server may share a name; they are distinct pack entries."""
    cur = manifest([("supabase", "skill", 500)])
    tgt = manifest([("supabase", "mcp", 900)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["mcp"] == ["supabase"]
    assert d["shed"]["skills"] == ["supabase"]


def test_lists_are_sorted_for_determinism(packdiff):
    cur = manifest([])
    tgt = manifest([("zeta", "skill", 1), ("alpha", "skill", 1)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == ["alpha", "zeta"]


def test_duplicate_entries_collapse(packdiff):
    cur = manifest([])
    tgt = manifest([("vue", "skill", 100), ("vue", "skill", 100)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == ["vue"]


def test_weight_falls_back_to_item_sum_when_absent(packdiff):
    cur = {"items": [{"name": "a", "kind": "skill", "weight": 700}], "model": None}
    tgt = {"items": [], "model": None}
    d = packdiff.diff_packs(cur, tgt)
    assert d["weight"] == {"current": 700, "target": 0, "delta": -700}


def test_render_shows_adds_sheds_model_and_net(packdiff):
    cur = manifest([("n8n", "skill", 4800)], model="sonnet")
    tgt = manifest([("vue-patterns", "skill", 2100)], model="opus")
    out = packdiff.render(packdiff.diff_packs(cur, tgt))
    assert "+ vue-patterns" in out
    assert "- n8n" in out
    assert "sonnet -> opus" in out
    assert "net" in out


def test_render_noop_says_so(packdiff):
    cur = manifest([("guardrails", "skill", 1000)])
    out = packdiff.render(packdiff.diff_packs(cur, dict(cur)))
    assert "already optimal" in out
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_pack_diff.py -q`
Expected: collection error — `FileNotFoundError` for `lib/pack-diff.py` when the fixture loads.

- [ ] **Step 4: Write the implementation**

Create `lib/pack-diff.py`:

```python
#!/usr/bin/env python3
"""kogitsune — pack differ.

Pure, side-effect-free. Compares two build-config manifests and reports what a
repack would add, shed, and cost. Shedding is first-class: an add-only diff is
what produces the heavy session kogitsune exists to prevent.

Usage:
    pack-diff.py --current cur.json --target tgt.json
    pack-diff.py --current cur.json --target tgt.json --json

Importable: diff_packs(current, target) -> dict ; render(diff) -> str
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

MCP_KIND = "mcp"


def _load_ctxest():
    """Load the hyphenated sibling module once, at import time."""
    path = pathlib.Path(__file__).with_name("context-est.py")
    spec = importlib.util.spec_from_file_location("_ctxest_for_diff", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CTXEST = _load_ctxest()


def _human(n: int) -> str:
    """Reuse context-est's formatter so the two never drift."""
    return _CTXEST.human(abs(int(n)))


def _split_kinds(manifest: dict) -> tuple[set[str], set[str]]:
    """Manifest items -> (skill names, mcp names). Deduped."""
    skills, mcp = set(), set()
    for item in manifest.get("items", []) or []:
        name = item.get("name")
        if not name:
            continue
        (mcp if item.get("kind") == MCP_KIND else skills).add(name)
    return skills, mcp


def _weight(manifest: dict) -> int:
    """Declared manifest weight, falling back to the sum of item weights."""
    declared = manifest.get("weight")
    if isinstance(declared, int):
        return declared
    return sum(int(i.get("weight", 0) or 0)
               for i in (manifest.get("items", []) or []))


def diff_packs(current: dict, target: dict) -> dict:
    """Compare two manifests. Pure."""
    cur_skills, cur_mcp = _split_kinds(current)
    tgt_skills, tgt_mcp = _split_kinds(target)

    add = {"skills": sorted(tgt_skills - cur_skills),
           "mcp": sorted(tgt_mcp - cur_mcp)}
    shed = {"skills": sorted(cur_skills - tgt_skills),
            "mcp": sorted(cur_mcp - tgt_mcp)}

    cur_model, tgt_model = current.get("model"), target.get("model")
    model = None
    if cur_model != tgt_model:
        model = {"from": cur_model, "to": tgt_model}

    cur_w, tgt_w = _weight(current), _weight(target)
    changed = any(add.values()) or any(shed.values()) or model is not None
    return {
        "add": add,
        "shed": shed,
        "model": model,
        "weight": {"current": cur_w, "target": tgt_w, "delta": tgt_w - cur_w},
        "noop": not changed,
    }


def _signed(n: int) -> str:
    return f"{'+' if n >= 0 else '-'}{_human(n)}"


def render(diff: dict) -> str:
    """Render the confirmation block. Pure."""
    if diff["noop"]:
        return "  pack already optimal for this task — nothing to add or shed"

    lines = []
    added = diff["add"]["skills"] + diff["add"]["mcp"]
    shedded = diff["shed"]["skills"] + diff["shed"]["mcp"]
    if added:
        lines.append(f"  + {', '.join(added)}")
    if shedded:
        lines.append(f"  - {', '.join(shedded)}")
    if diff["model"]:
        frm = diff["model"]["from"] or "(default)"
        to = diff["model"]["to"] or "(default)"
        lines.append(f"  model: {frm} -> {to}")

    w = diff["weight"]
    lines.append("")
    lines.append(f"  net {_signed(w['delta'])}   ·   "
                 f"{_human(w['current'])} -> {_human(w['target'])}")
    return "\n".join(lines)


def _load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="kogitsune pack differ")
    p.add_argument("--current", required=True, help="current session manifest JSON")
    p.add_argument("--target", required=True, help="proposed manifest JSON")
    p.add_argument("--json", action="store_true", help="emit the diff as JSON")
    ns = p.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        diff = diff_packs(_load(ns.current), _load(ns.target))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"pack-diff: could not read manifests: {exc}\n")
        return 2

    if ns.json:
        json.dump(diff, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_pack_diff.py -q`
Expected: `11 passed`.

- [ ] **Step 6: Verify the CLI end-to-end against two real manifests**

```bash
python3 lib/build-config.py lean --config tests/fixtures/kits.yaml \
  --mcp-on-demand tests/fixtures/mcp-on-demand.json --dry-run > /tmp/cur.json
python3 lib/build-config.py db --config tests/fixtures/kits.yaml \
  --mcp-on-demand tests/fixtures/mcp-on-demand.json --dry-run > /tmp/tgt.json
python3 lib/pack-diff.py --current /tmp/cur.json --target /tmp/tgt.json
python3 lib/pack-diff.py --current /tmp/cur.json --target /tmp/tgt.json --json | jq .noop
```

Expected: a human block naming the additions with a positive net, then `false`. If `build-config.py --dry-run` writes anything other than the manifest to stdout, use `--out-dir` to a temp dir instead and read the written manifest.

- [ ] **Step 7: Run the full suite**

Run: `make test`
Expected: all pytest tests and launcher tests pass.

- [ ] **Step 8: Commit**

```bash
git add lib/pack-diff.py tests/test_pack_diff.py tests/conftest.py
git commit -m "feat: pack differ for repack add/shed/weight reporting"
```

---

### Task 3: `source` field and distill weighting

Repack decisions are labelled by real felt need mid-task, not by a guess from a one-line description. They deserve more vote than an up-front pick. `confidence` is already the vote (`decisions/SCHEMA.md`, "Support vs. weight"); `source` scales it.

**Files:**
- Modify: `skills/lib/decider.sh:133-169` (`cmd_distill`) and the header comment block
- Modify: `decisions/SCHEMA.md`
- Test: `tests/test_decider.sh`

**Interfaces:**
- Consumes: decision records appended by `decider append-decision` (unchanged signature).
- Produces: an optional record field `source` (string; `"repack"` is the only recognised value today) which multiplies that record's contribution to a rule's `weight` by `SOURCE_WEIGHT_REPACK` (1.5). `support` stays a raw count. Task 4's skill sets `source: "repack"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_decider.sh`, immediately before the final `echo; echo "decider tests: ..."` summary lines:

```bash
echo "== decider: repack decisions outweigh up-front guesses =="
# A repack label is written mid-task, when the need is felt rather than guessed, so it
# counts for more per unit of confidence. 0.4 from a repack must beat 0.5 from a guess.
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
    || no "source=repack weight scaling" "weight=$rwt"
  [[ "$rsp" == "1" ]] \
    && ok "support stays a raw count, unscaled" \
    || no "support stays a raw count" "support=$rsp"
fi
m="$(KOG_DECIDER_DIR="$SW" "$DECIDER" match 'audit the login flow' 2>/dev/null)"
[[ "$m" == "flow" ]] \
  && ok "a repack label outranks a more confident up-front guess" \
  || no "repack label outranks up-front guess" "got: '$m'"

echo "== decider: unknown and absent source are neutral =="
SN="$(newdir)"
KOG_DECIDER_DIR="$SN" "$DECIDER" append-decision \
  '{"task":"a","decision":{"kit":"flow"},"signals":["auth"],"confidence":0.4,"source":"whatever"}' >/dev/null 2>&1
rn="$(KOG_DECIDER_DIR="$SN" "$DECIDER" distill 2>/dev/null)"
if command -v jq >/dev/null 2>&1; then
  nwt="$(jq -r '.rules[] | select(.kit=="flow") | .weight' "$rn" 2>/dev/null)"
  [[ "$nwt" == "0.4" ]] \
    && ok "unrecognised source leaves confidence untouched" \
    || no "unrecognised source is neutral" "weight=$nwt"
fi
```

Confirm the helper name `newdir` matches the one already used in the file's earlier blocks (the confidence-vs-support block uses `DW="$(newdir)"`); if the helper is named differently, use that name.

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/test_decider.sh 2>&1 | tail -20`
Expected: FAIL with `weight=0.4` where `0.6` was expected — `source` is currently ignored.

- [ ] **Step 3: Implement the source weighting**

In `skills/lib/decider.sh`, add the constant next to the `SIGNAL_VOCAB` definition (after the vocab block closes):

```bash
# ---- source weighting -------------------------------------------------------
# A decision's `confidence` is its vote (see decisions/SCHEMA.md). `source` scales
# that vote: a repack label is written mid-task, when the need is actually felt,
# rather than guessed from a one-line description before any work happened — so it
# is better training data per unit of stated confidence. Unrecognised or absent
# sources are neutral (factor 1.0); the scaling is deliberately mild.
SOURCE_WEIGHT_REPACK=1.5
```

Then in `cmd_distill`, replace the confidence extraction (currently lines 150-152):

```bash
    # an unstated or malformed confidence is treated as middling, never as certain
    conf="$(printf '%s' "$line" \
      | jq -r 'if (.confidence|type) == "number" then .confidence else 0.5 end')"
```

with:

```bash
    # an unstated or malformed confidence is treated as middling, never as certain,
    # then scaled by `source` — jq does the float math (bash 3.2 cannot).
    conf="$(printf '%s' "$line" | jq -r --argjson rf "$SOURCE_WEIGHT_REPACK" '
      (if (.confidence|type) == "number" then .confidence else 0.5 end)
      * (if .source == "repack" then $rf else 1.0 end)
      | . * 1000 | round / 1000')"
```

The existing `weight: ([ .[].confidence ] | add | . * 1000 | round / 1000)` aggregation and `support: length` need no change — scaling happens per record, before grouping, so `support` stays a raw count.

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/test_decider.sh 2>&1 | tail -20`
Expected: the four new assertions PASS and the pre-existing confidence-vs-support assertions still pass (0 failed).

- [ ] **Step 5: Document the field in the schema**

In `decisions/SCHEMA.md`, add a row to the record-format table after the `confidence` row:

```markdown
| `source` | string | how the decision was reached — `repack` for a mid-session repack, absent for an up-front pick |
```

Then append to the end of the "Support vs. weight" section:

```markdown
## Source weighting

`source` records *when* a decision was made, which changes how much it is worth. An
up-front pick is a guess from a one-line task description, made at the moment you know
least. A **repack** decision is made mid-task, against what the session turned out to
actually need — a label produced by felt need rather than prediction.

`distill` therefore multiplies a `source: "repack"` record's confidence by
`SOURCE_WEIGHT_REPACK` (1.5, in `skills/lib/decider.sh`) before it reaches a rule's
`weight`. Absent or unrecognised sources are neutral. `support` is unaffected — it stays
an honest count of how many decisions produced the rule.

The scaling is deliberately mild: repack labels should win ties and near-ties against
up-front guesses, not overwrite the hand-made gold labels.
```

- [ ] **Step 6: Lint and run the full suite**

Run: `make lint && make test && bash tests/test_decider.sh`
Expected: shellcheck silent, all suites report 0 failures.

- [ ] **Step 7: Commit**

```bash
git add skills/lib/decider.sh decisions/SCHEMA.md tests/test_decider.sh
git commit -m "feat: weight repack decisions above up-front picks in distill"
```

---

### Task 4: The `repack` skill

The procedure itself. No new launcher code — `kit save` + `kit <name> -- ARGS` do the relaunch.

**Files:**
- Create: `skills/repack/SKILL.md`
- Modify: `.gitignore`
- Modify: `README.md`
- Test: `tests/test_launcher.sh`

**Interfaces:**
- Consumes: `KOGITSUNE_KIT` / `KOGITSUNE_PACK_SKILLS` / `KOGITSUNE_PACK_MCP` / `KOGITSUNE_PACK_MODEL` (Task 1); `lib/pack-diff.py --current --target [--json]` (Task 2); `decider append-decision` with `source: "repack"` (Task 3); `decider match` / `decider latest` for the hot path.
- Produces: `.kogitsune/handoff.md` and a printed relaunch command. Nothing downstream consumes these.

- [ ] **Step 1: Ignore the handoff directory**

`.kogitsune/handoff.md` is session-local scratch. In `.gitignore`, under the `# generated session configs` block, add:

```
.kogitsune/
```

- [ ] **Step 2: Write the failing end-to-end launcher test**

The relaunch path is `kit save _repack …` then `kit _repack --dry-run`. `kit save` **writes to the config file**, so the test must point `KOGITSUNE_CONFIG` at a copy — never at the shared fixture.

Append to `tests/test_launcher.sh`, before the final summary:

```bash
echo "== repack relaunch path (save then launch a derived kit) =="
# repack's whole restart mechanism is `kit save _repack` + `kit _repack -- ARGS`.
# Save mutates the config file, so work on a copy — never the shared fixture.
RCFG="$TMP/repack-kits.yaml"; cp "$FIX/kits.yaml" "$RCFG"
( export KOGITSUNE_CONFIG="$RCFG"
  "$ROOT/bin/kit" save _repack --skills guardrails --model opus >/dev/null 2>&1 )
grep -q '_repack' "$RCFG" \
  && ok "kit save writes the derived _repack kit" \
  || no "_repack not saved into the config"
( export KOGITSUNE_CONFIG="$RCFG"
  "$ROOT/bin/kit" _repack --dry-run >"$TMP/repack.dry" 2>&1 )
grep -q 'kit=_repack' "$TMP/repack.dry" \
  && ok "_repack resolves and would launch" \
  || no "_repack did not resolve: $(cat "$TMP/repack.dry")"
grep -q 'model=opus' "$TMP/repack.dry" \
  && ok "derived kit carries its model" \
  || no "derived model lost: $(cat "$TMP/repack.dry")"
# saving again must overwrite, not accumulate — _repack is reserved scratch
( export KOGITSUNE_CONFIG="$RCFG"
  "$ROOT/bin/kit" save _repack --skills guardrails --model sonnet >/dev/null 2>&1 )
[[ "$(grep -c '^  _repack:' "$RCFG")" == "1" ]] \
  && ok "re-saving _repack overwrites rather than duplicating" \
  || no "_repack duplicated on re-save: $(grep -c '^  _repack:' "$RCFG") entries"
clean_tmp
```

Verify the indentation in the duplicate-check `grep -c '^  _repack:'` matches how `save_kit_text` actually writes kit keys — inspect `$RCFG` after the first save and adjust the pattern if kits are nested differently.

Confirm the skill name `guardrails` exists in `tests/fixtures/kits.yaml`; if not, substitute a skill the fixture actually defines.

- [ ] **Step 3: Run the test to verify it fails or passes**

Run: `bash tests/test_launcher.sh 2>&1 | tail -20`
Expected: these assertions likely PASS immediately — they characterise existing `kit save` / `kit launch` behaviour that repack depends on. That is the point: they are regression guards on the reused primitives. If any FAIL, that is a real gap in the reuse assumption and must be fixed before the skill is written.

- [ ] **Step 4: Write the skill**

Create `skills/repack/SKILL.md`:

```markdown
---
name: repack
version: 0.1.0
description: Use when a running session's pack is wrong for the work actually happening — missing a skill or MCP server it needs, or carrying dead weight from an earlier phase. Symptoms: "I don't have the right skill for this", a long session that has drifted, wanting to shed an unused half of the harness, "repack", "reconfigure for this".
---

# repack

## Overview
kogitsune makes you choose the pack **before** the session starts, from a one-line task
description — a guess made at the moment you know least. `repack` re-derives the optimal
pack for what is *actually* happening and relaunches into it.

Shedding is first-class. A proposal that only ever adds is what produces the heavy
session kogitsune exists to prevent.

## When to Use
- A task needs a skill or MCP server that was not packed
- A long session has drifted and half the pack is now dead weight
- The model is wrong for the phase (cheap exploration done, hard work starting)

## When NOT to Use
- Mid-edit, or with uncommitted work you would lose — a repack **restarts the session**
- For MCP alone: `kitsune` mounts servers on demand with no restart. Use it instead.

## Constraints (why this restarts)
| Layer | Changes mid-session? |
|---|---|
| Skills — add | Yes, ~1 turn lag |
| Skills — edit in place | No (body cached from first scan) |
| MCP | Yes (`kitsune`) |
| Model, `CLAUDE.md`, hooks | No — fixed at process start |

Skill hot-add works but is deliberately unused: a restart is required anyway for
model/`CLAUDE.md`/hooks, and taking it uniformly avoids both the lag and the stale-body
trap. See `docs/SPEC-2026-07-30-repack.md`.

## Procedure

### 1. Read the current pack
```bash
echo "kit=${KOGITSUNE_KIT:-?} model=${KOGITSUNE_PACK_MODEL:-default}"
echo "skills=${KOGITSUNE_PACK_SKILLS:-}"
echo "mcp=${KOGITSUNE_PACK_MCP:-}"
```
All four empty means the session was not launched by `kit`. Say so and stop — there is
no pack to diff against, and guessing one would produce a bogus decision label.

### 2. Read the need
Signals come from the conversation: what has the work actually been about, what was
reached for and missing, what has gone untouched. Add any hint the user passed
(`/repack vue supabase`).

### 3. Derive the target pack
**Hot path first.** The learned router answers known patterns with no model call:
```bash
skills/lib/decider.sh match "<task summary>"
```
Exit 0 prints a kit name — propose it. Exit 1 is the cold path.

**Cold path.** Read the menu and compose:
```bash
skills/lib/decider.sh latest context     # scout's snapshot, if any
cat kits.yaml                            # named kits + catalog with weights
cat docs/ecc-skills-descriptions.tsv     # 277 skills, name + one-liner
```
Reason over these in-context. Only fall back to a haiku one-shot (`kit for "<task>"`)
if in-context matching is genuinely inconclusive.

Name what to **shed** as explicitly as what to add. Anything packed that the work has
not touched and is not about to is a candidate.

### 4. Render the diff
```bash
mkdir -p .kogitsune
python3 lib/build-config.py "${KOGITSUNE_KIT}" --dry-run > .kogitsune/cur.json
python3 lib/build-config.py --skills "<target skills>" --mcp "<target mcp>" \
  --model "<target model>" --dry-run > .kogitsune/tgt.json
python3 lib/pack-diff.py --current .kogitsune/cur.json --target .kogitsune/tgt.json
```
If the diff is a no-op, say the pack is already right and stop. Do not manufacture
churn to look useful.

### 5. Confirm
Show the diff and ask. **Nothing is written before the user answers.**
```
repack: <one line on what the task looks like>

  + <additions>
  - <sheds>
  model: <from> -> <to>

  net <delta>   ·   <current> -> <target>

restart to apply? [y/N]
```

### 6. On confirm — write the handoff, save, print the command
Write `.kogitsune/handoff.md`: where the work stands, what is done, what is next, any
decision the user has already made that the next session must not re-litigate. Short
and concrete — claude-mem carries the broader history, this covers the last mile.

```bash
kit save _repack --skills "<target skills>" --mcp "<target mcp>" --model "<target model>"
```
Then **print** this for the user to run — do not execute it:
```bash
kit _repack -- "$(cat .kogitsune/handoff.md)"
```
`_repack` is reserved scratch and is overwritten on every repack. To keep a derived
pack, the user runs `kit save <realname> …` themselves.

### 7. Log the decision
```bash
skills/lib/decider.sh append-decision '{
  "ts": "<ISO-8601 UTC>",
  "decider": "skill:repack",
  "task": "<task summary>",
  "decision": {"kit": "_repack", "model": "<m>", "mcp": [], "skills": [],
               "launch": "kit _repack"},
  "signals": ["<canonical signals>"],
  "rationale": "<one line>",
  "confidence": 0.0,
  "source": "repack",
  "alternatives": [{"kit": "<runner-up>", "why_not": "<why>"}]
}'
```
Set `confidence` honestly — it is the vote, not decoration (`decisions/SCHEMA.md`).
`source: "repack"` is what earns the label its extra weight in `distill`; omitting it
throws away the reason this decision is worth more than an up-front guess.

Periodically: `skills/lib/decider.sh distill` to fold new labels into a fresh router.

## Anti-patterns
- **Add-only proposals.** If nothing is shed, justify why in one line or find something.
- **Repacking to seem useful.** A no-op diff is a good outcome; report it and stop.
- **Auto-running the relaunch.** Print it. The user decides when the session dies.
- **Skipping the handoff.** The new session starts cold without it.
- **Logging without `source`.** Silently degrades the label to an up-front guess.
```

- [ ] **Step 5: Verify the skill's commands actually run**

Working through the procedure by hand in a `kit`-launched session:

```bash
kit lean -- -p 'Run: echo "kit=$KOGITSUNE_KIT skills=$KOGITSUNE_PACK_SKILLS"'
```
Expected: prints the real pack, confirming step 1 works from inside a session.

Then verify step 4's manifest commands resolve against the real config:
```bash
mkdir -p .kogitsune
python3 lib/build-config.py lean --dry-run > .kogitsune/cur.json
python3 lib/build-config.py --skills guardrails --dry-run > .kogitsune/tgt.json
python3 lib/pack-diff.py --current .kogitsune/cur.json --target .kogitsune/tgt.json
```
Expected: a rendered diff. If `build-config.py` needs `--config` or `--mcp-on-demand`
explicitly in this context, add those flags to the skill's step-4 commands to match.

- [ ] **Step 6: Publish to the global skills dir**

`kit-selector` and friends are published to `~/.claude/skills/` so they are reachable
from any session. Match that:

```bash
ln -sfn "$PWD/skills/repack" "$HOME/.claude/skills/repack"
ls -l "$HOME/.claude/skills/repack"
```

Then check how the existing skills were published and follow it exactly — if they are
copies rather than symlinks, copy instead, and if `install.sh` publishes them, add
`repack` to that list:

```bash
ls -l ~/.claude/skills/ | grep -E 'kit-selector|kit-builder|kit-scout'
grep -n 'kit-selector\|skills/' install.sh
```

- [ ] **Step 7: Document it in the README**

Add `repack` alongside the existing kit-selection skills in `README.md`, one entry
matching the surrounding format. Read the relevant section first and match its style:

```bash
grep -n 'kit-selector\|kit-builder\|kit-scout' README.md
```

- [ ] **Step 8: Run everything**

Run: `make check`
Expected: shellcheck silent; pytest and launcher suites report 0 failures.

Run: `bash tests/test_decider.sh`
Expected: 0 failed.

- [ ] **Step 9: Commit**

```bash
git add skills/repack/SKILL.md .gitignore README.md tests/test_launcher.sh
git commit -m "feat: repack skill for mid-session harness reconfiguration"
```

---

## Verification against the spec

| Spec section | Covered by |
|---|---|
| Trigger — user-invoked, no hooks | Task 4 (skill frontmatter; no hook registered anywhere) |
| Flow steps 1-6 | Task 4 steps 1-6 of the procedure |
| Pack derivation — hot path, cold path, shedding | Task 4 procedure step 3 |
| Restart and handoff — `kit save` + `kit … -- ARGS` | Task 4 procedure step 6; Task 4 Step 2 test |
| Decision logging with `source: "repack"` | Task 3 (mechanism) + Task 4 procedure step 7 (use) |
| Interface — confirmation block, print not exec | Task 2 `render()`; Task 4 procedure steps 5-6 |
| Build item 1 — `skills/repack/SKILL.md` | Task 4 |
| Build item 2 — pack identity export | Task 1 (file reference corrected to `bin/kit`) |
| Build item 3 — `lib/pack-diff.py` | Task 2 |
| Build item 4 — `source` field + distill weighting | Task 3 |
| Build item 5 — handoff writer (no code) | Task 4 procedure step 6 |
| Build item 6 — publish to `~/.claude/skills/` | Task 4 Step 6 |
| Testing — pack-diff units, launcher export, decision round-trip, end-to-end | Task 2 Step 2; Task 1 Step 2; Task 3 Step 1; Task 4 Step 2 |
| Non-goals — no hooks, no hot-add, no auto-exec, no in-place edits | Nothing in any task implements these |

## Deferred (from the spec, not built here)

- Auto-exec the relaunch, once the print flow is proven in daily use.
- Skills-only fast path via hot-add, when a repack needs only additions.
