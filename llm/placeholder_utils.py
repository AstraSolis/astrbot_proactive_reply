"""
占位符工具函数

提供占位符替换和时间格式化功能
"""

import datetime
from astrbot.api import logger
from ..utils.formatters import ensure_string_encoding, safe_string_replace
from ..core.runtime_data import runtime_data


def replace_placeholders(
    prompt: str, session: str, config: dict, build_user_context_func
) -> str:
    """替换提示词中的占位符

    Args:
        prompt: 原始提示词
        session: 会话ID
        config: 配置字典
        build_user_context_func: 构建用户上下文的函数

    Returns:
        替换后的提示词
    """
    try:
        # 确保输入参数的编码正确
        prompt = ensure_string_encoding(prompt)
        session = ensure_string_encoding(session)

        user_info = runtime_data.session_user_info.get(session, {})
        last_sent_time = runtime_data.ai_last_sent_times.get(session, "从未发送过")

        # 构建占位符字典，确保所有值都是正确编码的字符串
        user_last_time = ensure_string_encoding(
            user_info.get("last_active_time", "未知")
        )

        placeholders = {
            "{user_context}": ensure_string_encoding(build_user_context_func(session)),
            "{user_last_message_time}": user_last_time,
            "{user_last_message_time_ago}": ensure_string_encoding(
                format_time_ago(user_last_time)
            ),
            "{username}": ensure_string_encoding(user_info.get("username", "未知用户")),
            "{platform}": ensure_string_encoding(user_info.get("platform", "未知平台")),
            "{chat_type}": ensure_string_encoding(user_info.get("chat_type", "未知")),
            "{ai_last_sent_time}": ensure_string_encoding(last_sent_time),
            "{current_time}": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "{unreplied_count}": str(
                runtime_data.session_unreplied_count.get(session, 0)
            ),
        }

        # 替换所有占位符，使用安全的字符串替换
        result = prompt
        for placeholder, value in placeholders.items():
            try:
                result = safe_string_replace(result, placeholder, str(value))
            except Exception as replace_error:
                logger.warning(f"替换占位符 {placeholder} 失败: {replace_error}")
                continue

        return result

    except Exception as e:
        logger.error(f"替换占位符失败: {e}")
        import traceback

        logger.error(f"详细错误信息: {traceback.format_exc()}")
        return prompt  # 如果替换失败，返回原始提示词


def format_time_ago(time_str: str) -> str:
    """将时间字符串转换为相对时间描述（如"5分钟前"）

    Args:
        time_str: 时间字符串

    Returns:
        相对时间描述
    """
    try:
        if not time_str or time_str == "未知":
            return "未知"

        # 解析时间字符串
        last_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        current_time = datetime.datetime.now()

        # 计算时间差
        time_diff = current_time - last_time
        total_seconds = int(time_diff.total_seconds())

        if total_seconds < 0:
            return "刚刚"
        elif total_seconds < 60:
            return f"{total_seconds}秒前"
        elif total_seconds < 3600:  # 小于1小时
            minutes = total_seconds // 60
            return f"{minutes}分钟前"
        elif total_seconds < 86400:  # 小于1天
            hours = total_seconds // 3600
            return f"{hours}小时前"
        elif total_seconds < 2592000:  # 小于30天
            days = total_seconds // 86400
            return f"{days}天前"
        elif total_seconds < 31536000:  # 小于365天
            months = total_seconds // 2592000
            return f"{months}个月前"
        else:
            years = total_seconds // 31536000
            return f"{years}年前"

    except Exception as e:
        logger.error(f"格式化相对时间失败: {e}")
        return "未知"
