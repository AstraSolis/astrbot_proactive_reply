"""
运行时数据存储

存储不应该出现在配置界面中的运行时数据，如用户信息、发送时间记录等。
这些数据通过 PersistenceManager 持久化到独立的 YAML 文件中。
"""

from astrbot.api import logger

# session_user_info 中应保持为字符串的字段（user_id 如 QQ 号、纯数字昵称等
# 易被 YAML 隐式转型为 int/bool/date）
_USER_INFO_STR_FIELDS = (
    "username",
    "user_id",
    "platform",
    "chat_type",
    "last_active_time",
)


def _as_str(value) -> str:
    """将标量规整为字符串（None 视为空串）"""
    if value is None:
        return ""
    return str(value)


def _stringify_values(mapping) -> dict:
    """将映射的「值」统一规整为字符串"""
    if not isinstance(mapping, dict):
        return {}
    return {key: _as_str(value) for key, value in mapping.items()}


def _intify_values(mapping) -> dict:
    """将映射的「值」尽量规整为 int（失败回退 0）"""
    if not isinstance(mapping, dict):
        return {}
    result = {}
    for key, value in mapping.items():
        try:
            result[key] = int(value)
        except (TypeError, ValueError):
            result[key] = 0
    return result


def _normalize_user_info(mapping) -> dict:
    """规整 session_user_info：保证每个会话的信息为 dict，且字符串字段不被转型"""
    if not isinstance(mapping, dict):
        return {}
    result = {}
    for session, info in mapping.items():
        if not isinstance(info, dict):
            continue
        normalized = dict(info)
        for field in _USER_INFO_STR_FIELDS:
            if field in normalized and normalized[field] is not None:
                normalized[field] = str(normalized[field])
        result[session] = normalized
    return result


def _ordered_user_info(info: dict) -> dict:
    """按固定字段顺序重排单个会话的用户信息（未知字段追加在后，顺序稳定）"""
    if not isinstance(info, dict):
        return {}
    ordered = {field: info[field] for field in _USER_INFO_STR_FIELDS if field in info}
    for key, value in info.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _is_nested_format(data: dict) -> bool:
    """判断持久化数据是否为 session-major 嵌套格式

    新格式以 ``sessions`` 为顶层键聚合每个会话的数据；旧的扁平格式以
    ``session_user_info`` 等字段为顶层键。以结构而非 ``data_version`` 判定，
    对历史文件与手动编辑更健壮。
    """
    return isinstance(data.get("sessions"), dict) and "session_user_info" not in data


def _unnest_persistent(data: dict) -> dict:
    """将 session-major 嵌套格式展开回扁平的运行时字段映射

    与 :meth:`RuntimeDataStore.load_from_dict` 期望的扁平结构对齐，便于复用既有
    的类型规整逻辑。缺失 / ``None`` 的子字段直接跳过（保持映射精简）。
    """
    meta = data.get("meta") or {}
    sessions = data.get("sessions") or {}

    session_user_info: dict = {}
    ai_last_sent_times: dict = {}
    last_sent_times: dict = {}
    session_next_fire_times: dict = {}
    session_sleep_remaining: dict = {}
    session_last_proactive_message: dict = {}
    session_unreplied_count: dict = {}
    session_consecutive_failures: dict = {}
    session_ai_scheduled: dict = {}

    for umo, block in sessions.items():
        if not isinstance(block, dict):
            continue

        user = block.get("user")
        if isinstance(user, dict):
            session_user_info[umo] = user

        timers = block.get("timers") or {}
        if timers.get("next_fire_time") is not None:
            session_next_fire_times[umo] = timers["next_fire_time"]
        if timers.get("sleep_remaining") is not None:
            session_sleep_remaining[umo] = timers["sleep_remaining"]

        activity = block.get("activity") or {}
        if activity.get("last_sent_time") is not None:
            last_sent_times[umo] = activity["last_sent_time"]
        if activity.get("ai_last_sent_time") is not None:
            ai_last_sent_times[umo] = activity["ai_last_sent_time"]
        if activity.get("unreplied_count") is not None:
            session_unreplied_count[umo] = activity["unreplied_count"]
        if activity.get("consecutive_failures") is not None:
            session_consecutive_failures[umo] = activity["consecutive_failures"]

        scheduled = block.get("ai_scheduled")
        if scheduled:
            session_ai_scheduled[umo] = scheduled

        message = block.get("last_proactive_message")
        if message is not None:
            session_last_proactive_message[umo] = message

    return {
        "session_user_info": session_user_info,
        "ai_last_sent_times": ai_last_sent_times,
        "last_sent_times": last_sent_times,
        "session_next_fire_times": session_next_fire_times,
        "session_sleep_remaining": session_sleep_remaining,
        "timing_config_signature": meta.get("timing_config_signature", ""),
        "session_last_proactive_message": session_last_proactive_message,
        "session_unreplied_count": session_unreplied_count,
        "session_consecutive_failures": session_consecutive_failures,
        "session_ai_scheduled": session_ai_scheduled,
        "timezone_signature": meta.get("timezone_signature", ""),
    }


class RuntimeDataStore:
    """运行时数据存储类

    单例模式，存储运行时数据，避免将这些数据放入 config 对象中
    （config 对象的内容会显示在 AstrBot 配置界面上）
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 运行时数据
        self.session_user_info: dict = {}
        self.ai_last_sent_times: dict = {}
        self.last_sent_times: dict = {}
        # 计时器相关
        self.session_next_fire_times: dict = {}  # session -> "2025-12-29 22:00:00"
        self.session_sleep_remaining: dict = {}  # session -> 3600.0 (秒)
        self.timing_config_signature: str = ""  # 配置签名，用于检测配置变化
        # 重复检测相关
        self.session_last_proactive_message: dict = {}  # session -> message
        # 未回复计数
        self.session_unreplied_count: dict = {}  # session -> int
        # 连续失败计数（用于错误通知）
        self.session_consecutive_failures: dict = {}  # session -> int
        # AI 自主调度信息
        self.session_ai_scheduled: dict = {}
        # 时区签名，用于检测时区配置变化
        self.timezone_signature: str = ""

        logger.debug("心念 | RuntimeDataStore 初始化完成")

    def load_from_dict(self, data: dict):
        """从字典加载数据

        对关键字段做轻量类型规整：YAML 会把形如 ``"123"`` / ``"true"`` /
        ``"2025-01-01 09:00:00"`` 的无引号标量隐式转型，而用户昵称、user_id
        （如 QQ 号）、各类时间戳（发送/下次触发时间，下游用 ``strptime`` 解析）、
        签名等本应是字符串。``safe_dump`` 写出的文件能正确 round-trip，此处主要
        防御「手动编辑后类型漂移」的情况（无引号时间戳会被 ``safe_load`` 转成
        ``datetime``，传给 ``strptime`` 会抛 ``TypeError``）。

        Args:
            data: 包含运行时数据的字典（兼容 session-major 嵌套格式与旧的扁平格式）
        """
        if not isinstance(data, dict):
            return
        # 兼容新的 session-major 嵌套格式：先展开回扁平结构再做类型规整
        if _is_nested_format(data):
            data = _unnest_persistent(data)
        if "session_user_info" in data:
            self.session_user_info = _normalize_user_info(data["session_user_info"])
        if "ai_last_sent_times" in data:
            self.ai_last_sent_times = _stringify_values(data["ai_last_sent_times"])
        if "last_sent_times" in data:
            self.last_sent_times = _stringify_values(data["last_sent_times"])
        if "session_next_fire_times" in data:
            self.session_next_fire_times = _stringify_values(
                data["session_next_fire_times"]
            )
        if "session_sleep_remaining" in data:
            self.session_sleep_remaining = data["session_sleep_remaining"]
        if "timing_config_signature" in data:
            self.timing_config_signature = _as_str(data["timing_config_signature"])
        if "session_last_proactive_message" in data:
            self.session_last_proactive_message = _stringify_values(
                data["session_last_proactive_message"]
            )
        if "session_unreplied_count" in data:
            self.session_unreplied_count = _intify_values(
                data["session_unreplied_count"]
            )
        if "session_consecutive_failures" in data:
            self.session_consecutive_failures = _intify_values(
                data["session_consecutive_failures"]
            )
        if "session_ai_scheduled" in data:
            self.session_ai_scheduled = data["session_ai_scheduled"]
        if "timezone_signature" in data:
            self.timezone_signature = _as_str(data["timezone_signature"])

    def to_dict(self) -> dict:
        """导出为字典

        Returns:
            包含所有运行时数据的字典
        """
        return {
            "session_user_info": self.session_user_info,
            "ai_last_sent_times": self.ai_last_sent_times,
            "last_sent_times": self.last_sent_times,
            "session_next_fire_times": self.session_next_fire_times,
            "session_sleep_remaining": self.session_sleep_remaining,
            "timing_config_signature": self.timing_config_signature,
            "session_last_proactive_message": self.session_last_proactive_message,
            "session_unreplied_count": self.session_unreplied_count,
            "session_consecutive_failures": self.session_consecutive_failures,
            "session_ai_scheduled": self.session_ai_scheduled,
            "timezone_signature": self.timezone_signature,
        }

    def to_persistent_dict(self) -> dict:
        """导出为 session-major 嵌套字典（持久化文件的当前磁盘格式）

        将分散在各字段映射里的数据按「会话」聚合，并把全局状态收纳进 ``meta``，
        使持久化文件直观、便于查阅与 diff。``meta`` 中的 ``last_update`` 由
        :class:`PersistenceManager` 在写盘时填充。

        Returns:
            形如 ``{"meta": {...}, "sessions": {umo: {...}}}`` 的字典
        """
        # 收集所有出现过的会话 UMO，保持插入顺序（diff 稳定，避免无谓churn）
        ordered_umos: list = []
        seen: set = set()
        for mapping in (
            self.session_user_info,
            self.session_next_fire_times,
            self.session_sleep_remaining,
            self.last_sent_times,
            self.ai_last_sent_times,
            self.session_unreplied_count,
            self.session_consecutive_failures,
            self.session_ai_scheduled,
            self.session_last_proactive_message,
        ):
            for umo in mapping:
                if umo not in seen:
                    seen.add(umo)
                    ordered_umos.append(umo)

        sessions: dict = {}
        for umo in ordered_umos:
            sessions[umo] = {
                "user": _ordered_user_info(self.session_user_info.get(umo, {})),
                "timers": {
                    "next_fire_time": self.session_next_fire_times.get(umo),
                    "sleep_remaining": self.session_sleep_remaining.get(umo),
                },
                "activity": {
                    "last_sent_time": self.last_sent_times.get(umo),
                    "ai_last_sent_time": self.ai_last_sent_times.get(umo),
                    "unreplied_count": int(self.session_unreplied_count.get(umo, 0)),
                    "consecutive_failures": int(
                        self.session_consecutive_failures.get(umo, 0)
                    ),
                },
                "ai_scheduled": self.session_ai_scheduled.get(umo, []),
                "last_proactive_message": self.session_last_proactive_message.get(umo),
            }

        return {
            "meta": {
                "data_version": "3.1",
                "last_update": "",
                "timezone_signature": self.timezone_signature,
                "timing_config_signature": self.timing_config_signature,
            },
            "sessions": sessions,
        }

    def clear_all(self):
        """清除所有运行时数据"""
        self.session_user_info = {}
        self.ai_last_sent_times = {}
        self.last_sent_times = {}
        self.session_next_fire_times = {}
        self.session_sleep_remaining = {}
        self.timing_config_signature = ""
        self.session_last_proactive_message = {}
        self.session_unreplied_count = {}
        self.session_consecutive_failures = {}
        self.session_ai_scheduled = {}
        logger.info("心念 | ✅ 已清除所有运行时数据")


# 全局单例实例
runtime_data = RuntimeDataStore()
