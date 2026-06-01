from __future__ import annotations

from types import SimpleNamespace

import main as app
from core.models import DeliveryResult, WorkflowOutcome


def test_main_paper_run_disabled_path(monkeypatch, capsys) -> None:
    fake_config = SimpleNamespace(
        app_name="AI Trading Firm",
        mode="research",
        paper_trading=SimpleNamespace(enabled=False),
    )
    fake_runtime = SimpleNamespace(mode="DRY_RUN", reason="test", allow_live_sends=False)

    class FakeOrchestrator:
        def run_daily_brief(self) -> WorkflowOutcome:
            return WorkflowOutcome(
                workflow_run_id=123,
                report_text="daily brief",
                delivery=DeliveryResult(success=True, status="DRY_RUN", recipient="not-configured"),
            )

    monkeypatch.setattr(app, "load_config", lambda project_root: fake_config)
    monkeypatch.setattr(app, "setup_logging", lambda config: None)
    monkeypatch.setattr(app, "resolve_telegram_runtime", lambda config, options: fake_runtime)
    monkeypatch.setattr(app, "initialize_database", lambda database_path: None)
    monkeypatch.setattr(app, "build_orchestrator", lambda config, runtime: FakeOrchestrator())
    fake_config.database_path = "unused.db"

    exit_code = app.main(["--dry-run", "--paper-run"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "daily brief" in output
    assert "Paper trading disabled" in output
