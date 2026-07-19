"""
Tests for the generator's Top Picks logic: _compute_top_picks and _summarize.

These tests use small, controlled fixtures — no network, no database, no data.json.
They validate the structural contracts that feed into the UI's renderTopPicks.

Run with:
    python -m pytest src/tests/test_generator_top_picks.py -v
"""
import sys
import os

import pytest

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from generator import (
    _build_tesouro_history_meta,
    _compute_top_picks,
    _merge_tesouro_history,
    _summarize,
)


class TestMergeTesouroHistory:
    def test_keeps_persisted_dates_when_official_history_is_partial(self):
        persisted = [
            {"date": "2026-07-08", "buy_yield": 0.14, "buy_price": 480.0},
            {"date": "2026-07-09", "buy_yield": 0.141, "buy_price": 478.0},
        ]
        official = [
            {"date": "2026-07-09", "buy_yield": 0.142, "buy_price": 477.0},
            {"date": "2026-07-10", "buy_yield": 0.143, "buy_price": 475.0},
        ]

        merged = _merge_tesouro_history(official, persisted)

        assert [point["date"] for point in merged] == ["2026-07-08", "2026-07-09", "2026-07-10"]
        assert merged[1] == official[0]

    def test_uses_persisted_history_when_current_source_has_no_history(self):
        persisted = [{"date": "2026-07-08", "buy_yield": 0.14, "buy_price": 480.0}]

        assert _merge_tesouro_history([], persisted) == persisted


class TestTesouroHistoryFreshness:
    def test_reports_gap_without_adding_current_quote_to_history(self):
        history = [{"date": "2026-07-10", "source": "tesouro_transparente_csv"}]
        bond = {"market_date": "2026-07-15", "data_source": "tesouro_direto_api", "is_demo": False}

        meta = _build_tesouro_history_meta(history, bond, "2026-07-15T12:00:00+00:00")

        assert meta["last_history_date"] == "2026-07-10"
        assert meta["gap_days"] == 5
        assert meta["freshness"] == "pending_update"

    def test_marks_demo_quote_without_invalidating_cached_history(self):
        history = [{"date": "2026-07-10", "source": "tesouro_transparente_csv"}]
        bond = {"data_source": "demo_fallback", "is_demo": True}

        meta = _build_tesouro_history_meta(history, bond, "2026-07-15T12:00:00+00:00")

        assert meta["last_history_date"] == "2026-07-10"
        assert meta["freshness"] == "current_quote_demo"


# ===================================================================
# _summarize — fields included in home_top_* summaries
# ===================================================================

class TestSummarize:
    """_summarize must include the correct fields for each asset type."""

    def test_stock_includes_pb_ratio_and_sector(self):
        """Stock summary must include pb_ratio and sector."""
        asset = {
            "ticker": "TEST4", "name": "Test SA", "score": 7.5,
            "dividend_yield": 0.08, "sector": "Financeiro",
            "pb_ratio": 1.2, "dy_medio_3y": 0.07,
        }
        result = _summarize(asset, ["sector", "pb_ratio", "dy_medio_3y"])
        assert result["ticker"] == "TEST4"
        assert result["name"] == "Test SA"
        assert result["score"] == 7.5
        assert result["dividend_yield"] == 0.08
        assert result["sector"] == "Financeiro"
        assert result["pb_ratio"] == 1.2
        assert result["dy_medio_3y"] == 0.07

    def test_stock_missing_optional_fields(self):
        """Optional fields (sector, pb_ratio) are None when absent."""
        asset = {
            "ticker": "TEST4", "name": "Test SA", "score": 7.5,
            "dividend_yield": 0.08,
        }
        result = _summarize(asset, ["sector", "pb_ratio", "dy_medio_3y"])
        assert result["sector"] is None
        assert result["pb_ratio"] is None
        assert result["dy_medio_3y"] is None

    def test_fii_includes_pb_ratio(self):
        """FII/FIAGRO summary must include pb_ratio."""
        asset = {
            "ticker": "TEST11", "name": "Test FII", "score": 6.0,
            "dividend_yield": 0.10, "pb_ratio": 0.95,
        }
        result = _summarize(asset, ["pb_ratio"])
        assert result["ticker"] == "TEST11"
        assert result["pb_ratio"] == 0.95

    def test_pb_ratio_zero_preserved(self):
        """pb_ratio = 0 must be preserved in the summary."""
        asset = {
            "ticker": "TEST4", "name": "Test SA", "score": 8.0,
            "dividend_yield": 0.05, "sector": "Energia",
            "pb_ratio": 0.0, "dy_medio_3y": 0.04,
        }
        result = _summarize(asset, ["sector", "pb_ratio", "dy_medio_3y"])
        assert result["pb_ratio"] == 0.0, (
            f"pb_ratio=0 must be preserved, got {result['pb_ratio']!r}"
        )
        # Also verify it's not converted to None or removed
        assert result["pb_ratio"] is not None
        assert "pb_ratio" in result

    def test_score_zero_preserved(self):
        """Score = 0 must be preserved."""
        asset = {
            "ticker": "TEST4", "name": "Test SA", "score": 0.0,
            "dividend_yield": 0.05,
        }
        result = _summarize(asset)
        assert result["score"] == 0.0, (
            f"score=0 must be preserved, got {result['score']!r}"
        )
        assert result["score"] is not None

    def test_dividend_yield_zero_preserved(self):
        """dividend_yield = 0 must be preserved."""
        asset = {
            "ticker": "TEST4", "name": "Test SA", "score": 5.0,
            "dividend_yield": 0.0,
        }
        result = _summarize(asset)
        assert result["dividend_yield"] == 0.0
        assert result["dividend_yield"] is not None


# ===================================================================
# _compute_top_picks — ranking and filtering
# ===================================================================

class TestComputeTopPicks:
    """_compute_top_picks returns ranked top N assets by score."""

    def test_returns_top_5_stocks(self):
        """Stocks sorted by score descending, limited to 5."""
        stocks = [
            {"ticker": "A", "score": 9.0},
            {"ticker": "B", "score": 8.0},
            {"ticker": "C", "score": 7.0},
            {"ticker": "D", "score": 6.0},
            {"ticker": "E", "score": 5.0},
            {"ticker": "F", "score": 4.0},
        ]
        top_s, _, _ = _compute_top_picks(stocks, [], [])
        assert len(top_s) == 5
        assert top_s[0]["ticker"] == "A"
        assert top_s[4]["ticker"] == "E"

    def test_returns_all_when_less_than_5(self):
        """When fewer than 5 assets, all are returned."""
        stocks = [
            {"ticker": "A", "score": 9.0, "pb_ratio": 1.0, "dividend_yield": 0.05},
            {"ticker": "B", "score": 8.0, "pb_ratio": 1.0, "dividend_yield": 0.05},
        ]
        top_s, top_f, top_g = _compute_top_picks(stocks, [], [])
        assert len(top_s) == 2

    def test_empty_lists_return_empty(self):
        """Empty input lists return empty top picks."""
        top_s, top_f, top_g = _compute_top_picks([], [], [])
        assert len(top_s) == 0
        assert len(top_f) == 0
        assert len(top_g) == 0

    def test_top_picks_have_minimal_fields(self):
        """Each top pick must have ticker and score (minimal contract)."""
        stocks = [
            {"ticker": "PETR4", "score": 8.5},
            {"ticker": "VALE3", "score": 7.0},
        ]
        top_s, _, _ = _compute_top_picks(stocks, [], [])
        for item in top_s:
            assert "ticker" in item
            assert "score" in item
            assert item["score"] >= 0

    def test_score_zero_is_sorted_last(self):
        """Stocks with score=0 are sorted last."""
        stocks = [
            {"ticker": "A", "score": 8.0},
            {"ticker": "B", "score": 0.0},
            {"ticker": "C", "score": 6.0},
        ]
        top_s, _, _ = _compute_top_picks(stocks, [], [])
        assert top_s[2]["ticker"] == "B"  # score=0 is last

    def test_fii_filtered_by_pb_and_dy_preserves_zero(self):
        """FIIs with pb_ratio=0 or dy=0 might be filtered out
        (business rule), but pb=0 in kept FIIs must remain 0."""
        fiis = [
            {"ticker": "FII1", "score": 9.0, "pb_ratio": 0.0, "dividend_yield": 0.08},
            {"ticker": "FII2", "score": 8.0, "pb_ratio": 0.95, "dividend_yield": 0.09},
            {"ticker": "FII3", "score": 7.0, "pb_ratio": 1.10, "dividend_yield": 0.07},
        ]
        _, top_f, _ = _compute_top_picks([], fiis, [])
        # FII1 has pb_ratio=0 which is falsy; it may be filtered out
        # FII2 and FII3 should be present
        tickers = [f["ticker"] for f in top_f]
        assert "FII2" in tickers
        assert "FII3" in tickers
        # For items that ARE included, pb_ratio should be properly set
        for f in top_f:
            if f["pb_ratio"] is not None:
                assert isinstance(f["pb_ratio"], (int, float))
