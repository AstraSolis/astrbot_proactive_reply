"""
时间工具模块

提供时间相关的工具函数
"""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from astrbot.api import logger


def _get_astrbot_timezone(astrbot_config) -> str:
    """从 AstrBot 全局配置中读取时区字符串

    Args:
        astrbot_config: AstrBot 全局配置对象（AstrBotConfig）

    Returns:
        时区字符串，未找到时返回空字符串
    """
    try:
        if hasattr(astrbot_config, "get"):
            tz = astrbot_config.get("timezone", "") or ""
            if tz:
                return tz
        if hasattr(astrbot_config, "timezone"):
            return astrbot_config.timezone or ""
    except Exception as e:
        logger.debug(f"心念 | 读取 AstrBot 时区失败: {e}")
    return ""


def get_tz(config: dict, astrbot_config=None):
    """获取有效时区对象

    优先级：AstrBot 全局时区（需启用开关）> 插件自身时区 > 系统本地时区

    Args:
        config: 插件配置字典
        astrbot_config: AstrBot 全局配置对象（可选），有值时才会尝试读取 AstrBot 时区

    Returns:
        ZoneInfo 对象，无有效配置时返回 None（使用系统本地时区）
    """
    time_awareness_config = config.get("time_awareness", {})
    timezone_settings = config.get("basic_settings", {})

    # 启用了「跟随 AstrBot 时区」且提供了 AstrBot 配置
    use_astrbot = (
        timezone_settings.get("use_astrbot_timezone", False)
        or time_awareness_config.get("use_astrbot_timezone", False)  # 兼容旧配置
    )
    if use_astrbot and astrbot_config is not None:
        tz_str = _get_astrbot_timezone(astrbot_config)
        if tz_str:
            try:
                return ZoneInfo(tz_str)
            except (ZoneInfoNotFoundError, KeyError) as e:
                logger.warning(
                    f"心念 | ⚠️ AstrBot 时区配置无效 '{tz_str}': {e}，回退到插件时区配置"
                )
        elif use_astrbot:
            logger.debug("心念 | 已启用「跟随 AstrBot 时区」但 AstrBot 未配置时区，回退到插件时区配置")

    # 使用插件自身的时区配置（兼容新旧两个字段位置）
    tz_str = timezone_settings.get("timezone", "") or time_awareness_config.get("timezone", "")
    if not tz_str:
        return None
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError) as e:
        logger.warning(f"心念 | ⚠️ 无效的时区配置 '{tz_str}': {e}，回退到系统本地时区")
        return None


def get_now(config: dict, astrbot_config=None) -> datetime.datetime:
    """获取当前时间（使用有效时区）

    Args:
        config: 插件配置字典
        astrbot_config: AstrBot 全局配置对象（可选）

    Returns:
        当前时间，tz 已配置时为 aware datetime，否则为 naive 本地时间
    """
    tz = get_tz(config, astrbot_config)
    if tz is not None:
        return datetime.datetime.now(tz=tz)
    return datetime.datetime.now()


def is_in_time_range(time_range: str, tz=None) -> bool:
    """检查当前时间是否在指定的时间范围内

    支持跨午夜的时间段（如 "22:00-8:00"）

    Args:
        time_range: 时间范围字符串，格式为 "HH:MM-HH:MM"
        tz: 时区对象（可选，None 使用系统本地时区）

    Returns:
        True 如果当前时间在范围内，False 否则
    """
    try:
        start_time, end_time = time_range.split("-")
        start_hour, start_min = map(int, start_time.split(":"))
        end_hour, end_min = map(int, end_time.split(":"))

        now = datetime.datetime.now(tz=tz) if tz is not None else datetime.datetime.now()
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
        logger.warning(f"心念 | ⚠️ 时间范围解析错误: {e}")
        return False


def is_sleep_time(config: dict, astrbot_config=None) -> bool:
    """检查当前是否处于睡眠时间

    从配置中读取 time_awareness.sleep_mode_enabled 和 time_awareness.sleep_hours

    Args:
        config: 插件配置字典
        astrbot_config: AstrBot 全局配置对象（可选）

    Returns:
        True 如果处于睡眠时间（不应发送主动消息），False 否则
    """
    time_awareness_config = config.get("time_awareness", {})

    # 检查睡眠时间功能是否启用
    if not time_awareness_config.get("sleep_mode_enabled", False):
        return False

    sleep_hours = time_awareness_config.get("sleep_hours", "22:00-8:00")
    tz = get_tz(config, astrbot_config)
    return is_in_time_range(sleep_hours, tz=tz)


def get_seconds_until_sleep_end(config: dict, astrbot_config=None) -> int:
    """计算到睡眠结束的秒数

    Args:
        config: 插件配置字典
        astrbot_config: AstrBot 全局配置对象（可选）

    Returns:
        到睡眠结束的秒数，如果不在睡眠时间则返回 0
    """
    time_awareness_config = config.get("time_awareness", {})

    # 检查睡眠时间功能是否启用
    if not time_awareness_config.get("sleep_mode_enabled", False):
        return 0

    sleep_hours = time_awareness_config.get("sleep_hours", "22:00-8:00")
    tz = get_tz(config, astrbot_config)

    # 如果不在睡眠时间，返回 0
    if not is_in_time_range(sleep_hours, tz=tz):
        return 0

    try:
        _, end_time = sleep_hours.split("-")
        end_hour, end_min = map(int, end_time.split(":"))

        now = datetime.datetime.now(tz=tz) if tz is not None else datetime.datetime.now()
        # 构造结束时间（下一分钟的开始，因为 is_in_time_range 使用分钟精度）
        # 例如：睡眠时间 "xx:xx-15:21" 表示到 15:21:59 结束，即 15:22:00 开始不在睡眠时间
        end_datetime = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        end_datetime += datetime.timedelta(minutes=1)  # 加1分钟，对齐 is_in_time_range 的语义

        # 如果结束时间已经过了，说明是跨午夜，结束时间是明天
        if end_datetime <= now:
            end_datetime += datetime.timedelta(days=1)

        seconds_until_end = (end_datetime - now).total_seconds()
        return max(1, int(seconds_until_end))  # 至少返回1秒
    except Exception as e:
        logger.warning(f"心念 | ⚠️ 计算睡眠结束时间失败: {e}")
        return 0



def get_sleep_prompt_if_active(config: dict, astrbot_config=None) -> str:
    """获取睡眠时间提示（如果当前处于睡眠时间）

    Args:
        config: 插件配置字典
        astrbot_config: AstrBot 全局配置对象（可选）

    Returns:
        睡眠提示字符串，如果不在睡眠时间则返回空字符串
    """
    if not is_sleep_time(config, astrbot_config):
        return ""

    time_awareness_config = config.get("time_awareness", {})
    return time_awareness_config.get(
        "sleep_prompt", "【系统提示】当前处于睡眠时间段，请以符合人设的方式自然回应。"
    )
