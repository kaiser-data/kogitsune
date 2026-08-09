"""Tests for lib/leak-scan.py — ancestor context that bypasses the session mirror."""


def _tree(tmp_path, *rel_files):
    for rel in rel_files:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x" * 400)
    return tmp_path


# ---- ancestor walk ----------------------------------------------------------

def test_ancestors_walks_up_to_and_including_root(leakscan, tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    found = leakscan.ancestors(str(deep), stop=str(tmp_path))
    assert str(deep) in found and str(tmp_path) in found


def test_ancestors_stops_at_the_boundary(leakscan, tmp_path):
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    found = leakscan.ancestors(str(deep), stop=str(tmp_path / "a"))
    assert str(tmp_path) not in found


# ---- what leaks -------------------------------------------------------------

def test_finds_ancestor_claude_md(leakscan, tmp_path):
    _tree(tmp_path, "CLAUDE.md")
    proj = tmp_path / "proj"
    proj.mkdir()
    hits = leakscan.scan(str(proj), stop=str(tmp_path))
    assert any(h["path"].endswith("CLAUDE.md") for h in hits)


def test_finds_ancestor_dot_claude_md_and_rules(leakscan, tmp_path):
    _tree(tmp_path, ".claude/CLAUDE.md", ".claude/rules/pack/a.md",
          ".claude/rules/pack/b.md")
    proj = tmp_path / "proj"
    proj.mkdir()
    kinds = {h["kind"] for h in leakscan.scan(str(proj), stop=str(tmp_path))}
    assert kinds == {"claude_md", "rules"}


def test_rules_hit_aggregates_every_file(leakscan, tmp_path):
    _tree(tmp_path, ".claude/rules/pack/a.md", ".claude/rules/pack/b.md")
    proj = tmp_path / "proj"
    proj.mkdir()
    rules = [h for h in leakscan.scan(str(proj), stop=str(tmp_path))
             if h["kind"] == "rules"][0]
    assert rules["count"] == 2
    assert rules["bytes"] == 800


def test_clean_tree_reports_nothing(leakscan, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    assert leakscan.scan(str(proj), stop=str(tmp_path)) == []


def test_ignores_the_cwd_itself(leakscan, tmp_path):
    # a project's own CLAUDE.md is intended context, not a leak
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "CLAUDE.md").write_text("mine")
    assert leakscan.scan(str(proj), stop=str(tmp_path)) == []


# ---- reporting --------------------------------------------------------------

def test_total_tokens_sums_every_hit(leakscan, tmp_path):
    _tree(tmp_path, "CLAUDE.md", ".claude/rules/pack/a.md")
    proj = tmp_path / "proj"
    proj.mkdir()
    hits = leakscan.scan(str(proj), stop=str(tmp_path))
    assert leakscan.total_tokens(hits) == sum(h["tokens"] for h in hits)


def test_render_is_quiet_when_clean(leakscan):
    assert leakscan.render([]) == ""


def test_render_names_the_biggest_source(leakscan, tmp_path):
    _tree(tmp_path, ".claude/rules/pack/a.md")
    proj = tmp_path / "proj"
    proj.mkdir()
    out = leakscan.render(leakscan.scan(str(proj), stop=str(tmp_path)))
    assert "rules" in out and "mirror" in out.lower()


def test_render_declares_itself_an_upper_bound(leakscan, tmp_path):
    # a rules/ tree is reported whole though only part may load — never imply otherwise
    _tree(tmp_path, ".claude/rules/pack/a.md")
    proj = tmp_path / "proj"
    proj.mkdir()
    out = leakscan.render(leakscan.scan(str(proj), stop=str(tmp_path)))
    assert "Upper bound" in out and "up to" in out


# ---- migration detection ----------------------------------------------------

def test_leaks_by_location_true_inside_a_dot_claude_dir(leakscan):
    assert leakscan.leaks_by_location("/Users/x/.claude/rules")


def test_leaks_by_location_true_when_nested_deeper(leakscan):
    assert leakscan.leaks_by_location("/Users/x/.claude/rules/ecc/common")


def test_leaks_by_location_false_for_a_sibling_dir(leakscan):
    # verified empirically 2026-08-09 with a positive control: a .claude/rules canary
    # leaked, a .claude-rules canary did not
    assert not leakscan.leaks_by_location("/Users/x/.claude-rules")


def test_leaks_by_location_false_for_an_unrelated_path(leakscan):
    assert not leakscan.leaks_by_location("/opt/rules")


def test_migration_hint_names_the_source_and_destination(leakscan):
    out = leakscan.migration_hint("/Users/x/.claude/rules")
    assert "/Users/x/.claude/rules" in out
    assert leakscan.SUGGESTED_ROOT in out
    assert "rules_root:" in out


def test_migration_hint_is_empty_when_already_migrated(leakscan):
    assert leakscan.migration_hint("/Users/x/.claude-rules") == ""


def test_migration_hint_keeps_guardrails_in_place(leakscan):
    # moving guardrails.md too would break @rules/guardrails.md in the global
    # CLAUDE.md and silently drop guardrails from every non-kit session
    assert "guardrails.md" in leakscan.migration_hint("/Users/x/.claude/rules")


def test_residual_is_still_reported_after_migration(leakscan, tmp_path):
    # the post-migration state: packs moved out, but an ancestor CLAUDE.md and a
    # guardrails-only rules dir remain. The scan must NOT report zero — claiming
    # victory here would hide ~719 tok that this fix cannot remove.
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "guardrails.md").write_text("g" * 1500)
    (tmp_path / ".claude" / "CLAUDE.md").write_text("c" * 700)
    proj = tmp_path / "proj"
    proj.mkdir()
    hits = leakscan.scan(str(proj), stop=str(tmp_path))
    assert leakscan.total_tokens(hits) > 0
    assert leakscan.render(hits) != ""
