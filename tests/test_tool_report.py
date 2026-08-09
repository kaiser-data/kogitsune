"""Tests for lib/tool-report.py — pure attribution over a captured API request."""

import json


def _req(tools=None, system=None):
    return {
        "model": "claude-haiku-4-5-20251001",
        "system": system if system is not None else "You are Claude Code.",
        "tools": tools or [],
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    }


def _tool(name, desc="x", schema=None):
    return {"name": name, "description": desc,
            "input_schema": schema or {"type": "object", "properties": {}}}


# ---- token estimation -------------------------------------------------------

def test_est_tokens_is_bytes_over_four(toolreport):
    assert toolreport.est_tokens(0) == 0
    assert toolreport.est_tokens(4) == 1
    assert toolreport.est_tokens(21229) == 5307  # Workflow, per the aihero.dev measurement
    assert toolreport.est_tokens(154948) == 38737


# ---- tool entries -----------------------------------------------------------

def test_tool_entries_measures_each_tool_serialized_size(toolreport):
    t = _tool("Bash", desc="run a command")
    entries = toolreport.tool_entries(_req([t]))
    assert len(entries) == 1
    assert entries[0]["name"] == "Bash"
    assert entries[0]["bytes"] == len(json.dumps(t))


def test_tool_entries_sorted_by_bytes_descending(toolreport):
    req = _req([_tool("Small", "x"), _tool("Huge", "y" * 500), _tool("Mid", "z" * 100)])
    names = [e["name"] for e in toolreport.tool_entries(req)]
    assert names == ["Huge", "Mid", "Small"]


def test_tool_entries_on_request_without_tools(toolreport):
    assert toolreport.tool_entries(_req()) == []


# ---- grouping ---------------------------------------------------------------

def test_builtin_tools_group_as_builtin(toolreport):
    entries = toolreport.tool_entries(_req([_tool("Workflow")]))
    assert entries[0]["group"] == "builtin"


def test_mcp_tools_group_by_server_id(toolreport):
    req = _req([_tool("mcp__supabase__list_tables"),
                _tool("mcp__plugin_ecc_chrome-devtools__click")])
    groups = {e["name"]: e["group"] for e in toolreport.tool_entries(req)}
    assert groups["mcp__supabase__list_tables"] == "mcp:supabase"
    assert groups["mcp__plugin_ecc_chrome-devtools__click"] == "mcp:plugin_ecc_chrome-devtools"


def test_group_totals_aggregates_and_counts(toolreport):
    req = _req([_tool("mcp__supabase__a", "y" * 200),
                _tool("mcp__supabase__b", "y" * 200),
                _tool("Bash", "x")])
    totals = {g["group"]: g for g in toolreport.group_totals(toolreport.tool_entries(req))}
    assert totals["mcp:supabase"]["count"] == 2
    assert totals["builtin"]["count"] == 1
    assert totals["mcp:supabase"]["bytes"] > totals["builtin"]["bytes"]


def test_group_totals_sorted_by_bytes_descending(toolreport):
    req = _req([_tool("Bash", "x" * 400), _tool("mcp__tiny__a", "y")])
    assert [g["group"] for g in toolreport.group_totals(toolreport.tool_entries(req))] \
        == ["builtin", "mcp:tiny"]


# ---- system blocks ----------------------------------------------------------

def test_system_entries_from_plain_string(toolreport):
    entries = toolreport.system_entries(_req(system="hello world"))
    assert len(entries) == 1
    assert entries[0]["bytes"] == len("hello world")


def test_system_entries_from_block_list_labels_by_first_line(toolreport):
    system = [{"type": "text", "text": "# Harness\nrest of it"},
              {"type": "text", "text": "# Skills\nmore"}]
    labels = [e["label"] for e in toolreport.system_entries(_req(system=system))]
    assert labels == ["# Harness", "# Skills"]


def test_system_entries_truncates_long_labels(toolreport):
    entries = toolreport.system_entries(_req(system=[{"type": "text", "text": "z" * 200}]))
    assert len(entries[0]["label"]) <= toolreport.LABEL_MAX


def test_system_entries_on_missing_system(toolreport):
    assert toolreport.system_entries({"tools": []}) == []


# ---- message blocks ---------------------------------------------------------
# CLAUDE.md imports and rules packs ride in as messages, not system blocks — a
# report that skips them scores every kit as if its guardrails were free.

def test_message_entries_measure_string_content(toolreport):
    req = _req()
    req["messages"] = [{"role": "user", "content": "hello there"}]
    entries = toolreport.message_entries(req)
    assert entries[0]["role"] == "user"
    assert entries[0]["bytes"] == len("hello there")


def test_message_entries_split_block_content_per_block(toolreport):
    # each block is a distinct cost centre (agent catalog, skill list, CLAUDE.md),
    # so they must be attributed separately rather than summed into one row
    req = _req()
    req["messages"] = [{"role": "user", "content": [
        {"type": "text", "text": "aaa"}, {"type": "text", "text": "bbbb"}]}]
    entries = toolreport.message_entries(req)
    assert [e["bytes"] for e in entries] == [3, 4]


def test_message_entries_label_by_first_line(toolreport):
    req = _req()
    req["messages"] = [{"role": "user", "content": "# Guardrails\nrest"}]
    assert toolreport.message_entries(req)[0]["label"] == "# Guardrails"


def test_label_skips_wrapper_tags_so_blocks_stay_distinguishable(toolreport):
    req = _req()
    req["messages"] = [{"role": "user", "content": [
        {"type": "text", "text": "<system-reminder>\nAvailable agent types:\n- x"},
        {"type": "text", "text": "<system-reminder>\nThe following skills:\n- y"}]}]
    labels = [e["label"] for e in toolreport.message_entries(req)]
    assert labels == ["Available agent types:", "The following skills:"]


def test_label_falls_back_to_the_tag_when_that_is_all_there_is(toolreport):
    assert toolreport._label("<system-reminder>") == "<system-reminder>"


def test_message_entries_on_missing_messages(toolreport):
    assert toolreport.message_entries({"tools": []}) == []


# ---- summary ----------------------------------------------------------------

def test_summarize_totals_cover_tools_system_and_messages(toolreport):
    req = _req([_tool("Bash", "x" * 100)], system="s" * 40)
    s = toolreport.summarize(req)
    t = s["totals"]
    assert t["tool_count"] == 1
    assert t["tool_bytes"] == sum(e["bytes"] for e in s["tools"])
    assert t["system_bytes"] == 40
    assert t["message_bytes"] == sum(e["bytes"] for e in s["messages"])
    assert t["total_bytes"] == t["tool_bytes"] + t["system_bytes"] + t["message_bytes"]


def test_summarize_is_json_serializable(toolreport):
    json.dumps(toolreport.summarize(_req([_tool("Bash")])))


# ---- rendering --------------------------------------------------------------

def test_render_includes_totals_and_top_tool(toolreport):
    req = _req([_tool("Workflow", "w" * 900), _tool("Bash", "b" * 10)])
    out = toolreport.render(toolreport.summarize(req))
    assert "Workflow" in out
    assert "2 tools" in out


def test_render_respects_top_limit(toolreport):
    req = _req([_tool(f"T{i}", "x" * (100 - i)) for i in range(10)])
    out = toolreport.render(toolreport.summarize(req), top=3)
    assert "T0" in out and "T9" not in out
