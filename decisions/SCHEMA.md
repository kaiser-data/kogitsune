# Decision database

Append-only log of **config-selection decisions**: given a task and the full
skill/feature catalog, which config (kit / composition) was chosen, by whom, and why.

## Why this exists — teacher → student distillation

The strongest model (**opus 4.8**) is an accurate but slow/expensive *teacher*: it
sees the whole catalog and composes the optimal config per task. Every decision it
makes is logged here as a **gold label**. Over time this log becomes a training set to
**distill a fast decision skill** (the *student*) that answers instantly — no model
call — for tasks whose signals it has learned. Model calls become *rare*, not cheap.

Tiers the log is meant to bootstrap:

| Tier | Path | Latency | Role |
|------|------|---------|------|
| 0 hot  | learned skill / cached record | ~0 ms | answers known patterns instantly |
| 1 warm | haiku `kit for` (`--bare`)    | ~6 s  | cheap fallback for unknown-but-easy tasks |
| 2 cold | **opus 4.8 full-catalog compose** | ~30 s+ | teacher; always logs a gold label |

## Record format (`decisions.jsonl`, one JSON object per line)

| field | type | purpose |
|-------|------|---------|
| `id` | string | stable decision id (`D001`…) |
| `ts` | ISO-8601 UTC | when decided |
| `decider` | string | model id that decided (e.g. `claude-opus-4-8`, `haiku`, `skill:kit-router`) |
| `task` | string | the task text the decision was for |
| `catalog_hash` | string | fingerprint of the catalog at decision time (kits.yaml + kit list) |
| `git_sha` | string | repo sha at decision time |
| `decision` | object | `{kit, model, mcp[], skills[], launch}` — the chosen config |
| `signals` | string[] | task features that drove the pick — **the learnable input** |
| `rationale` | string | one-line why |
| `confidence` | number | 0–1 |
| `source` | string | how the decision was reached — `repack` for a mid-session repack, absent for an up-front pick |
| `alternatives` | object[] | `{kit, why_not}` runners-up — negative labels for learning |

`signals` + `decision` are the (X → y) pairs a future classifier/skill learns from;
`alternatives` supply contrastive negatives.

## Signal normalization

Signals are written as free text, but `distill` folds them onto a fixed vocabulary before
they reach a router rule — two decisions that said `"auth/security-sensitive"` and
`"needs a login audit"` must reinforce the *same* rule, not two unrelated ones.

| Token | folds from (examples) |
|-------|----------------------|
| `auth` | auth, authentication, jwt, oauth, login, credential, password |
| `security` | security, secure, vulnerability, crypto, secret, injection, xss, csrf |
| `testing` | test, tests, TDD, coverage |
| `docs` | doc, docs, documentation, readme, changelog, comment |
| `performance` | perf, latency, optimize, throughput, bottleneck, profiling, slow |
| `refactor` | refactor, cleanup, rename, restructure, dead code, simplify |
| `bugfix` | bug, fix, defect, broken, crash, regression |
| `feature` | feature, implement, add support, new endpoint |
| `multi-file` / `single-file` | multi-file, cross-file, project-wide / single file, one file |
| `trivial` | trivial, typo, tiny, one-liner, minor, nit |
| `python` `typescript` `go` `rust` `shell` | language + framework names (django, react, cargo, …) |

Inspect the folding for any text with `decider normalize "<text>"`. Extend the vocabulary in
`SIGNAL_VOCAB` (`skills/lib/decider.sh`) — patterns are plain substrings against lowercased,
punctuation-stripped, space-padded text; wrap one in spaces for a whole-word match (`" test"`
is what keeps *latest* from reading as a testing signal).

**Not every decision becomes a rule.** Records whose `decision.kit` is `custom`, or whose
`launch` starts with `n/a`, are skipped: the router's output is a kit name to launch, and a
bespoke composition or an architecture call can't be replayed by name.

## Support vs. weight

Each rule carries both:

| Field | Meaning |
|-------|---------|
| `support` | how many decisions produced this rule (count) |
| `weight`  | those decisions' summed `confidence` |

`match` ranks by signal overlap first, then **weight**, then support. Counting alone would let
volume win: `kit for` logs every cold-path pick at `confidence: 0.6`, so a handful of hesitant
automated picks would eventually outrank a hand-made 0.97 label. An absent or non-numeric
`confidence` is read as `0.5` — unstated is middling, never certain.

This is why `confidence` is worth setting honestly. It is not decoration; it is the vote.

## Source weighting

`source` records *when* a decision was made, which changes how much it is worth. An
up-front pick is a guess from a one-line task description, made at the moment you know
least about the task. A **repack** decision is made mid-task, against what the session
turned out to actually need — a label produced by felt need rather than by prediction.

`distill` therefore multiplies a `source: "repack"` record's confidence by
`SOURCE_WEIGHT_REPACK` (1.5, in `skills/lib/decider.sh`) before it reaches a rule's
`weight`. Absent or unrecognised sources are neutral. `support` is unaffected — it stays
an honest count of how many decisions produced the rule.

The scaling is deliberately mild: repack labels should win ties and near-ties against
up-front guesses, not overwrite the hand-made gold labels.
