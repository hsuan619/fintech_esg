# import fitz  # PyMuPDF
# import numpy as np
# from typing import Any, Dict, List

# def analyze_page_metrics(page: fitz.Page) -> Dict[str, Any]:
#     """
#     核心分析邏輯：分析頁面的文字分佈、繪圖物件與文字量
#     原則：結合「物理特徵 (Density/Drawings)」與「語義特徵 (Keywords)」來區分複雜表格與圖表。
#     """
#     # 1. 提取基礎資訊
#     raw_text = page.get_text()
#     text_len = len(raw_text.strip())
#     words = page.get_text("words")
#     drawings = page.get_drawings()
#     drawing_count = len(drawings)
#     images = page.get_images(full=True)
#     img_count = len(images)

#     # 2. 語義關鍵字偵測 (Semantic Keyword Detection)
#     # 當物理指標(線條/密度)無法區分表格與圖表時，這些詞是關鍵線索
#     chart_keywords = [
#         "趨勢圖", "分析圖", "統計圖", "走勢圖", "分布圖", "示意圖", "路徑圖",
#         "Figure", "Chart", "Graph", "Diagram", "Trend", "Plot"
#     ]
#     # 檢查前 500 個字元通常能包含標題，不需要掃描全文
#     header_text = raw_text[:800] 
#     has_chart_keyword = any(k in header_text for k in chart_keywords)

#     # 3. 計算垂直密度直方圖
#     page_height = page.rect.height
#     densities = [0.0, 0.0, 0.0]
    
#     if page_height > 0 and len(words) > 0:
#         y_positions = [w[1] for w in words]
#         hist, _ = np.histogram(y_positions, bins=10, range=(0, page_height))
#         total_words = len(words)
#         bin_densities = hist / total_words
        
#         top_density = sum(bin_densities[:3])
#         middle_density = sum(bin_densities[3:7])
#         bottom_density = sum(bin_densities[7:])
#         densities = [top_density, middle_density, bottom_density]

#     # 4. 決策樹邏輯 (Decision Tree)
#     mode = "TEXT"
#     reason = "Normal Text"

#     # === 規則 0: 高文字量防護網 (Priority 1) ===
#     # 文字極多時，代表主要資訊是文字，忽略圖表特徵
#     if text_len > 1500:
#         mode = "TEXT"
#         reason = "High Text Density (Report/Table)"

#     # === 規則 A: 掃描檔/空頁 ===
#     elif text_len < 100:
#         if img_count > 0:
#             mode = "VISION"
#             reason = "Scanned Page (Image Dominant)"
#         else:
#             mode = "VISION"
#             reason = "Sparse Content"

#     # === 規則 B: 圖片存在 ===
#     elif img_count > 0:
#         mode = "HYBRID"
#         reason = "Image Detected (with Low Text)"

#     # === 規則 C: 向量圖形判定 (The Tie-Breaker) ===
#     # 當線條數量夠多 (>50) 時，我們需要區分是「複雜表格」還是「圖表」
#     elif drawing_count > 50:
#         # 情況 1: 中間很空 -> 肯定是圖表 (Chart)
#         if middle_density < 0.2:
#             mode = "HYBRID"
#             reason = "Vector Chart (Hollow Middle)"
        
#         # 情況 2: 中間有字 (可能是表格，也可能是圖表+標籤) -> 啟用關鍵字檢查
#         elif has_chart_keyword:
#             mode = "HYBRID"
#             reason = "Chart Keyword Detected ('趨勢圖'/Figure)"
        
#         # 情況 3: 中間有字且沒關鍵字 -> 視為表格 (Table)
#         else:
#             mode = "TEXT"
#             reason = "Complex Table (Vectors + Dense Text)"

#     # === 規則 D: 佈局偵測 (Layout Detection) ===
#     elif (top_density > 0.4 or (top_density + bottom_density > 0.6)):
#         # 同樣加入關鍵字輔助
#         if middle_density < 0.15:
#             if drawing_count > 5 or has_chart_keyword:
#                 mode = "HYBRID"
#                 reason = "Chart Layout (Hollow Middle)"
#             else:
#                 mode = "TEXT" # 純排版留白
#                 reason = "Layout Gap"
#         else:
#             mode = "TEXT"
#             reason = "Table Layout (Text in Middle)"

#     # === 預設 ===
#     else:
#         mode = "TEXT"
#         reason = "Uniform Text Distribution"

#     return {
#         "mode": mode,
#         "reason": reason,
#         "text_len": text_len,
#         "img_count": img_count,
#         "drawing_count": drawing_count,
#         "densities": densities
#     }

# # extract_mixed_content 維持不變...
# def extract_mixed_content(pdf_path: str) -> List[Dict[str, Any]]:
#     pages_data: List[Dict[str, Any]] = []
#     doc = fitz.open(pdf_path)
    
#     for i in range(len(doc)):
#         page = doc.load_page(i)
#         metrics = analyze_page_metrics(page)
#         mode = metrics["mode"]
        
#         final_text = ""
#         final_images = []

#         if mode == "VISION":
#             pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
#             final_images.append(pix.tobytes("png"))
#             final_text = "[System: Scanned Page / Image Detected]"
#         elif mode == "HYBRID":
#             final_text = page.get_text()
#             pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
#             final_images.append(pix.tobytes("png"))
#         else:
#             final_text = page.get_text()

#         pages_data.append({
#             "page_index": i,
#             "text": final_text,
#             "images": final_images,
#             "mode": mode,
#             "debug_reason": metrics["reason"]
#         })

#     doc.close()
#     return pages_data


import fitz  # PyMuPDF
import numpy as np
from typing import Any, Dict, List

def analyze_page_metrics(page: fitz.Page) -> Dict[str, Any]:
    """
    核心分析邏輯：結合「物理特徵」與「語義特徵」來區分複雜表格與圖表。
    """
    # 1. 提取基礎資訊
    raw_text = page.get_text()
    text_len = len(raw_text.strip())
    words = page.get_text("words")
    drawings = page.get_drawings()
    drawing_count = len(drawings)
    images = page.get_images(full=True)
    img_count = len(images)

    # 2. [關鍵修改] 語義關鍵字偵測
    # 當物理指標無法區分表格與圖表時，這些詞是關鍵線索
    chart_keywords = [
        "趨勢圖", "分析圖", "統計圖", "走勢圖", "分布圖", "示意圖", "路徑圖",
        "Figure", "Chart", "Graph", "Diagram", "Trend", "Plot", "Performance"
    ]
    # 檢查前 1000 個字元 (通常包含標題)
    header_text = raw_text[:1000] 
    has_chart_keyword = any(k in header_text for k in chart_keywords)

    # 3. 計算垂直密度直方圖
    page_height = page.rect.height
    densities = [0.0, 0.0, 0.0]
    
    if page_height > 0 and len(words) > 0:
        y_positions = [w[1] for w in words]
        hist, _ = np.histogram(y_positions, bins=10, range=(0, page_height))
        total_words = len(words)
        bin_densities = hist / total_words
        
        top_density = sum(bin_densities[:3])
        middle_density = sum(bin_densities[3:7])
        bottom_density = sum(bin_densities[7:])
        densities = [top_density, middle_density, bottom_density]

    # 4. 決策樹邏輯
    mode = "TEXT"
    reason = "Normal Text"

    # Rule 0: 高文字量防護 (Priority 1)
    if text_len > 1500:
        mode = "TEXT"
        reason = "High Text Density (Report/Table)"

    # Rule A: 掃描檔/空頁
    elif text_len < 100:
        if img_count > 0:
            mode = "VISION"
            reason = "Scanned Page (Image Dominant)"
        else:
            mode = "VISION"
            reason = "Sparse Content"

    # Rule B: 圖片存在
    elif img_count > 0:
        mode = "HYBRID"
        reason = "Image Detected (with Low Text)"

    # Rule C: 向量圖形判定 (關鍵修改)
    elif drawing_count > 50:
        # 情況 1: 中間很空 -> 肯定是圖表
        if middle_density < 0.2:
            mode = "HYBRID"
            reason = "Vector Chart (Hollow Middle)"
        # 情況 2: 中間有字 + 有關鍵字 -> 強制 HYBRID (解決台塑案例)
        elif has_chart_keyword:
            mode = "HYBRID"
            reason = "Chart Keyword Detected"
        # 情況 3: 中間有字 + 無關鍵字 -> 視為複雜表格
        else:
            mode = "TEXT"
            reason = "Complex Table (Vectors + Dense Text)"

    # Rule D: 佈局偵測
    elif (top_density > 0.4 or (top_density + bottom_density > 0.6)):
        if middle_density < 0.15:
            if drawing_count > 5 or has_chart_keyword:
                mode = "HYBRID"
                reason = "Chart Layout (Hollow Middle)"
            else:
                mode = "TEXT"
                reason = "Layout Gap"
        else:
            mode = "TEXT"
            reason = "Table Layout (Text in Middle)"

    else:
        mode = "TEXT"
        reason = "Uniform Text Distribution"

    return {
        "mode": mode,
        "reason": reason,
        "text_len": text_len
    }

def extract_mixed_content(pdf_path: str) -> List[Dict[str, Any]]:
    pages_data: List[Dict[str, Any]] = []
    doc = fitz.open(pdf_path)
    
    for i in range(len(doc)):
        page = doc.load_page(i)
        metrics = analyze_page_metrics(page)
        mode = metrics["mode"]
        
        final_text = ""
        final_images = []

        if mode == "VISION":
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            final_images.append(pix.tobytes("png"))
            final_text = "[System: Scanned Page / Image Detected]"
        elif mode == "HYBRID":
            final_text = page.get_text()
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            final_images.append(pix.tobytes("png"))
        else:
            final_text = page.get_text()

        pages_data.append({
            "page_index": i,
            "text": final_text,
            "images": final_images,
            "mode": mode
        })

    doc.close()
    return pages_data