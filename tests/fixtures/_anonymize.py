"""匿名化スクリプト: .tmp_recon/list.html → tests/fixtures/list_sample.json.

実機 HTML から vue-container[data] を抽出 → HTML エンティティをアンエスケープ →
json.loads で構造化したうえで、client.username / client.user_id /
client.user_picture_url を匿名化し、JSON として保存する。

匿名化方針 (Jobs 確定方針 C):
- client.user_id      : 連番 (1, 2, 3, ...) で置換 (ユニーク性は維持)
- client.username     : f"user_{連番}" で置換
- client.user_picture_url: 空文字列で置換 (該当属性のみ削除はせず空に統一)

その他フィールド (job_offer.id, title, description_digest, payment, entry, ...)
は CrowdWorks の公開 HTML で誰でも閲覧可能な情報のため変更しない。

このスクリプトは決定論的で、同じ入力に対して同じ出力を返す (連番採番のみ)。
.tmp_recon/list.html が存在しない場合はエラー終了する。

Usage:
    python tests/fixtures/_anonymize.py
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# .tmp_recon は git に含めずローカル限定。匿名化後フィクスチャのみリポジトリに残す。
DEFAULT_INPUT = Path(__file__).resolve().parents[2] / ".tmp_recon" / "list.html"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "list_sample.json"

# vue-container 要素の data 属性の正規表現 (HTMLエスケープされた JSON 文字列)
# Crowdworks 一覧 HTML には他にも data="..." 属性が多数存在するため、
# `<vue-container ... data="{..."` で限定する。
VUE_CONTAINER_RE = re.compile(
    r'<vue-container[^>]*\bdata="(\{[^"]+\})"',
    re.DOTALL,
)


def _extract_vue_data(html_text: str) -> dict:
    """vue-container[data] 属性から JSON を取り出す."""
    match = VUE_CONTAINER_RE.search(html_text)
    if match is None:
        # フォールバック: 単に最初の data="{...}" を取る
        fallback = re.search(r'\bdata="(\{[^"]+\})"', html_text, re.DOTALL)
        if fallback is None:
            raise RuntimeError("vue-container[data] not found in input HTML")
        match = fallback
    raw = html.unescape(match.group(1))
    return json.loads(raw)


def _anonymize_client(client: dict, mapping: dict, counter: list) -> dict:
    """client セクションを匿名化."""
    if not isinstance(client, dict):
        return client
    real_id = client.get("user_id")
    if real_id is None:
        return client
    if real_id not in mapping:
        counter[0] += 1
        mapping[real_id] = counter[0]
    seq = mapping[real_id]
    return {
        "user_id": seq,
        "username": f"user_{seq}",
        "user_picture_url": "",
        "is_employer_certification": client.get("is_employer_certification", False),
    }


def anonymize(data: dict) -> dict:
    """vue-container[data] 全体を匿名化."""
    sr = data.get("searchResult") or {}
    mapping: dict = {}
    counter = [0]

    def _walk(offers: list) -> list:
        if not isinstance(offers, list):
            return offers
        out = []
        for entry in offers:
            if not isinstance(entry, dict):
                out.append(entry)
                continue
            new_entry = dict(entry)
            if "client" in new_entry:
                new_entry["client"] = _anonymize_client(
                    new_entry["client"], mapping, counter
                )
            out.append(new_entry)
        return out

    if "job_offers" in sr:
        sr["job_offers"] = _walk(sr["job_offers"])
    for key in ("pr_diamond", "pr_platinum", "pr_gold", "recommendation", "watchlists"):
        if key in sr:
            sr[key] = _walk(sr[key])
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 1

    html_text = args.input.read_text(encoding="utf-8")
    data = _extract_vue_data(html_text)
    data = anonymize(data)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sr = data.get("searchResult") or {}
    print(
        f"wrote {args.output} job_offers={len(sr.get('job_offers') or [])} "
        f"pr_diamond={len(sr.get('pr_diamond') or [])} "
        f"pr_platinum={len(sr.get('pr_platinum') or [])} "
        f"pr_gold={len(sr.get('pr_gold') or [])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
