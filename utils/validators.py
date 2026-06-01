"""
验证工具函数

提供数据结构验证功能
"""

from astrbot.api import logger


def validate_persistent_data(data: dict) -> bool:
    """验证持久化数据结构

    同时支持两种格式：
    - session-major 嵌套格式（当前）：``{"meta": {...}, "sessions": {...}}``。
    - 旧的扁平格式：以 ``session_user_info`` 等字段为顶层键。

    Args:
        data: 持久化数据字典

    Returns:
        是否验证通过
    """
    if not isinstance(data, dict):
        logger.error("心念 | ❌ 持久化数据应为字典类型")
        return False

    # session-major 嵌套格式
    if "sessions" in data:
        if not isinstance(data["sessions"], dict):
            logger.error(
                f"心念 | ❌ 持久化数据键 sessions 应为字典类型，"
                f"实际为 {type(data['sessions']).__name__}"
            )
            return False
        if not isinstance(data.get("meta", {}), dict):
            logger.error(
                f"心念 | ❌ 持久化数据键 meta 应为字典类型，"
                f"实际为 {type(data['meta']).__name__}"
            )
            return False
        for session, block in data["sessions"].items():
            if not isinstance(block, dict):
                logger.error(
                    f"心念 | ❌ 会话 {session} 的数据应为字典类型，"
                    f"实际为 {type(block).__name__}"
                )
                return False
        return True

    # 旧的扁平格式（向后兼容）
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
            logger.error(
                f"心念 | ❌ 持久化数据键 {key} 应为字典类型，实际为 {type(data[key]).__name__}"
            )
            return False

    return True
