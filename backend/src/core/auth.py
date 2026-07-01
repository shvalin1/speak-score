"""Firebase IDトークン検証 → Principal（scope uid ＋ 書込可否）。FastAPI Depends で注入。

役割モデル（信頼境界はこの backend。フロントの出し分けは UX に過ぎない）:
  - 匿名 / 許可リスト外 Google … reader。全員 demo_uid に寄せ read-only（共有プールを閲覧のみ）。
  - 許可リストの google.com（verified メール） … writer。各自の uid で個人スコープ＋書込可。
  - AUTH_DISABLED=1（ローカル/実機検証窓）… dev_uid の writer。

get_uid は GET 系（reader も可）、require_writer は書込系（create/start）に付ける。
設計根拠: design_review_and_frontback.md §10
"""

import os
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings

# writer を許可する唯一のプロバイダ。email_verified クレームは verify_id_token では
# 検証されず復号されるだけなので、プロバイダを google.com に固定して詐称経路を塞ぐ
# （将来 Email/Password 等が有効化されても任意 email での writer 化を防ぐ）。
_WRITER_PROVIDER = "google.com"


@dataclass(frozen=True)
class Principal:
    """認証済み主体。uid はスコープ用（reader は demo_uid、writer は各自 uid）。"""

    uid: str
    is_writer: bool
    email: str | None
    provider: str | None


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    return authorization.split(" ", 1)[1].strip()


def get_principal(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Authorization: Bearer <Firebase IDトークン> を検証し Principal を返す。"""
    if settings.auth_disabled:
        # ローカル/実機検証窓のみ。dev_uid は demo_uid とは別スコープの writer。
        return Principal(uid=settings.dev_uid, is_writer=True, email=None, provider="dev")

    token = _extract_bearer(authorization)
    # firebase_admin は重い & 認証無効時は不要なので遅延 import
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not firebase_admin._apps:
        # verify_id_token は audience(project_id) 照合に project を要する。
        # Cloud Run の ADC 解決に依存せず、run.tf が注入する FIREBASE_PROJECT を明示する
        # （未設定時は従来どおり ADC 任せにフォールバック）。
        project = os.environ.get("FIREBASE_PROJECT")
        options = {"projectId": project} if project else None
        firebase_admin.initialize_app(options=options)
    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        ) from e

    provider = decoded.get("firebase", {}).get("sign_in_provider")
    email = decoded.get("email")
    # writer 判定は provider(google.com) を必須 AND する多層防御。email が空/未検証なら reader。
    normalized = email.strip().casefold() if email else ""
    is_writer = (
        provider == _WRITER_PROVIDER
        and bool(decoded.get("email_verified"))
        and normalized != ""
        and normalized in settings.allowed_email_set
    )
    # reader（匿名・未許可 Google）は全員 demo_uid の共有プールに寄せ read-only。
    # writer は各自の uid で個人スコープに分離する。
    uid = decoded["uid"] if is_writer else settings.demo_uid
    return Principal(uid=uid, is_writer=is_writer, email=email, provider=provider)


def get_uid(principal: Principal = Depends(get_principal)) -> str:
    """スコープ uid を返す（GET 系。reader は demo_uid、writer は各自 uid）。"""
    return principal.uid


def require_writer(principal: Principal = Depends(get_principal)) -> str:
    """書込系（create/start）に付ける。reader は 403、writer は自分の uid を返す。"""
    if not principal.is_writer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この操作には許可されたアカウントでのログインが必要です",
        )
    return principal.uid
