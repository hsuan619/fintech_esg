from typing import Any, Dict, List

# 支援兩種執行方式：
# 1. 作為 package 匯入：  from pepsico.core.pdf_extractor import ...
# 2. 直接在 pepsico 目錄執行：python esg_goal_miner.py
try:
    from ..pp import extract_content_smart  # type: ignore[import-not-found]
except ImportError:  # 當前目錄直接執行時走這條
    from pp import extract_content_smart  # type: ignore[import-not-found]


def extract_mixed_content(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Step 2: PDF 混合內容提取器

    - 使用 PyMuPDF 逐頁讀取
    - 提取純文字
    - 提取該頁所有圖片 (bytes)

    回傳格式:
        [
          {
            "page_index": 0,
            "text": "...",
            "images": [b"...", ...],
            "is_scanned": bool,
          },
          ...
        ]
    """
    # extract_content_smart 內部已負責開啟與關閉 PDF
    pages: List[Dict[str, Any]] = []

    import fitz  # lazy import to keep dependency localized

    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    doc.close()

    for i in range(page_count):
        text, images, is_scanned = extract_content_smart(pdf_path, i)

        # 為了確保 LLM 一定看到整張圖表/趨勢圖，
        # 非掃描模式下再額外補上一張整頁截圖。
        if not is_scanned:
            doc_page = fitz.open(pdf_path).load_page(i)
            pix = doc_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            images.append(pix.tobytes("png"))

        pages.append(
            {
                "page_index": i,
                "text": text,
                "images": images,
                "is_scanned": is_scanned,
            }
        )

    return pages


