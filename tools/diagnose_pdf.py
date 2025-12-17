import fitz
import sys
import os
from prettytable import PrettyTable

# 確保可以 import 到 core 模組
# 假設 tools 資料夾與 core 資料夾在同一層級
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from core.pdf_extractor import analyze_page_metrics
except ImportError:
    print("錯誤: 無法匯入 core.pdf_extractor。請確認目錄結構是否正確。")
    sys.exit(1)

def diagnose_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"錯誤：找不到檔案 {pdf_path}")
        return

    doc = fitz.open(pdf_path)
    print(f"\n正在診斷檔案: {os.path.basename(pdf_path)}")
    print(f"總頁數: {len(doc)}\n")

    # 設定表格欄位
    table = PrettyTable()
    table.field_names = [
        "Page", "Mode", "Tokens", "Drawings", 
        "Top %", "Mid %", "Bot %", "Reason"
    ]
    table.align = "l"
    table.float_format = "0.2" # 小數點兩位

    for i in range(len(doc)):
        page = doc.load_page(i)
        
        # 使用與 pdf_extractor 完全相同的邏輯
        metrics = analyze_page_metrics(page)
        
        mode = metrics["mode"]
        densities = metrics["densities"]
        
        # 顏色標記 (ANSI codes)
        mode_display = mode
        if mode == "HYBRID":
            mode_display = f"\033[93m{mode}\033[0m" # 黃色
        elif mode == "VISION":
            mode_display = f"\033[91m{mode}\033[0m" # 紅色
        else:
            mode_display = f"\033[92m{mode}\033[0m" # 綠色

        table.add_row([
            i + 1,
            mode_display,
            metrics["text_len"],
            metrics["drawing_count"],
            f"{densities[0]*100:.1f}%", # Top Density
            f"{densities[1]*100:.1f}%", # Mid Density
            f"{densities[2]*100:.1f}%", # Bot Density
            metrics["reason"]
        ])

    print(table)
    print("\n[欄位說明]")
    print("Drawings: 向量繪圖指令數量 (線條、路徑)。數量 > 50 通常代表有複雜圖表。")
    print("Top/Mid/Bot %: 文字在頁面上、中、下區域的分佈比例。")
    print("  - Top-Heavy (Top% 高, Mid% 低) 通常代表上方表格 + 下方圖表。")
    
    doc.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python tools/diagnose_pdf.py <pdf_path>")
    else:
        diagnose_pdf(sys.argv[1])