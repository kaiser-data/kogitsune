#!/usr/bin/env python3
"""kogitsune — pack-weight estimator.

Pure, side-effect-free. Sums the context-weight hints of a selection and renders
a total plus an ASCII bar relative to the "lean" baseline (memory + guardrails only).

Usage:
    context-est.py --weights 10000 2000           # explicit weights
    context-est.py --manifest session.json        # read weights from a build-config manifest
    context-est.py --weights 10000 --baseline 1200 --width 20

Importable: render(total, baseline=..., width=...) -> str
"""
from __future__ import annotations

import argparse
import json
import sys

LEAN_BASELINE = 1200  # approx tokens for pinned memory + guardrails + graphify

# A rough ceiling used to scale the bar; selections above this just peg the bar full.
BAR_FULL_AT = 30000


def human(n: int) -> str:
    """1234 -> '1.2K', 950 -> '950'."""
    if n >= 1000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return str(n)


def render(total: int, baseline: int = LEAN_BASELINE, width: int = 10,
           full_at: int = BAR_FULL_AT) -> str:
    """Render a single-line pack-weight bar. Pure."""
    total = max(0, int(total))
    span = max(1, full_at - baseline)
    frac = min(1.0, max(0.0, (total - baseline) / span))
    filled = round(frac * width)
    bar = "▓" * filled + "░" * (width - filled)
    return (f"pack weight: ~{human(total)} tokens  {bar}  "
            f"(lean = ~{human(baseline)})")


def total_from_manifest(manifest: dict) -> int:
    """Sum item weights from a build-config manifest, including pinned baseline."""
    items = manifest.get("items", [])
    return sum(int(i.get("weight", 0) or 0) for i in items)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="kogitsune pack-weight estimator")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--weights", nargs="*", type=int, help="explicit item weights")
    src.add_argument("--manifest", help="path to a build-config manifest JSON")
    p.add_argument("--baseline", type=int, default=LEAN_BASELINE)
    p.add_argument("--width", type=int, default=10)
    p.add_argument("--full-at", type=int, default=BAR_FULL_AT)
    p.add_argument("--json", action="store_true", help="emit {total, baseline} as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])
    if ns.manifest:
        with open(ns.manifest) as fh:
            manifest = json.load(fh)
        total = ns.baseline + total_from_manifest(manifest)
    else:
        total = ns.baseline + sum(ns.weights or [])
    if ns.json:
        print(json.dumps({"total": total, "baseline": ns.baseline}))
    else:
        print(render(total, baseline=ns.baseline, width=ns.width, full_at=ns.full_at))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
