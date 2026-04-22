"""
验证工具函数

提供数据结构验证功能
"""

from astrbot.api import logger


def validate_persistent_data(data: dict) -> bool:
    """验证持久化数据结构

    Args:
        data: 持久化数据字典

    Returns:
        是否验证通过
    """
    dict_keys = [
        "session_user_info",
        "ai_last_sent_times",
        "last_sent_times",
        "session_next_fire_times",
        "session_sleep_remaining",
        "session_last_proactive_message",
        "session_unreplied_count",
        "session_consecutive_failures",
        "session_ai_scheduled",
    ]

    for key in dict_keys:
        if key not in data:
            logger.error(f"心念 | ❌ 持久化数据缺少必需键: {key}")
            return False
        if not isinstance(data[key], dict):
            logger.error(f"心念 | ❌ 持久化数据键 {key} 应为字典类型，实际为 {type(data[key]).__name__}")
            return False

    return True
