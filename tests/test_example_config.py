"""Guards on the *shipped* examples/kits.example.yaml.

The fixture config in tests/fixtures exercises the resolver's logic; this file
checks the config users actually copy. The live kits.yaml is gitignored, so the
example is the only config CI can see — and it drifting is a real failure mode.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "kits.example.yaml"


@pytest.fixture(scope="module")
def example(buildcfg):
    return buildcfg.load_yaml(str(EXAMPLE))


def _resolved(buildcfg, example):
    """{kit name -> resolved selection} for every kit in the example config."""
    return {name: buildcfg.resolve_kit(name, example["kits"]) for name in example["kits"]}


def test_example_config_parses(example):
    assert example["catalog"]["mcp"] and example["catalog"]["skills"]
    assert example["kits"], "example config ships no kits"


def test_every_kit_resolves(buildcfg, example):
    # catches a dangling `extends:`, a cycle, or a "+name" delta on a missing base
    for name, sel in _resolved(buildcfg, example).items():
        assert isinstance(sel["mcp"], list), name
        assert isinstance(sel["skills"], list), name


def test_kits_only_reference_known_catalog_entries(buildcfg, example):
    for name, sel in _resolved(buildcfg, example).items():
        for kind in ("mcp", "skills"):
            unknown = set(sel[kind]) - set(example["catalog"][kind])
            assert not unknown, f"kit '{name}' references unknown {kind}: {sorted(unknown)}"


def test_no_plugin_entry_is_dead_weight(buildcfg, example):
    """Every plugin-backed catalog entry must be claimed by at least one kit.

    Regression guard for the ponytail bug (fixed 554f1d7): a plugin entry that no
    kit references can't be gated by kit selection, so it just stays enabled in the
    *global* settings and taxes every session — the opposite of what the catalog
    toggle implies. Non-plugin entries (dirs, rules, inline MCP defs) cost nothing
    while unselected, so only plugins are held to this rule.
    """
    claimed = {"mcp": set(), "skills": set()}
    for sel in _resolved(buildcfg, example).values():
        for kind in ("mcp", "skills"):
            claimed[kind].update(sel[kind])

    dead = [
        f"{kind}.{entry}"
        for kind in ("mcp", "skills")
        for entry, spec in example["catalog"][kind].items()
        if buildcfg.kind_of(spec) == "plugin" and entry not in claimed[kind]
    ]
    assert not dead, f"plugin entries referenced by no kit (dead weight): {dead}"


def test_ponytail_is_kit_gated_not_global(buildcfg, example):
    """ponytail's hooks are a standing cost, so it rides in specific kits only."""
    spec = example["catalog"]["skills"]["ponytail"]
    assert buildcfg.kind_of(spec) == "plugin"
    assert spec["plugin"] == "ponytail@ponytail"

    resolved = _resolved(buildcfg, example)
    carriers = {n for n, sel in resolved.items() if "ponytail" in sel["skills"]}
    assert carriers == {"build", "feature"}, f"unexpected ponytail carriers: {carriers}"
    assert "ponytail" not in resolved["lean"]["skills"]


def test_ponytail_resolves_into_the_manifest_plugin_set(buildcfg, example):
    """End to end: picking `build` must put the plugin id in the session's plugin set."""
    import json
    servers = json.loads(
        (ROOT / "tests" / "fixtures" / "mcp-on-demand.json").read_text()
    )["mcpServers"]
    m = buildcfg.build(example, servers, kit="build", mcp_sel=None, skills_sel=None)
    assert "ponytail@ponytail" in m["plugins"]

    lean = buildcfg.build(example, servers, kit="lean", mcp_sel=None, skills_sel=None)
    assert "ponytail@ponytail" not in lean["plugins"]
