from __future__ import annotations

from types import SimpleNamespace

import main as app


def test_main_paper_report_prints_local_report_without_running_workflow(monkeypatch, capsys) -> None:
    fake_config = SimpleNamespace(
        app_name="AI Trading Firm",
        mode="research",
        database_path="unused.db",
        paper_trading=SimpleNamespace(enabled=False, starting_equity=10_000.0),
    )
    calls = {
        "initialize_database": 0,
        "build_orchestrator": 0,
        "build_paper_report": 0,
    }

    def fake_build_paper_report(config) -> str:
        calls["build_paper_report"] += 1
        return "PAPER TRADING REPORT\nSIMULATED ONLY\nNO REAL EXECUTION"

    monkeypatch.setattr(app, "load_config", lambda project_root: fake_config)
    monkeypatch.setattr(app, "setup_logging", lambda config: None)
    monkeypatch.setattr(app, "build_paper_report", fake_build_paper_report)
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

    exit_code = app.main(["--paper-report"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "PAPER TRADING REPORT" in output
    assert calls["build_paper_report"] == 1
    assert calls["initialize_database"] == 0
    assert calls["build_orchestrator"] == 0
