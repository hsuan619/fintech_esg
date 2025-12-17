import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import streamlit as st

from core.gemini_client import GeminiClient
from core.pdf_extractor import extract_mixed_content


def _infer_year_from_name(name: str, default: int = 2024) -> int:
    match = re.search(r"20\d{2}", name)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return default
    return default


def _run_extraction(
    pdf_path: Path, report_year: int, pages_filter: Optional[Set[int]] = None
) -> List[Dict[str, Any]]:
    """直接在記憶體中執行 PDF → JSON 目標擷取，不寫入實體 JSON 檔。

    pages_filter:
        若提供，僅對指定頁碼呼叫 Gemini（0-based page index）。
        例如 {0, 4, 5} 代表第 1, 5, 6 頁。
    """
    pages = extract_mixed_content(str(pdf_path))

    if pages_filter:
        pages = [p for p in pages if int(p.get("page_index", -1)) in pages_filter]
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

    return all_items


def render() -> None:
    """單一頁籤：上傳 PDF → 直接產出目標 JSON。"""
    st.header("步驟一：上傳 ESG 報告並自動擷取目標 (PDF → JSON)")
    st.markdown(
        """
        上傳 ESG 報告 PDF 後，系統將：
        1. 逐頁讀取文字與圖表（含整頁截圖給 Vision 模型）
        2. 依照標準化字典與 Schema，自動擷取「承諾目標」並輸出 JSON
        """
    )

    uploaded_pdf = st.file_uploader(
        "上傳 ESG 報告書 (PDF)", type=["pdf"], key="pdf_uploader_v2"
    )

    # 推測預設年份
    default_year = 2024
    if uploaded_pdf:
        default_year = _infer_year_from_name(uploaded_pdf.name, default_year)

    report_year = st.number_input(
        "設定報告年份",
        min_value=2000,
        max_value=2050,
        value=default_year,
        key="report_year_input_v2",
    )

    if "goal_json" not in st.session_state:
        st.session_state.goal_json = None

    # 可選：限制要解析的頁碼，降低 API 成本
    pages_raw = st.text_input(
        "（選填）只解析特定頁碼以節省 API 成本，例如：5 或 3-7,10（以 1 為起始頁）",
        value="",
        key="pages_filter_v2",
    )

    pages_filter: Optional[Set[int]] = None
    if pages_raw.strip():
        pages_filter = set()
        for part in pages_raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                try:
                    start_s, end_s = part.split("-", 1)
                    start = int(start_s)
                    end = int(end_s)
                    for p in range(start, end + 1):
                        # 轉為 0-based index
                        pages_filter.add(p - 1)
                except ValueError:
                    continue
            else:
                try:
                    p = int(part)
                    pages_filter.add(p - 1)
                except ValueError:
                    continue

    if uploaded_pdf is not None:
        if st.button("開始解析目標 (PDF → JSON)"):
            st.info(f"正在處理檔案: {uploaded_pdf.name} ... 這可能需要數十秒。")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_pdf.read())
                tmp_path = Path(tmp_pdf.name)

            try:
                with st.spinner("Gemini 正在解析圖表與文字..."):
                    data = _run_extraction(tmp_path, int(report_year), pages_filter)
                st.session_state.goal_json = data
                st.success(f"解析完成！共擷取到 {len(data)} 筆目標紀錄。")
            except Exception as e:  # noqa: BLE001
                st.session_state.goal_json = None
                st.error(f"解析過程發生錯誤：{e}")
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    if st.session_state.goal_json:
        st.subheader("📄 抽取出的目標 JSON")
        pretty = json.dumps(st.session_state.goal_json, ensure_ascii=False, indent=2)
        st.code(pretty, language="json")

        file_name = f"{uploaded_pdf.name}_{int(report_year)}.json"
        st.download_button(
            label="📥 下載目標 JSON 檔",
            data=pretty,
            file_name=file_name,
            mime="application/json",
        )


