from __future__ import annotations

import re
from typing import Literal

ResponseLanguage = Literal["zh-CN", "en"]

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def detect_response_language(question: str) -> ResponseLanguage:
    """Choose the response language once from the original user question."""
    return "zh-CN" if _CJK_RE.search(question) else "en"


def is_chinese(language: ResponseLanguage) -> bool:
    return language == "zh-CN"
