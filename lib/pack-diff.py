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
    skills: set[str] = set()
    mcp: set[str] = set()
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


def _read(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="kogitsune pack differ")
    p.add_argument("--current", required=True, help="current session manifest JSON")
    p.add_argument("--target", required=True, help="proposed manifest JSON")
    p.add_argument("--json", action="store_true", help="emit the diff as JSON")
    ns = p.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        diff = diff_packs(_read(ns.current), _read(ns.target))
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
