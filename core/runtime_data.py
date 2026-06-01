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
        ``"2025-01-01"`` 的无引号标量隐式转型，而用户昵称、user_id（如 QQ 号）、
        签名等本应是字符串。``safe_dump`` 写出的文件能正确 round-trip，此处主要
        防御「手动编辑后类型漂移」的情况。

        Args:
            data: 包含运行时数据的字典
        """
        if "session_user_info" in data:
            self.session_user_info = _normalize_user_info(data["session_user_info"])
        if "ai_last_sent_times" in data:
            self.ai_last_sent_times = data["ai_last_sent_times"]
        if "last_sent_times" in data:
            self.last_sent_times = data["last_sent_times"]
        if "session_next_fire_times" in data:
            self.session_next_fire_times = data["session_next_fire_times"]
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
