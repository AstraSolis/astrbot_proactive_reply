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
    required_keys = ["session_user_info", "ai_last_sent_times", "last_sent_times"]

    for key in required_keys:
        if key not in data:
            logger.error(f"心念 | ❌ 持久化数据缺少必需键: {key}")
            return False
        if not isinstance(data[key], dict):
            logger.error(f"心念 | ❌ 持久化数据键 {key} 不是字典类型")
            return False

    return True
