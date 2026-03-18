"""
gemini_review.py
~~~~~~~~~~~~~~~~
使用 ZenMux API 对候选股票进行图表分析评分。
继承自 BaseReviewer 基础架构。

用法：
    python agent/gemini_review.py
    python agent/gemini_review.py --config config/gemini_review.yaml

配置：
    默认读取 config/gemini_review.yaml。

环境变量：
    ZENMUX_API_KEY  —— ZenMux API Key（必填）

输出：
    ./data/review/{pick_date}/{code}.json   每支股票的评分 JSON
    ./data/review/{pick_date}/suggestion.json  汇总推荐建议
"""

import argparse
import base64
import os
import sys
from pathlib import Path
from typing import Any

import openai
import yaml

from base_reviewer import BaseReviewer

# ────────────────────────────────────────────────
# 配置加载
# ────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _ROOT / "config" / "gemini_review.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    # 路径参数（相对路径默认基于项目根目录）
    "candidates": "data/candidates/candidates_latest.json",
    "kline_dir": "data/kline",
    "output_dir": "data/review",
    "prompt_path": "agent/prompt.md",
    # ZenMux API 参数
    "model": "google/gemini-2.5-pro",
    "request_delay": 5,
    "skip_existing": False,
    "suggest_min_score": 4.0,
    # ZenMux API 基础 URL
    "base_url": "https://zenmux.ai/api/v1",
}


def _resolve_cfg_path(path_like, base_dir=_ROOT):
    p = Path(path_like)
    return p if p.is_absolute() else (base_dir / p)


def load_config(config_path=None):
    cfg_path = config_path or _DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"找不到配置文件：{cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = {**DEFAULT_CONFIG, **raw}

    # BaseReviewer 依赖这些路径字段为 Path 对象
    cfg["candidates"] = _resolve_cfg_path(cfg["candidates"])
    cfg["kline_dir"] = _resolve_cfg_path(cfg["kline_dir"])
    cfg["output_dir"] = _resolve_cfg_path(cfg["output_dir"])
    cfg["prompt_path"] = _resolve_cfg_path(cfg["prompt_path"])

    return cfg


class ZenMuxReviewer(BaseReviewer):
    def __init__(self, config):
        super().__init__(config)

        api_key = os.environ.get("ZENMUX_API_KEY", "")
        if not api_key:
            print(
                "[ERROR] 未找到环境变量 ZENMUX_API_KEY，请先设置后重试。",
                file=sys.stderr,
            )
            sys.exit(1)

        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=config.get("base_url", "https://zenmux.ai/api/v1"),
        )

    @staticmethod
    def image_to_base64(path: Path) -> str:
        """将图片文件转为 base64 编码的 data URL。"""
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime_type = mime_map.get(suffix, "image/jpeg")
        data = path.read_bytes()
        base64_data = base64.b64encode(data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        """
        调用 ZenMux API，对单支股票进行图表分析，返回解析后的 JSON 结果。
        """
        user_text = (
            f"股票代码：{code}\n\n"
            "以下是该股票的 **日线图**，请按照系统提示中的框架进行分析，"
            "并严格按照要求输出 JSON。"
        )

        # 将图片转为 base64 data URL
        image_data_url = self.image_to_base64(day_chart)

        response = self.client.chat.completions.create(
            model=self.config.get("model", "google/gemini-2.5-pro"),
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "【日线图】"},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
            temperature=0.2,
        )

        response_text = response.choices[0].message.content
        if response_text is None:
            raise RuntimeError(f"ZenMux API 返回空响应，无法解析 JSON（code={code}）")

        result = self.extract_json(response_text)
        result["code"] = code  # 附加股票代码便于追溯
        return result


def main():
    parser = argparse.ArgumentParser(description="ZenMux 图表复评")
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="配置文件路径（默认 config/gemini_review.yaml）",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    reviewer = ZenMuxReviewer(config)
    reviewer.run()


if __name__ == "__main__":
    main()
