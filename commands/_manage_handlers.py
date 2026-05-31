"""功能管理与调试命令"""

import asyncio
from astrbot.api.event import AstrMessageEvent
from ..core.runtime_data import runtime_data


class ManageHandlersMixin:
    """功能管理与调试命令"""

    async def manage_functions(self, event: AstrMessageEvent, action: str = ""):
        """管理功能 - 支持多种管理操作

        基础管理操作：
        - clear: 清除记录的用户信息和发送时间
        - task_status: 检查定时任务状态（查看任务运行情况）
        - force_stop: 强制停止所有定时任务
        - force_start: 强制启动定时任务（忽略配置中的enabled状态）
        - save_config: 强制保存配置文件

        故障排查操作：
        - debug_info: 调试用户信息（查看AI收到的用户上下文信息）
        - debug_send: 调试发送功能（查看LLM生成的消息内容）
        - debug_times: 调试时间记录（查看所有AI发送时间记录）

        使用方法: /proactive manage [操作]
        例如: /proactive manage debug_info
        """
        manage_type = action

        if manage_type == "clear":
            async for result in self._manage_clear(event):
                yield result
        elif manage_type == "task_status":
            async for result in self._manage_task_status(event):
                yield result
        elif manage_type == "force_stop":
            async for result in self._manage_force_stop(event):
                yield result
        elif manage_type == "force_start":
            async for result in self._manage_force_start(event):
                yield result
        elif manage_type == "save_config":
            async for result in self._manage_save_config(event):
                yield result
        elif manage_type == "debug_info":
            async for result in self._debug_info(event):
                yield result
        elif manage_type == "debug_send":
            async for result in self._debug_send(event):
                yield result
        elif manage_type == "debug_times":
            async for result in self._debug_times(event):
                yield result

        else:
            yield event.plain_result("""管理操作:
• clear - 清除用户信息
• task_status - 任务状态
• force_stop - 强制停止
• force_start - 强制启动
• save_config - 保存配置
• debug_info - 调试信息
• debug_send - 调试发送
• debug_times - 调试时间""")

    async def _manage_clear(self, event: AstrMessageEvent):
        """清除记录"""
        try:
            # 清除运行时数据存储
            runtime_data.clear_all()

            # 保存清空后的持久化数据
            self.plugin.persistence_manager.save_persistent_data()
            self.plugin.task_manager.notify_wakeup()
            yield event.plain_result("✅ 已清除所有用户信息和发送时间记录")
        except Exception as e:
            yield event.plain_result(f"❌ 清除失败: {e}")

    async def _manage_task_status(self, event: AstrMessageEvent):
        """检查任务状态"""
        try:
            task_info = []
            current_task = self.plugin.task_manager.proactive_task
            if current_task:
                task_info.append(
                    f"✅ 定时任务: {'运行中' if not current_task.done() else '已完成'}"
                )
            else:
                task_info.append("❌ 当前没有定时任务")

            enabled = self.config.get("proactive_reply", {}).get("enabled", False)
            task_info.append(f"⚙️ 配置状态: {'✅ 启用' if enabled else '❌ 禁用'}")

            yield event.plain_result("\n".join(task_info))
        except Exception as e:
            yield event.plain_result(f"❌ 检查失败: {e}")

    async def _manage_force_stop(self, event: AstrMessageEvent):
        """强制停止"""
        try:
            await self.plugin.task_manager.force_stop_all_tasks()
            yield event.plain_result("✅ 已强制停止所有任务")
        except Exception as e:
            yield event.plain_result(f"❌ 停止失败: {e}")

    async def _manage_force_start(self, event: AstrMessageEvent):
        """强制启动"""
        try:
            await self.plugin.task_manager.stop_proactive_task()
            self.plugin.task_manager.proactive_task = asyncio.create_task(
                self.plugin.task_manager.proactive_message_loop()
            )
            yield event.plain_result("✅ 已强制启动任务")
        except Exception as e:
            yield event.plain_result(f"❌ 启动失败: {e}")

    async def _manage_save_config(self, event: AstrMessageEvent):
        """保存配置"""
        try:
            self.plugin.config_manager.save_config_safely()
            yield event.plain_result("✅ 配置保存成功")
        except Exception as e:
            yield event.plain_result(f"❌ 保存失败: {e}")

    async def _debug_info(self, event: AstrMessageEvent):
        """调试用户信息"""
        try:
            session_id = event.unified_msg_origin
            user_context = (
                self.plugin.user_info_manager.build_user_context_for_proactive(
                    session_id
                )
            )
            yield event.plain_result(f"🔧 调试信息:\n{user_context}")
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    async def _debug_send(self, event: AstrMessageEvent):
        """调试发送功能"""
        try:
            session_id = event.unified_msg_origin
            message, _ = await self.plugin.message_generator.generate_proactive_message(
                session_id
            )
            if message:
                yield event.plain_result(f"🔧 生成的消息:\n{message}")
            else:
                yield event.plain_result("❌ LLM生成失败")
        except Exception as e:
            yield event.plain_result(f"❌ 调试失败: {e}")

    async def _debug_times(self, event: AstrMessageEvent):
        """调试时间记录"""
        try:
            ai_times = runtime_data.ai_last_sent_times
            text = f"🔧 AI发送时间记录 (共{len(ai_times)}条):\n\n"
            for session, time in list(ai_times.items())[:10]:
                text += f"• {session[:30]}...: {time}\n"
            yield event.plain_result(text)
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")
