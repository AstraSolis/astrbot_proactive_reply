"""
运行时数据存储

存储不应该出现在配置界面中的运行时数据，如用户信息、发送时间记录等。
这些数据通过 PersistenceManager 持久化到独立的 JSON 文件中。
"""

from astrbot.api import logger


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

        logger.debug("RuntimeDataStore 初始化完成")

    def load_from_dict(self, data: dict):
        """从字典加载数据

        Args:
            data: 包含运行时数据的字典
        """
        if "session_user_info" in data:
            self.session_user_info = data["session_user_info"]
        if "ai_last_sent_times" in data:
            self.ai_last_sent_times = data["ai_last_sent_times"]
        if "last_sent_times" in data:
            self.last_sent_times = data["last_sent_times"]
        if "session_next_fire_times" in data:
            self.session_next_fire_times = data["session_next_fire_times"]
        if "session_sleep_remaining" in data:
            self.session_sleep_remaining = data["session_sleep_remaining"]
        if "timing_config_signature" in data:
            self.timing_config_signature = data["timing_config_signature"]
        if "session_last_proactive_message" in data:
            self.session_last_proactive_message = data["session_last_proactive_message"]
        if "session_unreplied_count" in data:
            self.session_unreplied_count = data["session_unreplied_count"]
        if "session_consecutive_failures" in data:
            self.session_consecutive_failures = data["session_consecutive_failures"]

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
        logger.info("已清除所有运行时数据")


# 全局单例实例
runtime_data = RuntimeDataStore()
