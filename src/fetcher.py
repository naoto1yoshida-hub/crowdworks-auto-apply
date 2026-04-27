"""CrowdWorks 一覧 HTML から案件レコードを抽出するパーサ群。

実装計画書 v0.3 §Task 4 / feasibility v0.3 §3.2 に対応。

設計方針 (オーナー確定方針 A):
- CrowdWorks の `/public/jobs` ページは Vue ベース SPA で、HTML 内の
  `<vue-container ... data="...">` 属性に searchResult JSON が埋め込まれている
- 旧 BS4 + DOM セレクタ方式は実 HTML に対応する DOM が存在しないため廃止
- 1 リクエストで 50 件分の案件メタデータが取得可能 (Phase 1 ではこの digest で
  スコアリング、60 点以上のみ詳細取得して応募文生成)

スキーマ参考: tests/fixtures/list_sample.json (匿名化済み実機サンプル)
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from src.models import Job


# vue-container 要素の data 属性 (HTML エスケープ済み JSON 文字列) を抽出する正規表現。
# 一覧 HTML には `data="..."` を持つ要素が複数あるため、`<vue-container ...>` で限定する。
_VUE_CONTAINER_RE = re.compile(
    r'<vue-container[^>]*\bdata="(\{[^"]+\})"',
    re.DOTALL,
)

# 詳細ページ URL テンプレート (Config 経由で差替可能だが fetcher 単体テスト用にデフォルト保持)
_DEFAULT_DETAIL_URL_TEMPLATE = "https://crowdworks.jp/public/jobs/{job_id}"

# payment サブタイプ → 日本語ラベル (Scorer / ProposalGen 入力用、人間可読)
_PAYMENT_LABEL = {
    "fixed_price_payment": "固定報酬",
    "task_payment": "タスク",
    "hourly_payment": "時給",
    "fixed_price_writing_payment": "記事単価",
    "competition_payment": "コンペ",
}


def extract_vue_data(html_text: str) -> dict:
    """一覧 HTML から `<vue-container data="...">` の JSON を抽出する。

    Raises:
        ValueError: vue-container[data] が見つからない、または JSON パース失敗時。
    """
    match = _VUE_CONTAINER_RE.search(html_text)
    if match is None:
        raise ValueError("vue-container[data] not found in HTML")
    raw = html.unescape(match.group(1))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse vue-container JSON: {exc}") from exc


def parse_payment(payment: Optional[dict]) -> str:
    """payment dict (5 サブタイプのいずれか) を可読な単一文字列に正規化する。

    payment は `{"<subtype_key>": {...フィールド...}}` という構造。サブタイプは
    fixed_price_payment / task_payment / hourly_payment / fixed_price_writing_payment /
    competition_payment の 5 つ (実機 50 件で網羅確認済)。

    例:
        >>> parse_payment({"fixed_price_payment": {"min_budget": 100000, "max_budget": 200000}})
        '固定報酬: min_budget=100000, max_budget=200000'
    """
    if not isinstance(payment, dict) or not payment:
        return ""
    parts: list[str] = []
    for ptype, body in payment.items():
        label = _PAYMENT_LABEL.get(ptype, ptype)
        if isinstance(body, dict):
            kv = ", ".join(f"{k}={_format_payment_value(v)}" for k, v in body.items())
            parts.append(f"{label}: {kv}")
        else:
            parts.append(f"{label}: {body}")
    return "; ".join(parts)


def _format_payment_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """ISO8601 (例: 2026-04-27T10:02:01+09:00) を tz-aware datetime に変換。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_url(job_id: str, url_template: str) -> str:
    return url_template.format(job_id=job_id)


def parse_job_offer_entry(
    entry: dict,
    *,
    scanned_at: datetime,
    detail_url_template: str = _DEFAULT_DETAIL_URL_TEMPLATE,
) -> Optional[Job]:
    """job_offers の 1 エントリ (job_offer + payment + entry + client) を Job に変換。

    job_offer.id が欠落する異常レコードは None を返してスキップする。一覧時点では
    description は description_digest (120 字) を採用し、詳細取得後にフルテキストで
    上書きする運用 (Phase 1 スコープ確定方針)。
    """
    job_offer = entry.get("job_offer") if isinstance(entry, dict) else None
    if not isinstance(job_offer, dict):
        return None
    raw_id = job_offer.get("id")
    if raw_id is None:
        return None
    job_id = str(raw_id)
    title = job_offer.get("title") or ""
    description_digest = job_offer.get("description_digest") or ""
    category_id = job_offer.get("category_id")
    genre = job_offer.get("genre")
    posted_at = _parse_iso8601(job_offer.get("last_released_at"))
    payment_text = parse_payment(entry.get("payment")) or None
    category = None
    if genre is not None and category_id is not None:
        category = f"{genre}/{category_id}"
    elif genre is not None:
        category = str(genre)
    elif category_id is not None:
        category = f"category_id={category_id}"
    return Job(
        job_id=job_id,
        title=title,
        url=_build_url(job_id, detail_url_template),
        description=description_digest,
        scanned_at=scanned_at,
        budget_text=payment_text,
        category=category,
        posted_at=posted_at,
    )


def parse_list_html(
    html_text: str,
    *,
    scanned_at: Optional[datetime] = None,
    detail_url_template: str = _DEFAULT_DETAIL_URL_TEMPLATE,
) -> list[Job]:
    """一覧ページ HTML 全体を Job のリストに変換する。

    pr_diamond / pr_platinum / pr_gold は通常検索結果ではなく広告枠扱いのため
    Phase 1 では除外し、`searchResult.job_offers` のみを採用する (feasibility v0.3 §3.2)。
    """
    if scanned_at is None:
        scanned_at = datetime.now(timezone.utc)
    data = extract_vue_data(html_text)
    sr = data.get("searchResult") or {}
    offers = sr.get("job_offers") or []
    jobs: list[Job] = []
    for entry in _iter_entries(offers):
        job = parse_job_offer_entry(
            entry,
            scanned_at=scanned_at,
            detail_url_template=detail_url_template,
        )
        if job is not None:
            jobs.append(job)
    return jobs


def _iter_entries(offers: Iterable[Any]) -> Iterable[dict]:
    for entry in offers:
        if isinstance(entry, dict):
            yield entry
