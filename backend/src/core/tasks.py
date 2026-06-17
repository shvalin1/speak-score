"""Cloud Tasks enqueue（worker /api/tasks/process を OIDC で起動）。

task名は job_id+uuid の一意接尾辞（tombstone回避）。dedupは /start transaction に一本化（§5）。
ローカル（queue未設定）は即時同期HTTP呼び出しに倒す（Cloud Tasksの本物は実GCPでスパイク §9）。
設計根拠: design_review_and_frontback.md §5.1, §8, §9
"""

from __future__ import annotations

import json
import uuid

from .config import get_settings


def enqueue_process(job_id: str) -> None:
    settings = get_settings()

    if not settings.tasks_queue:
        # --- ローカル: worker を同期HTTPで直接叩く（OIDC/retryは本番でのみ） ---
        import httpx

        target = (settings.worker_url or "http://localhost:8080") + "/api/tasks/process"
        try:
            httpx.post(target, json={"job_id": job_id}, timeout=5.0)
        except Exception:  # noqa: BLE001
            # ローカルで worker 未起動でも /start は成功させる（fire-and-forget）
            pass
        return

    # --- 本番: Cloud Tasks ---
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
