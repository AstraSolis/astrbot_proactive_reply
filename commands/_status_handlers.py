"""状态查询命令"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from ..core.runtime_data import runtime_data


class StatusHandlersMixin:
    """状态查询命令"""

    async def status(self, event: AstrMessageEvent):
        """查看插件状态

        显示插件的详细运行状态，包括：
        - 当前会话信息和在列表中的状态
        - 用户信息附加功能配置
        - 智能主动发送功能详细配置
        - LLM提供商可用性
        - 定时模式、发送间隔、睡眠时间等
        - 已记录的会话数和发送记录数
        """
        try:
            user_config = self.config.get("user_info", {})
            proactive_config = self.config.get("proactive_reply", {})

            sessions_data = proactive_config.get("sessions", [])
            from ..utils.parsers import parse_sessions_list

            sessions = parse_sessions_list(sessions_data)
            session_count = len(sessions)

            # 获取用户信息记录数量（从运行时数据存储）
            user_info_count = len(runtime_data.session_user_info)

            # 获取发送时间记录数量
            ai_sent_times_count = len(runtime_data.ai_last_sent_times)

            # 检查当前会话状态
            current_session = event.unified_msg_origin

            # 检查LLM状态
            try:
                provider_id = await self.context.get_current_chat_provider_id(
                    umo=current_session
                )
                llm_available = provider_id is not None
            except Exception:
                llm_available = False
            is_current_in_list = current_session in sessions

            # 获取各会话的下次发送时间信息
            next_fire_info = ""
            if proactive_config.get("enabled", False) and session_count > 0:
                sessions_status = self.plugin.task_manager.get_all_sessions_status()
                if sessions_status:
                    next_fire_info = "\n\n⏱️ 各会话下次发送时间："
                    for sess, info in sessions_status[:5]:  # 最多显示5个
                        sess_display = sess[:30] + "..." if len(sess) > 30 else sess
                        next_fire_info += f"\n  - {sess_display}: {info}"
                    if len(sessions_status) > 5:
                        next_fire_info += (
                            f"\n  ... 还有 {len(sessions_status) - 5} 个会话"
                        )

            # 获取 AI 自主调度配置
            ai_schedule_config = self.config.get("ai_schedule", {})
            ai_schedule_enabled = ai_schedule_config.get("enabled", False)
            ai_schedule_provider = ai_schedule_config.get("provider_id", "")

            # 构建 AI 调度状态文本
            ai_schedule_status = f"\n\n🧠 AI 自主调度功能：{'✅ 已启用' if ai_schedule_enabled else '❌ 已禁用'}"
            if ai_schedule_enabled:
                provider_text = (
                    ai_schedule_provider
                    if ai_schedule_provider
                    else "主模型（与用户对话相同）"
                )
                ai_schedule_status += f"\n  - 分析模型：{provider_text}"
                ai_schedule_status += (
                    "\n  - 功能说明：AI 在对话中提到时间约定时自动设置定时任务"
                )

            status_text = f"""📊 主动回复插件状态

📍 当前会话：
  - 会话ID：{current_session[:50]}{"..." if len(current_session) > 50 else ""}
  - 发送状态：{"✅ 已在主动对话列表中" if is_current_in_list else "❌ 未在主动对话列表中"}
  - 操作提示：{"使用 /proactive remove_session 移除" if is_current_in_list else "使用 /proactive add_session 添加"}

🔧 用户信息附加功能：✅ 已启用
  - 时间格式：{user_config.get("time_format", "%Y-%m-%d %H:%M:%S")}
  - 已记录用户信息：{user_info_count} 个会话

🤖 智能主动发送功能：{"✅ 已启用" if proactive_config.get("enabled", False) else "❌ 已禁用"}
  - LLM提供商：{"✅ 可用" if llm_available else "❌ 不可用"}
  - 时间模式：{proactive_config.get("timing_mode", "fixed_interval")}
  - 发送间隔：{proactive_config.get("interval_minutes", 60)} 分钟
  - 睡眠时间：{self._get_sleep_time_status()}
  - 配置会话数：{session_count}
  - AI发送记录数：{ai_sent_times_count}{next_fire_info}{ai_schedule_status}

💡 使用 /proactive help 查看更多指令"""
            yield event.plain_result(status_text)
        except Exception as e:
            logger.error(f"心念 | ❌ 查询状态失败: {e}")
            yield event.plain_result(f"查询状态失败: {e}")
