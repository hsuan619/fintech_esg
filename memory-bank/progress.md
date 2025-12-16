### 檔案進度與設計理由總覽

此文件紀錄目前每個檔案「在幹嘛」以及「為什麼要這樣設計」，方便未來自己或其他開發者接手。

---

### 1. `app.py`

- **目前狀態**
  - 原始版本：同時包含所有清洗邏輯、風險計算、Prompt 模板與三個 Streamlit 分頁 UI。  
  - 設計目標：逐步收斂為「只做頁籤配置與呼叫 UI 模組」的薄入口。

- **下一步建議重構**
  - 已新增 `core/` 與 `ui/` 模組，建議你接下來將：  
    - 風險計算相關的 `calculate_risk` 全數移到 `core/risk.py`（目前已存在強化版，可改為從該模組匯入）。  
    - 數值與年份清洗 `clean_year`、`clean_value`、`normalize_packaging_scope` 改用 `core/cleaning.py`。  
    - Tab1/2/3 的 UI 內容，改為呼叫 `ui/tab_*.py` 中的 `render()` 函式，讓 `app.py` 只保留：  
      ```python
      tab1, tab2, tab3 = st.tabs([...])
      with tab1: tab_pdf_to_md.render()
      ```

- **設計理由**
  - 保留舊實作可以降低一次性大改的風險，你可以在本地逐步測試、確認新 core / ui 模組穩定後，再讓 `app.py` 完全切換到新架構。

---

### 2. `core/cleaning.py`

- **在幹嘛**
  - 集中所有「通用前處理」：  
    - `clean_year` 統一處理各種年份格式。  
    - `clean_value` 統一處理數值、百分比、會計負數、避免單位黏數字。  
    - `normalize_packaging_scope` 整理包裝相關 scope tag。

- **為什麼這樣設計**
  - 這些函式與 UI 完全無關，只跟資料有關，適合獨立在 core 層，方便：  
    - 單元測試。  
    - 其他服務（如批次腳本、API）重用。

---

### 3. `core/risk.py`

- **在幹嘛**
  - `calculate_risk(json_data)`：統一管理所有 ESG 目標風險計算邏輯。  
  - 將舊版 `app.py` 中的核心演算法抽出並加上型別註記與錯誤處理，使其更穩定、可重複使用。

- **為什麼這樣設計**
  - 風險演算法是業務核心，不應該散落在 UI 程式碼裡。  
  - 分離後：  
    - 可以很容易在 Jupyter Notebook、CLI 或後端服務中重用同一個 `calculate_risk`。  
    - 未來若要改演算法（例如加上新的 flag 或 scoring），只需改這一支。

---

### 4. `core/prompt.py`

- **在幹嘛**
  - `get_audit_prompt(current_year, content)`：封裝 LLM Prompt 模板的產生邏輯。
  - 把舊 `app.py` 裡長長的 f-string 抽出來，變成乾淨的一個函式。

- **為什麼這樣設計**
  - Prompt 本質上是「文字模板」，和 UI 或資料計算邏輯不同。  
  - 抽到 core 之後：  
    - 可以在 CLI 或其他介面直接呼叫 `get_audit_prompt`，不用依賴 Streamlit。  
    - 未來若要針對不同客戶／標準（如 SBTi / TCFD）調整 Prompt，可以增加多個函式或參數，而不污染 UI 程式碼。

---

### 5. `ui/tab_pdf_to_md.py`

- **在幹嘛**
  - 負責 Tab1：「報告轉換 (PDF → Markdown)」的所有畫面與流程。  
  - 只處理：檔案上傳、年份輸入、呼叫 `MarkItDown` 轉檔、寫入 `st.session_state`、顯示預覽與提供下載。

- **為什麼這樣設計**
  - 讓「一個檔案對應一個頁籤」，降低耦合。  
  - 若未來要增加更多轉檔方式（例如支援 DOCX、HTML），只改這一支，不影響風險計算與 Prompt。

---

### 6. `ui/tab_generate_prompt.py`

- **在幹嘛**
  - 負責 Tab2：「產生稽核 Prompt」的畫面。  
  - 從 `session_state` 取 Markdown + 年份，呼叫 `core.prompt.get_audit_prompt`，顯示與下載。

- **為什麼這樣設計**
  - UI 層只專注在展示與下載，真正的 Prompt 結構留在 core。  
  - 若未來要多一種 Prompt（例如「回溯歷史驗證用」），可以在這裡多一個選項 + 調用不同的 core 函式。

---

### 7. `ui/tab_risk_assessment.py`

- **在幹嘛**
  - 負責 Tab3：「績效追蹤與風險評估」。  
  - 上傳 JSON → 呼叫 `core.risk.calculate_risk` → 顯示 DataFrame + 下載 CSV → 對負向進度顯示紅色警示。

- **為什麼這樣設計**
  - 演算法與 UI 明確分離：  
    - 當你想改 UI（例如加上篩選、多語言切換）時，不會誤動到風險演算法。  
    - 當你想改演算法，也不用動到任何 Streamlit 元件。

---

### 後續建議（Roadmap）

- **短期**
  - 將 `app.py` 逐步改寫為只匯入 `ui/` 模組並呼叫 `render()`。  
  - 刪除 `app.py` 裡已被抽出到 `core/` 的函式，避免重複邏輯。  

- **中期**
  - 為 `core/cleaning.py` 與 `core/risk.py` 增加簡單的單元測試，確保未來改動不會破壞演算法。  
  - 把共用常數（例如 emoji、文字標籤）集中到一個 `constants.py`。  

- **長期**
  - 將 core 封裝成可被其他專案 import 的小型 package，Streamlit 僅是其中一個前端介面。  
  - 若有需要，可以新增一個 `api/` 層（FastAPI / Flask）讓外部系統能呼叫同一套風險計算邏輯。


