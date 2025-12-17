import json
import os
from typing import Any, Dict, List

import google.generativeai as genai
from dotenv import load_dotenv

# 假設 prompt.py 在同一層目錄或正確的 package 下
from .prompt import get_audit_prompt

class GeminiClient:
    """
    輕量封裝 Google Gemini 1.5 Flash
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
            raise RuntimeError("Environment variable GOOGLE_API_KEY not set.")
        
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)
        # Vision 模型可以用更強的 Pro 版本，或共用 Flash
        self._vision_model = (
            genai.GenerativeModel(vision_model_name)
            if vision_model_name
            else self._model
        )

    def _describe_images(self, images: List[bytes]) -> str:
        """
        使用 Vision 模型將圖表「翻譯」成文字。
        **關鍵：強制要求忽略 PDF 文字層的亂序，改用視覺對齊。**
        """
        if not images:
            return ""

        parts: List[Any] = [
            (
                "你是一位 ESG 報告稽核員，請專注解析圖片中的**圖表、趨勢圖或路徑圖**。\n"
                "**嚴重警告：此 PDF 的原始文字層順序是錯亂的（依高度而非時間排序）。**\n"
                "**請務必忽略任何隱藏的文字層順序，嚴格執行「視覺掃描」：**\n\n"
                "1. **視覺定位 X 軸 (年份)**：先找到圖表下方的年份標示 (如 2005, 2010...)。\n"
                "2. **從左到右讀取數據**：根據折線或長條的物理位置，由左至右對應到正確的年份。\n"
                "3. **請提取以下資訊**：\n"
                "   - 目標值 (Target)：年份與數值 (例如 2025年 2,467 萬噸)。\n"
                "   - 歷史進度 (Historical Data)：請列出所有可見的「年份: 數值」數據點。\n"
                "     (格式範例：`2005: 2,567`, `2006: 2,710`)\n"
                "   - 基準年 (Baseline)：若有標示，請指出基準年數值。\n\n"
                "請輸出一段詳細的文字描述，供後續數據校對使用。"
            )
        ]

        for img in images:
            parts.append({"mime_type": "image/png", "data": img})

        # 使用 temperature=0.0 以獲得最客觀的數據讀取
        response = self._vision_model.generate_content(
            parts, 
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )
        return response.text or ""

    def extract_goals_from_page(
        self,
        *,
        page_text: str,
        images: List[bytes],
        current_year: int,
        mode: str = "TEXT"  # [新增] 接收來自 extractor 的模式
    ) -> List[Dict[str, Any]]:
        """
        核心方法：
        1. 若是 HYBRID，先看圖產生描述。
        2. 將 文字 + 描述 + 警告 組合後，填入 prompt.py 的樣板。
        3. 讓 LLM 輸出 JSON。
        """
        image_desc = ""
        
        # 步驟 1: 只有在 HYBRID 模式且有圖片時，才呼叫 Vision Model
        if mode == "HYBRID" and images:
            image_desc = self._describe_images(images)

        # 步驟 2: 組合最終要送給 LLM 的 context
        merged_content_parts: List[str] = []

        # [系統警告]：若是 HYBRID，告訴主模型不要太相信原始文字的順序
        if mode == "HYBRID" and images:
            merged_content_parts.append(
                "⚠️ [SYSTEM WARNING]: This page contains Charts/Graphs with potentially jumbled text layers. "
                "Please PRIORITIZE the information in the '# Image-derived Details' section below "
                "for any trend data, year-value alignment, or chart interpretation."
            )

        merged_content_parts.append(f"# Raw Page Text\n{page_text.strip()}")
        
        if image_desc:
            merged_content_parts.append(
                f"\n# Image-derived Details (High Confidence for Charts)\n{image_desc.strip()}"
            )

        final_content = "\n".join(merged_content_parts)

        # 步驟 3: 呼叫 prompt.py 中的函數來產生最終 Prompt
        # 這裡的 final_content 已經包含了 警告 + 文字 + 圖片描述
        prompt = get_audit_prompt(current_year=current_year, content=final_content)

        # 步驟 4: 送出請求
        response = self._model.generate_content(
            [prompt],
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            ),
        )

        raw_text = response.text or "[]"

        # 步驟 5: JSON 解析 (維持不變)
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                obj = json.loads(raw_text)
                for key in ("items", "data", "results"):
                    if key in obj and isinstance(obj[key], list):
                        return obj[key]
                if isinstance(obj, dict): return [obj]
                if isinstance(obj, list): return obj
            except Exception:
                return []

        if isinstance(data, dict): return [data]
        if isinstance(data, list): return data
        return []

__all__ = ["GeminiClient"]