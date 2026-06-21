"""構造化ログ（core/logging）と pipeline / worker のステージ・outcome ログのテスト。

ネットワーク・実音声非依存。formatter の出力形と、各ステージ/ outcome が
期待フィールド（stage/duration_ms/outcome/attempt）を構造化で出すことを検証する。
"""

from __future__ import annotations

import asyncio
import json
import logging

from src.core.logging import JsonFormatter, configure_logging
from src.repositories.job_repo import InMemoryJobRepo
from src.services import pipeline

from .test_pipeline import _mock_media, _mock_services, _ready_job


def test_json_formatter_emits_severity_and_extra() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="", lineno=0,
        msg="stage_complete", args=(), exc_info=None,
    )
    record.job_id = "job-1"
    record.stage = "transcribing"
    record.duration_ms = 12.3

    payload = json.loads(formatter.format(record))

    assert payload["severity"] == "INFO"
    assert payload["message"] == "stage_complete"
    assert payload["logger"] == "t"
    assert payload["job_id"] == "job-1"
    assert payload["stage"] == "transcribing"
    assert payload["duration_ms"] == 12.3


def test_json_formatter_includes_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname="", lineno=0,
            msg="job_outcome", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert payload["severity"] == "ERROR"
    assert "ValueError" in payload["exception"]


def test_configure_logging_replaces_handlers_with_json() -> None:
    configure_logging("INFO")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    # 再呼び出しでハンドラが重複しない（二重出力防止）。
    configure_logging("DEBUG")
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG


def test_pipeline_emits_stage_complete_logs(monkeypatch, caplog) -> None:
    repo = InMemoryJobRepo()
    jid = _ready_job(repo)
    _mock_media(monkeypatch)
    _mock_services(monkeypatch)

    with caplog.at_level(logging.INFO, logger="src.services.pipeline"):
        asyncio.run(pipeline.run_pipeline(jid, repo, "w1"))

    stages = {
        r.stage: r
        for r in caplog.records
        if r.message == "stage_complete" and hasattr(r, "stage")
    }
    assert set(stages) == {"extracting_audio", "transcribing", "analyzing_audio", "evaluating"}
    for record in stages.values():
        assert isinstance(record.duration_ms, float)
        assert record.job_id == jid
    # 抽出ステージは入力サイズ（WAV bytes）を載せる。
    assert stages["extracting_audio"].input_bytes > 0


def test_pipeline_logs_stage_failed_on_error(monkeypatch, caplog) -> None:
    repo = InMemoryJobRepo()
    jid = _ready_job(repo)
    # 長尺で extracting_audio ステージを FatalError にする。
    _mock_media(monkeypatch, duration=99999.0)

    with caplog.at_level(logging.WARNING, logger="src.services.pipeline"):
        try:
            asyncio.run(pipeline.run_pipeline(jid, repo, "w1"))
        except Exception:  # noqa: BLE001 ログ出力の検証が目的
            pass

    failed = [r for r in caplog.records if r.message == "stage_failed"]
    assert failed and failed[0].stage == "extracting_audio"
    assert failed[0].error_type == "FatalError"


def test_worker_emits_job_outcome_log(client, monkeypatch, caplog) -> None:
    """worker が outcome/attempt/duration を構造化ログに出す（recoverable_retry 経路）。"""
    from datetime import UTC, datetime, timedelta

    from src.core.errors import RecoverableError
    from src.repositories import job_repo
    from src.services import pipeline as worker_pipeline

    async def _boom(*a, **k):
        raise RecoverableError("transient")

    monkeypatch.setattr(worker_pipeline, "run_pipeline", _boom)
    repo = job_repo.get_job_repo()
    jid = "outcome-job"
    repo.create(
        jid, owner_uid="dev-user",
        expire_at=datetime.now(UTC) + timedelta(days=1), content_type="video/mp4",
    )
    repo.mark_processing(jid)

    with caplog.at_level(logging.INFO, logger="src.api.tasks"):
        res = client.post("/api/tasks/process", json={"job_id": jid})

    assert res.status_code == 503
    outcomes = [r for r in caplog.records if r.message == "job_outcome"]
    assert outcomes and outcomes[0].outcome == "recoverable_retry"
    assert outcomes[0].job_id == jid
    assert outcomes[0].attempt == 1
    assert isinstance(outcomes[0].duration_ms, float)


def test_init_sentry_skips_without_dsn(monkeypatch) -> None:
    import sentry_sdk

    from src.core.config import Settings
    from src.main import _init_sentry

    called: dict = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: called.update(kw))

    _init_sentry(Settings(sentry_dsn=""))
    assert called == {}  # DSN 無しは init を呼ばない

    _init_sentry(Settings(sentry_dsn="https://k@o1.ingest.sentry.io/1", sentry_environment="prod"))
    assert called["dsn"].startswith("https://")
    assert called["environment"] == "prod"
    assert called["send_default_pii"] is False  # 面接 PII を送らない


def test_report_to_sentry_sets_tags_and_context(monkeypatch) -> None:
    import sentry_sdk

    from src.api import tasks

    captured: dict = {"tags": {}, "ctx": {}}

    class _FakeScope:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def set_tag(self, k, v):
            captured["tags"][k] = v

        def set_context(self, k, v):
            captured["ctx"][k] = v

    monkeypatch.setattr(sentry_sdk, "new_scope", lambda: _FakeScope())
    monkeypatch.setattr(sentry_sdk, "capture_exception", lambda e: captured.__setitem__("exc", e))

    err = ValueError("boom")
    tasks._report_to_sentry(err, job_id="j1", outcome="fatal_fail", attempt=2)

    assert captured["tags"] == {"outcome": "fatal_fail", "error_type": "ValueError", "attempt": 2}
    assert captured["ctx"]["job"] == {"job_id": "j1"}
    assert captured["exc"] is err
