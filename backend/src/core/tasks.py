"""Cloud Tasks enqueue（worker /api/tasks/process を OIDC で起動）。

task名は job_id+uuid の一意接尾辞（tombstone回避）。dedupは /start transaction に一本化（§5）。
ローカル（queue未設定）は即時同期HTTP呼び出しに倒す（Cloud Tasksの本物は実GCPでスパイク §9）。
設計根拠: design_review_and_frontback.md §5.1, §8, §9
"""

from __future__ import annotations

import json
import logging
import uuid

from .config import get_settings

log = logging.getLogger(__name__)


def enqueue_process(job_id: str) -> None:
    settings = get_settings()

    if not settings.tasks_queue:
        # --- ローカル: worker を同期HTTPで直接叩く（OIDC/retryは本番でのみ） ---
        import httpx

        target = (settings.worker_url or "http://localhost:8080") + "/api/tasks/process"
        try:
            resp = httpx.post(target, json={"job_id": job_id}, timeout=5.0)
            if resp.status_code >= 400:
                # 401 は WORKER_OIDC_DISABLED 付け忘れの典型。例外にならず /start は成功する
                # ため、warning を出さないとジョブが静かに pending 滞留して気付けない。
                log.warning(
                    "local worker dispatch returned %s for job %s (WORKER_OIDC_DISABLED 未設定?)",
                    resp.status_code,
                    job_id,
                )
        except Exception:  # noqa: BLE001
            # ローカルで worker 未起動でも /start は成功させる（fire-and-forget）
            log.warning("local worker dispatch failed for job %s (worker 未起動?)", job_id)
        return

    # --- 本番: Cloud Tasks ---
    if not settings.worker_url:
        # 2パス apply の2パス目（worker_url 注入）を忘れると url が相対になり
        # create_task が失敗する。黙って壊れるより明示エラーで気付かせる。
        raise RuntimeError(
            "WORKER_URL 未設定: Cloud Tasks 有効時は backend の公開URLが必須"
            "（terraform の worker_url を入れて再 apply する）"
        )

    from google.cloud import tasks_v2  # 遅延import

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(settings.gcp_project, settings.region, settings.tasks_queue)
    task = {
        "name": client.task_path(
            settings.gcp_project,
            settings.region,
            settings.tasks_queue,
            f"{job_id}-{uuid.uuid4().hex[:8]}",
        ),
        # 実 pipeline は ffmpeg+librosa+LLM で既定 600s を超えうる。Cloud Run timeout(1800s)
        # に揃え、超過時の二重 dispatch（lease で多重処理は防げるが無駄 retry）を避ける。
        # 重要な不等式: soft_timeout(840s) < lease(900s) < dispatch_deadline(1800s)。
        # これにより worker は dispatch_deadline 内に必ず応答し、Cloud Tasks の再試行は
        # 逐次（同時再配信なし）になる＝同一 job への並行 worker を防ぐ前提が成立する。
        "dispatch_deadline": {"seconds": 1800},
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": settings.worker_url + "/api/tasks/process",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"job_id": job_id}).encode(),
            "oidc_token": {
                "service_account_email": settings.worker_sa,
                "audience": settings.worker_audience or settings.worker_url,
            },
        },
    }
    client.create_task(parent=parent, task=task)
