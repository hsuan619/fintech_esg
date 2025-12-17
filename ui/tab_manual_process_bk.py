import tempfile
from pathlib import Path
from typing import Optional, Set

import streamlit as st

# 重用 core 的邏輯
from core.pdf_extractor import extract_mixed_content
from core.prompt import get_audit_prompt

def render() -> None:
    """Tab 4: 手動模式 (預覽圖片 + 產生 Prompt)"""
    st.header("步驟四：手動處理模式 (免 API)")
    st.markdown(
        """
        當 API 額度不足或需要除錯時，可使用此模式：
        1. **上傳 PDF**：系統會解析每一頁的模式 (TEXT/HYBRID)。
        2. **預覽圖片**：針對圖表頁，您可以下載圖片或直接截圖。
        3. **複製 Prompt**：系統會自動組好包含 Schema 與文字的 Prompt，您只需複製並貼給 ChatGPT/Gemini (記得連同圖片一起上傳)。
        """
    )

    uploaded_pdf = st.file_uploader(
        "上傳 ESG 報告書 (PDF)", type=["pdf"], key="pdf_uploader_manual"
    )

    report_year = st.number_input(
        "設定報告年份",
        min_value=2000,
        max_value=2050,
        value=2024,
        key="report_year_manual",
    )

    # 頁碼過濾 (方便只處理特定幾頁)
    pages_raw = st.text_input(
        "（選填）只顯示特定頁碼，例如：5 或 3-7（以 1 為起始頁）",
        value="",
        key="pages_filter_manual",
    )

    if uploaded_pdf is not None:
        if st.button("開始解析 (不消耗 API)"):
            with st.spinner("正在解析 PDF 結構與提取圖片..."):
                # 1. 儲存暫存檔
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    tmp_pdf.write(uploaded_pdf.read())
                    tmp_path = Path(tmp_pdf.name)

                try:
                    # 2. 執行核心提取 (不呼叫 Gemini Client)
                    pages = extract_mixed_content(str(tmp_path))
                    
                    # 3. 處理頁碼過濾
                    pages_filter = _parse_pages_filter(pages_raw)
                    if pages_filter:
                        pages = [p for p in pages if int(p.get("page_index", -1)) in pages_filter]

                    st.success(f"解析完成！顯示 {len(pages)} 個頁面。")
                    st.divider()

                    # 4. 逐頁顯示介面
                    for p in pages:
                        idx = p["page_index"] + 1
                        mode = p["mode"]
                        text = p["text"]
                        images = p["images"]

                        # 設定顏色標記
                        mode_color = "green"
                        if mode == "HYBRID": mode_color = "orange"
                        if mode == "VISION": mode_color = "red"
                        
                        with st.expander(f"第 {idx} 頁 - :{mode_color}[{mode}]"):
                            
                            # A. 顯示圖片 (如果是 HYBRID/VISION)
                            if mode in ["HYBRID", "VISION"] and images:
                                st.info("📸 **此頁包含圖表或為掃描檔，請將下方圖片存檔或截圖，連同 Prompt 一起貼給 AI。**")
                                for img_bytes in images:
                                    st.image(img_bytes, caption=f"Page {idx} Screenshot", use_container_width=True)
                            
                            # B. 組合 Prompt
                            manual_content_parts = []
                            
                            # 加入手動模式專用提示
                            if mode in ["HYBRID", "VISION"] and images:
                                manual_content_parts.append(
                                    "⚠️ [USER INSTRUCTION]: I have uploaded an image corresponding to this page. "
                                    "Please combine the visual trend information from the image with the text below."
                                )
                                manual_content_parts.append(
                                    "⚠️ [SYSTEM WARNING]: The PDF text layer might be disordered. "
                                    "Rely on the image for 'Year-Value' alignment in charts."
                                )
                            
                            manual_content_parts.append(f"# Raw Page Text\n{text.strip()}")
                            
                            # 產生最終完整 Prompt
                            full_prompt = get_audit_prompt(
                                current_year=report_year, 
                                content="\n\n".join(manual_content_parts)
                            )

                            # C. 顯示 Prompt 複製區
                            st.subheader("📋 複製 Prompt")
                            st.text_area(
                                label="請複製以下內容 (JSON Schema + Data)",
                                value=full_prompt,
                                height=250,
                                key=f"prompt_area_{idx}"
                            )

                except Exception as e:
                    st.error(f"解析發生錯誤: {e}")
                finally:
                    # 清理暫存
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

def _parse_pages_filter(pages_raw: str) -> Optional[Set[int]]:
    """解析頁碼字串 (例如 "1, 3-5") 回傳 0-based index set"""
    if not pages_raw.strip():
        return None
    
    pages_filter = set()
    for part in pages_raw.split(","):
        part = part.strip()
        if not part: continue
        
        if "-" in part:
            try:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s), int(end_s)
                for p in range(start, end + 1):
                    pages_filter.add(p - 1)
            except ValueError:
                continue
        else:
            try:
                pages_filter.add(int(part) - 1)
            except ValueError:
                continue
    return pages_filter