"""
命令处理器 - 完整版

包含所有原始main.py中的命令功能
"""

import asyncio
import datetime
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class CommandHandlers:
    """集中的命令处理器 - 完整实现所有命令"""

    def __init__(self, plugin):
        """初始化命令处理器

        Args:
            plugin: 主插件实例，包含所有管理器
        """
        self.plugin = plugin
        self.config = plugin.config
        self.context = plugin.context

    # ==================== 状态命令 ====================

    async def status(self, event: AstrMessageEvent):
        """查看插件状态

        显示插件的详细运行状态，包括：
        - 当前会话信息和在列表中的状态
        - 用户信息附加功能配置
        - 智能主动发送功能详细配置
        - LLM提供商可用性
        - 定时模式、发送间隔、活跃时间等
        - 已记录的会话数和发送记录数
        """
        try:
            user_config = self.config.get("user_info", {})
            proactive_config = self.config.get("proactive_reply", {})

            sessions_data = proactive_config.get("sessions", [])
            from ..utils.parsers import parse_sessions_list

            sessions = parse_sessions_list(sessions_data)
            session_count = len(sessions)

            # 获取用户信息记录数量
            session_user_info = proactive_config.get("session_user_info", {})
            user_info_count = len(session_user_info)

            # 获取发送时间记录数量
            ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})
            ai_sent_times_count = len(ai_last_sent_times)

            # 检查LLM状态
            provider = self.context.get_using_provider()
            llm_available = provider is not None

            # 检查当前会话状态
            current_session = event.unified_msg_origin
            is_current_in_list = current_session in sessions

            status_text = f"""📊 主动回复插件状态

📍 当前会话：
  - 会话ID：{current_session[:50]}{"..." if len(current_session) > 50 else ""}
  - 发送状态：{"✅ 已在发送列表中" if is_current_in_list else "❌ 未在发送列表中"}
  - 操作提示：{"使用 /proactive remove_session 移除" if is_current_in_list else "使用 /proactive add_session 添加"}

🔧 用户信息附加功能：✅ 已启用
  - 时间格式：{user_config.get("time_format", "%Y-%m-%d %H:%M:%S")}
  - 已记录用户信息：{user_info_count} 个会话

🤖 智能主动发送功能：{"✅ 已启用" if proactive_config.get("enabled", False) else "❌ 已禁用"}
  - LLM提供商：{"✅ 可用" if llm_available else "❌ 不可用"}
  - 时间模式：{proactive_config.get("timing_mode", "fixed_interval")}
  - 发送间隔：{proactive_config.get("interval_minutes", 60)} 分钟
  - 活跃时间：{proactive_config.get("active_hours", "9:00-22:00")}
  - 配置会话数：{session_count}
  - AI发送记录数：{ai_sent_times_count}

💡 使用 /proactive help 查看更多指令"""
            yield event.plain_result(status_text)
        except Exception as e:
            logger.error(f"查询状态失败: {e}")
            yield event.plain_result(f"查询状态失败: {e}")

    # ==================== 会话管理命令 ====================

    async def add_session(self, event: AstrMessageEvent):
        """添加当前会话到定时列表"""
        try:
            session_id = event.unified_msg_origin
            sessions = self.config.get("proactive_reply", {}).get("sessions", [])

            if session_id in sessions:
                yield event.plain_result("当前会话已在定时发送列表中")
            else:
                sessions.append(session_id)
                if "proactive_reply" not in self.config:
                    self.config["proactive_reply"] = {}
                self.config["proactive_reply"]["sessions"] = sessions
                self.plugin.config_manager.save_config_safely()
                yield event.plain_result(
                    f"✅ 已添加会话到定时发送列表\n会话ID: {session_id}"
                )
        except Exception as e:
            logger.error(f"添加会话失败: {e}")
            yield event.plain_result(f"添加会话失败: {e}")

    async def remove_session(self, event: AstrMessageEvent):
        """从定时列表移除当前会话"""
        try:
            session_id = event.unified_msg_origin
            sessions = self.config.get("proactive_reply", {}).get("sessions", [])

            if session_id in sessions:
                sessions.remove(session_id)
                self.config["proactive_reply"]["sessions"] = sessions
                self.plugin.config_manager.save_config_safely()
                yield event.plain_result("✅ 已从定时发送列表移除当前会话")
            else:
                yield event.plain_result("当前会话不在定时发送列表中")
        except Exception as e:
            logger.error(f"移除会话失败: {e}")
            yield event.plain_result(f"移除会话失败: {e}")

    # ==================== 测试命令 ====================

    async def test_proactive(self, event: AstrMessageEvent):
        """测试功能 - 支持多种测试类型

        可用的测试类型：
        - basic: 基础测试发送（默认）- 测试向当前会话发送主动消息
        - llm: 测试LLM请求 - 检查LLM提供商是否可用
        - generation: 测试LLM生成主动消息 - 测试完整的消息生成流程
        - prompt: 测试系统提示词构建 - 查看构建的提示词内容
        - placeholders: 测试占位符替换 - 验证占位符替换功能
        - history: 测试对话历史记录 - 查看对话历史获取功能
        - save: 测试对话保存功能 - 验证对话保存机制

        使用方法: /proactive test [类型]
        例如: /proactive test generation
        """
        message_parts = event.message_str.strip().split()
        test_type = message_parts[2] if len(message_parts) > 2 else ""

        if test_type == "basic":
            async for result in self._test_basic(event):
                yield result
        elif test_type == "llm":
            async for result in self._test_llm(event):
                yield result
        elif test_type == "generation":
            async for result in self._test_generation(event):
                yield result
        elif test_type == "prompt":
            async for result in self._test_prompt(event):
                yield result
        elif test_type == "placeholders":
            async for result in self._test_placeholders(event):
                yield result
        elif test_type == "history":
            async for result in self._test_history(event):
                yield result
        elif test_type == "save":
            async for result in self._test_save_conversation(event):
                yield result
        else:
            help_text = """可用的测试命令:
-  `/proactive test basic` - 测试基本发送功能
- `/proactive test llm` - 测试LLM连接
- `/proactive test generation` - 测试LLM生成
- `/proactive test prompt` - 测试提示词构建
- `/proactive test placeholders` - 测试占位符替换
- `/proactive test history` - 测试对话历史
- `/proactive test save` - 测试对话保存"""
            yield event.plain_result(help_text)

    async def _test_basic(self, event: AstrMessageEvent):
        """基础测试发送"""
        yield event.plain_result("⏳ 正在测试基本发送功能...")
        try:
            session_id = event.unified_msg_origin
            await self.plugin.message_generator.send_proactive_message(session_id)
            yield event.plain_result("✅ 测试完成")
        except Exception as e:
            logger.error(f"测试失败: {e}")
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_llm(self, event: AstrMessageEvent):
        """测试LLM连接"""
        yield event.plain_result("⏳ 正在测试LLM请求...")
        try:
            provider = self.plugin.message_generator.get_llm_provider()
            if provider:
                yield event.plain_result("✅ LLM提供商可用")
            else:
                yield event.plain_result("❌ LLM提供商不可用")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_generation(self, event: AstrMessageEvent):
        """测试LLM生成"""
        yield event.plain_result("⏳ 正在测试LLM生成功能...")
        try:
            session_id = event.unified_msg_origin
            message = await self.plugin.message_generator.generate_proactive_message(
                session_id
            )
            if message:
                yield event.plain_result(f"✅ 生成成功:\n{message}")
            else:
                yield event.plain_result("❌ LLM生成失败")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_prompt(self, event: AstrMessageEvent):
        """测试提示词构建 - 显示完整的组合系统提示词"""
        yield event.plain_result("⏳ 正在测试提示词构建...")
        try:
            session_id = event.unified_msg_origin
            
            # 1. 获取主动对话提示词
            final_prompt = self.plugin.prompt_builder.get_proactive_prompt(
                session_id,
                self.plugin.user_info_manager.build_user_context_for_proactive,
            )
            if not final_prompt:
                yield event.plain_result("❌ 主动对话提示词为空")
                return
            
            # 2. 获取人格系统提示词
            base_system_prompt = await self.plugin.prompt_builder.get_persona_system_prompt(
                session_id
            )
            
            # 3. 获取历史记录（如果启用）
            contexts = []
            proactive_config = self.config.get("proactive_reply", {})
            
            if proactive_config.get("include_history_enabled", False):
                history_count = proactive_config.get("history_message_count", 10)
                history_count = max(1, min(50, history_count))
                contexts = await self.plugin.conversation_manager.get_conversation_history(
                    session_id, history_count
                )
            
            # 4. 构建历史记录引导提示词
            history_guidance = ""
            if proactive_config.get("include_history_enabled", False) and contexts:
                history_guidance = "\n\n--- 上下文说明 ---\n你可以参考上述对话历史来生成更自然和连贯的回复。"
            
            # 5. 构建完整的组合系统提示词
            combined_system_prompt = self.plugin.prompt_builder.build_combined_system_prompt(
                base_system_prompt, final_prompt, history_guidance
            )
            
            # 6. 构建详细的输出信息
            result_text = "✅ 提示词构建成功!\n\n"
            result_text += f"📊 统计信息:\n"
            result_text += f"- 人格提示词长度: {len(base_system_prompt)} 字符\n"
            result_text += f"- 主动对话提示词长度: {len(final_prompt)} 字符\n"
            result_text += f"- 历史记录条数: {len(contexts)} 条\n"
            result_text += f"- 完整系统提示词长度: {len(combined_system_prompt)} 字符\n\n"
            result_text += f"{'='*50}\n"
            result_text += f"📝 完整系统提示词预览:\n"
            result_text += f"{'='*50}\n"
            result_text += combined_system_prompt[:1000]
            
            if len(combined_system_prompt) > 1000:
                result_text += f"\n\n... (已省略 {len(combined_system_prompt) - 1000} 字符)"
            
            yield event.plain_result(result_text)
            
        except Exception as e:
            logger.error(f"测试提示词构建失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_placeholders(self, event: AstrMessageEvent):
        """测试占位符替换"""
        try:
            session_id = event.unified_msg_origin
            test_prompt = """测试占位符:
- 当前时间:{current_time}
- AI上次发送:{ai_last_sent_time}
- 用户昵称:{username}"""

            from ..llm.placeholder_utils import replace_placeholders

            result = replace_placeholders(
                test_prompt,
                session_id,
                self.config,
                self.plugin.user_info_manager.build_user_context_for_proactive,
            )
            yield event.plain_result(f"✅ 占位符替换测试:\n{result}")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_history(self, event: AstrMessageEvent):
        """测试对话历史"""
        try:
            session_id = event.unified_msg_origin
            history = await self.plugin.conversation_manager.get_conversation_history(
                session_id, 5
            )
            yield event.plain_result(f"✅ 历史记录: {len(history)} 条")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_save_conversation(self, event: AstrMessageEvent):
        """测试对话保存"""
        yield event.plain_result("⏳ 正在测试对话保存功能...")
        try:
            session_id = event.unified_msg_origin
            test_msg = f"测试消息 {datetime.datetime.now().strftime('%H:%M:%S')}"
            await self.plugin.conversation_manager.add_message_to_conversation_history(
                session_id, test_msg
            )
            yield event.plain_result("✅ 对话保存测试完成")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    # ==================== 显示命令 ====================

    async def show_info(self, event: AstrMessageEvent):
        """显示信息 - 支持多种显示类型

        可用的显示类型：
        - prompt: 显示当前配置下会输入给LLM的组合话本（主动对话提示词列表）
        - users: 显示已记录的用户信息（包括昵称、平台等）

        使用方法: /proactive show [类型]
        例如: /proactive show prompt
        """
        message_parts = event.message_str.strip().split()
        show_type = message_parts[2] if len(message_parts) > 2 else ""

        if show_type == "prompt":
            prompts = self.config.get("proactive_reply", {}).get(
                "proactive_prompt_list", []
            )
            text = f"📝 主动对话提示词列表 (共{len(prompts)}条):\n\n"
            for i, prompt in enumerate(prompts, 1):
                text += (
                    f"{i}. {prompt[:100]}...\n"
                    if len(str(prompt)) > 100
                    else f"{i}. {prompt}\n"
                )
            yield event.plain_result(text)

        elif show_type == "users":
            user_info = self.config.get("proactive_reply", {}).get(
                "session_user_info", {}
            )
            text = f"👥 已记录用户信息 (共{len(user_info)}个):\n\n"
            for session, info in list(user_info.items())[:10]:
                text += f"• {info.get('username', '未知')} ({info.get('platform', '未知')})\n"
            yield event.plain_result(text)

        else:
            yield event.plain_result(
                "可用的显示命令:\n- `/proactive show prompt` - 显示提示词\n- `/proactive show users` - 显示用户信息"
            )

    # ==================== 管理命令 ====================

    async def manage_functions(self, event: AstrMessageEvent):
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
        message_parts = event.message_str.strip().split()
        manage_type = message_parts[2] if len(message_parts) > 2 else ""

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
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}

            self.config["proactive_reply"]["session_user_info"] = {}
            self.config["proactive_reply"]["last_sent_times"] = {}
            self.config["proactive_reply"]["ai_last_sent_times"] = {}

            self.plugin.config_manager.save_config_safely()
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
            message = await self.plugin.message_generator.generate_proactive_message(
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
            ai_times = self.config.get("proactive_reply", {}).get(
                "ai_last_sent_times", {}
            )
            text = f"🔧 AI发送时间记录 (共{len(ai_times)}条):\n\n"
            for session, time in list(ai_times.items())[:10]:
                text += f"• {session[:30]}...: {time}\n"
            yield event.plain_result(text)
        except Exception as e:
            yield event.plain_result(f"❌ 获取失败: {e}")

    # ==================== 通用命令 ====================

    async def help_command(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """🤖 AstrBot 主动回复插件

基础命令:
- `/proactive status` - 查看状态
- `/proactive add_session` - 添加会话
- `/proactive remove_session` - 移除会话
- `/proactive restart` - 重启任务

测试命令:
- `/proactive test [类型]` - 测试功能
  类型: basic, llm, generation, prompt, placeholders, history, save

显示命令:
- `/proactive show [类型]` - 显示信息
  类型: prompt, users

管理命令:
- `/proactive manage [操作]` - 管理功能
  操作: clear, task_status, force_stop, force_start, save_config
  调试: debug_info, debug_send, debug_times

💡 详细配置请在 AstrBot 配置面板中修改"""
        yield event.plain_result(help_text)

    async def restart(self, event: AstrMessageEvent):
        """重启定时任务"""
        yield event.plain_result("⏳ 正在重启定时任务...")
        try:
            await self.plugin.task_manager.restart_proactive_task()
            yield event.plain_result("✅ 定时任务已重启")
        except Exception as e:
            yield event.plain_result(f"❌ 重启失败: {e}")

    async def show_config(self, event: AstrMessageEvent):
        """显示配置"""
        base_prompt = self.plugin.prompt_builder.get_base_system_prompt()
        text = f"📋 当前配置:\n\n基础人格提示词:\n{base_prompt[:200]}..."
        yield event.plain_result(text)
