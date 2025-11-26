"""
格式化工具函数

提供字符串编码处理和安全字符串操作
"""

from astrbot.api import logger


def ensure_string_encoding(text: str) -> str:
    """确保字符串的正确编码

    Args:
        text: 输入文本

    Returns:
        正确编码的字符串
    """
    try:
        if not isinstance(text, str):
            text = str(text)

        # 尝试编码和解码以确保字符串正确
        encoded = text.encode("utf-8", errors="replace")
        decoded = encoded.decode("utf-8", errors="replace")

        return decoded
    except Exception as e:
        logger.warning(f"字符串编码处理失败: {e}, 原文本: {repr(text)}")
        return str(text)


def safe_string_replace(text: str, old: str, new: str) -> str:
    """安全的字符串替换，处理编码问题

    Args:
        text: 原始文本
        old: 要替换的字符串
        new: 替换后的字符串

    Returns:
        替换后的字符串
    """
    try:
        # 确保所有字符串都是正确编码的
        text = ensure_string_encoding(text)
        old = ensure_string_encoding(old)
        new = ensure_string_encoding(new)

        result = text.replace(old, new)
        return ensure_string_encoding(result)
    except Exception as e:
        logger.warning(f"字符串替换失败: {e}")
        return text
