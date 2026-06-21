"""get_uid の provider 分岐（匿名→共有 demo_uid / 本物→個人 uid）の単体テスト。

既存テストは AUTH_DISABLED=1 で検証を丸ごと飛ばすため、ここでは auth_disabled=False の
Settings を直接渡し、firebase_admin を fake module に差し替えて検証経路を通す。
"""

from __future__ import annotations

import sys
import types

import pytest

from src.core.auth import get_uid
from src.core.config import Settings


def _install_fake_firebase(monkeypatch, decoded: dict) -> None:
    """firebase_admin を差し替え、verify_id_token が decoded を返すようにする。"""
    fb = types.ModuleType("firebase_admin")
    fb._apps = {"default": object()}  # truthy → initialize_app をスキップ
    auth_mod = types.ModuleType("firebase_admin.auth")
    auth_mod.verify_id_token = lambda _token: decoded  # type: ignore[attr-defined]
    fb.auth = auth_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "firebase_admin", fb)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", auth_mod)


@pytest.fixture
def settings() -> Settings:
    return Settings(auth_disabled=False, demo_uid="demo-shared")


def test_anonymous_maps_to_shared_demo_uid(monkeypatch, settings):
    _install_fake_firebase(
        monkeypatch,
        {"uid": "anon-abc", "firebase": {"sign_in_provider": "anonymous"}},
    )
    uid = get_uid(authorization="Bearer faketoken", settings=settings)
    assert uid == "demo-shared"


def test_google_keeps_individual_uid(monkeypatch, settings):
    _install_fake_firebase(
        monkeypatch,
        {"uid": "google-xyz", "firebase": {"sign_in_provider": "google.com"}},
    )
    uid = get_uid(authorization="Bearer faketoken", settings=settings)
    assert uid == "google-xyz"


def test_missing_provider_falls_back_to_uid(monkeypatch, settings):
    # firebase クレームが無い／provider 不明なトークンは従来どおり uid を返す。
    _install_fake_firebase(monkeypatch, {"uid": "plain-uid"})
    uid = get_uid(authorization="Bearer faketoken", settings=settings)
    assert uid == "plain-uid"


def test_missing_bearer_raises_401(settings):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        get_uid(authorization=None, settings=settings)
    assert ei.value.status_code == 401
