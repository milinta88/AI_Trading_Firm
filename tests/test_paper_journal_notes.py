from __future__ import annotations

from pathlib import Path

from database.init_db import initialize_database
from paper_trading.repository import PaperTradingRepository


def test_paper_journal_notes_support_insert_list_update_and_soft_delete(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    repository = PaperTradingRepository(database_path)

    note_id = repository.add_journal_note(
        note_type="GENERAL",
        note_text="Initial review note.",
        asset="BTC",
        profile="balanced",
        title="Morning review",
        tags="journal,btc",
    )

    notes = repository.list_journal_notes(limit=10)
    assert note_id > 0
    assert len(notes) == 1
    assert notes[0]["note_text"] == "Initial review note."
    assert notes[0]["asset"] == "BTC"

    updated = repository.update_journal_note(
        note_id,
        title="Updated review",
        note_text="Updated review note.",
        tags="journal,updated",
    )
    assert updated is True

    updated_note = repository.list_journal_notes(limit=10)[0]
    assert updated_note["title"] == "Updated review"
    assert updated_note["note_text"] == "Updated review note."
    assert updated_note["updated_at"] is not None

    deleted = repository.soft_delete_journal_note(note_id)
    assert deleted is True
    assert repository.list_journal_notes(limit=10) == []

    deleted_notes = repository.list_journal_notes(limit=10, include_deleted=True)
    assert len(deleted_notes) == 1
    assert deleted_notes[0]["is_deleted"] == 1

