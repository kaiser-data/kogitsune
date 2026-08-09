"""Tests for lib/context-est.py — pure pack-weight rendering.

The bar models a whole session, not just the catalog items: measured 2026-08-09, the
built-in harness and system prompt are ~35.7K before a single item is picked, and the
harness axis can deny ~22K of that. A bar that ignored both would misdescribe the
session by more than everything it did show.
"""


def test_human(ctxest):
    assert ctxest.human(950) == "950"
    assert ctxest.human(1000) == "1K"
    assert ctxest.human(12000) == "12K"
    assert ctxest.human(11300) == "11.3K"


# ---- bar rendering ----------------------------------------------------------

def test_render_at_baseline_is_empty_bar(ctxest):
    out = ctxest.render(ctxest.MIN_SESSION, baseline=ctxest.MIN_SESSION, width=10)
    assert "░" * 10 in out
    assert "▓" not in out


def test_render_at_full_is_full_bar(ctxest):
    out = ctxest.render(ctxest.BAR_FULL_AT, baseline=ctxest.MIN_SESSION,
                        width=10, full_at=ctxest.BAR_FULL_AT)
    assert "▓" * 10 in out


def test_render_clamps_over_full(ctxest):
    out = ctxest.render(999999, baseline=1200, width=8, full_at=30000)
    assert out.count("▓") == 8


def test_render_clamps_under_baseline(ctxest):
    # a heavily-denied session can fall below the modelled minimum; never render
    # a negative bar
    out = ctxest.render(1, baseline=1200, width=8, full_at=30000)
    assert out.count("▓") == 0


# ---- session total ----------------------------------------------------------

def test_session_total_adds_the_floor_to_the_items(ctxest):
    m = {"items": [{"weight": 10000}, {"weight": 2000}], "harness_saved": 0}
    assert ctxest.session_total(m) == ctxest.BASE_FLOOR + 12000


def test_session_total_subtracts_harness_savings(ctxest):
    m = {"items": [{"weight": 2350}], "harness_saved": 21231}
    assert ctxest.session_total(m) == ctxest.BASE_FLOOR + 2350 - 21231


def test_session_total_without_harness_key(ctxest):
    assert ctxest.session_total({"items": [{"weight": 500}]}) == ctxest.BASE_FLOOR + 500


def test_session_total_never_goes_negative(ctxest):
    m = {"items": [], "harness_saved": 10 ** 9}
    assert ctxest.session_total(m) == 0


def test_total_from_manifest_still_sums_items_only(ctxest):
    # kept for callers that want the catalog-only figure (kit ls, kit show)
    manifest = {"items": [{"weight": 10000}, {"weight": 2000}, {"weight": 0}]}
    assert ctxest.total_from_manifest(manifest) == 12000


# ---- constants are grounded in measurement ----------------------------------

def test_floor_is_above_the_minimum_session(ctxest):
    # the floor is what a session costs with nothing denied; the minimum is what
    # remains once the harness axis has denied everything it may
    assert ctxest.BASE_FLOOR > ctxest.MIN_SESSION > 0


def test_bar_ceiling_leaves_headroom_above_the_floor(ctxest):
    assert ctxest.BAR_FULL_AT > ctxest.BASE_FLOOR


# ---- cli --------------------------------------------------------------------

def test_main_weights_includes_the_floor(ctxest, capsys):
    rc = ctxest.main(["--weights", "10000", "2000"])
    out = capsys.readouterr().out
    assert rc == 0
    assert ctxest.human(ctxest.BASE_FLOOR + 12000) in out


def test_main_harness_saved_reduces_the_total(ctxest, capsys):
    ctxest.main(["--weights", "2350", "--harness-saved", "21231"])
    out = capsys.readouterr().out
    assert ctxest.human(ctxest.BASE_FLOOR + 2350 - 21231) in out


def test_main_json_reports_total_and_baseline(ctxest, capsys):
    import json
    ctxest.main(["--weights", "1000", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == ctxest.BASE_FLOOR + 1000
    assert payload["baseline"] == ctxest.MIN_SESSION
