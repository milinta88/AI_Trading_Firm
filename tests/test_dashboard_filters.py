from __future__ import annotations

from datetime import date

from dashboard.data_loader import build_market_chart_rows, build_score_chart_rows, filter_rows


def test_filter_rows_applies_date_asset_data_type_and_limit() -> None:
    rows = [
        {"timestamp": "2026-05-27T00:00:00+00:00", "asset": "BTC", "data_type": "price"},
        {"timestamp": "2026-05-28T00:00:00+00:00", "asset": "Gold", "data_type": "us10y"},
        {"timestamp": "2026-05-29T00:00:00+00:00", "asset": "BTC", "data_type": "funding_rate"},
        {"timestamp": "2026-05-30T00:00:00+00:00", "asset": "BTC", "data_type": "funding_rate"},
    ]

    filtered = filter_rows(
        rows,
        start_date=date(2026, 5, 28),
        end_date=date(2026, 5, 30),
        asset="BTC",
        data_type="funding_rate",
        limit=1,
    )

    assert filtered == [rows[2]]


def test_build_market_chart_rows_extracts_numeric_values_only() -> None:
    rows = [
        {
            "timestamp": "2026-05-29T02:00:00+00:00",
            "asset": "BTC",
            "data_type": "price",
            "source": "test",
            "status": "OK",
            "value_json": '{"price": "100.25"}',
        },
        {
            "timestamp": "2026-05-29T01:00:00+00:00",
            "asset": "BTC",
            "data_type": "funding_rate",
            "source": "test",
            "status": "OK",
            "value_json": '{"funding_rate": 0.0001}',
        },
        {
            "timestamp": "2026-05-29T03:00:00+00:00",
            "asset": "BTC",
            "data_type": "price",
            "source": "test",
            "status": "FAIL",
            "value_json": '{"price": 101}',
        },
    ]

    chart_rows = build_market_chart_rows(rows)

    assert [row["data_type"] for row in chart_rows] == ["funding_rate", "price"]
    assert chart_rows[1]["value"] == 100.25


def test_build_score_chart_rows_extracts_total_score() -> None:
    rows = [
        {"timestamp": "2026-05-29T00:00:00+00:00", "asset": "BTC", "total_score": "61"},
        {"timestamp": "2026-05-29T01:00:00+00:00", "asset": "Gold", "total_score": 48},
        {"timestamp": "2026-05-29T02:00:00+00:00", "asset": "BTC", "total_score": None},
    ]

    chart_rows = build_score_chart_rows(rows)

    assert [row["asset"] for row in chart_rows] == ["BTC", "Gold"]
    assert chart_rows[0]["total_score"] == 61.0
