from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import main as app


def test_parse_args_supports_paper_export() -> None:
    args = app.parse_args(["--paper-export"])

    assert args.paper_export is True


def test_main_paper_export_prints_export_paths_without_running_workflow(monkeypatch, capsys, tmp_path: Path) -> None:
    fake_config = SimpleNamespace(
        app_name="AI Trading Firm",
        mode="research",
        database_path=tmp_path / "paper.db",
        paper_trading=SimpleNamespace(enabled=False, starting_equity=10_000.0),
    )
    export_paths = [
        tmp_path / "data" / "exports" / "paper_signal_reviews_20260601_010203.csv",
        tmp_path / "data" / "exports" / "paper_run_summaries_20260601_010203.csv",
    ]
    calls = {
        "initialize_database": 0,
        "build_orchestrator": 0,
        "export_paper_review_files": 0,
    }

    monkeypatch.setattr(app, "load_config", lambda project_root: fake_config)
    monkeypatch.setattr(app, "setup_logging", lambda config: None)
    monkeypatch.setattr(
        app,
        "export_paper_review_files",
        lambda config, project_root: calls.__setitem__("export_paper_review_files", calls["export_paper_review_files"] + 1) or export_paths,
    )
    monkeypatch.setattr(
        app,
        "initialize_database",
        lambda database_path: calls.__setitem__("initialize_database", calls["initialize_database"] + 1),
    )
    monkeypatch.setattr(
        app,
        "build_orchestrator",
        lambda config, runtime: calls.__setitem__("build_orchestrator", calls["build_orchestrator"] + 1),
    )

    exit_code = app.main(["--paper-export"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert str(export_paths[0]) in output
    assert str(export_paths[1]) in output
    assert calls["export_paper_review_files"] == 1
    assert calls["initialize_database"] == 0
    assert calls["build_orchestrator"] == 0
