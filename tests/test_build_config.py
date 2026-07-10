"""Tests for lib/build-config.py — pure selection -> manifest logic."""
import pytest


# --- kit resolution ---------------------------------------------------------

def test_resolve_kit_basic(buildcfg, config):
    sel = buildcfg.resolve_kit("db", config["kits"])
    assert sel == {"mcp": ["supabase"], "skills": ["postgres-bp"], "model": "opus"}


def test_resolve_kit_extends_add(buildcfg, config):
    sel = buildcfg.resolve_kit("db-heavy", config["kits"])
    assert sel["mcp"] == ["supabase", "notion"]
    assert sel["skills"] == ["postgres-bp"]  # inherited


def test_resolve_kit_extends_remove_and_add(buildcfg, config):
    sel = buildcfg.resolve_kit("trimmed", config["kits"])
    assert sel["mcp"] == ["inliney"]      # supabase removed, inliney added
    assert sel["skills"] == []            # postgres-bp removed


def test_resolve_kit_unknown_suggests(buildcfg, config):
    with pytest.raises(KeyError) as e:
        buildcfg.resolve_kit("dbb", config["kits"])
    assert "did you mean 'db'" in str(e.value)


def test_resolve_kit_circular(buildcfg):
    kits = {"a": {"extends": "b"}, "b": {"extends": "a"}}
    with pytest.raises(ValueError):
        buildcfg.resolve_kit("a", kits)


def test_apply_delta_order_preserved(buildcfg):
    assert buildcfg._apply_delta(["x"], ["y", "+z", "-x"]) == ["y", "z"]


# --- model selection --------------------------------------------------------

def test_kit_model_in_manifest(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="db", mcp_sel=None, skills_sel=None)
    assert m["model"] == "opus"


def test_kit_model_inherited_via_extends(buildcfg, config):
    assert buildcfg.resolve_kit("db-heavy", config["kits"])["model"] == "opus"


def test_kit_model_child_overrides_parent(buildcfg, config):
    assert buildcfg.resolve_kit("trimmed", config["kits"])["model"] == "haiku"


def test_model_none_when_unset(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="lean", mcp_sel=None, skills_sel=None)
    assert m["model"] is None


def test_model_override_beats_kit(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="db", mcp_sel=None, skills_sel=None, model="sonnet")
    assert m["model"] == "sonnet"  # picker override wins over the kit's opus


def test_render_kit_entry_includes_model(buildcfg):
    out = buildcfg.render_kit_entry("x", ["a"], ["b"], model="opus")
    assert "model: opus" in out and "mcp: [a]" in out
    assert "model" not in buildcfg.render_kit_entry("x", ["a"], ["b"])


# --- full build -------------------------------------------------------------

def test_build_db_kit(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="db", mcp_sel=None, skills_sel=None)
    # pinned memory plugin + selected postgres plugin both enabled
    assert m["plugins"]["claude-mem@thedotmack"] is True
    assert m["plugins"]["postgres-best-practices@supabase-agent-skills"] is True
    # strict mcp-config carries only supabase, resolved from mcp-on-demand
    assert list(m["mcp_config"]["mcpServers"]) == ["supabase"]
    assert m["mcp_config"]["mcpServers"]["supabase"]["command"] == "mcp-server-supabase"
    # pinned skill graphify symlinked + pinned guardrails imported
    assert any(s.endswith("/graphify") for s in m["skills"])
    assert any(p.endswith("RULES.md") for p in m["imports"])
    assert m["weight"] == 12000  # 10000 supabase + 2000 postgres
    assert m["warnings"] == []


def test_build_lean_is_empty_but_pinned(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="lean", mcp_sel=None, skills_sel=None)
    assert m["mcp_config"]["mcpServers"] == {}
    assert m["weight"] == 0
    assert m["plugins"]["claude-mem@thedotmack"] is True  # memory still rides along


def test_build_inline_mcp_def(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="trimmed", mcp_sel=None, skills_sel=None)
    assert m["mcp_config"]["mcpServers"]["inliney"] == {"command": "foo", "args": ["--bar"]}


def test_build_dir_and_prefix_globs(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit=None, mcp_sel=[], skills_sel=["n8n", "sc-commands"])
    skills = " ".join(m["skills"])
    assert "n8n-code" in skills and "n8n-validate" in skills
    assert "sc-analyze" in skills and "sc-build" in skills


def test_build_unknown_ref_warns(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit=None, mcp_sel=["supabse"], skills_sel=[])
    assert any("did you mean 'supabase'" in w for w in m["warnings"])


def test_build_rules_pack_folds_into_imports(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="ruled", mcp_sel=None, skills_sel=None)
    imported = " ".join(m["imports"])
    assert "style.md" in imported and "workflow.md" in imported  # every *.md in the pack
    assert m["warnings"] == []
    assert m["weight"] == 1000


def test_rules_pack_missing_warns(buildcfg):
    warnings = []
    e = buildcfg.resolve_item("ghost", {"rules": "no-such-pack"}, {}, warnings)
    assert e["paths"] == []
    assert any("no *.md" in w for w in warnings)


def test_plugin_gate_mcp_folds_into_exclude(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="gated", mcp_sel=None, skills_sel=None)
    assert m["plugin_mcp_exclude"] == ["heavy@heavymp"]
    assert m["plugins"]["heavy@heavymp"] is True  # plugin still enabled; only its MCP gated
    assert m["warnings"] == []


def test_plugin_without_gate_mcp_not_excluded(buildcfg, config, servers):
    m = buildcfg.build(config, servers, kit="db", mcp_sel=None, skills_sel=None)
    assert m["plugin_mcp_exclude"] == []


def test_deep_merge_overlay(buildcfg):
    base = {"kits": {"db": {"mcp": ["supabase"]}}, "catalog": {"mcp": {"a": {}}}}
    over = {"kits": {"x": {"mcp": []}}}
    merged = buildcfg.deep_merge(base, over)
    assert "db" in merged["kits"] and "x" in merged["kits"]
    assert merged["catalog"]["mcp"]["a"] == {}


def test_kind_of(buildcfg):
    assert buildcfg.kind_of({"plugin": "p"}) == "plugin"
    assert buildcfg.kind_of({"weight": 1}) is None
