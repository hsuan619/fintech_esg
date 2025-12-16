def get_audit_prompt(current_year: int, content: str) -> str:
    """
    產生 ESG 漂綠稽核用的 LLM Prompt。

    參數:
        current_year: 報告年份
        content: Markdown 或文字形式的報告內容
    """
    # 注意：這裡使用 {{ }} 來轉義 JSON 的大括號，以便 f-string 正確運作
    template = f"""
# Role
你是一位精通 ESG 報告標準 (如 GRI, SASB) 的稽核員。你的任務是從企業永續報告書中提取「承諾目標」，並依據內建的標準化字典進行分類，以便進行跨年度數據比對。

# Context
**目前正在處理的報告年份**: {current_year}

# Input Data
你將解析提供的表格圖片或文字。這些數據來自上述年份的永續報告書。

# Task 1: Extraction & Standardization (提取與標準化)
請將提取出的目標映射到以下的標準化階層結構。如果不完全匹配，請選擇語意最接近的選項。

## 📚 Standardized ESG Dictionary (標準化字典)

### 1. 🌍 Focus Area: Climate (氣候變遷)
   - **Target Metrics**: 
     - `Absolute GHG Reduction` (溫室氣體絕對減量)
     - `Net Zero` (淨零排放)
     - `Renewable Energy` (再生能源比例)
     - `Energy Efficiency` (能源使用效率)
   - **Typical Scopes**: `Scope 1+2`, `Scope 3`, `Value Chain`, `Global Operations`
   - **Strict Formatting Rule**: 
     - 當目標涉及 Scope 1 與 Scope 2 時，Output Scope 欄位請**嚴格**填入 `Scope 1+2`。
     - **禁止**在 Scope 欄位加入地區、子公司或括號註記 (例如：**不要寫** `Scope 1+2 (Taiwan Operations)` 或 `Scope 1+2 (Company only)`，一律刪除括號內容，只保留 `Scope 1+2`)。

### 2. 📦 Focus Area: Packaging (包裝與循環經濟)
   - **Target Metrics**: 
     - `Recycled Content` (再生料使用比例, e.g., rPET)
     - `Virgin Plastic Reduction` (原生塑膠減量)
     - `Packaging Design` (可回收/可堆肥設計, e.g., Recyclability)
     - `Reuse Models` (重複使用模式/減量)
     - `Waste to Landfill` (廢棄物掩埋率)
   - **Typical Scopes**: `Plastic Packaging`, `Beverage Containers`, `Food Packaging`, `Global Portfolio`

### 3. 💧 Focus Area: Water (水資源)
   - **Target Metrics**: 
     - `Water Replenishment` (水資源回補)
     - `Water Use Efficiency` (用水效率/強度)
   - **Typical Scopes**: `High Water-Risk Areas`, `Manufacturing Operations`

### 4. 🌱 Focus Area: Agriculture (永續農業)
   - **Target Metrics**: 
     - `Regenerative Agriculture` (再生農業採用面積)
     - `Sustainably Sourced` (永續採購比例)
   - **Typical Scopes**: `Key Ingredients`, `Direct Supply Chain`

### 5. 👥 Focus Area: Human Rights & Social (人權與社會)
   - **Target Metrics**: 
     - `Gender Diversity` (性別多樣性/管理層比例)
     - `Safety` (工傷率/安全事故)
     - `Human Rights Audit` (人權盡職調查)
   - **Typical Scopes**: `Global Workforce`, `Management Roles`, `Tier 1 Suppliers`
# Task 2: Data Cleaning Rules (資料清洗規則)
1. **歷史進度與趨勢數據抽取 (Progress_History)**:
   - 當圖表或表格中出現「年度 + 數值」的趨勢線或長條圖 (例如 2005~2030 年排放量趨勢)，請**盡可能抽取所有可以辨識的年度與對應數值**。
   - 這些年度與數值請一律填入 `Progress_History` 欄位。
   - 即使這些年份小於或等於 {current_year}，也**不要忽略**，因為後續風險計算需要完整的歷史趨勢。
2. **Deadline Logic**:
   - 優先檢查目標描述內的年份 (如 "by 2025")。
   - 若無，則使用表頭年份 (如 "2030 Target")。
3. **Value Parsing**: 只提取目標數值 (如 "100%", "50%", "2,467 萬噸")，去除無關敘述，但可保留必要單位。
4. **Baseline Logic (基準年判定策略)**:
   - **直接描述**: 優先檢查目標文字中是否包含 "vs. 20XX baseline" 或 "from a 20XX base"。
   - **註腳關聯 (Footnote & Superscript)**: 檢查目標文字或**該區塊標題**旁邊是否有上標數字 (如 `[1]`, `1`)。若有，請務必檢索表格底部或頁尾的註腳文字 (Footnotes/Comments)，通常基準年會定義在那裡 (例如 "Measured versus a 2020 baseline")。
   - **層級繼承 (Hierarchy Inheritance)**: 若該指標 (e.g., Recycled Content) 屬於一個大目標 (Parent Goal, e.g., Virgin Plastic Reduction) 的子項，且大目標或區塊標題有明確基準年，請**繼承**該基準年。
   - **最後手段**: 若以上皆無，才考慮使用 Progress_History 中最早那年 - 1。

# Output JSON Schema
請輸出一個 JSON List：
[
  {{
    "Report_Year": {current_year},
"Standardized_Focus_Area": "String (e.g., 'Packaging', 'Climate')",
    "Standardized_Metric": "String (e.g., 'Recycled Content')",
    
    // Level 3: 適用範疇/材質
    // 規則：
    // 1. 優先從註腳或標題提取主要範疇 (如 "Primary plastic packaging")。
    // 2. 若 Original_Goal_Text 中明確提及衡量方式 (如 "absolute tonnage", "per serving")，請務必補充在括號內。
    // 範例輸入: "Reduce absolute tonnage... of primary plastic" -> 輸出: "Primary plastic packaging (absolute tonnage)"
    "Scope": "String",
    
    "Original_Goal_Text": "String (保留報告中的完整原始描述)",
    "Target_Deadline": Number (e.g., 2025, 2030),
    "Target_Value": "String (e.g., '25%', '50%', 'Net Zero')",
    
    // Baseline 提取注意：請務必檢查上標(superscript)對應的註腳，或大標題的基準年設定
    "Baseline_Year": "String (若有提及基準年則填入，否則 null)",
    "Progress_History": [
       {{ "Year": Number, "Value": "String" }}
    ]
  }}
]

# Begin Extraction
請分析以下內容：
{content}
"""
    return template


