"""Tests for the harness axis — denying built-in tool schemas per kit.

The built-in tools are the largest single block in a session (~27.6K measured) and were
the one axis the catalog could not touch. A kit opts in with `harness: [group, ...]`,
an allowlist of optional groups; omitting the key changes nothing.
"""
import copy

import pytest


HARNESS = {
    "agents":  {"tools": ["Workflow", "Agent", "SendMessage"], "weight": 8653},
    "watch":   {"tools": ["Monitor"], "weight": 1915},
    "cron":    {"tools": ["CronCreate", "CronList"], "weight": 1000},
}


@pytest.fixture
def cfg(config):
    # deep-copied: tests that add a group must not mutate the shared literal
    c = copy.deepcopy(dict(config))
    c["harness"] = copy.deepcopy(HARNESS)
    return c


def _build(buildcfg, cfg, servers, **kw):
    kw.setdefault("kit", None)
    kw.setdefault("mcp_sel", [])
    kw.setdefault("skills_sel", [])
    return buildcfg.build(cfg, servers, **kw)


# ---- group resolution -------------------------------------------------------

def test_no_harness_key_denies_nothing(buildcfg, cfg, servers):
    # backward compatibility: every existing kit must be untouched
    assert _build(buildcfg, cfg, servers)["deny"] == []


def test_allowlist_denies_the_groups_not_named(buildcfg, cfg, servers):
    m = _build(buildcfg, cfg, servers, harness_sel=["agents"])
    assert "Monitor" in m["deny"]
    assert "CronCreate" in m["deny"]
    assert "Workflow" not in m["deny"]


def test_empty_allowlist_denies_every_optional_group(buildcfg, cfg, servers):
    deny = set(_build(buildcfg, cfg, servers, harness_sel=[])["deny"])
    assert deny == {"Workflow", "Agent", "SendMessage", "Monitor",
                    "CronCreate", "CronList"}


def test_deny_list_is_sorted_and_deduped(buildcfg, cfg, servers):
    cfg["harness"]["dup"] = {"tools": ["Monitor", "Monitor"], "weight": 1}
    deny = _build(buildcfg, cfg, servers, harness_sel=[])["deny"]
    assert deny == sorted(set(deny))


def test_unknown_group_warns_and_denies_nothing_extra(buildcfg, cfg, servers):
    m = _build(buildcfg, cfg, servers, harness_sel=["nope"])
    assert any("nope" in w for w in m["warnings"])
    assert "Workflow" in m["deny"]


# ---- essentials are never deniable ------------------------------------------

def test_essential_tools_are_never_denied(buildcfg, cfg, servers):
    # a group that names an essential must not be able to strip it: losing Bash or
    # Read would break the session outright, and settings.json needs a restart to undo
    cfg["harness"]["reckless"] = {"tools": ["Bash", "Read", "Monitor"], "weight": 1}
    deny = _build(buildcfg, cfg, servers, harness_sel=[])["deny"]
    assert "Bash" not in deny and "Read" not in deny
    assert "Monitor" in deny


def test_essentials_constant_covers_the_edit_write_loop(buildcfg):
    for t in ("Bash", "Read", "Edit", "Write", "Skill"):
        assert t in buildcfg.ESSENTIAL_TOOLS


# ---- weight accounting ------------------------------------------------------

def test_denied_groups_subtract_from_the_pack_weight(buildcfg, cfg, servers):
    full = _build(buildcfg, cfg, servers)["harness_saved"]
    lean = _build(buildcfg, cfg, servers, harness_sel=[])["harness_saved"]
    assert full == 0
    assert lean == 8653 + 1915 + 1000


def test_kept_group_is_not_counted_as_saved(buildcfg, cfg, servers):
    m = _build(buildcfg, cfg, servers, harness_sel=["agents"])
    assert m["harness_saved"] == 1915 + 1000


# ---- kit wiring -------------------------------------------------------------

def test_kit_declares_harness_and_it_resolves(buildcfg, cfg, servers):
    cfg["kits"]["solo"] = {"mcp": [], "skills": [], "harness": []}
    assert "Workflow" in _build(buildcfg, cfg, servers, kit="solo")["deny"]


def test_harness_is_inherited_through_extends(buildcfg, cfg, servers):
    cfg["kits"]["solo"] = {"mcp": [], "skills": [], "harness": []}
    cfg["kits"]["solo2"] = {"extends": "solo"}
    assert "Workflow" in _build(buildcfg, cfg, servers, kit="solo2")["deny"]


def test_child_harness_overrides_the_parent(buildcfg, cfg, servers):
    cfg["kits"]["solo"] = {"mcp": [], "skills": [], "harness": []}
    cfg["kits"]["team"] = {"extends": "solo", "harness": ["agents"]}
    deny = _build(buildcfg, cfg, servers, kit="team")["deny"]
    assert "Workflow" not in deny and "Monitor" in deny
