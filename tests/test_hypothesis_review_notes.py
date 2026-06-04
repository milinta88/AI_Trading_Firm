from __future__ import annotations

from pathlib import Path

from database.init_db import initialize_database
from database.repository import WorkflowRepository


def test_hypothesis_review_note_insert_list_update_and_soft_delete(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    repository = WorkflowRepository(database_path)

    note_id = repository.add_hypothesis_review_note(
        note_type="GENERAL",
        reference_type="OUTCOME",
        reference_id="42",
        asset="BTC",
        strategy_family="BTC_TREND_CONTINUATION",
        regime="TREND_UP",
        horizon_hours=24,
        title="First review note",
        note_text="Need more BTC follow-up samples before any review promotion.",
        tags="btc,review",
    )

    assert note_id > 0
    notes = repository.list_hypothesis_review_notes()
    assert len(notes) == 1
    assert notes[0]["note_text"].startswith("Need more BTC")

    updated = repository.update_hypothesis_review_note(
        note_id,
        title="Updated review note",
        note_text="Updated text",
        tags="btc,updated",
    )
    assert updated is True

    updated_note = repository.list_hypothesis_review_notes()[0]
    assert updated_note["title"] == "Updated review note"
    assert updated_note["note_text"] == "Updated text"
    assert updated_note["tags"] == "btc,updated"

    deleted = repository.soft_delete_hypothesis_review_note(note_id)
    assert deleted is True
    assert repository.list_hypothesis_review_notes() == []

    deleted_notes = repository.list_hypothesis_review_notes(include_deleted=True)
    assert len(deleted_notes) == 1
    assert deleted_notes[0]["is_deleted"] == 1
