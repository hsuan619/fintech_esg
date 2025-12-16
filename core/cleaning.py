import re
from typing import Any, Optional, Tuple

import pandas as pd


def clean_year(value: Any) -> Optional[int]:
    """將輸入轉換為年份整數 (e.g. '2015' -> 2015)；失敗則回傳 None。"""
    try:
        if pd.isna(value) or value == "None" or value is None:
            return None
        # 處理可能的浮點數年份或字串
        return int(float(str(value).split(".")[0]))
    except Exception:
        return None


def clean_value(value: Any) -> Tuple[Optional[float], bool, bool]:
    """
    通用數值清洗 (修復版)：
    1. 修復誤判括號為負數的問題 (例如 "Scope (3)" 不應被視為負數)。
    2. 修復數值黏連問題 (例如 "100 tCO2" 不應變 "1002")。
    3. 支援會計負數格式 (例如 "(5)" -> -5)。

    Returns:
        (數值, 是否為百分比格式, 是否為會計負數格式)
    """
    try:
        if pd.isna(value) or str(value).lower() == "none":
            return None, False, False

        str_val = str(value).strip()

        # 1. 判斷百分比
        is_percentage = "%" in str_val

        # 2. 暫時移除 % 以便後續處理數值 (避免干擾數字提取)
        temp_str = str_val.replace("%", "").strip()

        # 3. 判斷是否為會計負數格式 (括號包住純數字)
        accounting_pattern = r"^\s*\(\s*([\d,.]+)\s*\)\s*$"
        accounting_match = re.match(accounting_pattern, temp_str)

        is_negative_format = False
        float_val = 0.0

        if accounting_match:
            # 確實是 (5) 這種格式 -> 視為負數
            is_negative_format = True
            clean_str = accounting_match.group(1).replace(",", "")
            float_val = -abs(float(clean_str))
        else:
            # 一般格式 extraction
            # 尋找字串中「第一個」符合數值格式的部分
            extract_pattern = (
                r"(?:^|[\s\(\[])([-+]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)"
            )
            match = re.search(extract_pattern, temp_str)

            if match:
                clean_str = match.group(1).replace(",", "")
                float_val = float(clean_str)
            else:
                return None, False, False

        # 4. 處理百分比數值
        if is_percentage:
            return float_val / 100, True, is_negative_format

        return float_val, False, is_negative_format

    except Exception:
        return None, False, False


def normalize_packaging_scope(scope: str) -> str:
    """標準化包裝相關 Scope 字串。"""
    s = scope.lower().strip()

    if "virgin" in s and "plastic" in s:
        return "virgin_plastic_absolute"

    if "recycled" in s:
        return "recycled_content"

    if "reusable" in s or "recyclable" in s or "compostable" in s:
        return "rrc_packaging"

    return "packaging_general"


