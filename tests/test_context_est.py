"""Tests for lib/context-est.py — pure pack-weight rendering."""


def test_human(ctxest):
    assert ctxest.human(950) == "950"
    assert ctxest.human(1000) == "1K"
    assert ctxest.human(12000) == "12K"
    assert ctxest.human(11300) == "11.3K"


def test_render_at_baseline_is_empty_bar(ctxest):
    out = ctxest.render(ctxest.LEAN_BASELINE, baseline=ctxest.LEAN_BASELINE, width=10)
    assert "░" * 10 in out
    assert "▓" not in out


def test_render_at_full_is_full_bar(ctxest):
    out = ctxest.render(ctxest.BAR_FULL_AT, baseline=ctxest.LEAN_BASELINE,
                        width=10, full_at=ctxest.BAR_FULL_AT)
    assert "▓" * 10 in out


def test_render_clamps_over_full(ctxest):
    out = ctxest.render(999999, baseline=1200, width=8, full_at=30000)
    assert out.count("▓") == 8


def test_total_from_manifest(ctxest):
    manifest = {"items": [{"weight": 10000}, {"weight": 2000}, {"weight": 0}]}
    assert ctxest.total_from_manifest(manifest) == 12000


def test_main_weights(ctxest, capsys):
    rc = ctxest.main(["--weights", "10000", "2000", "--baseline", "1200"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "13.2K" in out  # 1200 + 12000
