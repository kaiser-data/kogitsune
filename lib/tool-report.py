#!/usr/bin/env python3
"""kogitsune — per-tool attribution over a captured Anthropic API request.

`kit measure <name>` gives one number: the real context total for a kit. It cannot
say *which* item bought it. This module reads a request body captured by
lib/measure-proxy.py and breaks the payload down by tool, by MCP server, and by
system-prompt block — so catalog `weight:` hints in kits.yaml can be replaced with
measured numbers instead of hand-entered guesses.

Sizes are bytes of the serialized JSON the client actually sent. Tokens are
estimated at BYTES_PER_TOKEN (no tokenizer dependency) and are labelled as
estimates everywhere they surface.

Note what this can and cannot see: only *eagerly loaded* tools appear in the
request's `tools` array. Deferred tools (loaded on demand via ToolSearch) cost
only their name inside a system block, so they show up in the system totals, not
the tool ranking. That asymmetry is the point — it is what tells you which
denials are worth making.

    tool-report.py capture.json            # ranked table
    tool-report.py capture.json --json     # machine-readable summary
    tool-report.py capture.json --top 30
"""
from __future__ import annotations

import argparse
import json
import sys

# Rough bytes-per-token for JSON tool schemas. Good enough for ranking and for
# sizing catalog weights; not a substitute for a real tokenizer.
BYTES_PER_TOKEN = 4

# Longest system-block label we print before truncating.
LABEL_MAX = 48

MCP_PREFIX = "mcp__"
BUILTIN_GROUP = "builtin"


def est_tokens(n_bytes: int) -> int:
    """Estimate tokens from a byte count. Pure."""
    return round(max(0, int(n_bytes)) / BYTES_PER_TOKEN)


def group_of(tool_name: str) -> str:
    """Attribute a tool to its source: an MCP server, or the built-in harness.

    `mcp__supabase__list_tables` -> `mcp:supabase`, so every tool a server
    contributes aggregates under one catalog-comparable line.
    """
    if not tool_name.startswith(MCP_PREFIX):
        return BUILTIN_GROUP
    server = tool_name[len(MCP_PREFIX):].split("__", 1)[0]
    return f"mcp:{server}" if server else BUILTIN_GROUP


def tool_entries(request: dict) -> list[dict]:
    """One entry per eagerly-loaded tool, largest first. Pure."""
    entries = []
    for tool in request.get("tools") or []:
        name = tool.get("name", "?")
        n = len(json.dumps(tool))
        entries.append({"name": name, "group": group_of(name),
                        "bytes": n, "tokens": est_tokens(n)})
    return sorted(entries, key=lambda e: (-e["bytes"], e["name"]))


def group_totals(entries: list[dict]) -> list[dict]:
    """Aggregate tool entries by group, largest first. Pure."""
    acc: dict[str, dict] = {}
    for e in entries:
        g = acc.setdefault(e["group"], {"group": e["group"], "count": 0, "bytes": 0})
        g["count"] += 1
        g["bytes"] += e["bytes"]
    for g in acc.values():
        g["tokens"] = est_tokens(g["bytes"])
    return sorted(acc.values(), key=lambda g: (-g["bytes"], g["group"]))


def _is_wrapper(line: str) -> bool:
    """A bare tag line like <system-reminder> — every injected block opens with one,
    so using it as a label would make four different cost centres look identical."""
    return line.startswith("<") and line.endswith(">")


def _label(text: str) -> str:
    """First meaningful line of a block, truncated for the table. Pure."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first = next((ln for ln in lines if not _is_wrapper(ln)), None)
    if first is None:
        first = lines[0] if lines else "(empty)"
    return first if len(first) <= LABEL_MAX else first[:LABEL_MAX - 1] + "…"


def system_entries(request: dict) -> list[dict]:
    """One entry per system block (or a single entry for a plain string). Pure."""
    system = request.get("system")
    if not system:
        return []
    if isinstance(system, str):
        return [{"label": _label(system), "bytes": len(system),
                 "tokens": est_tokens(len(system))}]
    entries = []
    for block in system:
        text = block.get("text", "") if isinstance(block, dict) else str(block)
        entries.append({"label": _label(text), "bytes": len(text),
                        "tokens": est_tokens(len(text))})
    return entries


def _texts_of(content) -> list[str]:
    """A message's content as one string per block. Pure."""
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
    return [str(content or "")]


def message_entries(request: dict) -> list[dict]:
    """One entry per content block. Pure.

    Not decoration, and not summed per message: the session CLAUDE.md, the agent
    catalog, the skill list and any SessionStart hook each arrive as their own
    block of the first user message. They are separately controllable, so they are
    attributed separately — and a report counting only tools + system would price
    all of them at zero.
    """
    entries = []
    for msg in request.get("messages") or []:
        role = msg.get("role", "?")
        for text in _texts_of(msg.get("content")):
            entries.append({"role": role, "label": _label(text),
                            "bytes": len(text), "tokens": est_tokens(len(text))})
    return entries


def summarize(request: dict) -> dict:
    """Full attribution for a captured request. Pure."""
    tools = tool_entries(request)
    groups = group_totals(tools)
    system = system_entries(request)
    messages = message_entries(request)
    tool_bytes = sum(e["bytes"] for e in tools)
    system_bytes = sum(e["bytes"] for e in system)
    message_bytes = sum(e["bytes"] for e in messages)
    total_bytes = tool_bytes + system_bytes + message_bytes
    return {
        "model": request.get("model", "?"),
        "tools": tools,
        "groups": groups,
        "system": system,
        "messages": messages,
        "totals": {
            "tool_count": len(tools),
            "tool_bytes": tool_bytes,
            "tool_tokens": est_tokens(tool_bytes),
            "system_bytes": system_bytes,
            "system_tokens": est_tokens(system_bytes),
            "message_bytes": message_bytes,
            "message_tokens": est_tokens(message_bytes),
            "total_bytes": total_bytes,
            "total_tokens": est_tokens(total_bytes),
        },
    }


def _row(label: str, n_bytes: int, tokens: int, width: int = 34) -> str:
    return f"  {label:<{width}} {n_bytes:>8,} B  ~{tokens:>6,} tok"


def render(summary: dict, top: int = 15) -> str:
    """Human-readable attribution report. Pure."""
    t = summary["totals"]
    out = [
        f"🦊 payload attribution — model {summary['model']}",
        f"   {t['tool_count']} tools · {t['tool_bytes']:,} tool bytes "
        f"(~{t['tool_tokens']:,} tok) · system ~{t['system_tokens']:,} tok "
        f"· messages ~{t['message_tokens']:,} tok · total ~{t['total_tokens']:,} tok",
        "",
        f"── eagerly loaded tools (top {top}) " + "─" * 12,
    ]
    out += [_row(e["name"], e["bytes"], e["tokens"]) for e in summary["tools"][:top]]
    if len(summary["tools"]) > top:
        rest = summary["tools"][top:]
        out.append(_row(f"… {len(rest)} more", sum(e["bytes"] for e in rest),
                        est_tokens(sum(e["bytes"] for e in rest))))
    out += ["", "── by source (compare to kits.yaml weights) " + "─" * 4]
    out += [_row(f"{g['group']}  ({g['count']} tools)", g["bytes"], g["tokens"])
            for g in summary["groups"]]
    if summary["system"]:
        out += ["", "── system prompt blocks " + "─" * 24]
        out += [_row(e["label"], e["bytes"], e["tokens"]) for e in summary["system"]]
    if summary["messages"]:
        out += ["", "── messages (CLAUDE.md, guardrails, rules) " + "─" * 5]
        out += [_row(f"{e['role']}: {e['label']}", e["bytes"], e["tokens"])
                for e in summary["messages"]]
    out += ["", f"   tokens estimated at {BYTES_PER_TOKEN} bytes/token; only "
                "eagerly-loaded tools are listed (deferred ones cost just a name)."]
    return "\n".join(out)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Attribute a captured API request by tool.")
    p.add_argument("capture", help="request JSON written by measure-proxy.py")
    p.add_argument("--top", type=int, default=15, help="how many tools to list")
    p.add_argument("--json", action="store_true", help="emit the summary as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        with open(ns.capture) as fh:
            request = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"tool-report: cannot read capture {ns.capture}: {exc}", file=sys.stderr)
        return 1
    summary = summarize(request)
    print(json.dumps(summary) if ns.json else render(summary, top=ns.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
