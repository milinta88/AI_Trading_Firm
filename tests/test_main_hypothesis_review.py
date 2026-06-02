from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import main as app


def test_parse_args_supports_hypothesis_review() -> None:
    args = app.parse_args(["--hypothesis-review"])

    assert args.hypothesis_review is True


def test_main_hypothesis_review_prints_summary_without_running_workflow(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    fake_config = SimpleNamespace(
        app_name="AI Trading Firm",
        mode="research",
        database_path=tmp_path / "database.db",
    )
    calls = {
        "initialize_database": 0,
        "build_orchestrator": 0,
        "build_hypothesis_review_report": 0,
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
        "build_hypothesis_review_report",
        lambda config: calls.__setitem__("build_hypothesis_review_report", calls["build_hypothesis_review_report"] + 1)
        or "HYPOTHESIS REVIEW ANALYTICS\nREVIEW ONLY\nNO TRADING",
    )

    exit_code = app.main(["--hypothesis-review"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "HYPOTHESIS REVIEW ANALYTICS" in output
    assert calls["initialize_database"] == 1
    assert calls["build_hypothesis_review_report"] == 1
    assert calls["build_orchestrator"] == 0
