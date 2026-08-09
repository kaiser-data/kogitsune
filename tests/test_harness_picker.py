"""Tests for exposing the harness axis through the picker and `kit save`.

The picker treats harness groups as ordinary rows: ✔ means the group is kept, ○ means
it is denied. A kit that declares no `harness:` seeds every group checked, so the
existing kits look unchanged until someone deliberately unchecks something.
"""
import copy
import json

import pytest


HARNESS = {
    "agents": {"tools": ["Workflow", "Agent"], "weight": 8653},
    "watch":  {"tools": ["Monitor"], "weight": 1915},
    "web":    {"tools": ["WebSearch"], "weight": 950},
}


@pytest.fixture
def cfg(config):
    c = copy.deepcopy(dict(config))
    c["harness"] = copy.deepcopy(HARNESS)
    c["kits"] = copy.deepcopy(c["kits"])
    c["kits"]["solo"] = {"mcp": [], "skills": [], "harness": ["web"]}
    return c


# ---- --list exposes the catalog the picker renders --------------------------

def test_list_emits_the_harness_catalog(buildcfg, cfg, servers, capsys, tmp_path):
    p = tmp_path / "k.yaml"
    p.write_text(json.dumps(cfg))  # JSON is valid YAML
    buildcfg.main(["--config", str(p), "--list"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["harness"]["agents"]["weight"] == 8653


def test_list_kit_info_carries_each_kit_harness(buildcfg, cfg, capsys, tmp_path):
    p = tmp_path / "k.yaml"
    p.write_text(json.dumps(cfg))
    buildcfg.main(["--config", str(p), "--list"])
    info = json.loads(capsys.readouterr().out)["kit_info"]
    assert info["solo"]["harness"] == ["web"]
    # a kit that declares none reports null, so the picker knows to check every box
    assert info["lean"]["harness"] is None


# ---- --harness drives an ad-hoc selection -----------------------------------

def test_harness_flag_selects_groups(buildcfg, cfg, servers):
    m = buildcfg.build(cfg, servers, kit=None, mcp_sel=[], skills_sel=[],
                       harness_sel=["web"])
    assert "Workflow" in m["deny"] and "WebSearch" not in m["deny"]


def test_split_parses_a_comma_list(buildcfg):
    assert buildcfg._split("agents,web") == ["agents", "web"]


def test_empty_harness_selection_denies_everything(buildcfg, cfg, servers):
    m = buildcfg.build(cfg, servers, kit=None, mcp_sel=[], skills_sel=[],
                       harness_sel=[])
    assert m["harness_saved"] == 8653 + 1915 + 950


def test_selecting_every_group_denies_nothing(buildcfg, cfg, servers):
    m = buildcfg.build(cfg, servers, kit=None, mcp_sel=[], skills_sel=[],
                       harness_sel=list(HARNESS))
    assert m["deny"] == [] and m["harness_saved"] == 0


# ---- saving a tuned pack keeps its harness ----------------------------------

def test_render_kit_entry_includes_harness(buildcfg):
    out = buildcfg.render_kit_entry("x", ["a"], ["b"], harness=["web", "agents"])
    assert "harness: [web, agents]" in out


def test_render_kit_entry_omits_harness_when_none(buildcfg):
    # None means "the kit said nothing" — writing an empty list would silently
    # deny every group on the next launch
    assert "harness" not in buildcfg.render_kit_entry("x", ["a"], ["b"])


def test_render_kit_entry_keeps_an_explicit_empty_list(buildcfg):
    assert "harness: []" in buildcfg.render_kit_entry("x", [], [], harness=[])
