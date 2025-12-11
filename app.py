import streamlit as st
import tempfile
import os
import re
import pandas as pd
import json
import ast
from datetime import datetime
from markitdown import MarkItDown  # 需安裝: pip install markitdown

# 設定頁面配置 (必須是第一個 Streamlit 指令)
st.set_page_config(page_title="ESG 漂綠稽核小幫手", layout="wide", page_icon="🌱")

# ==========================================
# 核心邏輯區 (移植自 app_bk.py 並增強)
# ==========================================

def clean_year(value):
    """將輸入轉換為年份整數 (e.g. '2015' -> 2015)"""
    try:
        if pd.isna(value) or value == 'None' or value is None: 
            return None
        # 處理可能的浮點數年份或字串
        return int(float(str(value).split('.')[0]))
    except:
        return None

def clean_value(value):
    """
    通用數值清洗 (來自 app_bk.py 增強版)：
    1. 移除逗號 (,)
    2. 移除單位 (tCO2e, tons等)
    3. 判斷是否為百分比
    4. [新增] 判斷括號數值為負數，例如 (5)% -> -0.05
    回傳: (數值 float, 是否為百分比 bool, 是否為括號負數格式 bool)
    """
    try:
        if pd.isna(value) or value == 'None': return None, False, False
        str_val = str(value).strip()
        
        # 判斷是否為負數 (括號包圍)
        is_negative_format = '(' in str_val and ')' in str_val
        
        is_percentage = '%' in str_val
        
        # 移除非數字字符 (保留小數點)
        clean_str = re.sub(r'[^\d.]', '', str_val)
        
        if not clean_str: return None, False, False
        
        float_val = float(clean_str)
        
        # 處理負號邏輯
        if is_negative_format or '-' in str_val:
            float_val = -abs(float_val)
        
        # 如果原始字串有%，除以100
        if is_percentage:
            return float_val / 100, True, is_negative_format
        
        return float_val, False, is_negative_format
    except:
        return None, False, False

def calculate_risk(json_data):
    """
    核心風險計算函式 (移植自 app_bk.py)
    支援: 線性預期法、距離目標法、絕對值動態轉百分比
    回傳: (DataFrame, 警告列表)
    """
    results = []
    warnings = []  # 追蹤需要顯示警告的記錄

    # --- 預處理：為每筆資料判斷是否與同組的前一筆 target 不同 ---
    from collections import defaultdict
    change_notes_by_index = {}
    entries = []
    for idx, it in enumerate(json_data):
        f = it.get('Standardized_Focus_Area', 'Unknown')
        m = it.get('Standardized_Metric', 'Unknown')
        s = it.get('Scope', 'Global')
        norm_s = it.get('Normalize_Scope') or it.get('Normalized_Scope') or it.get('NormalizedScope') or it.get('Standardized_Scope') or s
        ry = clean_year(it.get('Report_Year'))
        ty = clean_year(it.get('Target_Deadline'))
        tv = it.get('Target_Value')
        by = clean_year(it.get('Baseline_Year'))
        entries.append({'idx': idx, 'focus': f, 'metric': m, 'norm_scope': norm_s, 'report_year': ry, 'target_year': ty, 'target_val': tv, 'baseline_year': by})

    groups = defaultdict(list)
    for e in entries:
        groups[(e['focus'], e['metric'], e['norm_scope'])].append(e)

    for key, lst in groups.items():
        # 先按 Report_Year 升序排列，缺年者放到最後（維持原始順序）
        lst_with_year = [e for e in lst if e['report_year'] is not None]
        lst_no_year = [e for e in lst if e['report_year'] is None]
        lst_sorted = sorted(lst_with_year, key=lambda x: x['report_year']) + lst_no_year
        for i in range(1, len(lst_sorted)):
            prev = lst_sorted[i-1]
            cur = lst_sorted[i]
            prev_ty = prev.get('target_year')
            prev_tv = prev.get('target_val')
            cur_ty = cur.get('target_year')
            cur_tv = cur.get('target_val')
            prev_by = prev.get('baseline_year')
            cur_by = cur.get('baseline_year')
            # 先比較 target（deadline 或 value），若 target 相同再比較 baseline year
            if (prev_ty != cur_ty) or (prev_tv != cur_tv):
                change_notes_by_index[cur['idx']] = f"; 目標已變更 (前: {prev_ty}年 {prev_tv} -> 現: {cur_ty}年 {cur_tv})"
                if prev_by != cur_by:
                    change_notes_by_index[cur['idx']] += f"; 基準年已變更 (前: {prev_by} -> 現: {cur_by})"
            elif (prev_ty != cur_ty) or (prev_tv != cur_tv):
                change_notes_by_index[cur['idx']] = f"目標已變更 (前: {prev_ty}年 {prev_tv} -> 現: {cur_ty}年 {cur_tv})"
    
    for idx, item in enumerate(json_data):
        try:
            # --- A. 基礎資料讀取 ---
            focus_area = item.get('Standardized_Focus_Area', 'Unknown')
            metric = item.get('Standardized_Metric', 'Unknown')
            scope = item.get('Scope', 'Global')
            report_year = clean_year(item.get('Report_Year'))
            
            # 讀取目標 (Target)
            target_year = clean_year(item.get('Target_Deadline'))
            target_val_str = item.get('Target_Value')
            # 優先嘗試可能的標準化 scope 欄位
            norm_scope = item.get('Normalize_Scope') or item.get('Normalized_Scope') or item.get('NormalizedScope') or item.get('Standardized_Scope') or scope
            # 從預處理結果中取得變更備註（若有）
            change_note = change_notes_by_index.get(idx, "")
            
            # 讀取基準年 (Baseline)
            base_year = clean_year(item.get('Baseline_Year'))
            
            # 目標通常是百分比，強制視為百分比處理
            target_reduction, _, _ = clean_value(target_val_str)
            
            # 如果目標沒寫%，但數值比如是 20，通常指 20% (0.2)
            if target_reduction is not None and target_reduction > 1: 
                target_reduction /= 100
            
            # --- B. 解析進度歷史 (Progress History) ---
            history_str = item.get('Progress_History', '[]')
            try:
                if isinstance(history_str, list):
                    history_list = history_str
                else:
                    history_list = ast.literal_eval(history_str)
            except:
                history_list = []
            
            if not history_list:
                results.append({
                    "Focus_Area": focus_area, "Metric": metric, "Report_Year": report_year,
                    "Risk_Level": "數據不足", "Analysis_Note": "無歷史進度數據", "Target": f"{target_year}年 {target_val_str}",
                    "Has_Negative_Warning": False,
                    "Target_Change_Note": change_note
                })
                continue
            
            # 整理歷史數據
            history_map = {}
            valid_history = []
            has_negative_warning = False  # 追蹤是否有負數警告
            
            for h in history_list:
                y = clean_year(h.get('Year'))
                raw_v = h.get('Value')
                v, is_pct, is_negative_fmt = clean_value(raw_v)
                
                if y is not None and v is not None:
                    record = {'Year': y, 'Value': v, 'Is_Pct': is_pct, 'Raw': raw_v, 'Is_Negative_Fmt': is_negative_fmt}
                    valid_history.append(record)
                    history_map[y] = record
                    # 如果最新年份有負數格式警告
                    if is_negative_fmt:
                        has_negative_warning = True
            
            if not valid_history:
                results.append({
                    "Focus_Area": focus_area, "Metric": metric, "Report_Year": report_year, "Scope": scope,
                    "Risk_Level": "數據不足", "Note": "無歷史進度數據", "Target": f"{target_year}年 {target_val_str}",
                    "Current_Status": "N/A",
                    "Has_Negative_Warning": False, "Target_Change_Note": change_note, "Analysis_Note": ""
                })
                continue
            
            valid_history.sort(key=lambda x: x['Year'])
            latest_record = valid_history[-1]
            Y_current = latest_record['Year']
            
            # 如果缺少基準年，但有歷史數據，顯示該年度的減量狀況
            if base_year is None:
                actual_reduction = latest_record['Value']
                results.append({
                    "Focus_Area": focus_area, "Metric": metric, "Report_Year": report_year, "Scope": scope,
                    "Risk_Level": "數據不足",  "Target": f"{target_year}年 {target_val_str}",
                    "Current_Status": f"{Y_current}年 (減量 {actual_reduction:.1%})" if actual_reduction is not None else "N/A",
                    "Has_Negative_Warning": False, "Target_Change_Note": change_note, "Analysis_Note": "無法計算風險（缺少基準年）"
                })
                continue
            
            # --- C. 計算實際減量 (Actual Reduction) ---
            actual_reduction = 0.0
            calc_method = ""
            
            # 判斷是用「絕對值」算還是直接拿「百分比」
            if not latest_record['Is_Pct']:
                # 情境 1: 歷史數據是「絕對數值」(Absolute Value)
                if base_year in history_map:
                    base_val = history_map[base_year]['Value']
                    curr_val = latest_record['Value']
                    
                    if base_val != 0:
                        # 公式: (基準 - 現在) / 基準
                        actual_reduction = (base_val - curr_val) / base_val
                        calc_method = f"絕對值計算 (基準{base_year}: {base_val:,.0f} -> {Y_current}: {curr_val:,.0f})"
                    else:
                        results.append({"Focus_Area": focus_area, "Metric": metric, "Report_Year": report_year, "Risk_Level": "數據錯誤", "Analysis_Note": "基準年排放量為 0", "Has_Negative_Warning": False, "Target_Change_Note": change_note})
                        continue
                else:
                    results.append({
                        "Focus_Area": focus_area, "Metric": metric, "Report_Year": report_year,
                        "Risk_Level": "數據不足", "Target": f"{target_year}年 {target_val_str}",
                        "Analysis_Note": f"歷史數據為絕對值，但在 History 中找不到基準年 ({base_year}) 的數據。",
                        "Has_Negative_Warning": False,
                        "Target_Change_Note": change_note
                    })
                    continue
            else:
                # 情境 2: 歷史數據本身就是「減量百分比」
                actual_reduction = latest_record['Value']
                calc_method = "直接讀取百分比"

            # --- D. 核心演算法 (Risk Logic) ---
            total_years = target_year - base_year
            elapsed_years = Y_current - base_year

            if total_years <= 0:
                results.append({"Focus_Area": focus_area, "Metric": metric, "Report_Year": report_year, "Risk_Level": "設定錯誤", "Analysis_Note": "目標年早於基準年", "Has_Negative_Warning": False, "Target_Change_Note": change_note})
                continue
            
            elapsed_years = max(0, elapsed_years)

            # 方法一：線性預期進度法
            expected_progress = (elapsed_years / total_years) * target_reduction
            
            if expected_progress > 0:
                gap = (expected_progress - actual_reduction) / expected_progress
            else:
                gap = 0
            
            flag1 = gap > 0.1 # 落後 10% 以上
            flag3 = gap > 1.0 # 落後 100% 以上

            # 方法二：距離目標法
            time_ratio = elapsed_years / total_years
            target_ratio = actual_reduction / target_reduction if target_reduction > 0 else 0
            
            flag2 = (time_ratio >= 0.5 and target_ratio < 0.5)

            # --- E. 風險判定 ---
            if (flag1 and flag2) or flag3:
                risk_level = "🔴 高度風險"
            elif flag1 or flag2:
                risk_level = "🟠 中度風險"
            else:
                risk_level = "🟢 低風險"

            # --- F. 產生備註 ---
            if risk_level.startswith("🟢"):
                note = f"進度符合預期。{calc_method}"
            else:
                note = (
                    f"應減 {expected_progress:.1%}, 實減 {actual_reduction:.1%} (Gap: {gap:.1%})。 "
                    f"{calc_method}"
                )


            result_item = {
                "Focus_Area": focus_area,
                "Report_Year": report_year,
                "Metric": metric,
                "Scope": scope,
                "Target": f"{target_year}年 {target_val_str}",
                "Current_Status": f"{Y_current}年 (減量 {actual_reduction:.1%})",
                "Risk_Level": risk_level,
                "Analysis_Note": note,
                "Has_Negative_Warning": has_negative_warning and actual_reduction < 0,
                "Target_Change_Note": change_note
            }
            results.append(result_item)
            
            # 如果有負數警告，添加到警告列表
            if result_item["Has_Negative_Warning"]:
                warnings.append({
                    "Focus_Area": focus_area,
                    "Metric": metric,
                    "Year": Y_current,
                    "Status": actual_reduction
                })

        except Exception as e:
            results.append({
                "Focus_Area": item.get('Standardized_Focus_Area'),
                "Metric": item.get('Standardized_Metric'),
                "Report_Year": item.get('Report_Year'),
                "Risk_Level": "計算錯誤",
                "Note": str(e),
                "Current_Status": "N/A",
                "Target": "N/A",
                "Analysis_Note": "N/A",
                "Scope": "N/A",
                "Has_Negative_Warning": False
            })

    return pd.DataFrame(results), warnings

def get_audit_prompt(current_year, content):
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
1. **忽略歷史數據**: 請忽略所有小於或等於 {current_year} 的進度數值 (Results/Status)，我們只關心「未來的目標 (Target)」。
2. **Deadline Logic**:
   - 優先檢查目標描述內的年份 (如 "by 2025")。
   - 若無，則使用表頭年份 (如 "2030 Target")。
3. **Value Parsing**: 只提取目標數值 (如 "100%", "50%")，去除文字敘述。

# Output JSON Schema
請輸出一個 JSON List：
[
  {{
    "Report_Year": {current_year},
    "Standardized_Focus_Area": "String (e.g., 'Packaging', 'Climate')",
    "Standardized_Metric": "String (e.g., 'Recycled Content')",
    "// Level 3: 適用範疇/材質
    // 注意：對於 Climate 領域，請忽略 "(Taiwan Operations)" 等地區後綴，只輸出標準範疇 (如 "Scope 1+2")
    "Scope": "String (e.g., 'Plastic Packaging', 'Scope 1+2', 'Scope 3')",
    "Original_Goal_Text": "String (保留報告中的完整原始描述)",
    "Target_Deadline": Number (e.g., 2025, 2030),
    "Target_Value": "String (e.g., '25%', '50%', 'Net Zero')",
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

# ==========================================
# 3. Streamlit 網頁介面 (Web Interface)
# ==========================================

st.title("🌱 ESG 報告書漂綠稽核小幫手")
st.markdown("""
本工具提供從 **PDF 報告轉換** 到 **績效風險稽核** 的一站式流程。
請依序使用下方分頁功能：
""")

# 建立三個主要頁籤
tab1, tab2, tab3 = st.tabs([
    "📄 1. 報告轉換 (PDF to MD)", 
    "🤖 2. 產生稽核 Prompt", 
    "📊 3. 績效追蹤與風險評估"
])

# ------------------------------------------
# Tab 1: 報告轉換 (PDF -> Markdown)
# ------------------------------------------
with tab1:
    st.header("步驟一：上傳並轉換報告書")
    st.markdown("將 PDF 格式的 ESG 報告書轉換為 AI 可讀的 Markdown 格式。")
    
    uploaded_pdf = st.file_uploader("上傳 ESG 報告書 (PDF)", type=["pdf"], key="pdf_uploader")
    
    # 狀態保存：Markdown 內容
    if 'markdown_content' not in st.session_state:
        st.session_state.markdown_content = ""
    
    # 嘗試從檔名自動提取年份
    default_year = 2024
    if uploaded_pdf:
        match = re.search(r'20\d{2}', uploaded_pdf.name)
        if match:
            default_year = int(match.group(0))
            
    report_year = st.number_input("設定報告年份", min_value=2000, max_value=2030, value=default_year, key="report_year_input")
    st.session_state.report_year = report_year

    if uploaded_pdf is not None:
        if st.button("開始轉換"):
            st.info(f"正在處理檔案: {uploaded_pdf.name} ...")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(uploaded_pdf.read())
                tmp_pdf_path = tmp_pdf.name

            try:
                md = MarkItDown()
                result = md.convert(tmp_pdf_path)
                st.session_state.markdown_content = result.text_content
                os.remove(tmp_pdf_path)
                st.success("轉換成功！請至「產生稽核 Prompt」分頁查看。")
                
            except Exception as e:
                st.error(f"轉換錯誤: {e}")
                if os.path.exists(tmp_pdf_path): os.remove(tmp_pdf_path)
    
    if st.session_state.markdown_content:
        with st.expander("查看轉換後的 Markdown 內容"):
            st.text_area("內容預覽", st.session_state.markdown_content, height=300)
            st.download_button(
                label="下載 Markdown (.md)",
                data=st.session_state.markdown_content,
                file_name=f"report_{report_year}.md",
                mime="text/markdown"
            )

# ------------------------------------------
# Tab 2: 產生稽核 Prompt
# ------------------------------------------
with tab2:
    st.header("步驟二：生成 AI 稽核 Prompt")
    st.markdown("將轉換後的內容結合標準化指令，產生可供 ChatGPT/Claude/Gemini 使用的 Prompt。")
    
    if st.session_state.markdown_content:
        final_prompt = get_audit_prompt(st.session_state.report_year, st.session_state.markdown_content)
        
        st.info("💡 請複製下方內容，貼給 LLM 模型，並將其回傳的 JSON 存檔供步驟三使用。")
        st.text_area("Prompt 預覽", final_prompt, height=400)
        
        st.download_button(
            label="下載完整 Prompt (.txt)",
            data=final_prompt,
            file_name=f"Audit_Prompt_{st.session_state.report_year}.txt",
            mime="text/plain"
        )
    else:
        st.warning("請先在步驟一上傳並轉換 PDF 報告。")

# ------------------------------------------
# Tab 3: 績效追蹤與風險評估 (核心邏輯區)
# ------------------------------------------
with tab3:
    st.header("步驟三：績效追蹤與風險評估")
    st.markdown("""
    請上傳由 LLM 產出的 **結構化 JSON 檔案**。
    系統將自動執行：
    1. **解析歷年數據** (支援絕對值轉百分比，自動將 `(5)%` 轉為 `-5%`)。
    2. **對應基準年** (Baseline Mapping)。
    3. **計算風險等級** (線性預期法 + 距離目標法)。
    """)
    
    uploaded_json = st.file_uploader("上傳 LLM 產出的 JSON 檔案", type=["json"], key="json_uploader")

    if uploaded_json is not None:
        try:
            # 讀取 JSON
            json_data = json.load(uploaded_json)
            st.success(f"成功讀取檔案！共 {len(json_data)} 筆目標資料。")
            
            # 執行計算
            with st.spinner('正在進行風險評估演算法...'):
                df_result, warnings_list = calculate_risk(json_data)
            
            # 顯示警告彈窗 (Current_Status 背道而馳)
            if warnings_list:
                for warn in warnings_list:
                    st.error(
                        f"❌年度: {warn['Year']} - {warn['Focus_Area']} - {warn['Metric']}\n\n"
                        f"該年度的減量狀況為負數 ({warn['Status']:.1%})，"
                        f"與目標背道而馳！"
                    )

            # 顯示結果
            st.subheader("📊 稽核分析結果")

            # 直接顯示表格（隱藏內部欄位 Has_Negative_Warning）
            df_display = df_result.drop(columns=['Has_Negative_Warning'], errors='ignore')
            # 依 Report_Year 預設升序排序（若有此欄位）
            if 'Report_Year' in df_display.columns:
                try:
                    df_display = df_display.sort_values(by='Report_Year', ascending=True)
                except Exception:
                    pass
            st.dataframe(df_display, use_container_width=True)

            # 下載 CSV
            # 在導出前移除 Has_Negative_Warning 列
            df_export = df_result.drop(columns=['Has_Negative_Warning'], errors='ignore')
            csv = df_export.to_csv(index=False, encoding='utf-8-sig')
            base_name = uploaded_json.name.replace(".json", "")
            file_name = f"Audit_Result_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{base_name}.csv"
            
            st.download_button(
                label="📥 下載完整分析報表 (CSV)",
                data=csv,
                file_name=file_name,
                mime="text/csv",
            )

        except Exception as e:
            st.error(f"分析過程發生錯誤: {e}")
            st.info("請確認上傳的 JSON 格式是否符合 Prompt 定義的 Schema。")
    else:
        st.info("👋 等待上傳 JSON 檔案中...")