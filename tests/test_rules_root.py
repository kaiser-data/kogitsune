"""Tests for rules_root precedence — config > env > default.

Config must beat env so a committed kits.yaml resolves the same paths on a
teammate's machine without them setting anything in their shell.
"""
import os


def test_default_when_nothing_is_set(buildcfg, monkeypatch):
    monkeypatch.delenv("KOGITSUNE_RULES_DIR", raising=False)
    assert buildcfg.rules_root() == buildcfg.expand(buildcfg.DEFAULT_RULES_ROOT)


def test_env_overrides_the_default(buildcfg, monkeypatch):
    monkeypatch.setenv("KOGITSUNE_RULES_DIR", "/env/rules")
    assert buildcfg.rules_root() == "/env/rules"


def test_config_beats_env(buildcfg, monkeypatch):
    monkeypatch.setenv("KOGITSUNE_RULES_DIR", "/env/rules")
    assert buildcfg.rules_root({"rules_root": "/cfg/rules"}) == "/cfg/rules"


def test_config_value_is_expanded(buildcfg, monkeypatch):
    monkeypatch.delenv("KOGITSUNE_RULES_DIR", raising=False)
    assert buildcfg.rules_root({"rules_root": "~/x"}) == os.path.expanduser("~/x")


def test_empty_config_value_falls_through_to_env(buildcfg, monkeypatch):
    monkeypatch.setenv("KOGITSUNE_RULES_DIR", "/env/rules")
    assert buildcfg.rules_root({"rules_root": ""}) == "/env/rules"


def test_build_resolves_a_rules_pack_from_the_configured_root(
        buildcfg, config, servers, tmp_path):
    # conftest points the env at the fixture rules dir; config must win anyway
    pack = tmp_path / "ecc-common"
    pack.mkdir()
    (pack / "a.md").write_text("# a")
    cfg = dict(config)
    cfg["rules_root"] = str(tmp_path)
    m = buildcfg.build(cfg, servers, kit=None, mcp_sel=[], skills_sel=["ecc-rules"])
    assert str(pack / "a.md") in m["imports"]
    # scoped to the rules pack: unrelated pinned items may warn for their own reasons
    assert not [w for w in m["warnings"] if "rules pack" in w]
