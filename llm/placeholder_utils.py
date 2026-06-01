"""
占位符工具函数

提供统一的占位符注册表、解析器与时间格式化功能。

设计目标（唯一真相源）：
- ``PLACEHOLDER_GROUPS`` / ``PLACEHOLDER_DEFS`` 统一声明所有占位符及其分组、说明；
- ``build_placeholder_map`` 是唯一的取值逻辑，可同时服务「用户信息模板」（带 event 取实时值）
  与「主动提示词」（无 event，回退 runtime_data 快照）两种场景；
- ``render_template`` 是唯一的替换逻辑；
- ``stabilize_static_prompt_template`` 与前端速查面板、Web API 均从本注册表派生，避免多处漂移。
"""

import datetime
from astrbot.api import logger
from ..core.runtime_data import runtime_data
from ..utils.time_utils import get_now, get_tz

DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

WEEKDAY_NAMES = [
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
]

# 占位符分组（决定 Web UI 展示顺序与归类），token 顺序与历史前端保持一致。
PLACEHOLDER_GROUPS = [
    {
        "key": "user_info",
        "tokens": [
            "username",
            "user_id",
            "time",
            "current_time",
            "weekday",
            "platform",
            "chat_type",
            "user_last_message_time",
            "user_last_message_time_ago",
            "ai_last_sent_time",
        ],
    },
    {
        "key": "proactive",
        "tokens": [
            "user_context",
            "username",
            "platform",
            "chat_type",
            "current_time",
            "weekday",
            "user_last_message_time",
            "user_last_message_time_ago",
            "ai_last_sent_time",
            "unreplied_count",
        ],
    },
]

# 每个占位符的中文说明（desc，供 Web API / 配置文档回退）与稳定化描述（stable，
# 用于固定系统提示词防缓存污染）。这里是占位符语义的唯一声明处。
PLACEHOLDER_DEFS = {
    "user_context": {
        "desc": "完整的用户上下文信息（含用户名、平台、时间等）",
        "stable": "系统提供的用户上下文",
    },
    "username": {"desc": "用户昵称", "stable": "系统提供的用户昵称"},
    "user_id": {"desc": "用户 ID", "stable": "系统提供的用户ID"},
    "time": {"desc": "消息时间", "stable": "系统提供的消息时间"},
    "current_time": {"desc": "当前时间", "stable": "系统提供的当前时间"},
    "weekday": {"desc": "当前星期（如“星期一”）", "stable": "系统提供的星期信息"},
    "platform": {
        "desc": "平台名称（如 aiocqhttp、telegram）",
        "stable": "系统提供的平台名称",
    },
    "chat_type": {"desc": "聊天类型（群聊/私聊）", "stable": "系统提供的聊天类型"},
    "user_last_message_time": {
        "desc": "用户上次发消息的时间",
        "stable": "系统提供的用户上次发消息时间",
    },
    "user_last_message_time_ago": {
        "desc": "用户上次发消息的相对时间（如“5分钟前”）",
        "stable": "系统提供的用户上次发消息相对时间",
    },
    "ai_last_sent_time": {
        "desc": "AI 上次发送消息的时间",
        "stable": "系统提供的AI上次发送时间",
    },
    "unreplied_count": {
        "desc": "用户连续未回复次数",
        "stable": "系统提供的连续未回复次数",
    },
}


def get_placeholder_catalog() -> list:
    """返回占位符分组目录（供 Web API / 前端速查面板消费）

    Returns:
        形如 ``[{"key": "user_info", "tokens": [{"token": "username", "desc": "..."}, ...]}, ...]``
    """
    catalog = []
    for group in PLACEHOLDER_GROUPS:
        tokens = []
        for token in group["tokens"]:
            tokens.append(
                {
                    "token": token,
                    "desc": PLACEHOLDER_DEFS.get(token, {}).get("desc", ""),
                }
            )
        catalog.append({"key": group["key"], "tokens": tokens})
    return catalog


def resolve_event_identity(event) -> dict:
    """从消息事件提取用户名/用户ID/平台/聊天类型（统一身份解析）

    供 ``build_placeholder_map``（实时取值）与会话快照记录复用，避免重复实现。
    """
    message_obj = event.message_obj
    if hasattr(message_obj, "sender") and message_obj.sender:
        username = message_obj.sender.nickname or "未知用户"
        user_id = message_obj.sender.user_id or event.get_sender_id() or "未知"
    else:
        username = event.get_sender_name() or "未知用户"
        user_id = event.get_sender_id() or "未知"
    return {
        "username": username,
        "user_id": user_id,
        "platform": event.get_platform_name() or "未知平台",
        "chat_type": "群聊" if message_obj.group_id else "私聊",
    }


def _resolve_current_time(event, config, astrbot_config, tz, time_format) -> str:
    """计算 current_time/time 的取值

    有 event 时优先使用消息时间戳（按 time_format 格式化），否则使用当前时间。
    """
    if event is None:
        return get_now(config, astrbot_config).strftime(DEFAULT_TIME_FORMAT)
    try:
        message_obj = event.message_obj
        if hasattr(message_obj, "timestamp") and message_obj.timestamp:
            return datetime.datetime.fromtimestamp(
                message_obj.timestamp, tz=tz
            ).strftime(time_format)
        return get_now(config, astrbot_config).strftime(time_format)
    except Exception as e:
        logger.warning(f"心念 | ⚠️ 时间格式错误 '{time_format}': {e}，使用默认格式")
        return get_now(config, astrbot_config).strftime(DEFAULT_TIME_FORMAT)


def build_placeholder_map(
    session: str,
    config: dict,
    astrbot_config=None,
    *,
    event=None,
    time_format: str = DEFAULT_TIME_FORMAT,
    build_user_context_func=None,
) -> dict:
    """构建统一的占位符取值映射（唯一真相源）

    Args:
        session: 会话ID
        config: 插件配置字典
        astrbot_config: AstrBot 全局配置对象（可选，用于时区解析）
        event: 消息事件（可选）。提供时取实时值（用户名/ID/平台/聊天类型/消息时间），
            否则回退到 runtime_data 中保存的会话快照。
        time_format: 消息时间格式（仅在提供 event 时生效）
        build_user_context_func: 构建 ``{user_context}`` 的回调（可选）。
            仅在提供时才会产出 ``user_context`` 键。

    Returns:
        ``{token: value}`` 形式的映射（键不含花括号）。
    """
    user_info = runtime_data.session_user_info.get(session, {})
    last_sent_time = runtime_data.ai_last_sent_times.get(session, "从未发送过")
    user_last_time = user_info.get("last_active_time", "未知")

    tz = get_tz(config, astrbot_config)
    now = get_now(config, astrbot_config)
    current_time = _resolve_current_time(event, config, astrbot_config, tz, time_format)

    if event is not None:
        identity = resolve_event_identity(event)
        username = identity["username"]
        user_id = identity["user_id"]
        platform = identity["platform"]
        chat_type = identity["chat_type"]
    else:
        username = user_info.get("username", "未知用户")
        user_id = user_info.get("user_id", "未知")
        platform = user_info.get("platform", "未知平台")
        chat_type = user_info.get("chat_type", "未知")

    mapping = {
        "username": username,
        "user_id": user_id,
        "time": current_time,
        "current_time": current_time,
        "weekday": WEEKDAY_NAMES[now.weekday()],
        "platform": platform,
        "chat_type": chat_type,
        "user_last_message_time": user_last_time,
        "user_last_message_time_ago": format_time_ago(user_last_time, tz=tz),
        "ai_last_sent_time": str(last_sent_time),
        "unreplied_count": str(runtime_data.session_unreplied_count.get(session, 0)),
    }

    # user_context 取值代价较高，仅在调用方需要时才计算
    if build_user_context_func is not None:
        try:
            mapping["user_context"] = build_user_context_func(session)
        except Exception as e:
            logger.warning(f"心念 | ⚠️ 构建 user_context 失败: {e}")

    return mapping


def render_template(template: str, mapping: dict) -> str:
    """使用映射替换模板中的占位符

    使用字符串替换，避免 str.format() 和 re.sub 的特殊字符问题。

    Args:
        template: 模板字符串
        mapping: ``{token: value}`` 映射（键不含花括号）

    Returns:
        替换后的字符串
    """
    if not template:
        return template
    result = template
    for token, value in mapping.items():
        try:
            result = result.replace("{" + token + "}", str(value))
        except Exception as replace_error:
            logger.warning(f"心念 | ⚠️ 替换占位符 {token} 失败: {replace_error}")
            continue
    return result


def replace_placeholders(
    prompt: str,
    session: str,
    config: dict,
    build_user_context_func,
    astrbot_config=None,
) -> str:
    """替换提示词中的占位符（主动提示词场景，无 event）

    Args:
        prompt: 原始提示词
        session: 会话ID
        config: 配置字典
        build_user_context_func: 构建用户上下文的函数
        astrbot_config: AstrBot 全局配置对象（可选），用于时区解析

    Returns:
        替换后的提示词
    """
    try:
        mapping = build_placeholder_map(
            session,
            config,
            astrbot_config,
            build_user_context_func=build_user_context_func,
        )
        return render_template(prompt, mapping)
    except Exception as e:
        logger.error(f"心念 | ❌ 替换占位符失败: {e}")
        import traceback

        logger.error(f"心念 | 详细错误信息: {traceback.format_exc()}")
        return prompt  # 如果替换失败，返回原始提示词


def stabilize_static_prompt_template(prompt: str) -> str:
    """将固定系统提示词中的动态占位符替换为稳定描述，避免污染前缀缓存"""
    if not prompt:
        return ""

    result = prompt
    for token, meta in PLACEHOLDER_DEFS.items():
        result = result.replace("{" + token + "}", meta["stable"])
    return result


def format_time_ago(time_str: str, tz=None) -> str:
    """将时间字符串转换为相对时间描述（如"5分钟前"）

    Args:
        time_str: 时间字符串
        tz: 时区对象（可选，None 使用系统本地时区）

    Returns:
        相对时间描述
    """
    try:
        if not time_str or time_str == "未知":
            return "未知"

        # 解析时间字符串
        last_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        if tz is not None:
            last_time = last_time.replace(tzinfo=tz)
        current_time = (
            datetime.datetime.now(tz=tz) if tz is not None else datetime.datetime.now()
        )

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
        logger.error(f"心念 | ❌ 格式化相对时间失败: {e}")
        return "未知"
