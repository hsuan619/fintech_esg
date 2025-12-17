import json
from datetime import datetime

import streamlit as st

from core.risk import calculate_risk


def render() -> None:
    """Tab 3: 績效追蹤與風險評估"""
    st.header("績效追蹤與風險評估")
    st.markdown(
        """
    請上傳由 LLM 產出的 **結構化 JSON 檔案**。
    系統將自動執行：
    1. **解析歷年數據** (支援絕對值轉百分比，自動將 `(5)%` 轉為 `-5%`)。
    2. **對應基準年** (Baseline Mapping)。
    3. **計算風險等級** (線性預期法 + 距離目標法)。
    """
    )

    uploaded_json = st.file_uploader(
        "上傳 LLM 產出的 JSON 檔案", type=["json"], key="json_uploader"
    )

    if uploaded_json is not None:
        try:
            # 讀取 JSON
            json_data = json.load(uploaded_json)
            st.success(f"成功讀取檔案！共 {len(json_data)} 筆目標資料。")

            # 執行計算
            with st.spinner("正在進行風險評估演算法..."):
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
            df_display = df_result.drop(columns=["Has_Negative_Warning"], errors="ignore")
            # 依 Report_Year 預設升序排序（若有此欄位）
            if "Report_Year" in df_display.columns:
                try:
                    df_display = df_display.sort_values(by="Report_Year", ascending=True)
                except Exception:  # noqa: BLE001
                    pass
            st.dataframe(df_display, use_container_width=True)

            # 下載 CSV
            df_export = df_result.drop(columns=["Has_Negative_Warning"], errors="ignore")
            csv = df_export.to_csv(index=False, encoding="utf-8-sig")
            base_name = uploaded_json.name.replace(".json", "")
            file_name = (
                f"Audit_Result_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{base_name}.csv"
            )

            st.download_button(
                label="📥 下載完整分析報表 (CSV)",
                data=csv,
                file_name=file_name,
                mime="text/csv",
            )

        except Exception as e:  # noqa: BLE001
            st.error(f"分析過程發生錯誤: {e}")
            st.info("請確認上傳的 JSON 格式是否符合 Prompt 定義的 Schema。")
    else:
        st.info("👋 等待上傳 JSON 檔案中...")


