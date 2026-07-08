"""会话管理命令"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from ..utils.parsers import parse_sessions_list


class SessionHandlersMixin:
    """会话管理命令"""

    async def add_session(self, event: AstrMessageEvent):
        """添加当前会话到主动对话列表"""
        try:
            session_id = event.unified_msg_origin
            had_proactive_key = "proactive_reply" in self.config
            original_proactive_config = self.config.get("proactive_reply")
            proactive_config = original_proactive_config
            if not isinstance(proactive_config, dict):
                proactive_config = {}
            original_sessions = proactive_config.get("sessions", [])
            sessions = parse_sessions_list(original_sessions)

            if session_id in sessions:
                yield event.plain_result("当前会话已在主动对话列表中")
            else:
                sessions.append(session_id)
                self.config["proactive_reply"] = proactive_config
                proactive_config["sessions"] = sessions
                if not self.plugin.config_manager.save_config_safely():
                    if had_proactive_key:
                        if isinstance(original_proactive_config, dict):
                            proactive_config["sessions"] = original_sessions
                        else:
                            self.config["proactive_reply"] = original_proactive_config
                    else:
                        if "proactive_reply" in self.config:
                            del self.config["proactive_reply"]
                    yield event.plain_result(
                        "❌ 配置保存失败，已撤销本次添加；请检查日志或文件权限"
                    )
                    return
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
            proactive_config = self.config.get("proactive_reply", {})
            if not isinstance(proactive_config, dict):
                proactive_config = {}
            original_sessions = proactive_config.get("sessions", [])
            sessions = parse_sessions_list(original_sessions)

            if session_id in sessions:
                sessions.remove(session_id)
                proactive_config["sessions"] = sessions
                if not self.plugin.config_manager.save_config_safely():
                    proactive_config["sessions"] = original_sessions
                    yield event.plain_result(
                        "❌ 配置保存失败，已撤销本次移除；请检查日志或文件权限"
                    )
                    return
                # 清除该会话的计时器
                self.plugin.task_manager.clear_session_timer(session_id)
                yield event.plain_result("✅ 已从主动对话列表移除当前会话")
            else:
                yield event.plain_result("当前会话不在主动对话列表中")
        except Exception as e:
            logger.error(f"心念 | ❌ 移除会话失败: {e}")
            yield event.plain_result(f"移除会话失败: {e}")
