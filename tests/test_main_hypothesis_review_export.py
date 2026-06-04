from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import main as app


def test_parse_args_supports_hypothesis_review_export() -> None:
    args = app.parse_args(["--hypothesis-review-export"])

    assert args.hypothesis_review_export is True


def test_main_hypothesis_review_export_prints_paths_without_running_workflow(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    fake_config = SimpleNamespace(
        app_name="AI Trading Firm",
        mode="research",
        database_path=tmp_path / "database.db",
    )
    export_paths = [
        tmp_path / "data" / "exports" / "strategy_hypotheses_20260602_010203.csv",
        tmp_path / "data" / "exports" / "strategy_hypothesis_outcomes_20260602_010203.csv",
        tmp_path / "data" / "exports" / "hypothesis_review_summaries_20260602_010203.csv",
    ]
    calls = {
        "initialize_database": 0,
        "build_orchestrator": 0,
        "run_paper_trading": 0,
        "export_hypothesis_review_files": 0,
    }

    monkeypatch.setattr(app, "load_config", lambda project_root: fake_config)
    monkeypatch.setattr(app, "setup_logging", lambda config: None)
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
    monkeypatch.setattr(
        app,
        "run_paper_trading",
        lambda config, workflow_run_id: calls.__setitem__("run_paper_trading", calls["run_paper_trading"] + 1),
    )
    monkeypatch.setattr(
        app,
        "export_hypothesis_review_files",
        lambda config, project_root: calls.__setitem__(
            "export_hypothesis_review_files",
            calls["export_hypothesis_review_files"] + 1,
        ) or export_paths,
    )

    exit_code = app.main(["--hypothesis-review-export"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert str(export_paths[0]) in output
    assert str(export_paths[2]) in output
    assert calls["initialize_database"] == 1
    assert calls["export_hypothesis_review_files"] == 1
    assert calls["build_orchestrator"] == 0
    assert calls["run_paper_trading"] == 0
