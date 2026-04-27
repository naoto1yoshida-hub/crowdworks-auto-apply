"""http_client.py のテスト (TDD)。

requests を本物の HTTP に飛ばすと外部依存になるため、requests_mock がないこの
プロジェクトでは Session.request を monkeypatch して挙動を検証する。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.http_client import HttpClient, RobotsChecker


def _make_response(status_code: int = 200, text: str = "ok") -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode("utf-8")
    return response


def test_http_client_sends_user_agent_header() -> None:
    client = HttpClient(user_agent="TEGG-Test/1.0", request_interval_sec=0)
    with patch.object(client._session, "get", return_value=_make_response()) as mock_get:
        client.get("https://example.com/")
    mock_get.assert_called_once()
    # User-Agent は Session.headers に設定される (requests がリクエスト時に適用)
    assert client._session.headers["User-Agent"] == "TEGG-Test/1.0"


def test_http_client_returns_response_on_success() -> None:
    client = HttpClient(user_agent="TEGG-Test/1.0", request_interval_sec=0)
    with patch.object(client._session, "get", return_value=_make_response(200, "hello")):
        response = client.get("https://example.com/")
    assert response.status_code == 200
    assert response.text == "hello"


def test_http_client_retries_on_5xx_then_succeeds() -> None:
    client = HttpClient(
        user_agent="TEGG-Test/1.0",
        retry_max_attempts=3,
        retry_backoff_base=1.0,
        request_interval_sec=0,
    )
    responses = [_make_response(503, "fail"), _make_response(200, "ok")]
    with patch.object(client._session, "get", side_effect=responses) as mock_get, \
         patch("src.http_client.time.sleep") as mock_sleep:
        response = client.get("https://example.com/")
    assert response.status_code == 200
    assert mock_get.call_count == 2
    assert mock_sleep.called  # backoff sleep が発動


def test_http_client_raises_after_exhausting_retries_on_5xx() -> None:
    client = HttpClient(
        user_agent="TEGG-Test/1.0",
        retry_max_attempts=2,
        retry_backoff_base=1.0,
        request_interval_sec=0,
    )
    with patch.object(client._session, "get", return_value=_make_response(503, "fail")), \
         patch("src.http_client.time.sleep"):
        with pytest.raises(requests.HTTPError):
            client.get("https://example.com/")


def test_http_client_does_not_retry_on_4xx() -> None:
    client = HttpClient(
        user_agent="TEGG-Test/1.0",
        retry_max_attempts=3,
        retry_backoff_base=1.0,
        request_interval_sec=0,
    )
    with patch.object(client._session, "get", return_value=_make_response(404, "nf")) as mock_get, \
         patch("src.http_client.time.sleep"):
        with pytest.raises(requests.HTTPError):
            client.get("https://example.com/")
    assert mock_get.call_count == 1  # 4xx はリトライしない


def test_http_client_retries_on_connection_error() -> None:
    client = HttpClient(
        user_agent="TEGG-Test/1.0",
        retry_max_attempts=2,
        retry_backoff_base=1.0,
        request_interval_sec=0,
    )
    side_effects: list[Any] = [
        requests.ConnectionError("boom"),
        _make_response(200, "ok"),
    ]
    with patch.object(client._session, "get", side_effect=side_effects), \
         patch("src.http_client.time.sleep"):
        response = client.get("https://example.com/")
    assert response.status_code == 200


def test_http_client_respects_rate_limit() -> None:
    """連続リクエスト時に request_interval_sec - elapsed の sleep が走ることを検証。"""
    client = HttpClient(
        user_agent="TEGG-Test/1.0",
        retry_max_attempts=1,
        request_interval_sec=1.5,
    )
    # 呼び出し順: (1) 1回目 GET 直後 (2) 2回目 _respect_rate_limit (3) 2回目 GET 直後
    monotonic_values = iter([100.0, 100.5, 102.0])
    with patch.object(client._session, "get", return_value=_make_response()), \
         patch("src.http_client.time.monotonic", side_effect=lambda: next(monotonic_values)), \
         patch("src.http_client.time.sleep") as mock_sleep:
        client.get("https://example.com/a")
        client.get("https://example.com/b")
    # 2 リクエスト目: elapsed = 100.5 - 100.0 = 0.5、wait = 1.5 - 0.5 = 1.0
    sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
    assert any(abs(arg - 1.0) < 0.01 for arg in sleep_args), (
        f"expected sleep(~1.0), got {sleep_args}"
    )


def test_http_client_skips_rate_limit_when_interval_zero() -> None:
    client = HttpClient(
        user_agent="TEGG-Test/1.0",
        retry_max_attempts=1,
        request_interval_sec=0,
    )
    with patch.object(client._session, "get", return_value=_make_response()), \
         patch("src.http_client.time.sleep") as mock_sleep:
        client.get("https://example.com/a")
        client.get("https://example.com/b")
    assert mock_sleep.call_count == 0


def test_robots_checker_can_fetch_after_load() -> None:
    checker = RobotsChecker(
        robots_url="https://example.com/robots.txt",
        user_agent="TEGG-Test/1.0",
    )
    fake_robots = "User-agent: *\nDisallow: /private/\n"
    fake_client = MagicMock()
    fake_client.get.return_value = MagicMock(text=fake_robots)
    checker.load(http_client=fake_client)
    assert checker.can_fetch("https://example.com/public/jobs") is True
    assert checker.can_fetch("https://example.com/private/x") is False


def test_robots_checker_requires_load_before_can_fetch() -> None:
    checker = RobotsChecker(
        robots_url="https://example.com/robots.txt",
        user_agent="TEGG-Test/1.0",
    )
    with pytest.raises(RuntimeError):
        checker.can_fetch("https://example.com/")
