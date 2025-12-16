import fitz  # PyMuPDF
import google.generativeai as genai
from typing import List, Dict, Union, Tuple

def extract_content_smart(pdf_path: str, page_num: int) -> Tuple[str, List[bytes], bool]:
    """
    智慧提取：自動判斷是傳送文字還是傳送整頁圖片。
    
    Returns:
        text_content (str): 提取的文字
        images (List[bytes]): 圖片列表 (如果是掃描檔，這裡會包含整頁截圖)
        is_scanned_mode (bool): 是否啟用了掃描模式 (除錯用)
    """
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    
    text = page.get_text()
    images_to_send = []
    is_scanned_mode = False

    # === 判斷邏輯 ===
    # 如果文字太少 (例如少於 1000 字)，我們假設它是：
    # 1. 掃描檔 (Scanned PDF)
    # 2. 全版大圖/海報 (Infographic)
    # 這時我們啟動「視覺模式」，把整頁轉成圖片
    if len(text.strip()) < 1000:
        is_scanned_mode = True
        
        # 將整頁渲染為高解析度圖片 (zoom=2 代表 200% 解析度，OCR 準度較高)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
        img_bytes = pix.tobytes("png")
        images_to_send.append(img_bytes)
        
        # 在掃描模式下，Text 設為提示語，告訴 AI 這是一張截圖
        text = "[系統提示: 此頁面為掃描檔或全版圖表，請直接分析附圖內容]"
        
    else:
        # === 一般模式 (文字版 PDF) ===
        # 雖然有文字，但可能還有插圖 (Bar Chart 等)，也要抓出來
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                images_to_send.append(base_image["image"])
            except Exception:
                continue # 忽略損壞的圖片

    doc.close()
    return text, images_to_send, is_scanned_mode