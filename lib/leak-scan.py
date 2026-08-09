#!/usr/bin/env python3
"""kogitsune — find context that reaches a session without passing through the mirror.

lib/session-env.sh gates skills, plugins, MCP and rules by remapping CLAUDE_CONFIG_DIR.
That controls everything the harness loads *from the config dir* — but the harness also
walks up from the working directory, and anything it finds there is loaded with real
paths the mirror never sees. Measured 2026-08-09: ~4.8K tokens in every session run from
under $HOME, `lean` included (docs/FINDINGS-2026-08-09-payload-attribution.md).

Three ancestor artifacts load independently, verified by sandbox probe:

    <ancestor>/CLAUDE.md
    <ancestor>/.claude/CLAUDE.md      loads even when the above is absent
    <ancestor>/.claude/rules/**       loads even when both of the above are absent

The third is the expensive one, and it is why $HOME/.claude hurts: it is the real config
dir, so every project under $HOME re-imports the very rules the mirror gated out.

This module only reports. Fixing it means moving files the user owns, which is their call.

    leak-scan.py            # scan the current directory
    leak-scan.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BYTES_PER_TOKEN = 4

# Only these load automatically from an ancestor; a rules/ dir is scanned recursively.
CLAUDE_MD = "CLAUDE.md"
DOT_CLAUDE = ".claude"
RULES_DIR = "rules"
MD_SUFFIX = ".md"

# Where rules packs should live instead: a sibling of ~/.claude, verified 2026-08-09
# not to be picked up by the ancestor walk (positive control in the same run: a
# .claude/rules canary leaked, a .claude-rules canary did not).
SUGGESTED_ROOT = "~/.claude-rules"

# The pack subdirectory the migration moves. guardrails.md is deliberately left behind.
PACK_SUBDIR = "ecc"


def est_tokens(n_bytes: int) -> int:
    """Estimate tokens from a byte count. Pure."""
    return round(max(0, int(n_bytes)) / BYTES_PER_TOKEN)


def ancestors(start: str, stop: str = "/") -> list[str]:
    """Directories from `start` up to and including `stop`. Pure."""
    start, stop = os.path.abspath(start), os.path.abspath(stop)
    out, cur = [], start
    while True:
        out.append(cur)
        if cur == stop or cur == os.path.dirname(cur):
            break
        cur = os.path.dirname(cur)
    return out


def _size_of(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _rules_hit(rules_dir: str) -> dict | None:
    """Aggregate a rules/ tree into one hit — the files load as a set, not individually."""
    total = count = 0
    for root, _dirs, files in os.walk(rules_dir):
        for f in files:
            if f.endswith(MD_SUFFIX):
                total += _size_of(os.path.join(root, f))
                count += 1
    if not count:
        return None
    return {"kind": "rules", "path": rules_dir, "count": count,
            "bytes": total, "tokens": est_tokens(total)}


def scan(cwd: str | None = None, stop: str = "/") -> list[dict]:
    """Ancestor context that bypasses the mirror, largest first. Pure w.r.t. the fs.

    The starting directory is excluded: a project's own CLAUDE.md is intended context,
    not a leak. Everything above it arrives without the user choosing it per-session.
    """
    cwd = os.path.abspath(cwd or os.getcwd())
    hits: list[dict] = []
    for d in ancestors(cwd, stop)[1:]:
        top = os.path.join(d, CLAUDE_MD)
        if os.path.isfile(top):
            n = _size_of(top)
            hits.append({"kind": "claude_md", "path": top, "count": 1,
                         "bytes": n, "tokens": est_tokens(n)})
        nested = os.path.join(d, DOT_CLAUDE, CLAUDE_MD)
        if os.path.isfile(nested):
            n = _size_of(nested)
            hits.append({"kind": "claude_md", "path": nested, "count": 1,
                         "bytes": n, "tokens": est_tokens(n)})
        rules = os.path.join(d, DOT_CLAUDE, RULES_DIR)
        if os.path.isdir(rules):
            hit = _rules_hit(rules)
            if hit:
                hits.append(hit)
    return sorted(hits, key=lambda h: (-h["bytes"], h["path"]))


def total_tokens(hits: list[dict]) -> int:
    """Estimated tokens across every hit. Pure."""
    return sum(h["tokens"] for h in hits)


def render(hits: list[dict]) -> str:
    """Human-readable warning, or "" when nothing bypasses the mirror. Pure."""
    if not hits:
        return ""
    out = [f"⚠️  up to ~{total_tokens(hits):,} tok can reach every session without "
           f"passing through the mirror:"]
    for h in hits:
        what = f"{h['count']} files" if h["kind"] == "rules" else "file"
        out.append(f"     {h['path']}  ({what}, ~{h['tokens']:,} tok, {h['kind']})")
    out.append("     These load from the working directory's ancestors, so kit gating "
               "cannot reach them.")
    # An upper bound on purpose: a rules/ tree is reported whole, but only part of it
    # may load (measured 2026-08-09: 11 of 22 files here). Only a probe knows which.
    out.append("     Upper bound — not all of a rules/ tree necessarily loads; run "
               "'kit measure --proxy lean' for the real figure.")
    out.append("     Fix: move them off the ancestor path (see "
               "docs/FINDINGS-2026-08-09-payload-attribution.md).")
    return "\n".join(out)


def leaks_by_location(path: str) -> bool:
    """True when `path` sits inside a directory named `.claude`. Pure.

    That is the whole condition: the harness auto-loads `<ancestor>/.claude/rules/**`
    from the working directory's ancestors, so a rules root anywhere inside a `.claude`
    dir reaches every session no matter what the mirror excludes.
    """
    return DOT_CLAUDE in os.path.abspath(os.path.expanduser(path)).split(os.sep)


def migration_hint(rules_path: str, suggested: str = SUGGESTED_ROOT) -> str:
    """Instruction to move rules packs off the ancestor path, or "" if already clear.

    Moves only the pack subdirectory, never `guardrails.md`: the global CLAUDE.md refers
    to it as `@rules/guardrails.md`, so relocating it would silently drop guardrails from
    every non-kit session — a worse failure than the leak being fixed.
    """
    if not leaks_by_location(rules_path):
        return ""
    src = os.path.abspath(os.path.expanduser(rules_path))
    return "\n".join([
        f"rules packs under {src} are auto-loaded from cwd's ancestors —",
        "no kit can gate them. Move the packs (leave guardrails.md where it is):",
        f"    mkdir -p {suggested}",
        f"    mv {os.path.join(src, PACK_SUBDIR)} {suggested}/",
        f'then add to kits.yaml:    rules_root: "{suggested}"',
        "then verify:              kit measure --proxy lean",
    ])


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Find context that bypasses the mirror.")
    p.add_argument("--cwd", help="directory to scan from (default: current)")
    p.add_argument("--stop", default="/", help="stop walking at this directory")
    p.add_argument("--rules-root", help="configured rules root; checked for migration")
    p.add_argument("--json", action="store_true", help="emit hits as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])
    hits = scan(ns.cwd, ns.stop)
    hint = migration_hint(ns.rules_root) if ns.rules_root else ""
    if ns.json:
        print(json.dumps({"total_tokens": total_tokens(hits), "hits": hits,
                          "migration": hint}))
    else:
        print(render(hits) or "✓ nothing bypasses the mirror from here")
        if hint:
            print()
            print(hint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
