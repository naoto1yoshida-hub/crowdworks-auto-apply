"""Task 3: config（環境変数ローダ）の単体テスト。

実装計画書 v0.2 §Task 3 に対応。

検証観点:
- 必須キー（ANTHROPIC_API_KEY / SPREADSHEET_ID）のみで Config が成立し、他はデフォルト値
- 環境変数で個別キーを上書きできる
- 必須キー欠落時は RuntimeError を投げる
"""

import pytest

from src.config import Config


def test_config_loads_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc123")
    for k in [
        "DAILY_APPLY_LIMIT",
        "SCORE_THRESHOLD",
        "REQUEST_TIMEOUT",
        "REQUEST_INTERVAL_SEC",
        "MAX_DETAIL_FETCH",
        "ANTHROPIC_HAIKU_MODEL",
        "ANTHROPIC_SONNET_MODEL",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = Config.from_env()

    assert cfg.anthropic_api_key == "sk-ant-x"
    assert cfg.spreadsheet_id == "abc123"
    assert cfg.daily_apply_limit == 10
    assert cfg.score_threshold == 60
    assert cfg.request_timeout == 30
    assert cfg.request_interval_sec == 1.0
    assert cfg.max_detail_fetch == 30
    assert cfg.haiku_model == "claude-haiku-4-5-20251001"
    assert cfg.sonnet_model == "claude-sonnet-4-6"


def test_config_respects_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    monkeypatch.setenv("DAILY_APPLY_LIMIT", "5")
    monkeypatch.setenv("ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-8")

    cfg = Config.from_env()

    assert cfg.daily_apply_limit == 5
    assert cfg.sonnet_model == "claude-sonnet-4-8"


def test_config_raises_when_required_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SPREADSHEET_ID", "abc")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        Config.from_env()


def test_config_raises_when_spreadsheet_id_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.delenv("SPREADSHEET_ID", raising=False)

    with pytest.raises(RuntimeError, match="SPREADSHEET_ID"):
        Config.from_env()


def test_config_user_agent_default_matches_audit_resolution(monkeypatch):
    """audit M-3' で確定した User-Agent デフォルト文字列を保証."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    monkeypatch.delenv("USER_AGENT", raising=False)

    cfg = Config.from_env()

    assert (
        cfg.user_agent
        == "TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)"
    )
