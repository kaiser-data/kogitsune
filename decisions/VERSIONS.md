# Version ledger

Current versions of the experience-driven artifacts and the skills that produce them.
Update on every distill / re-scout / skill change.

## Skills
| Skill | Version | Role |
|-------|---------|------|
| kit-scout    | 0.1.0 | surveys superpowers+ECC+catalog → context snapshot |
| kit-selector | 0.2.0 | task → config decision (router-first, model-last) |
| kit-builder  | 0.1.0 | decision → assembled collection + outcome log |

## Learned artifacts (append-only history; "current" = highest N)
| Artifact | Current | Produced by | Grows from |
|----------|---------|-------------|-----------|
| `context/context.v<N>.json` | v1 | kit-scout    | re-scout when catalog changes |
| `router.v<N>.json`          | v3 | kit-selector | `decider distill` over decisions.jsonl |
| `decisions.jsonl`           | 3 records (D001–D003) | kit-selector | one gold label per selection |
| `builds.jsonl`              | 1 record (B001)       | kit-builder  | one outcome per build |

Regenerate/query with `skills/lib/decider.sh {stats|latest KIND|distill}`.

## Changelog
- **router v3** — rules carry `weight` (summed confidence) alongside `support` (count), and
  `match` breaks ties on weight first. `kit for` logs cold-path picks at confidence 0.6; without
  weighting, a run of hesitant picks would outvote a 0.97 gold label purely on volume.
- **router v2** — signals are folded onto the canonical vocabulary before aggregating,
  so rules key on comparable tokens (`auth`, `testing`, `docs`) instead of one-off
  phrasings (`"auth/security-sensitive"`, `"explicit tests -> TDD"`). Decisions that
  never named a launchable kit (D001, an architecture call) are excluded — hence
  `built_from.decisions: 2` against 3 stored records.
