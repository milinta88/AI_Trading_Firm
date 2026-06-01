from __future__ import annotations

import csv
from io import StringIO

from dashboard.data_loader import rows_to_csv


def test_rows_to_csv_exports_flat_and_nested_values() -> None:
    csv_text = rows_to_csv(
        [
            {
                "asset": "BTC",
                "status": "OK",
                "value": 100.5,
                "warnings": ["context-only"],
            }
        ]
    )

    parsed_rows = list(csv.DictReader(StringIO(csv_text)))

    assert parsed_rows[0]["asset"] == "BTC"
    assert parsed_rows[0]["status"] == "OK"
    assert parsed_rows[0]["value"] == "100.5"
    assert parsed_rows[0]["warnings"] == '["context-only"]'


def test_rows_to_csv_returns_empty_string_for_no_rows() -> None:
    assert rows_to_csv([]) == ""
