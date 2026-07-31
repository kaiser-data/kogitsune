# Handoff — 2026-07-31 session (repack: live verification + the pin)

For the next agent maintaining **kogitsune**. Predecessor:
`HANDOFF-2026-07-22-kit-selector-learning.md` (the selector learning loop).
This session did **not** build the repack feature — that was the prior session. This one
tried to *test* it, and testing turned up a design gap that made the feature unusable.

## Status: 9 commits on `feat/repack`, PR #1 open, all pushed except the last

`make check` green — 48 pytest / 88 launcher / 26 decider, shellcheck silent. Verified
three consecutive clean runs, not one.

```
cb2b2ff  feat: pin repack so it survives a wrong pack     ← this session, UNPUSHED
499f61d  docs: manual test guide for repack
e5b75f3  fix: resolve decider through PATH in the published kit skills
e4aa67b  docs: spec and implementation plan for repack
dbbf46f  feat: add repack skill for mid-session harness reconfiguration
1e325e9  chore: run decider tests as part of make test
7a3c362  feat: weight repack decisions above up-front picks in distill
5d7a8d4  feat: add pack differ for repack add/shed/weight reporting
cb39822  feat: export pack identity into the session for repack
```

`git push` is the one outstanding action. Nothing else is half-done.

---

## What happened, in order

### 1. §2 passed — the design's load-bearing assumption is now observed

The whole repack design rests on `KOGITSUNE_*` reaching the session. It had been verified
across two hops but **never in one direct observation** (nested `claude` launches hung
during development). Run live in a fresh `kit lean` session:

```
kit=lean  mcp=kitsune  skills=  model=
```

That is a **pass**. `skills=` and `model=` are empty because `lean` declares `skills: []`
and no model; `kit=` and `mcp=` carrying values is what proves the export arrived.

The guide's own pass criteria said *"skills populated"*, which would have read this
correct result as a failure. Fixed in `TESTING-repack.md`.

### 2. The blocking find: repack was unreachable from every kit

While confirming §2, the live session noticed `/repack` wasn't actually available. Checked
against the built manifest rather than by reading config:

```
$ build-config.py --dry-run lean
skills: ["~/.claude/skills/graphify"]
```

One skill, not repack. Root cause: **`repack` appears nowhere in `kits.yaml`** — not in
`pinned`, and not in `catalog.skills` either (`ecc, ecc-rules-*, postgres-bp, n8n,
frontend-design, superpowers, sp`). The skill publishes correctly to
`~/.claude/skills/repack/` and works in a *plain* session, but a kit-launched session
swaps in the mirror (`session-env.sh:47-52`), and the mirror links only pinned +
declared skills.

So `/repack` could not be invoked from `lean` or `flow` — both `skills: []` — which are
the packs most likely to be wrong. **§3 was blocked.**

### 3. Why pinned, and not a catalog entry

This was the session's one real decision. Recorded because the reasoning is not obvious
from the diff:

A catalog entry is **circular**. To repack out of `lean` you would have to have predicted,
while choosing `lean`, that you'd need to repack. And acquiring it mid-session means
editing `kits.yaml` and restarting — *which is the exact cost repack exists to avoid*. At
that point you'd skip the skill and run `kit db` directly. It has to be present before you
know you need it.

Cost is **~85 tokens/session**: the frontmatter description is 384 bytes, the 6.8K body
defers until invoked. Measured, not estimated.

A third option ("pin **and** add a catalog entry, for weight accounting") was considered
and **retracted** — the catalog weight is only consulted for entries in `skills_sel`, so a
pinned repack never activates it. The entry would be dead code. Worse, if a kit then
declared it, `_fold` appends the source twice with no dedupe and the mirror does `ln -s`,
not `ln -sfn` (`session-env.sh:51`) — a likely collision. *Not verified; flagged only.*

---

## Non-obvious things worth knowing

**`kits.yaml` is gitignored** (`.gitignore:2`). The live pin is local to this machine
only. `examples/kits.example.yaml` is the tracked template and carries the pin for fresh
installs. If a future session "fixes" a discrepancy between the two, check which one is
tracked before editing.

**Pinned weights never reach the pack-weight bar.** `build-config.py:239` sums `items`
only, and pinned entries live in a separate list. `LEAN_BASELINE` in `context-est.py:25`
is therefore the *sole* place a pinned item's cost is represented — it moved 2700 → 2785.
**Bump it whenever the pinned set changes.** There is now a comment saying so.

**`LEAN_BASELINE` is not insulated by the test fixtures.** I predicted it would be and was
wrong: tests use `tests/fixtures/kits.yaml` for the *config*, but the baseline is a shared
Python constant, so changing it turned two bar assertions red (14.7K→14.8K, 4.7K→4.8K in
`test_launcher.sh:248,254`). Caught by running the suite, not by reasoning about it.

---

## The intermittent test failure is now identified (not fixed)

Prior handoff called this "one unexplained flake, 82 passed 1 failed, never captured."
It reproduced twice this session and **was** captured:

`tests/test_launcher.sh:280` — **`preview model line missing`**, `87 passed, 1 failed`.

Mechanism, confirmed: `bin/kit` runs `set -euo pipefail`, and `cmd_tune_preview`
(`bin/kit:449`) makes unchecked subprocess calls — `tune_total`'s jq, then
`context-est.py` — *before* it echoes the model line. Any transient non-zero exit aborts
the function mid-render. Verified by breaking `list.json` deliberately: the preview
truncates at exactly that point.

Two consequences:
- The test captures with `2>/dev/null`, so **every** failure of that function reports as
  "missing model line" and the real error is discarded. That's why it went undiagnosed.
- **Not test-only.** In the real picker, a hiccup in either subprocess renders a silently
  half-drawn preview pane rather than an error.

**Still unknown:** what makes those subprocesses transiently exit non-zero. Both failures
came immediately after `pytest` in the same `make` invocation, suggesting spawn pressure —
but three subsequent clean runs is not enough to claim that, and it passes standalone
every time. *Do not record this as solved.*

Suggested fix, separable from repack: drop the `2>/dev/null` at line 280 so the next
occurrence is diagnosable, and make `cmd_tune_preview` fail loudly instead of truncating.

---

## Next steps, in order

1. **`git push`** — cb2b2ff is local only.
2. **§3, the real remaining test.** Needs a fresh session anyway, and that same relaunch
   picks up the pin:
   ```bash
   kit lean
   ```
   then `/repack I need to build a Vue component with Supabase auth`.

   Watch two things: **step 4** (`--config` resolution when cwd is not the kogitsune repo
   — the most likely genuine bug), and **step 6** (must *print* the relaunch command, not
   execute it).
3. §4 (negative test) and §5 (no-op test) — cheap once §3 works.
4. The `cmd_tune_preview` hardening above, as its own commit.

`docs/TESTING-repack.md` is the operative guide; §1 and §6 are already verified green.

## What I did not do

- Did not run §3–§5 — they need a session this one couldn't launch.
- Did not fix `cmd_tune_preview`; only diagnosed it. It is unrelated to repack and would
  have muddied the PR.
- Did not touch the two untracked docs in the working tree
  (`HANDOFF-2026-07-22-kit-selector-learning.md`, `NOTE-grok-build.md`) — they predate
  this session and I don't know your intent for them.
