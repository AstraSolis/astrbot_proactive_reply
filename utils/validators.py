"""
验证工具函数

提供数据结构和数据库schema的验证功能
"""

import sqlite3
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
            logger.error(f"持久化数据缺少必需键: {key}")
            return False
        if not isinstance(data[key], dict):
            logger.error(f"持久化数据键 {key} 不是字典类型")
            return False

    return True


def verify_database_schema(cursor) -> bool:
    """验证数据库表结构

    Args:
        cursor: 数据库游标

    Returns:
        是否验证通过
    """
    try:
        # 检查表是否存在
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='webchat_conversation'"
        )
        if not cursor.fetchone():
            logger.error("❌ webchat_conversation 表不存在")
            return False

        # 检查必需字段
        cursor.execute("PRAGMA table_info(webchat_conversation)")
        columns = [column[1] for column in cursor.fetchall()]
        required_columns = ["history", "updated_at", "cid"]

        missing_columns = [col for col in required_columns if col not in columns]
        if missing_columns:
            logger.error(f"❌ 数据库表缺少必需字段: {missing_columns}")
            return False

        return True

    except sqlite3.OperationalError as e:
        logger.error(f"数据库结构检查失败: {e}")
        return False
