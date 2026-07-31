# Testing `repack`

Manual test guide for the `repack` feature (`docs/SPEC-2026-07-30-repack.md`).
Status at time of writing: automated suite green, live-session path unverified.

## TL;DR

```bash
make check                                        # here, anytime
kit lean -- "build a Vue component with Supabase auth"   # fresh terminal
```
then `/repack` inside that session. Four checks: pack identity is populated, the diff
sheds as well as adds, it confirms before writing, it prints rather than executes.

**A fresh session is required.** Skill bodies are cached from first scan, so a session
started before a skill was written or edited serves the old body — see Constraints in
the spec.

---

## 1. Automated suite

```bash
make check
```

Expect: `48 pytest`, `88 launcher`, `26 decider`, 0 failures, shellcheck silent.

Covers the differ's arithmetic, the env-export contract, the `save` → `launch` relaunch
path, and `source` weighting. **Proves nothing about a live session** — everything here
runs against a fake `claude` on `PATH`.

## 2. Pack identity reaches the session ⚠️ the unproven one

The whole design rests on this. It is verified in two hops (launcher → `claude` process,
and `claude` process → Bash-tool subprocess) but never in one direct observation —
nested `claude` launches hung during development.

```bash
kit lean -- "check the repack env"
```

Inside that session:

```bash
echo "kit=$KOGITSUNE_KIT skills=$KOGITSUNE_PACK_SKILLS mcp=$KOGITSUNE_PACK_MCP model=$KOGITSUNE_PACK_MODEL"
```

| | |
|---|---|
| **Pass** | `kit=lean`, `mcp=kitsune`, `skills=` **empty**, `model=` empty |
| **Fail** | *all four* empty → the export is not reaching the session |

`skills=` and `model=` are empty because `lean` declares `skills: []` and no model
(`kits.yaml:56`). That is a pass, not a failure — `kit=` and `mcp=` carrying values is
what proves the export arrived. Any kit that declares skills will populate `skills=`.

**Status: PASS**, observed directly on 2026-07-31 in a live `kit lean` session
(`kit=lean mcp=kitsune skills= model=`). This closes the gap listed below.

On failure, look at `bin/kit:141-152` and confirm `claude` still runs as a **child**
process, not via `exec` (exec would also leak the mirror).

## 3. `/repack` end to end

In a `kit`-launched session, ask for something the pack plainly does not cover:

```
/repack I need to build a Vue component with Supabase auth
```

| Checkpoint | Correct behaviour |
|---|---|
| Step 1 | Names your actual current pack; does not guess |
| Step 3 | States whether it used the **hot path** (router, no model call) or the cold path |
| Step 4 | Diff shows **both** `+` and `−` lines, plus a net weight number |
| Step 5 | Asks before writing anything |
| Step 6 | **Prints** the relaunch command; does not execute it |

Most likely real failure: step 4's `--config` resolution when the working directory is
not the kogitsune repo. An error there is a genuine skill bug, not a setup problem.

Then run the printed command and confirm the new session:
- has the added skills available
- knows where the work stood, from `.kogitsune/handoff.md`

## 4. Negative test — refuse cleanly

Run `/repack` in a session **not** launched by `kit`.

Expected: it reports there is no pack to diff against and stops.

If it invents a pack instead, that is a bug — it would log a garbage decision label into
the training data.

## 5. No-op test — do not manufacture churn

Launch a kit that genuinely fits the task, then `/repack` for that same task.

Expected: "pack already optimal", and it stops. A proposal that churns the pack to look
useful is a bug.

## 6. `decider` resolution in the older kit skills

Regression guard for the fix in `e5b75f3`. Before it, every `decider` call inside the
published `kit-selector` / `kit-scout` / `kit-builder` failed silently, so the
learned-router hot path never ran.

```bash
kit lean -- "which kit should I use to harden the login flow?"
```

`kit-selector` should reach the router and answer `build` with no model call.
Cross-check the same lookup directly:

```bash
skills/lib/decider.sh match "harden the login flow"     # → build
skills/lib/decider.sh normalize "harden the login flow" # → auth
```

## 7. The learning loop — after several real repacks

Only meaningful once repack labels have accumulated.

```bash
skills/lib/decider.sh distill
jq '.rules[] | select(.weight > .support)' decisions/router.v*.json | tail -20
```

Any rule where `weight > support` is a repack-sourced label pulling more than its raw
count — the ×1.5 `SOURCE_WEIGHT_REPACK` scaling working as intended. `support` should
always stay an honest integer count.

---

## Known gaps

- ~~**Live-session pack identity** (§2) is inferred across two proven hops, not observed
  directly.~~ **Closed 2026-07-31** — observed directly in a live `kit lean` session.
- **One intermittent failure, now identified.** Captured 2026-07-31: it is
  `tests/test_launcher.sh:280`, `preview model line missing` (`87 passed, 1 failed`).
  Reproduced twice under `make check`, then clean on three reruns and on every
  standalone `bash tests/test_launcher.sh` — so it is intermittent, not ordering.

  Mechanism (confirmed): `bin/kit` runs `set -euo pipefail`, and `cmd_tune_preview`
  (`bin/kit:449`) makes unchecked subprocess calls — `tune_total`'s jq, then
  `context-est.py` — *before* it echoes the model line. Any transient non-zero exit
  aborts the function mid-render. Verified by breaking `list.json` deliberately: the
  preview truncates at exactly that point.

  Two consequences: the test captures with `2>/dev/null`, so every failure of that
  function reports itself as a missing model line and the real error is discarded —
  which is why this went undiagnosed. And it is not test-only: in the real picker a
  hiccup in either subprocess renders a silently half-drawn preview pane.

  **Still unknown:** what makes those subprocesses transiently exit non-zero. Both
  failures occurred immediately after `pytest` in the same `make` invocation, which
  suggests spawn pressure, but three clean runs is not enough to claim that. Fix worth
  making regardless: drop the `2>/dev/null` at line 280 so the next occurrence is
  diagnosable, and make `cmd_tune_preview` fail loudly instead of truncating.
