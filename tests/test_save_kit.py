"""Tests for lib/build-config.py save_kit_text — comment-preserving kit insert."""

SAMPLE = """\
# my kits
pinned:
  memory: { plugin: "claude-mem@thedotmack" }

kits:
  lean: { mcp: [], skills: [] }
  db:   { mcp: [supabase], skills: [postgres-bp] }
"""


def test_render_entry(buildcfg):
    assert buildcfg.render_kit_entry("x", ["a", "b"], ["c"]) == \
        "  x: { mcp: [a, b], skills: [c] }"


def test_insert_new_kit_preserves_comments_and_kits(buildcfg):
    out = buildcfg.save_kit_text(SAMPLE, "mine", ["notion"], ["frontend-design"])
    assert "# my kits" in out                 # comment preserved
    assert "lean: { mcp: [], skills: [] }" in out
    assert "  mine: { mcp: [notion], skills: [frontend-design] }" in out


def test_replace_existing_kit(buildcfg):
    out = buildcfg.save_kit_text(SAMPLE, "db", ["notion"], [])
    assert "  db: { mcp: [notion], skills: [] }" in out
    assert "supabase" not in out              # old db line replaced
    assert out.count("db:") == 1


def test_no_kits_block_appends_one(buildcfg):
    out = buildcfg.save_kit_text("pinned:\n  memory: {}\n", "solo", [], [])
    assert "kits:" in out
    assert "  solo: { mcp: [], skills: [] }" in out


def test_roundtrips_to_valid_yaml(buildcfg):
    import yaml
    out = buildcfg.save_kit_text(SAMPLE, "mine", ["notion"], ["frontend-design"])
    data = yaml.safe_load(out)
    assert data["kits"]["mine"] == {"mcp": ["notion"], "skills": ["frontend-design"]}
    assert "db" in data["kits"] and "lean" in data["kits"]


def test_remove_kit(buildcfg):
    import yaml
    out, removed = buildcfg.remove_kit_text(SAMPLE, "db")
    assert removed is True
    data = yaml.safe_load(out)
    assert "db" not in data["kits"]
    assert "lean" in data["kits"]          # siblings intact
    assert "# my kits" in out              # comments preserved


def test_remove_missing_kit_is_noop(buildcfg):
    out, removed = buildcfg.remove_kit_text(SAMPLE, "nope")
    assert removed is False
    assert out == SAMPLE


def test_save_then_remove_roundtrip(buildcfg):
    import yaml
    saved = buildcfg.save_kit_text(SAMPLE, "tmp", ["notion"], [])
    out, removed = buildcfg.remove_kit_text(saved, "tmp")
    assert removed is True
    assert "tmp" not in yaml.safe_load(out)["kits"]
