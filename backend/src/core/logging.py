"""構造化ログ（Cloud Logging 互換の JSON 出力）。

Cloud Run は stdout に出した JSON 1行を Cloud Logging の `jsonPayload` に自動パースし、
`severity` フィールドをログレベルとして扱う。これに合わせた formatter を root logger に
取り付け、job_id / stage / duration_ms / outcome 等を構造化フィールドとして出す。

PII 方針: 面接の transcript・音声内容は決してログに出さない。job_id・サイズ・型・stage・
duration といった非機微なメタデータのみを構造化フィールドに載せる（AGENTS の秘匿方針）。

設計根拠: docs/plans/002_step2_real_pipeline.md「観測性（Step2 必須に格上げ）」。
"""

from __future__ import annotations

import json
import logging
from typing import Any

# 標準 LogRecord に常に存在する属性。これら以外で record に積まれた属性を
# 構造化フィールド（extra）として JSON に展開する。
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """LogRecord を Cloud Logging 互換の1行 JSON にする。

    `severity` は Cloud Logging が認識するログレベル名（INFO/WARNING/ERROR 等）。
    `logging.info(..., extra={"job_id": ...})` で渡した任意フィールドは
    トップレベルに展開される（予約属性は除外）。
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        # extra で積まれた構造化フィールドを展開（予約属性・内部属性は除外）。
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            # スタックトレースは付けるが、例外メッセージに PII が混じらない前提
            # （本コードベースの例外文言は job_id・サイズ・型のみ）。
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """root logger に JSON formatter の StreamHandler を1つだけ取り付ける。

    多重設定（テスト/リロード）でハンドラが重複しないよう、既存ハンドラを置換する。
    uvicorn 配下でも stdout に出れば Cloud Run が拾うため propagate に依存しない。
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    # 既存ハンドラ（basicConfig や前回の configure 由来）を一掃して二重出力を防ぐ。
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
