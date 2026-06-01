from __future__ import annotations

from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database
from paper_trading.repository import PaperTradingRepository


def test_dashboard_loader_exposes_paper_journal_notes_safely(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    repository = PaperTradingRepository(database_path)
    repository.add_journal_note(
        note_type="RUN",
        reference_id="run-1",
        asset="BTC",
        profile="conservative",
        title="Run review",
        note_text="Observed a no-trade paper outcome.",
        tags="review,no-trade",
    )

    data = load_dashboard_data(tmp_path)

    assert data.database_path == database_path
    assert len(data.paper_journal_notes) == 1
    assert data.paper_journal_notes[0]["note_type"] == "RUN"
    assert data.paper_journal_notes[0]["note_text"] == "Observed a no-trade paper outcome."


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "database:",
                "  path: data/database.db",
                "risk:",
                "  execution_enabled: false",
                "paper_trading:",
                "  enabled: false",
                "  starting_equity: 10000",
            ]
        ),
        encoding="utf-8",
    )

