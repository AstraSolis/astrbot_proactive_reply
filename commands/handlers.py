"""
命令处理器

按命令域拆分到多个 Mixin（状态/会话/测试/显示/管理/通用），本类负责组合并保留共享的初始化与工具方法。
"""

from ._status_handlers import StatusHandlersMixin
from ._session_handlers import SessionHandlersMixin
from ._test_handlers import TestHandlersMixin
from ._display_handlers import DisplayHandlersMixin
from ._manage_handlers import ManageHandlersMixin
from ._general_handlers import GeneralHandlersMixin


class CommandHandlers(
    StatusHandlersMixin,
    SessionHandlersMixin,
    TestHandlersMixin,
    DisplayHandlersMixin,
    ManageHandlersMixin,
    GeneralHandlersMixin,
):
    """集中的命令处理器 - 完整实现所有命令"""

    def __init__(self, plugin):
        """初始化命令处理器

        Args:
            plugin: 主插件实例，包含所有管理器
        """
        self.plugin = plugin
        self.config = plugin.config
        self.context = plugin.context

    def _get_sleep_time_status(self) -> str:
        """获取睡眠时间的状态描述

        Returns:
            睡眠时间状态字符串
        """
        time_awareness_config = self.config.get("time_awareness", {})
        sleep_mode_enabled = time_awareness_config.get("sleep_mode_enabled", False)
        sleep_hours = time_awareness_config.get("sleep_hours", "22:00-8:00")
        send_on_wake = time_awareness_config.get("send_on_wake_enabled", False)
        wake_mode = time_awareness_config.get("wake_send_mode", "immediate")

        if sleep_mode_enabled:
            if send_on_wake:
                mode_text = "立即发送" if wake_mode == "immediate" else "延后发送"
                return f"✅ 已启用 ({sleep_hours}, 醒来{mode_text})"
            else:
                return f"✅ 已启用 ({sleep_hours}, 跳过)"
        else:
            return "❌ 未启用"
