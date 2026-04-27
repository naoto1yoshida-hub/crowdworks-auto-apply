"""HTTP 取得・robots.txt 検証ユーティリティ。

実装計画書 v0.3 §Task 4 に対応。

設計方針:
- requests.Session ベース。User-Agent は audit M-3' 確定値 (Config.user_agent)
- 指数バックオフ付きリトライ (5xx / connection error)
- レート制限: 直前の取得時刻からの経過時間で sleep 制御 (REQUEST_INTERVAL_SEC)
- robots.txt は urllib.robotparser で評価。User-Agent 文字列に対して can_fetch() を返す
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional
from urllib.robotparser import RobotFileParser

import requests


@dataclass
class HttpClient:
    """CrowdWorks 取得用の HTTP クライアント (Session ラッパ)。

    Attributes:
        user_agent: User-Agent 文字列 (audit M-3' 確定値推奨)
        timeout: 1 リクエストのタイムアウト秒数
        retry_max_attempts: 最大リトライ回数 (1 = 1回試行で終了)
        retry_backoff_base: 指数バックオフ基数 (sleep = base ** (attempt-1))
        request_interval_sec: 連続リクエスト間の最小間隔秒数
    """

    user_agent: str
    timeout: int = 30
    retry_max_attempts: int = 2
    retry_backoff_base: float = 2.0
    request_interval_sec: float = 1.0

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})
        self._last_request_at: Optional[float] = None

    def get(self, url: str) -> requests.Response:
        """URL を GET し、5xx / connection error はリトライする。

        Raises:
            requests.HTTPError: 4xx 応答 (リトライしない)
            requests.RequestException: 全リトライ失敗時の最終例外
        """
        attempts = max(1, self.retry_max_attempts)
        last_exc: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            self._respect_rate_limit()
            try:
                response = self._session.get(url, timeout=self.timeout)
                self._last_request_at = time.monotonic()
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= attempts:
                    raise
                self._sleep_backoff(attempt)
                continue
            if 500 <= response.status_code < 600 and attempt < attempts:
                self._sleep_backoff(attempt)
                continue
            response.raise_for_status()
            return response
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("unreachable: get() exited loop without return")

    def _respect_rate_limit(self) -> None:
        if self._last_request_at is None or self.request_interval_sec <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self.request_interval_sec - elapsed
        if wait > 0:
            time.sleep(wait)

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.retry_backoff_base ** (attempt - 1)
        time.sleep(delay)


@dataclass
class RobotsChecker:
    """robots.txt を取得して URL のクロール可否を判定するチェッカ。"""

    robots_url: str
    user_agent: str

    def __post_init__(self) -> None:
        self._parser: Optional[RobotFileParser] = None

    def load(self, http_client: Optional[HttpClient] = None) -> None:
        """robots.txt を取得してパーサにロードする (1 度だけ呼び出せばよい)。

        http_client が指定された場合はそちらの User-Agent / セッションで取得する。
        指定がない場合は urllib のデフォルト挙動 (RobotFileParser.read) を使う。
        """
        parser = RobotFileParser()
        parser.set_url(self.robots_url)
        if http_client is None:
            parser.read()
        else:
            response = http_client.get(self.robots_url)
            parser.parse(response.text.splitlines())
        self._parser = parser

    def can_fetch(self, url: str) -> bool:
        if self._parser is None:
            raise RuntimeError("RobotsChecker.load() must be called before can_fetch()")
        return self._parser.can_fetch(self.user_agent, url)
