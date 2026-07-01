"""get_principal / require_writer の権限分岐の単体テスト。

役割: 匿名・許可リスト外 Google → reader(demo_uid, 書込不可) / 許可 Google → writer(個人uid)。
既存テストは AUTH_DISABLED=1 で検証を丸ごと飛ばすため、ここでは auth_disabled=False の
Settings を直接渡し、firebase_admin を fake module に差し替えて検証経路を通す。
"""

from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

from src.core.auth import Principal, get_principal, require_writer
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
    return Settings(
        auth_disabled=False,
        demo_uid="demo-shared",
        allowed_emails="Alice@Example.com, bob@example.com",
    )


def _principal(monkeypatch, settings, decoded: dict) -> Principal:
    _install_fake_firebase(monkeypatch, decoded)
    return get_principal(authorization="Bearer faketoken", settings=settings)


def test_anonymous_is_reader_on_demo_uid(monkeypatch, settings):
    p = _principal(
        monkeypatch,
        settings,
        {"uid": "anon-abc", "firebase": {"sign_in_provider": "anonymous"}},
    )
    assert p.uid == "demo-shared"
    assert p.is_writer is False


def test_allowlisted_google_is_writer_with_own_uid(monkeypatch, settings):
    p = _principal(
        monkeypatch,
        settings,
        {
            "uid": "google-xyz",
            "email": "alice@example.com",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        },
    )
    assert p.uid == "google-xyz"
    assert p.is_writer is True


def test_allowlist_match_is_case_insensitive(monkeypatch, settings):
    # 許可リストは Alice@Example.com。大小差のトークン email でも一致する。
    p = _principal(
        monkeypatch,
        settings,
        {
            "uid": "g1",
            "email": "ALICE@example.COM",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        },
    )
    assert p.is_writer is True


def test_non_allowlisted_google_is_reader(monkeypatch, settings):
    p = _principal(
        monkeypatch,
        settings,
        {
            "uid": "google-outsider",
            "email": "eve@example.com",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        },
    )
    assert p.uid == "demo-shared"
    assert p.is_writer is False


def test_unverified_email_is_reader(monkeypatch, settings):
    p = _principal(
        monkeypatch,
        settings,
        {
            "uid": "g2",
            "email": "alice@example.com",
            "email_verified": False,
            "firebase": {"sign_in_provider": "google.com"},
        },
    )
    assert p.is_writer is False


def test_non_google_provider_cannot_be_writer(monkeypatch, settings):
    # provider が google.com 以外なら、たとえ email が許可リストにあり verified でも reader。
    # verify_id_token は email_verified を検証しないため provider を必須 AND する多層防御。
    p = _principal(
        monkeypatch,
        settings,
        {
            "uid": "pw-user",
            "email": "alice@example.com",
            "email_verified": True,
            "firebase": {"sign_in_provider": "password"},
        },
    )
    assert p.is_writer is False


def test_allowed_email_set_drops_empty_entries():
    # 空許可リストは frozenset()（"".split(",") == [""] の空要素混入を除去）。
    settings = Settings(auth_disabled=False, demo_uid="demo-shared", allowed_emails="")
    assert settings.allowed_email_set == frozenset()
    # 末尾カンマ/空白のみの要素も除去される。
    settings2 = Settings(allowed_emails="a@b.com, , ,")
    assert settings2.allowed_email_set == frozenset({"a@b.com"})


def test_empty_email_google_token_is_reader(monkeypatch):
    # 空 email + 空許可リスト + google.com + verified でも writer にならない（フェイルクローズ）。
    # "" in {""} で writer 化する空文字 split 罠を実経路で塞げていることを固定する。
    settings = Settings(auth_disabled=False, demo_uid="demo-shared", allowed_emails="")
    p = _principal(
        monkeypatch,
        settings,
        {
            "uid": "g-empty",
            "email": "",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        },
    )
    assert p.uid == "demo-shared"
    assert p.is_writer is False


def test_missing_bearer_raises_401(settings):
    with pytest.raises(HTTPException) as ei:
        get_principal(authorization=None, settings=settings)
    assert ei.value.status_code == 401


def test_auth_disabled_is_dev_writer():
    settings = Settings(auth_disabled=True, dev_uid="dev-user")
    p = get_principal(authorization=None, settings=settings)
    assert p.uid == "dev-user"
    assert p.is_writer is True


def test_require_writer_rejects_reader():
    reader = Principal(uid="demo-shared", is_writer=False, email=None, provider="anonymous")
    with pytest.raises(HTTPException) as ei:
        require_writer(principal=reader)
    assert ei.value.status_code == 403


def test_require_writer_returns_uid_for_writer():
    writer = Principal(uid="g1", is_writer=True, email="a@b.com", provider="google.com")
    assert require_writer(principal=writer) == "g1"
