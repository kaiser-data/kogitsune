"""Pack diffing: current manifest vs target -> add / shed / model / weight delta."""


def manifest(items, model=None, weight=None):
    """Build a minimal build-config-shaped manifest. items: [(name, kind, weight)]."""
    entries = [{"name": n, "kind": k, "weight": w} for n, k, w in items]
    return {
        "kit": "test",
        "model": model,
        "items": entries,
        "weight": weight if weight is not None else sum(w for _, _, w in items),
    }


def test_add_only(packdiff):
    cur = manifest([("guardrails", "skill", 1000)])
    tgt = manifest([("guardrails", "skill", 1000), ("vue-patterns", "skill", 2100)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == ["vue-patterns"]
    assert d["shed"]["skills"] == []
    assert d["weight"]["delta"] == 2100
    assert d["noop"] is False


def test_shed_only(packdiff):
    cur = manifest([("guardrails", "skill", 1000), ("html-email", "skill", 4800)])
    tgt = manifest([("guardrails", "skill", 1000)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == []
    assert d["shed"]["skills"] == ["html-email"]
    assert d["weight"]["delta"] == -4800


def test_mixed_add_and_shed_separates_mcp_from_skills(packdiff):
    cur = manifest([("n8n", "skill", 3000), ("postgres", "mcp", 1800)])
    tgt = manifest([("vue-patterns", "skill", 2100), ("supabase", "mcp", 900)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"] == {"skills": ["vue-patterns"], "mcp": ["supabase"]}
    assert d["shed"] == {"skills": ["n8n"], "mcp": ["postgres"]}
    assert d["weight"] == {"current": 4800, "target": 3000, "delta": -1800}


def test_noop_when_packs_match(packdiff):
    cur = manifest([("guardrails", "skill", 1000)], model="sonnet")
    d = packdiff.diff_packs(cur, dict(cur))
    assert d["noop"] is True
    assert d["model"] is None
    assert d["weight"]["delta"] == 0


def test_model_change_reported_and_is_not_a_noop(packdiff):
    cur = manifest([("guardrails", "skill", 1000)], model="sonnet")
    tgt = manifest([("guardrails", "skill", 1000)], model="opus")
    d = packdiff.diff_packs(cur, tgt)
    assert d["model"] == {"from": "sonnet", "to": "opus"}
    assert d["noop"] is False


def test_same_name_in_both_kinds_is_not_confused(packdiff):
    """A skill and an MCP server may share a name; they are distinct pack entries."""
    cur = manifest([("supabase", "skill", 500)])
    tgt = manifest([("supabase", "mcp", 900)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["mcp"] == ["supabase"]
    assert d["shed"]["skills"] == ["supabase"]


def test_lists_are_sorted_for_determinism(packdiff):
    cur = manifest([])
    tgt = manifest([("zeta", "skill", 1), ("alpha", "skill", 1)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == ["alpha", "zeta"]


def test_duplicate_entries_collapse(packdiff):
    cur = manifest([])
    tgt = manifest([("vue", "skill", 100), ("vue", "skill", 100)])
    d = packdiff.diff_packs(cur, tgt)
    assert d["add"]["skills"] == ["vue"]


def test_weight_falls_back_to_item_sum_when_absent(packdiff):
    cur = {"items": [{"name": "a", "kind": "skill", "weight": 700}], "model": None}
    tgt = {"items": [], "model": None}
    d = packdiff.diff_packs(cur, tgt)
    assert d["weight"] == {"current": 700, "target": 0, "delta": -700}


def test_render_shows_adds_sheds_model_and_net(packdiff):
    cur = manifest([("n8n", "skill", 4800)], model="sonnet")
    tgt = manifest([("vue-patterns", "skill", 2100)], model="opus")
    out = packdiff.render(packdiff.diff_packs(cur, tgt))
    assert "+ vue-patterns" in out
    assert "- n8n" in out
    assert "sonnet -> opus" in out
    assert "net" in out


def test_render_noop_says_so(packdiff):
    cur = manifest([("guardrails", "skill", 1000)])
    out = packdiff.render(packdiff.diff_packs(cur, dict(cur)))
    assert "already optimal" in out
