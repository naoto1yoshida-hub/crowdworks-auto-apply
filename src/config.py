"""CrowdWorks 自動応募システム v0.3 — 環境変数ローダ / 定数集約。

実装計画書 v0.2 §Task 3 に対応。

設計方針:
- 必須キーは ANTHROPIC_API_KEY と SPREADSHEET_ID のみ。他は安全なデフォルトを持つ
- audit C-2 解消のため Anthropic モデル ID は環境変数で差替可能（デフォルトのみ実装内固定）
- audit M-3' で確定した User-Agent をデフォルトに採用
- セレクタ系は HTML 構造変化時に Secret 経由で差替可能（feasibility v0.2 §8 R1 緩和策）
- frozen=True でランタイム改変を禁止し、構成のイミュータブル性を担保
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# audit M-3' で確定した User-Agent デフォルト
_DEFAULT_USER_AGENT = (
    "TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)"
)

# audit C-2 / implementation_plan v0.2 で固定する Anthropic モデル ID デフォルト
_DEFAULT_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_SONNET_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class Config:
    """ランタイム設定の集約。`Config.from_env()` でロードする。"""

    # Anthropic
    anthropic_api_key: str
    haiku_model: str
    sonnet_model: str

    # Sheets
    spreadsheet_id: str
    google_service_account_file: str
    google_service_account_json: str

    # CrowdWorks
    crowdworks_list_url: str
    crowdworks_detail_url_template: str
    crowdworks_robots_url: str
    user_agent: str

    # Rate limiting / retry
    request_timeout: int
    request_interval_sec: float
    max_detail_fetch: int
    retry_max_attempts: int
    retry_backoff_base: float

    # HTML selectors（環境変数で差替可能、デフォルトは Task 4 で実機検証して確定する暫定値）
    selector_job_item: str
    selector_job_link: str
    selector_job_title: str
    selector_job_posted_at: str
    selector_job_category: str
    selector_detail_body: str
    selector_detail_budget: str

    # Pipeline
    daily_apply_limit: int
    score_threshold: int

    @classmethod
    def from_env(cls) -> "Config":
        """環境変数から Config を構築する。

        必須キーが欠落している場合は RuntimeError を送出する。
        """
        required = ["ANTHROPIC_API_KEY", "SPREADSHEET_ID"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"missing required env vars: {', '.join(missing)}"
            )

        return cls(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            haiku_model=os.environ.get("ANTHROPIC_HAIKU_MODEL", _DEFAULT_HAIKU_MODEL),
            sonnet_model=os.environ.get("ANTHROPIC_SONNET_MODEL", _DEFAULT_SONNET_MODEL),
            spreadsheet_id=os.environ["SPREADSHEET_ID"],
            google_service_account_file=os.environ.get(
                "GOOGLE_SERVICE_ACCOUNT_FILE", "./service_account.json"
            ),
            google_service_account_json=os.environ.get(
                "GOOGLE_SERVICE_ACCOUNT_JSON", ""
            ),
            crowdworks_list_url=os.environ.get(
                "CROWDWORKS_LIST_URL",
                "https://crowdworks.jp/public/jobs?order=new",
            ),
            crowdworks_detail_url_template=os.environ.get(
                "CROWDWORKS_DETAIL_URL_TEMPLATE",
                "https://crowdworks.jp/public/jobs/{job_id}",
            ),
            crowdworks_robots_url=os.environ.get(
                "CROWDWORKS_ROBOTS_URL", "https://crowdworks.jp/robots.txt"
            ),
            user_agent=os.environ.get("USER_AGENT", _DEFAULT_USER_AGENT),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "30")),
            request_interval_sec=float(os.environ.get("REQUEST_INTERVAL_SEC", "1.0")),
            max_detail_fetch=int(os.environ.get("MAX_DETAIL_FETCH", "30")),
            retry_max_attempts=int(os.environ.get("RETRY_MAX_ATTEMPTS", "2")),
            retry_backoff_base=float(os.environ.get("RETRY_BACKOFF_BASE", "2.0")),
            selector_job_item=os.environ.get(
                "SELECTOR_JOB_ITEM", "ul.search_results li.jobs_lists"
            ),
            selector_job_link=os.environ.get("SELECTOR_JOB_LINK", "a.item_title"),
            selector_job_title=os.environ.get("SELECTOR_JOB_TITLE", "a.item_title"),
            selector_job_posted_at=os.environ.get(
                "SELECTOR_JOB_POSTED_AT", ".posted_time"
            ),
            selector_job_category=os.environ.get("SELECTOR_JOB_CATEGORY", ".category"),
            selector_detail_body=os.environ.get(
                "SELECTOR_DETAIL_BODY", ".job_detail_description"
            ),
            selector_detail_budget=os.environ.get(
                "SELECTOR_DETAIL_BUDGET", ".job_contents_price"
            ),
            daily_apply_limit=int(os.environ.get("DAILY_APPLY_LIMIT", "10")),
            score_threshold=int(os.environ.get("SCORE_THRESHOLD", "60")),
        )
