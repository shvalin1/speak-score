"""Firebase IDトークン検証 → uid。FastAPI Depends で各APIに注入。

ローカル/モック開発では AUTH_DISABLED=1 で検証を飛ばし dev_uid を返す。
設計根拠: design_review_and_frontback.md §10
"""

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    return authorization.split(" ", 1)[1].strip()


def get_uid(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Authorization: Bearer <Firebase IDトークン> を検証し uid を返す。"""
    if settings.auth_disabled:
        return settings.dev_uid

    token = _extract_bearer(authorization)
    # firebase_admin は重い & 認証無効時は不要なので遅延 import
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        ) from e
    return decoded["uid"]
