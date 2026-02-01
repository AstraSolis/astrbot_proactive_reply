"""
时间工具模块

提供时间相关的工具函数
"""

import datetime
from astrbot.api import logger


def is_in_time_range(time_range: str) -> bool:
    """检查当前时间是否在指定的时间范围内

    支持跨午夜的时间段（如 "22:00-8:00"）

    Args:
        time_range: 时间范围字符串，格式为 "HH:MM-HH:MM"

    Returns:
        True 如果当前时间在范围内，False 否则
    """
    try:
        start_time, end_time = time_range.split("-")
        start_hour, start_min = map(int, start_time.split(":"))
        end_hour, end_min = map(int, end_time.split(":"))

        now = datetime.datetime.now()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_hour * 60 + start_min
        end_minutes = end_hour * 60 + end_min

        # 处理跨午夜的时间段（如 22:00-8:00）
        if start_minutes > end_minutes:
            # 跨午夜：当前时间在开始时间之后 或 在结束时间之前
            return current_minutes >= start_minutes or current_minutes <= end_minutes
        else:
            # 不跨午夜：当前时间在开始和结束之间
            return start_minutes <= current_minutes <= end_minutes
    except Exception as e:
        logger.warning(f"时间范围解析错误: {e}")
        return False


def is_sleep_time(config: dict) -> bool:
    """检查当前是否处于睡眠时间

    从配置中读取 time_awareness.sleep_mode_enabled 和 time_awareness.sleep_hours

    Args:
        config: 插件配置字典

    Returns:
        True 如果处于睡眠时间（不应发送主动消息），False 否则
    """
    time_awareness_config = config.get("time_awareness", {})

    # 检查睡眠时间功能是否启用
    if not time_awareness_config.get("sleep_mode_enabled", False):
        return False

    sleep_hours = time_awareness_config.get("sleep_hours", "22:00-8:00")
    return is_in_time_range(sleep_hours)


def get_sleep_prompt_if_active(config: dict) -> str:
    """获取睡眠时间提示（如果当前处于睡眠时间）

    Args:
        config: 插件配置字典

    Returns:
        睡眠提示字符串，如果不在睡眠时间则返回空字符串
    """
    if not is_sleep_time(config):
        return ""

    time_awareness_config = config.get("time_awareness", {})
    return time_awareness_config.get(
        "sleep_prompt", "【系统提示】当前处于睡眠时间段，请以符合人设的方式自然回应。"
    )
