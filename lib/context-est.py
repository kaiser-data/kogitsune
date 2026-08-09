#!/usr/bin/env python3
"""kogitsune — session-weight estimator.

Pure, side-effect-free. Models what a whole session costs: the built-in floor, plus
the selection's catalog items, minus whatever the harness axis denied.

Modelling only the catalog items used to understate a session by ~20x. Measured
2026-08-09 (see docs/FINDINGS-2026-08-09-payload-attribution.md), a session with no
items at all is ~35.7K tokens, and a kit's `harness:` allowlist can deny ~22K of it —
both larger than anything the catalog can add.

Usage:
    context-est.py --weights 10000 2000                    # explicit item weights
    context-est.py --weights 2350 --harness-saved 21231    # with harness denials
    context-est.py --manifest session.json                 # read from a manifest

Importable: session_total(manifest) -> int, render(total, baseline=...) -> str
"""
from __future__ import annotations

import argparse
import json
import sys

# What a session costs with nothing selected and nothing denied: built-in tool schemas
# (~27.0K) + system prompt (~3.9K) + the pinned set's messages (~4.8K). Measured
# 2026-08-09 with `kit measure --proxy --mcp ""` on haiku. Re-measure after a Claude Code
# upgrade — the built-in tool set is the largest term and it moves between releases.
BASE_FLOOR = 35700

# The leanest session reachable: BASE_FLOOR minus everything the harness axis may deny
# (~22.2K across all groups), with no catalog items. The bar's zero point.
MIN_SESSION = 13500

# Bar ceiling, with headroom above an undenied floor plus a heavy pack.
BAR_FULL_AT = 50000


def human(n: int) -> str:
    """1234 -> '1.2K', 950 -> '950'."""
    if n >= 1000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return str(n)


def render(total: int, baseline: int = MIN_SESSION, width: int = 10,
           full_at: int = BAR_FULL_AT) -> str:
    """Render a single-line pack-weight bar. Pure."""
    total = max(0, int(total))
    span = max(1, full_at - baseline)
    frac = min(1.0, max(0.0, (total - baseline) / span))
    filled = round(frac * width)
    bar = "▓" * filled + "░" * (width - filled)
    return (f"session weight: ~{human(total)} tokens  {bar}  "
            f"(leanest ≈ {human(baseline)})")


def total_from_manifest(manifest: dict) -> int:
    """Sum the selection's catalog item weights only. Pure.

    The catalog-only figure, kept for callers that want to compare a pack against the
    catalog (`kit ls`, `kit show`). For what a session actually costs, use session_total.
    """
    items = manifest.get("items", [])
    return sum(int(i.get("weight", 0) or 0) for i in items)


def session_total(manifest: dict) -> int:
    """Whole-session estimate: floor + items − harness denials, never negative. Pure."""
    saved = int(manifest.get("harness_saved", 0) or 0)
    return max(0, BASE_FLOOR + total_from_manifest(manifest) - saved)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="kogitsune pack-weight estimator")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--weights", nargs="*", type=int, help="explicit item weights")
    src.add_argument("--manifest", help="path to a build-config manifest JSON")
    p.add_argument("--baseline", type=int, default=MIN_SESSION)
    p.add_argument("--harness-saved", type=int, default=0,
                   help="tokens denied by the kit's harness allowlist")
    p.add_argument("--width", type=int, default=10)
    p.add_argument("--full-at", type=int, default=BAR_FULL_AT)
    p.add_argument("--json", action="store_true", help="emit {total, baseline} as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])
    if ns.manifest:
        with open(ns.manifest) as fh:
            manifest = json.load(fh)
        total = session_total(manifest)
    else:
        total = session_total({"items": [{"weight": w} for w in (ns.weights or [])],
                               "harness_saved": ns.harness_saved})
    if ns.json:
        print(json.dumps({"total": total, "baseline": ns.baseline}))
    else:
        print(render(total, baseline=ns.baseline, width=ns.width, full_at=ns.full_at))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
