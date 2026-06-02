from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import main as app


def test_parse_args_supports_hypothesis_outcomes() -> None:
    args = app.parse_args(["--hypothesis-outcomes"])

    assert args.hypothesis_outcomes is True


def test_main_hypothesis_outcomes_prints_summary_without_running_workflow(
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
        "evaluate_hypothesis_outcomes": 0,
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
        "evaluate_hypothesis_outcomes",
        lambda config: calls.__setitem__("evaluate_hypothesis_outcomes", calls["evaluate_hypothesis_outcomes"] + 1)
        or "STRATEGY HYPOTHESIS OUTCOME REVIEW\nREAD-ONLY\nNO REAL EXECUTION",
    )

    exit_code = app.main(["--hypothesis-outcomes"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "STRATEGY HYPOTHESIS OUTCOME REVIEW" in output
    assert calls["initialize_database"] == 1
    assert calls["evaluate_hypothesis_outcomes"] == 1
    assert calls["build_orchestrator"] == 0
