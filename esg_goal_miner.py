"""
ESG-Goal-Miner
===============

用法（CLI）:

    cd pepsico
    python esg_goal_miner.py --pdf pdf/2023-ESG-Performance-Metrics.pdf --year 2023 --output All_json/2023.json

輸入:
    - 一份 ESG PDF 報告
    - 報告年份 current_year（手動指定，避免自動判斷出錯）

輸出:
    - 一個 JSON 檔案，內容為整份報告所有頁面中偵測到的「承諾目標」列表。
      結構遵守 core.prompt.get_audit_prompt 定義的 Schema。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from core.gemini_client import GeminiClient
from core.pdf_extractor import extract_mixed_content


def run_esg_goal_miner(pdf_path: Path, report_year: int, output_path: Path) -> None:
    pages = extract_mixed_content(str(pdf_path))

    client = GeminiClient()
    all_items: List[Dict[str, Any]] = []

    for page in pages:
        text: str = page["text"]
        images: List[bytes] = page["images"]

        page_items = client.extract_goals_from_page(
            page_text=text,
            images=images,
            current_year=report_year,
        )

        for item in page_items:
            if isinstance(item, dict):
                item.setdefault("Report_Year", report_year)
                all_items.append(item)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"[ESG-Goal-Miner] 共寫出 {len(all_items)} 筆目標至: {output_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESG-Goal-Miner: 從 ESG PDF 報告自動抽取承諾目標為 JSON")
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="輸入 PDF 檔案路徑，例如: pdf/2023-ESG-Performance-Metrics.pdf",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="報告年份 (current_year)，例如 2023",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="輸出 JSON 檔案路徑，例如: All_json/2023.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    pdf_path = Path(args.pdf)
    output_path = Path(args.output)

    if not pdf_path.is_file():
        raise SystemExit(f"找不到 PDF 檔案: {pdf_path}")

    run_esg_goal_miner(pdf_path=pdf_path, report_year=args.year, output_path=output_path)


if __name__ == "__main__":
    main()


