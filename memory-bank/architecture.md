### 專案架構總覽

本工具的目標是將 ESG 報告從 **PDF → Markdown → LLM JSON → 風險計算結果** 串成一條乾淨、可維護的資料流；
同時也提供一條 **PDF → LLM JSON (Vision) → 風險計算結果** 的 CLI 流程，用來直接從圖表頁擷取目標與歷史趨勢數據。

- **UI Layer (`ui/` + `app.py`)**  
  - 負責所有 Streamlit 互動、檔案上傳、按鈕與頁籤切換。
  - 不寫商業邏輯，只呼叫 core 模組。
- **Core Layer (`core/`)**  
  - 放所有與 ESG/數據處理相關的「純邏輯」：清洗、風險計算、Prompt 生成、PDF 混合內容抽取與 Gemini 串接。
  - 這層理論上可以被 CLI、API、Batch Job 重複使用。

---

### 檔案與模組職責

- **`app.py`**  
  - Streamlit 的入口檔（`streamlit run app.py`）。  
  - 建立 3 個頁籤，分別委派到 `ui/tab_pdf_to_md.py`、`ui/tab_generate_prompt.py`、`ui/tab_risk_assessment.py` 來渲染內容。  
  - 理想情況：這裡不再出現任何清洗邏輯或複雜演算法，只做「版面配置 + 呼叫模組」。目前仍保留舊版實作，可逐步收斂成僅呼叫 UI 模組。

#### Core Layer

- **`core/cleaning.py`**
  - `clean_year(value)`：將任意輸入（字串、float、None）轉為年份 `int`，失敗回 `None`。
  - `clean_value(value)`：通用數值 parser。  
    - 支援會計負數 `(5)` → `-5`。  
    - 避免抓到單位中的數字（例如 `tCO2` 的 `2`）。  
    - 自動辨識百分比並轉為 0–1 間小數。  
  - `normalize_packaging_scope(scope)`：將與包裝/塑膠相關的描述（virgin / recycled / reusable...）對應到標準化 Scope tag。
  - 此模組不依賴 Streamlit，可單獨用於 batch 處理或測試。

- **`core/risk.py`**
  - `calculate_risk(json_data)`：整個 ESG 目標的風險計算核心。  
  - 輸入：LLM 依照 Prompt schema 產出的 JSON list。  
  - 主要步驟：  
    1. 依 `Standardized_Focus_Area + Standardized_Metric + Scope` 分組，同組內比對目標與基準年的變更，產出 `Target_Change_Note`。  
    2. 對每筆目標解析 `Progress_History`，用 `clean_year`/`clean_value` 清洗。  
    3. 如果歷史是「絕對值」，依 `baseline` → `current` 計算減量百分比；若本身是百分比則直接使用。  
    4. 用 **線性預期進度法** + **距離目標法** 兩種方法算落後程度，輸出 `Risk_Level`（🔴/🟠/🟢）與說明文字。  
    5. 若發現會計負數且實際減量 < 0，標記為 `Has_Negative_Warning`，並在 UI 層彈出警告。  
  - 回傳：`(pandas.DataFrame, warnings_list)`。DataFrame 給 UI 顯示/下載，warnings 給 UI 顯示紅色 alert。

- **`core/pdf_extractor.py` + `pp.py`**
  - `pp.extract_content_smart(pdf_path, page_num)`：單頁智慧抽取器。  
    - 先用 PyMuPDF 讀取頁面文字；若文字長度 `< 1000`，視為「掃描/大圖頁」，直接把整頁渲染成高解析 PNG，並在回傳文字中標註為掃描提示。  
    - 若文字足夠，當作一般文字頁：保留 `page.get_text()` 的全文，同時抓取頁面中所有內嵌圖片 bytes。  
  - `core.pdf_extractor.extract_mixed_content(pdf_path)`：多頁混合內容提取器。  
    - 逐頁呼叫 `extract_content_smart`，組成一個 list，每頁包含：`page_index`, `text`, `images`, `is_scanned`。  
    - 為了確保 LLM 真的「看到」所有向量圖表，對於 **非掃描頁 (`is_scanned=False`)**，額外再補一張整頁 screenshot（中等解析度 PNG）放進 `images`。  
    - 最終保證：每一頁送進 Vision 的 `images` 中都至少有一張「完整頁面」的截圖，避免圖表被 PDF 向量格式吃掉。

- **`core/gemini_client.py`**
  - `GeminiClient`：封裝 Google Gemini 1.5/2.x Flash/Lite 模型（透過 `google-generativeai`）。  
    - 在 `__init__` 內使用 `python-dotenv` 載入 `.env`，從 `GOOGLE_API_KEY` 取得金鑰並呼叫 `genai.configure()`。  
    - `_describe_images(images)`：使用 Vision 模型先把圖表/趨勢圖轉成結構化描述文字（特別強調「年度 + 數值」與 baseline/減量百分比），輸出會長得像：  
      - `2005: 2,567 萬噸`, `2006: 2,710 萬噸`, `比 2007 年 3,182 萬噸減少 22%` … 等。  
    - `extract_goals_from_page(page_text, images, current_year)`：  
      1. 先呼叫 `_describe_images`，取得所有圖片中的目標值 + 歷史趨勢文字。  
      2. 將「原始頁面文字」與「Vision 產生的圖表描述」合併為一段 `content`，丟給 `core.prompt.get_audit_prompt` 產生長 Prompt。  
      3. 呼叫 Gemini，設定 `response_mime_type="application/json"`，強制產生符合 Schema 的 JSON list。  
      4. 對回傳結果做 `json.loads` 與容錯處理（單物件/包在 `items`、`data` 等 key 下都能處理），最後回傳 `List[Dict]`。

- **`core/prompt.py`**
  - `get_audit_prompt(current_year, content)`：產生給 LLM（ChatGPT/Claude/Gemini 等）的長 prompt。  
  - 內容包含：  
    - Role & Context（稽核員角色 + 報告年份）。  
    - 標準化 ESG 字典（Focus Area / Metric / Scope）。  
    - 資料清洗規則（**強制抽取歷史趨勢至 `Progress_History`**，以及 deadline/baseline 推論邏輯）：  
      - 專門一條規則描述：當圖表或表格中出現「年度 + 數值」的趨勢線或長條圖（例如 2005~2030 年排放量趨勢），LLM 必須盡可能把所有可辨識的年度與數值抽出來，填入 `Progress_History`（即使年份早於當前年份也不能忽略）。  
      - 其他規則則負責從原文判斷 Target 年份、Baseline 年份與 Target 值（例如「比 2007 年減少 22%」）。  
    - 最終輸出 JSON Schema。  
    - 並把實際的 Markdown 內容 (`content`) 夾在最後給 LLM 解析。
  - 這個函式是「單純 string 模板」，不依賴 Streamlit。

#### UI Layer

- **`ui/tab_pdf_to_md.py`**
  - Tab1：「報告轉換 (PDF → Markdown)」。  
  - 流程：  
    1. 使用 `st.file_uploader` 上傳 PDF。  
    2. 由檔名猜測預設年份（`20xx` regex）。  
    3. 使用 `MarkItDown` 將 PDF 轉成 Markdown 文字。  
    4. 結果寫入 `st.session_state.markdown_content` 與 `st.session_state.report_year`。  
    5. 提供 Markdown 預覽與 `.md` 下載。  
  - 此 tab 僅負責 **I/O 與狀態紀錄**，不處理後續 LLM 或風險計算。

- **`ui/tab_generate_prompt.py`**
  - Tab2：「產生稽核 Prompt」。  
  - 從 `st.session_state.markdown_content` & `report_year` 讀取資料，呼叫 `core.prompt.get_audit_prompt`。  
  - 顯示完整 Prompt 供複製，並提供 `.txt` 下載。  
  - 若尚未完成 Tab1 轉換，會顯示提示訊息。

- **`ui/tab_risk_assessment.py`**
  - Tab3：「績效追蹤與風險評估」。  
  - 流程：  
    1. 上傳 LLM 輸出的 JSON 檔（格式需符合 Prompt 定義）。  
    2. 呼叫 `core.risk.calculate_risk` 拿到 DataFrame 與警告列表。  
    3. 針對 `Has_Negative_Warning` 的紀錄以 `st.error` 顯示紅色警告。  
    4. 將結果以 `st.dataframe` 呈現，並輸出成 CSV 下載。  
  - UI 部分仍維持原本的排序、欄位隱藏邏輯，只是商業邏輯被搬到 core。

---

### 資料流 (Data Flow)

1. **PDF → Markdown（互動式 UI 流程）**
   - 使用者在 Tab1 上傳 PDF。  
   - `ui/tab_pdf_to_md.py` 呼叫 `MarkItDown` 抽取文字，寫入 `st.session_state.markdown_content`。  
   - 同時記錄 `report_year`。

2. **Markdown → LLM Prompt**
   - Tab2 讀取 `markdown_content` + `report_year`。  
   - 呼叫 `core.prompt.get_audit_prompt()` 產出長 prompt。  
   - 使用者將此 prompt 貼給 LLM，取得 JSON 檔案。

3. **LLM JSON → 風險分析**
   - 使用者在 Tab3 上傳 JSON。  
   - `ui/tab_risk_assessment.py` 呼叫 `core.risk.calculate_risk(json_data)`。  
   - 風險結果（包含 Gap、預期進度、實際進度與 Target_Change_Note）以表格與 CSV 形式呈現。

4. **PDF → LLM JSON（Vision + CLI 流程）**
   - 使用者在命令列執行：  
     - `python esg_goal_miner.py --pdf <報告PDF> --year <報告年份> --output <輸出JSON路徑>`。  
   - `esg_goal_miner.py`：  
     1. 呼叫 `core.pdf_extractor.extract_mixed_content`，逐頁取得 `{ page_index, text, images, is_scanned }`。  
     2. 對每一頁呼叫 `GeminiClient.extract_goals_from_page`，將文字 + 圖片（包含整頁 screenshot）送進 Gemini Vision + Text 模型。  
     3. 收集所有頁面的 JSON 結果，統一寫成一個 `.json` 檔（每筆至少包含 `Report_Year`, `Standardized_Focus_Area`, `Standardized_Metric`, `Scope`, `Original_Goal_Text`, `Target_Deadline`, `Target_Value`, `Baseline_Year`, `Progress_History`）。  
   - 後續若要做風險分析，可直接將此 JSON 檔丟進 UI Tab3 或在 Notebook 中呼叫 `core.risk.calculate_risk`。

---

### 效能與維護性優化說明

- 將清洗與計算邏輯集中到 `core/`，避免在 UI 中重複撰寫邏輯，之後若要改演算法只需改一處。  
- `calculate_risk` 先做一次分組與 target/baseline 變更偵測，再進入主計算迴圈，減少重複運算與判斷。  
- Streamlit 層專注在狀態（`st.session_state`）與 I/O，未來若要改成 API 服務，只需重用 core 模組即可。  
- UI 模組彼此獨立，新增第 4 個 tab（例如圖表視覺化）時，只需要新建一個 `ui/tab_xxx.py` 並在 `app.py` 新增一個 tab 呼叫。


