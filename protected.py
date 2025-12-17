import pikepdf
import pdfplumber
import fitz  # PyMuPDF
import io
import os

class PDFTextLiberator:
    def __init__(self, input_path):
        self.input_path = input_path
        self.unlocked_stream = None

    def unlock_pdf(self):
        """
        階段一：解除權限鎖定 (移除禁止複製的限制)
        使用 pikepdf 重新儲存檔案，通常能移除 Owner Password 限制。
        """
        try:
            # 開啟 PDF，允許 pikepdf 自動處理加密（只要能打開，就能移除權限）
            pdf = pikepdf.open(self.input_path, allow_overwriting_input=True)
            
            # 將處理後的 PDF 存入記憶體 (BytesIO)，不寫入硬碟以保護隱私/速度
            output_stream = io.BytesIO()
            pdf.save(output_stream)
            pdf.close()
            
            output_stream.seek(0)
            self.unlocked_stream = output_stream
            print("✅ PDF 權限解鎖成功。")
            return True
        except Exception as e:
            print(f"❌ 解鎖失敗: {e}")
            return False

    def extract_strategy_fitz(self):
        """
        策略 A：使用 PyMuPDF (Fitz)
        優勢：速度快，對壞掉的 Unicode Map 有較好的容錯率。
        """
        text_content = []
        try:
            # 從記憶體讀取解鎖後的 PDF
            doc = fitz.open(stream=self.unlocked_stream, filetype="pdf")
            
            for page_num, page in enumerate(doc):
                # flags=0 保持原樣，或者使用更激進的提取模式
                # sort=True 會嘗試根據座標重新排序文字
                text = page.get_text("text", sort=True) 
                text_content.append(f"--- Page {page_num + 1} ---\n{text}")
            
            return "\n".join(text_content)
        except Exception as e:
            return f"Fitz Extraction Failed: {e}"

    def extract_strategy_plumber(self):
        """
        策略 B：使用 pdfplumber
        優勢：提供每個字的座標 (x, y)，適合處理複雜排版 (如多欄位)。
        如果 PDF 故意把字順序打亂，這個策略可以透過座標強制排序。
        """
        text_content = []
        try:
            # 重置 stream 指針
            self.unlocked_stream.seek(0)
            
            with pdfplumber.open(self.unlocked_stream) as pdf:
                for i, page in enumerate(pdf.pages):
                    # extract_text 會自動根據視覺佈局 (visual layout) 進行聚類
                    # x_tolerance 和 y_tolerance 可調整以應對字距過寬的情況
                    text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if text:
                        text_content.append(f"--- Page {i + 1} ---\n{text}")
                    else:
                        text_content.append(f"--- Page {i + 1} ---\n[No text detected in text layer]")
            
            return "\n".join(text_content)
        except Exception as e:
            return f"Plumber Extraction Failed: {e}"

    def run(self):
        if not self.unlock_pdf():
            return

        print("正在嘗試策略 A (PyMuPDF - 快速且強大)...")
        text_a = self.extract_strategy_fitz()
        
        # 簡單判斷策略 A 是否提取到了有效內容 (非空白且長度足夠)
        if len(text_a) > 100: 
            print("策略 A 成功提取內容。")
            return text_a
        
        print("策略 A 結果不佳，切換至策略 B (pdfplumber - 佈局分析)...")
        text_b = self.extract_strategy_plumber()
        return text_b

# --- 使用範例 ---
if __name__ == "__main__":
    # 假設你有一個無法複製文字的 protected.pdf
    pdf_path = "protected.pdf" 
    
    # 檢查檔案是否存在
    if os.path.exists(pdf_path):
        tool = PDFTextLiberator(pdf_path)
        result = tool.run()
        
        # 將結果寫入 txt
        with open("extracted_text.txt", "w", encoding="utf-8") as f:
            f.write(result)
            print("✅ 文字已輸出至 extracted_text.txt")
    else:
        print("請提供有效的 PDF 路徑。")