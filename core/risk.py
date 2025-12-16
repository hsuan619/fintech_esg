import ast
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from .cleaning import clean_value, clean_year


def calculate_risk(
    json_data: List[Dict[str, Any]],
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    核心風險計算函式
    支援: 線性預期法、距離目標法、絕對值動態轉百分比

    參數:
        json_data: 由 LLM 輸出的目標資料列表

    回傳:
        (分析結果 DataFrame, 警告列表)
    """
    results: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []  # 追蹤需要顯示警告的記錄

    # --- 預處理：為每筆資料判斷是否與同組的前一筆 target 不同 ---
    change_notes_by_index: Dict[int, str] = {}
    entries: List[Dict[str, Any]] = []
    for idx, it in enumerate(json_data):
        f = it.get("Standardized_Focus_Area", "Unknown")
        m = it.get("Standardized_Metric", "Unknown")
        s = it.get("Scope", "Global")
        norm_s = (
            it.get("Normalize_Scope")
            or it.get("Normalized_Scope")
            or it.get("NormalizedScope")
            or it.get("Standardized_Scope")
            or s
        )
        ry = clean_year(it.get("Report_Year"))
        ty = clean_year(it.get("Target_Deadline"))
        tv = it.get("Target_Value")
        by = clean_year(it.get("Baseline_Year"))
        entries.append(
            {
                "idx": idx,
                "focus": f,
                "metric": m,
                "norm_scope": norm_s,
                "report_year": ry,
                "target_year": ty,
                "target_val": tv,
                "baseline_year": by,
            }
        )

    groups: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for e in entries:
        groups[(e["focus"], e["metric"], e["norm_scope"])].append(e)

    for _, lst in groups.items():
        # 先按 Report_Year 升序排列，缺年者放到最後（維持原始順序）
        lst_with_year = [e for e in lst if e["report_year"] is not None]
        lst_no_year = [e for e in lst if e["report_year"] is None]
        lst_sorted = sorted(lst_with_year, key=lambda x: x["report_year"]) + lst_no_year
        for i in range(1, len(lst_sorted)):
            prev = lst_sorted[i - 1]
            cur = lst_sorted[i]
            prev_ty = prev.get("target_year")
            prev_tv = prev.get("target_val")
            cur_ty = cur.get("target_year")
            cur_tv = cur.get("target_val")
            prev_by = prev.get("baseline_year")
            cur_by = cur.get("baseline_year")
            # 先比較 target（deadline 或 value），若 target 相同再比較 baseline year
            if (prev_ty != cur_ty) or (prev_tv != cur_tv):
                change_notes_by_index[
                    cur["idx"]
                ] = f"; 目標已變更 (前: {prev_ty}年 {prev_tv} -> 現: {cur_ty}年 {cur_tv})"
                if prev_by != cur_by:
                    change_notes_by_index[cur["idx"]] += (
                        f"; 基準年已變更 (前: {prev_by} -> 現: {cur_by})"
                    )
            elif prev_by != cur_by:
                change_notes_by_index[
                    cur["idx"]
                ] = f"基準年已變更 (前: {prev_by} -> 現: {cur_by})"

    # --- 主要計算流程 ---
    for idx, item in enumerate(json_data):
        try:
            # --- A. 基礎資料讀取 ---
            focus_area = item.get("Standardized_Focus_Area", "Unknown")
            metric = item.get("Standardized_Metric", "Unknown")
            scope = item.get("Scope", "Global")
            report_year = clean_year(item.get("Report_Year"))

            # 讀取目標 (Target)
            target_year = clean_year(item.get("Target_Deadline"))
            target_val_str = item.get("Target_Value")
            # 優先嘗試可能的標準化 scope 欄位
            norm_scope = (
                item.get("Normalize_Scope")
                or item.get("Normalized_Scope")
                or item.get("NormalizedScope")
                or item.get("Standardized_Scope")
                or scope
            )
            _ = norm_scope  # 保留變數以利日後擴充

            # 從預處理結果中取得變更備註（若有）
            change_note = change_notes_by_index.get(idx, "")

            # 讀取基準年 (Baseline)
            base_year = clean_year(item.get("Baseline_Year"))

            # 目標通常是百分比，強制視為百分比處理
            target_reduction, _, _ = clean_value(target_val_str)

            # 如果目標沒寫%，但數值比如是 20，通常指 20% (0.2)
            if target_reduction is not None and target_reduction > 1:
                target_reduction /= 100

            # --- B. 解析進度歷史 (Progress History) ---
            history_str = item.get("Progress_History", "[]")
            try:
                if isinstance(history_str, list):
                    history_list = history_str
                else:
                    history_list = ast.literal_eval(history_str)
            except Exception:
                history_list = []

            if not history_list:
                results.append(
                    {
                        "Focus_Area": focus_area,
                        "Metric": metric,
                        "Report_Year": report_year,
                        "Risk_Level": "數據不足",
                        "Analysis_Note": "無歷史進度數據",
                        "Target": f"{target_year}年 {target_val_str}",
                        "Has_Negative_Warning": False,
                        "Target_Change_Note": change_note,
                    }
                )
                continue

            # 整理歷史數據
            history_map: Dict[int, Dict[str, Any]] = {}
            valid_history: List[Dict[str, Any]] = []
            has_negative_warning = False  # 追蹤是否有負數警告

            for h in history_list:
                y = clean_year(h.get("Year"))
                raw_v = h.get("Value")
                v, is_pct, is_negative_fmt = clean_value(raw_v)

                if y is not None and v is not None:
                    record = {
                        "Year": y,
                        "Value": v,
                        "Is_Pct": is_pct,
                        "Raw": raw_v,
                        "Is_Negative_Fmt": is_negative_fmt,
                    }
                    valid_history.append(record)
                    history_map[y] = record
                    # 如果最新年份有負數格式警告
                    if is_negative_fmt:
                        has_negative_warning = True

            if not valid_history:
                results.append(
                    {
                        "Focus_Area": focus_area,
                        "Metric": metric,
                        "Report_Year": report_year,
                        "Scope": scope,
                        "Risk_Level": "數據不足",
                        "Note": "無歷史進度數據",
                        "Target": f"{target_year}年 {target_val_str}",
                        "Current_Status": "N/A",
                        "Has_Negative_Warning": False,
                        "Target_Change_Note": change_note,
                        "Analysis_Note": "",
                    }
                )
                continue

            valid_history.sort(key=lambda x: x["Year"])
            latest_record = valid_history[-1]
            Y_current = latest_record["Year"]

            # 如果缺少基準年，但有歷史數據，顯示該年度的減量狀況
            if base_year is None:
                actual_reduction = latest_record["Value"]
                results.append(
                    {
                        "Focus_Area": focus_area,
                        "Metric": metric,
                        "Report_Year": report_year,
                        "Scope": scope,
                        "Risk_Level": "數據不足",
                        "Target": f"{target_year}年 {target_val_str}",
                        "Current_Status": f"{Y_current}年 (減量 {actual_reduction:.1%})"
                        if actual_reduction is not None
                        else "N/A",
                        "Has_Negative_Warning": False,
                        "Target_Change_Note": change_note,
                        "Analysis_Note": "無法計算風險（缺少基準年）",
                    }
                )
                continue

            # --- C. 計算實際減量 (Actual Reduction) ---
            actual_reduction = 0.0
            calc_method = ""

            # 判斷是用「絕對值」算還是直接拿「百分比」
            if not latest_record["Is_Pct"]:
                # 情境 1: 歷史數據是「絕對數值」(Absolute Value)
                if base_year in history_map:
                    base_val = history_map[base_year]["Value"]
                    curr_val = latest_record["Value"]

                    if base_val != 0:
                        # 公式: (基準 - 現在) / 基準
                        actual_reduction = (base_val - curr_val) / base_val
                        calc_method = (
                            f"絕對值計算 (基準{base_year}: {base_val:,.0f} "
                            f"-> {Y_current}: {curr_val:,.0f})"
                        )
                    else:
                        results.append(
                            {
                                "Focus_Area": focus_area,
                                "Metric": metric,
                                "Report_Year": report_year,
                                "Risk_Level": "數據錯誤",
                                "Analysis_Note": "基準年排放量為 0",
                                "Has_Negative_Warning": False,
                                "Target_Change_Note": change_note,
                            }
                        )
                        continue
                else:
                    results.append(
                        {
                            "Focus_Area": focus_area,
                            "Metric": metric,
                            "Report_Year": report_year,
                            "Risk_Level": "數據不足",
                            "Target": f"{target_year}年 {target_val_str}",
                            "Analysis_Note": (
                                "歷史數據為絕對值，但在 History 中找不到基準年 "
                                f"({base_year}) 的數據。"
                            ),
                            "Has_Negative_Warning": False,
                            "Target_Change_Note": change_note,
                        }
                    )
                    continue
            else:
                # 情境 2: 歷史數據本身就是「減量百分比」
                actual_reduction = latest_record["Value"]
                calc_method = "直接讀取百分比"

            # --- D. 核心演算法 (Risk Logic) ---
            total_years = target_year - base_year
            elapsed_years = Y_current - base_year

            if total_years <= 0:
                results.append(
                    {
                        "Focus_Area": focus_area,
                        "Metric": metric,
                        "Report_Year": report_year,
                        "Risk_Level": "設定錯誤",
                        "Analysis_Note": "目標年早於基準年",
                        "Has_Negative_Warning": False,
                        "Target_Change_Note": change_note,
                    }
                )
                continue

            elapsed_years = max(0, elapsed_years)

            # 方法一：線性預期進度法
            expected_progress = (elapsed_years / total_years) * target_reduction

            if expected_progress and expected_progress > 0:
                gap = (expected_progress - actual_reduction) / expected_progress
            else:
                gap = 0

            flag1 = gap > 0.1  # 落後 10% 以上
            flag3 = gap > 1.0  # 落後 100% 以上

            # 方法二：距離目標法
            time_ratio = elapsed_years / total_years if total_years else 0
            target_ratio = (
                actual_reduction / target_reduction if target_reduction and target_reduction > 0 else 0
            )

            flag2 = time_ratio >= 0.5 and target_ratio < 0.5

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
                    f"應減 {expected_progress:.1%}, 實減 {actual_reduction:.1%} "
                    f"(Gap: {gap:.1%})。 {calc_method}"
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
                "Target_Change_Note": change_note,
            }
            results.append(result_item)

            # 如果有負數警告，添加到警告列表
            if result_item["Has_Negative_Warning"]:
                warnings.append(
                    {
                        "Focus_Area": focus_area,
                        "Metric": metric,
                        "Year": Y_current,
                        "Status": actual_reduction,
                    }
                )

        except Exception as e:  # noqa: BLE001
            results.append(
                {
                    "Focus_Area": item.get("Standardized_Focus_Area"),
                    "Metric": item.get("Standardized_Metric"),
                    "Report_Year": item.get("Report_Year"),
                    "Risk_Level": "計算錯誤",
                    "Note": str(e),
                    "Current_Status": "N/A",
                    "Target": "N/A",
                    "Analysis_Note": "N/A",
                    "Scope": "N/A",
                    "Has_Negative_Warning": False,
                }
            )

    return pd.DataFrame(results), warnings


