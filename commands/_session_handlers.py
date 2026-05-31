"""会话管理命令"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class SessionHandlersMixin:
    """会话管理命令"""

    async def add_session(self, event: AstrMessageEvent):
        """添加当前会话到主动对话列表"""
        try:
            session_id = event.unified_msg_origin
            sessions = self.config.get("proactive_reply", {}).get("sessions", [])

            if session_id in sessions:
                yield event.plain_result("当前会话已在主动对话列表中")
            else:
                sessions.append(session_id)
                if "proactive_reply" not in self.config:
                    self.config["proactive_reply"] = {}
                self.config["proactive_reply"]["sessions"] = sessions
                self.plugin.config_manager.save_config_safely()
                yield event.plain_result(
                    f"✅ 已添加会话到主动对话列表\n会话ID: {session_id}"
                )
        except Exception as e:
            logger.error(f"心念 | ❌ 添加会话失败: {e}")
            yield event.plain_result(f"添加会话失败: {e}")

    async def remove_session(self, event: AstrMessageEvent):
        """从主动对话列表移除当前会话"""
        try:
            session_id = event.unified_msg_origin
            sessions = self.config.get("proactive_reply", {}).get("sessions", [])

            if session_id in sessions:
                sessions.remove(session_id)
                self.config["proactive_reply"]["sessions"] = sessions
                self.plugin.config_manager.save_config_safely()
                # 清除该会话的计时器
                self.plugin.task_manager.clear_session_timer(session_id)
                yield event.plain_result("✅ 已从主动对话列表移除当前会话")
            else:
                yield event.plain_result("当前会话不在主动对话列表中")
        except Exception as e:
            logger.error(f"心念 | ❌ 移除会话失败: {e}")
            yield event.plain_result(f"移除会话失败: {e}")
