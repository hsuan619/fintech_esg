import os
import re
import tempfile

import streamlit as st
from markitdown import MarkItDown


def render() -> None:
    """Tab 1: 報告轉換 (PDF -> Markdown)"""
    st.header("步驟一：上傳並轉換報告書")
    st.markdown("將 PDF 格式的 ESG 報告書轉換為 AI 可讀的 Markdown 格式。")

    uploaded_pdf = st.file_uploader(
        "上傳 ESG 報告書 (PDF)", type=["pdf"], key="pdf_uploader"
    )

    # 狀態保存：Markdown 內容
    if "markdown_content" not in st.session_state:
        st.session_state.markdown_content = ""

    # 嘗試從檔名自動提取年份
    default_year = 2024
    if uploaded_pdf:
        match = re.search(r"20\d{2}", uploaded_pdf.name)
        if match:
            default_year = int(match.group(0))

    report_year = st.number_input(
        "設定報告年份",
        min_value=2000,
        max_value=2030,
        value=default_year,
        key="report_year_input",
    )
    st.session_state.report_year = report_year

    if uploaded_pdf is not None:
        if st.button("開始轉換"):
            st.info(f"正在處理檔案: {uploaded_pdf.name} ...")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_pdf.read())
                tmp_pdf_path = tmp_pdf.name

            try:
                md = MarkItDown()
                result = md.convert(tmp_pdf_path)
                st.session_state.markdown_content = result.text_content
                os.remove(tmp_pdf_path)
                st.success("轉換成功！請至「產生稽核 Prompt」分頁查看。")

            except Exception as e:  # noqa: BLE001
                st.error(f"轉換錯誤: {e}")
                if os.path.exists(tmp_pdf_path):
                    os.remove(tmp_pdf_path)

    if st.session_state.markdown_content:
        with st.expander("查看轉換後的 Markdown 內容"):
            st.text_area(
                "內容預覽", st.session_state.markdown_content, height=300, key="md_preview"
            )
            st.download_button(
                label="下載 Markdown (.md)",
                data=st.session_state.markdown_content,
                file_name=f"report_{report_year}.md",
                mime="text/markdown",
            )


