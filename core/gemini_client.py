import json
import os
from typing import Any, Dict, List

import google.generativeai as genai
from dotenv import load_dotenv

from .prompt import get_audit_prompt


class GeminiClient:
    """
    輕量封裝 Google Gemini 1.5 Flash

    - 自動從 .env / 環境變數讀取 GOOGLE_API_KEY
    - 提供圖片前處理 (圖表文字描述)
    - 以 JSON mode 回傳結構化結果
    """

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash-lite",
        vision_model_name: str | None = None,
        api_key: str | None = None,
    ) -> None:
        load_dotenv()

        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "環境變數 GOOGLE_API_KEY 未設定，請在專案根目錄建立 .env 並加入：\n"
                "GOOGLE_API_KEY=你的_API_Key"
            )

        genai.configure(api_key=api_key)

        self._model = genai.GenerativeModel(model_name)
        # 視覺前處理可用不同 model；若未指定則共用同一個
        self._vision_model = (
            genai.GenerativeModel(vision_model_name)
            if vision_model_name
            else self._model
        )

    def _describe_images(self, images: List[bytes]) -> str:
        """
        使用 Vision 模型先把圖表「翻譯成文字」，特別是抽出年度 + 數值的歷史趨勢。
        回傳：單一長文字描述，可直接拼在 content 後面。
        """
        if not images:
            return ""

        parts: List[Any] = [
            (
                "你是一位 ESG 報告稽核員，請專注解析**圖表或趨勢圖**中的：\n"
                "1. 目標值 (Target) 與目標年度 (例如 2025年 2,467 萬噸, 2030年 2,271 萬噸)\n"
                "2. 歷史進度 (Results / Status)：請盡可能列出所有「年度 + 數值」的資料點\n"
                "   - 請用類似 `2005: 2,567 萬噸`, `2006: 2,710 萬噸` 的格式逐年列出\n"
                "3. 基準年 (Baseline) 以及與基準年的減量百分比 (若有標示，例如「比 2007 年減少 22%」)\n\n"
                "請用條列式輸出，每個圖表一段，務必把你能看見的所有年度與數值都寫出來。"
            )
        ]

        for img in images:
            parts.append(
                {
                    "mime_type": "image/png",
                    "data": img,
                }
            )

        response = self._vision_model.generate_content(parts)
        return response.text or ""

    def extract_goals_from_page(
        self,
        *,
        page_text: str,
        images: List[bytes],
        current_year: int,
    ) -> List[Dict[str, Any]]:
        """
        核心方法：給一頁 PDF 的文字 + 圖片，回傳該頁所有「承諾目標」的 JSON list。
        """
        image_desc = self._describe_images(images)

        # 將原始文字與圖片描述合併，丟給 Prompt 模板
        merged_content_parts: List[str] = ["# Page Text", page_text.strip()]
        if image_desc:
            merged_content_parts.extend(
                [
                    "",
                    "# Image-derived Details",
                    image_desc.strip(),
                ]
            )

        merged_content = "\n".join(merged_content_parts)
        prompt = get_audit_prompt(current_year=current_year, content=merged_content)

        response = self._model.generate_content(
            [prompt],
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json"
            ),
        )

        raw_text = response.text or "[]"

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # 若模型外層多包一層物件，嘗試幾個常見 key
            try:
                obj = json.loads(raw_text)
                for key in ("items", "data", "results"):
                    if key in obj and isinstance(obj[key], list):
                        return obj[key]
                # 如果是單一物件而非 list，就包成 list
                if isinstance(obj, dict):
                    return [obj]
                if isinstance(obj, list):
                    return obj
            except Exception:
                # 最後退路：直接回傳空 list，避免整體流程中斷
                return []

        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
        return []


__all__ = ["GeminiClient"]


