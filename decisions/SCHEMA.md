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
| `alternatives` | object[] | `{kit, why_not}` runners-up — negative labels for learning |

`signals` + `decision` are the (X → y) pairs a future classifier/skill learns from;
`alternatives` supply contrastive negatives.
