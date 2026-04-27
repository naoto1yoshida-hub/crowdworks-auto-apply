"""fetcher.py のテスト (TDD)。

匿名化済み実機サンプル (tests/fixtures/list_sample.json) を vue-container[data] に
埋め込んだ最小 HTML を組み立て、parse_list_html / parse_payment / parse_job_offer_entry
の振る舞いを検証する。
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.fetcher import (
    extract_vue_data,
    parse_job_offer_entry,
    parse_list_html,
    parse_payment,
)
from src.models import Job


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "list_sample.json"


def _build_html_from_fixture() -> str:
    """匿名化済み JSON を vue-container[data] に埋め込んだ最小 HTML を生成。"""
    raw = _FIXTURE_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    encoded = html.escape(json.dumps(data, ensure_ascii=False), quote=True)
    return (
        '<html><body>'
        f'<vue-container component="public_jobs" data="{encoded}"></vue-container>'
        '</body></html>'
    )


def test_extract_vue_data_returns_search_result() -> None:
    page = _build_html_from_fixture()
    data = extract_vue_data(page)
    assert "searchResult" in data
    assert isinstance(data["searchResult"].get("job_offers"), list)


def test_extract_vue_data_raises_when_container_missing() -> None:
    with pytest.raises(ValueError):
        extract_vue_data("<html><body><div>no vue here</div></body></html>")


def test_parse_list_html_returns_50_jobs_from_fixture() -> None:
    page = _build_html_from_fixture()
    scanned = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    jobs = parse_list_html(page, scanned_at=scanned)
    assert len(jobs) == 50
    for job in jobs:
        assert isinstance(job, Job)
        assert job.job_id and isinstance(job.job_id, str)
        assert job.title
        assert job.url.startswith("https://crowdworks.jp/public/jobs/")
        assert job.url.endswith(job.job_id)
        assert job.scanned_at == scanned
        assert job.posted_at is None or job.posted_at.tzinfo is not None


def test_parse_list_html_uses_description_digest() -> None:
    """Phase 1 では一覧時点で description = description_digest (120 字)。"""
    page = _build_html_from_fixture()
    jobs = parse_list_html(page)
    assert any(job.description for job in jobs)
    for job in jobs:
        assert len(job.description) <= 200  # digest は実機 120 字、安全マージン込み


def test_parse_list_html_default_scanned_at_is_utc_now() -> None:
    page = _build_html_from_fixture()
    before = datetime.now(timezone.utc)
    jobs = parse_list_html(page)
    after = datetime.now(timezone.utc)
    assert jobs
    for job in jobs:
        assert before <= job.scanned_at <= after


def test_parse_list_html_excludes_pr_diamond_and_platinum() -> None:
    """広告枠 (pr_diamond / pr_platinum / pr_gold) は除外する。"""
    page = _build_html_from_fixture()
    jobs = parse_list_html(page)
    assert len(jobs) == 50  # job_offers のみ、PR 枠 7 件は含まない


def test_parse_list_html_raises_on_missing_container() -> None:
    with pytest.raises(ValueError):
        parse_list_html("<html>no vue-container here</html>")


@pytest.mark.parametrize(
    "payment, expected_substrings",
    [
        ({"fixed_price_payment": {"min_budget": 100000, "max_budget": 200000}},
         ["固定報酬", "min_budget=100000", "max_budget=200000"]),
        ({"task_payment": {"task_price": 7.0, "estimated_work_minutes": 19}},
         ["タスク", "task_price=7", "estimated_work_minutes=19"]),
        ({"hourly_payment": {"min_hourly_wage": 2000, "max_hourly_wage": 3000}},
         ["時給", "min_hourly_wage=2000", "max_hourly_wage=3000"]),
        ({"fixed_price_writing_payment":
            {"article_price": 600.0, "min_articles_length": 500.0, "max_articles_length": 500.0}},
         ["記事単価", "article_price=600", "min_articles_length=500"]),
        ({"competition_payment": {"competition_price": 6600}},
         ["コンペ", "competition_price=6600"]),
    ],
)
def test_parse_payment_normalizes_all_five_subtypes(
    payment: dict, expected_substrings: list[str]
) -> None:
    result = parse_payment(payment)
    for sub in expected_substrings:
        assert sub in result


def test_parse_payment_returns_empty_for_empty_input() -> None:
    assert parse_payment({}) == ""
    assert parse_payment(None) == ""


def test_parse_job_offer_entry_returns_none_when_id_missing() -> None:
    entry = {"job_offer": {"title": "no id"}}
    scanned = datetime(2026, 4, 27, tzinfo=timezone.utc)
    assert parse_job_offer_entry(entry, scanned_at=scanned) is None


def test_parse_job_offer_entry_maps_category_genre() -> None:
    entry = {
        "job_offer": {
            "id": 9999,
            "title": "Test",
            "description_digest": "digest",
            "category_id": 56,
            "genre": "sport",
            "last_released_at": "2026-04-27T10:02:01+09:00",
        },
        "payment": {"fixed_price_payment": {"min_budget": 1000, "max_budget": 2000}},
    }
    scanned = datetime(2026, 4, 27, tzinfo=timezone.utc)
    job = parse_job_offer_entry(entry, scanned_at=scanned)
    assert job is not None
    assert job.job_id == "9999"
    assert job.category == "sport/56"
    assert job.posted_at is not None
    assert job.posted_at.tzinfo is not None
    assert "固定報酬" in job.budget_text


def test_anonymized_fixture_has_no_real_usernames() -> None:
    """フィクスチャは匿名化済みであることを再検証 (実値混入の回帰防止)。"""
    raw = _FIXTURE_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    for entry in data["searchResult"]["job_offers"]:
        client = entry.get("client") or {}
        username = client.get("username") or ""
        user_id = client.get("user_id")
        # 匿名化後は username が "user_<seq>" 形式、user_id は連番 (1..N) のみ
        assert username.startswith("user_") or username == ""
        assert user_id is None or (isinstance(user_id, int) and 0 < user_id <= 1000)
