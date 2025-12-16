import streamlit as st

from core.prompt import get_audit_prompt


def render() -> None:
    """Tab 2: 產生稽核 Prompt"""
    st.header("步驟二：生成 AI 稽核 Prompt")
    st.markdown("將轉換後的內容結合標準化指令，產生可供 ChatGPT/Claude/Gemini 使用的 Prompt。")

    if st.session_state.get("markdown_content"):
        final_prompt = get_audit_prompt(
            st.session_state.get("report_year", 2024),
            st.session_state["markdown_content"],
        )

        st.info(
            "💡 請複製下方內容，貼給 LLM 模型，並將其回傳的 JSON 存檔供步驟三使用。"
        )
        st.text_area("Prompt 預覽", final_prompt, height=400, key="prompt_preview")

        st.download_button(
            label="下載完整 Prompt (.txt)",
            data=final_prompt,
            file_name=f"Audit_Prompt_{st.session_state.get('report_year', 2024)}.txt",
            mime="text/plain",
        )
    else:
        st.warning("請先在步驟一上傳並轉換 PDF 報告。")


