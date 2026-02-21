"""
命令处理器 - 完整版

包含所有原始main.py中的命令功能
"""

import asyncio
import datetime
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from ..core.runtime_data import runtime_data


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

    # ==================== 状态命令 ====================

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
  - AI发送记录数：{ai_sent_times_count}{next_fire_info}

💡 使用 /proactive help 查看更多指令"""
            yield event.plain_result(status_text)
        except Exception as e:
            logger.error(f"查询状态失败: {e}")
            yield event.plain_result(f"查询状态失败: {e}")

    # ==================== 会话管理命令 ====================

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
            logger.error(f"添加会话失败: {e}")
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
            logger.error(f"移除会话失败: {e}")
            yield event.plain_result(f"移除会话失败: {e}")

    # ==================== 测试命令 ====================

    async def test_proactive(self, event: AstrMessageEvent, test_type: str = ""):
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
        elif test_type == "schedule":
            async for result in self._test_schedule(event):
                yield result
        else:
            help_text = """可用的测试命令:
-  `/proactive test basic` - 测试基本发送功能
- `/proactive test llm` - 测试LLM连接
- `/proactive test generation` - 测试LLM生成
- `/proactive test prompt` - 测试提示词构建
- `/proactive test placeholders` - 测试占位符替换
- `/proactive test history` - 测试对话历史
- `/proactive test save` - 测试对话保存
- `/proactive test schedule` - 测试AI调度任务（注入+诊断）"""
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
            provider_id = await self.plugin.message_generator.get_provider_id(
                event.unified_msg_origin
            )
            if provider_id:
                yield event.plain_result(f"✅ LLM提供商可用 (ID: {provider_id})")
            else:
                yield event.plain_result("❌ LLM提供商不可用")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_generation(self, event: AstrMessageEvent):
        """测试LLM生成"""
        yield event.plain_result("⏳ 正在测试LLM生成功能...")
        try:
            session_id = event.unified_msg_origin
            message, _ = await self.plugin.message_generator.generate_proactive_message(
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
        yield event.plain_result("⏳ 正在构建提示词...")
        try:
            import random

            session_id = event.unified_msg_origin
            proactive_config = self.config.get("proactive_reply", {})

            # 1. 获取并选择提示词
            from ..utils.parsers import parse_prompt_list

            prompt_list_data = proactive_config.get("proactive_prompt_list", [])
            if not prompt_list_data:
                yield event.plain_result("❌ 未配置主动对话提示词列表")
                return

            prompt_list = parse_prompt_list(prompt_list_data)
            if not prompt_list:
                yield event.plain_result("❌ 主动对话提示词列表为空")
                return

            # 随机选择一个提示词进行演示
            selected_prompt = random.choice(prompt_list)

            # 2. 替换占位符
            from ..llm.placeholder_utils import replace_placeholders

            final_prompt = replace_placeholders(
                selected_prompt,
                session_id,
                self.config,
                self.plugin.user_info_manager.build_user_context_for_proactive,
            )

            # 3. 获取人格系统提示词
            base_system_prompt = (
                await self.plugin.prompt_builder.get_persona_system_prompt(session_id)
            )

            # 4. 获取历史记录（如果启用）- 与 message_generator.py 保持一致
            history_enabled = proactive_config.get("include_history_enabled", False)
            history_count = proactive_config.get("history_message_count", 10)
            history_info = ""
            history_preview = ""
            contexts = []

            if history_enabled:
                try:
                    history_count = max(1, min(50, history_count))
                    contexts = (
                        await self.plugin.conversation_manager.get_conversation_history(
                            session_id, history_count
                        )
                    )
                    if contexts:
                        history_preview = "\n".join(
                            [
                                f"  {ctx['role']}: {ctx['content'][:50]}..."
                                for ctx in contexts[-5:]
                            ]
                        )
                        history_info = f"✅ 已启用 (获取到{len(contexts)}条记录)"
                    else:
                        history_info = "✅ 已启用 (暂无历史记录)"
                except Exception as e:
                    history_info = f"✅ 已启用 (获取失败: {str(e)[:50]}...)"
            else:
                history_info = "❌ 未启用"

            # 5. 构建历史记录引导提示词 - 与 message_generator.py 保持一致
            history_guidance = ""
            if history_enabled and contexts:
                history_guidance = "\n\n--- 上下文说明 ---\n你可以参考上述对话历史来生成更自然和连贯的回复。"

            # 6. 使用 prompt_builder.build_combined_system_prompt 构建组合系统提示词
            # 这与实际 LLM 调用完全一致
            combined_system_prompt = (
                self.plugin.prompt_builder.build_combined_system_prompt(
                    base_system_prompt,
                    final_prompt,
                    history_guidance,
                    session_id,
                    self.plugin.user_info_manager.build_user_context_for_proactive,
                )
            )

            # 7. 获取时间增强提示词配置状态
            time_awareness_config = self.config.get("time_awareness", {})
            time_guidance_enabled = time_awareness_config.get(
                "time_guidance_enabled", True
            )
            time_guidance_prompt = time_awareness_config.get("time_guidance_prompt", "")
            time_guidance_info = "✅ 已启用" if time_guidance_enabled else "❌ 未启用"

            # 8. 构建详细的输出信息
            result_text = f"""🧪 系统提示词构建测试（与实际LLM调用一致）

📝 原始提示词：
{selected_prompt}

🔄 占位符替换后：
{final_prompt}

🤖 基础人格提示词：
{base_system_prompt[:200] + "..." if len(base_system_prompt) > 200 else base_system_prompt}

⏰ 时间感知增强提示词：
  - 状态: {time_guidance_info}
  - 内容预览: {time_guidance_prompt[:150] + "..." if len(time_guidance_prompt) > 150 else (time_guidance_prompt if time_guidance_prompt else "(使用默认值)")}

📚 历史记录配置：
  - 状态: {history_info}
  - 配置条数: {history_count} 条
  - 传递方式: contexts 参数（非系统提示词内嵌）
{f"  - 历史预览:{chr(10)}{history_preview}" if history_preview else ""}

📜 历史引导语：
{history_guidance if history_guidance else "(无 - 未启用或无历史记录)"}

🎭 最终组合系统提示词结构：
  [人格提示词 {len(base_system_prompt)}字符]
  {"[时间增强提示词 ~350字符]" if time_guidance_enabled else "[时间增强提示词 已禁用]"}
  [--- 主动对话指令 ---]
  [{final_prompt}]
  [历史引导语]

📊 统计信息:
- 可用提示词数量: {len(prompt_list)}
- 人格提示词长度: {len(base_system_prompt)} 字符
- 主动对话提示词长度: {len(final_prompt)} 字符
- 历史记录条数: {len(contexts)} 条
- 最终系统提示词长度: {len(combined_system_prompt)} 字符

💡 说明:
- 系统提示词包含: 人格 + 时间指导 + 主动对话指令 + 历史引导
- 历史记录通过 contexts 参数传递给 LLM，而非嵌入系统提示词"""

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
- 用户昵称: {username}
- 平台: {platform}
- 聊天类型: {chat_type}
- 当前时间: {current_time}
- 星期: {weekday}
- 用户上次发消息时间: {user_last_message_time}
- 用户上次发消息相对时间: {user_last_message_time_ago}
- AI上次发送时间: {ai_last_sent_time}
- 用户连续未回复次数: {unreplied_count}"""

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
        """测试对话历史 - 显示详细的历史记录内容"""
        try:
            session_id = event.unified_msg_origin
            proactive_config = self.config.get("proactive_reply", {})

            # 从配置读取历史记录条数
            history_enabled = proactive_config.get("include_history_enabled", False)
            history_count = proactive_config.get("history_message_count", 10)
            history_count = max(1, min(50, history_count))  # 限制范围 1-50

            history = await self.plugin.conversation_manager.get_conversation_history(
                session_id, history_count
            )

            # 构建详细的输出信息
            result_text = f"""🧪 对话历史记录测试

📊 配置信息:
  - 历史记录功能: {"✅ 已启用" if history_enabled else "❌ 未启用"}
  - 配置的历史条数: {history_count} 条
  - 实际获取条数: {len(history)} 条

📚 历史记录内容:"""

            if history:
                for i, ctx in enumerate(history, 1):
                    role = ctx.get("role", "未知")
                    content = ctx.get("content", "")
                    # 截断过长的内容
                    if len(content) > 100:
                        content = content[:100] + "..."
                    result_text += f"\n  {i}. [{role}]: {content}"
            else:
                result_text += "\n  (暂无历史记录)"

            result_text += "\n\n💡 提示: 历史记录用于主动消息生成时提供对话上下文"

            yield event.plain_result(result_text)
        except Exception as e:
            logger.error(f"测试对话历史失败: {e}")
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

    async def _test_schedule(self, event: AstrMessageEvent):
        """测试 AI 调度任务——注入一个 1 分钟后到期的任务并显示当前状态"""
        import uuid
        from datetime import datetime, timedelta

        session_id = event.unified_msg_origin
        try:
            # 1. 注入一个 1 分钟后到期的测试任务
            fire_dt = datetime.now() + timedelta(minutes=1)
            fire_time_str = fire_dt.strftime("%Y-%m-%d %H:%M:%S")
            task = {
                "task_id": str(uuid.uuid4()),
                "delay_minutes": 1,
                "fire_time": fire_time_str,
                "follow_up_prompt": "[测试] 这是通过 /proactive test schedule 注入的测试跟进消息，请据此发送一条简短的问候。",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.plugin.task_manager.apply_ai_schedule(session_id, task)

            # 2. 读取当前会话的 AI 任务列表供诊断
            ai_tasks = runtime_data.session_ai_scheduled.get(session_id, [])
            next_fire = self.plugin.task_manager.get_next_fire_info(session_id)

            task_list_text = ""
            for i, t in enumerate(ai_tasks, 1):
                task_list_text += (
                    f"  {i}. [{t.get('task_id', '无ID')[:8]}...] "
                    f"{t.get('fire_time', '?')} — {t.get('follow_up_prompt', '')[:30]}...\n"
                )

            yield event.plain_result(
                f"✅ 已注入测试 AI 调度任务\n"
                f"\n📋 当前会话调度列表 ({len(ai_tasks)} 个任务):\n{task_list_text}"
                f"\n⏱️ 下次触发时间: {next_fire}"
                f"\n\n💡 约 1 分钟后会话将收到 AI 调度消息。"
                f"若处于睡眠时段，任务将穿透发送并附带睡眠背景提示。"
            )
        except Exception as e:
            logger.error(f"测试调度失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            yield event.plain_result(f"❌ 测试失败: {e}")

    # ==================== 显示命令 ====================

    async def show_info(self, event: AstrMessageEvent, show_type: str = ""):
        """显示信息 - 支持多种显示类型

        可用的显示类型：
        - prompt: 显示当前配置下会输入给LLM的组合话本（主动对话提示词列表）
        - users: 显示已记录的用户信息（包括昵称、平台等）

        使用方法: /proactive show [类型]
        例如: /proactive show prompt
        """

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
            user_info = runtime_data.session_user_info
            text = f"👥 已记录用户信息 (共{len(user_info)}个):\n\n"
            for session, info in list(user_info.items())[:10]:
                text += f"• {info.get('username', '未知')} ({info.get('platform', '未知')})\n"
            yield event.plain_result(text)

        else:
            yield event.plain_result(
                "可用的显示命令:\n- `/proactive show prompt` - 显示提示词\n- `/proactive show users` - 显示用户信息"
            )

    # ==================== 管理命令 ====================

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

    # ==================== 通用命令 ====================

    async def help_command(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """🤖 AstrBot 主动回复插件

基础命令:
- `/proactive status` - 查看状态
- `/proactive config` - 查看配置
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
        """显示完整的插件配置"""
        try:
            user_config = self.config.get("user_info", {})
            proactive_config = self.config.get("proactive_reply", {})

            # 1. 用户信息配置
            config_text = "📋 插件完整配置\n\n"
            config_text += "=" * 50 + "\n"
            config_text += "👤 用户信息附加配置\n"
            config_text += "=" * 50 + "\n"
            config_text += (
                f"时间格式: {user_config.get('time_format', '%Y-%m-%d %H:%M:%S')}\n"
            )
            template = user_config.get(
                "template",
                "当前对话信息：\\n用户：{username}\\n时间：{time}\\n平台：{platform}（{chat_type}）\\n\\n",
            )
            config_text += (
                f"模板: {template[:100]}{'...' if len(template) > 100 else ''}\n"
            )
            config_text += "支持占位符: {username}, {user_id}, {time}, {current_time}, {platform}, {chat_type}, {user_last_message_time}, {user_last_message_time_ago}, {ai_last_sent_time}\n\n"

            # 2. 主动回复功能配置
            config_text += "=" * 50 + "\n"
            config_text += "🤖 主动回复功能配置\n"
            config_text += "=" * 50 + "\n"
            config_text += f"功能状态: {'✅ 已启用' if proactive_config.get('enabled', False) else '❌ 已禁用'}\n"
            config_text += (
                f"定时模式: {proactive_config.get('timing_mode', 'fixed_interval')}\n"
            )
            config_text += (
                f"发送间隔: {proactive_config.get('interval_minutes', 600)} 分钟\n"
            )
            config_text += f"睡眠时间: {self._get_sleep_time_status()}\n"
            config_text += f"随机延迟: {'✅ 已启用' if proactive_config.get('random_delay_enabled', False) else '❌ 未启用'}\n"

            if proactive_config.get("random_delay_enabled", False):
                config_text += f"  - 随机延迟范围: {proactive_config.get('min_random_minutes', 0)}-{proactive_config.get('max_random_minutes', 30)} 分钟\n"

            # 3. 历史记录配置
            config_text += f"\n对话历史记录: {'✅ 已启用' if proactive_config.get('include_history_enabled', False) else '❌ 未启用'}\n"
            if proactive_config.get("include_history_enabled", False):
                config_text += f"  - 历史记录条数: {proactive_config.get('history_message_count', 10)} 条\n"

            # 4. 消息分割配置
            split_config = self.config.get("message_split", {})
            config_text += f"\n消息分割功能: {'✅ 已启用' if split_config.get('enabled', True) else '❌ 未启用'}\n"
            if split_config.get("enabled", True):
                config_text += (
                    f"  - 分割模式: {split_config.get('mode', 'backslash')}\n"
                )
                config_text += (
                    f"  - 分割延迟: {split_config.get('delay_ms', 500)} 毫秒\n"
                )

            # 5. 会话和记录统计
            # 获取会话列表
            from ..utils.parsers import parse_sessions_list

            sessions_data = proactive_config.get("sessions", [])
            sessions = parse_sessions_list(sessions_data)

            config_text += "\n" + "=" * 50 + "\n"
            config_text += "📊 数据统计\n"
            config_text += "=" * 50 + "\n"
            config_text += f"配置的会话数: {len(sessions)}\n"
            config_text += f"记录的用户信息: {len(runtime_data.session_user_info)} 个\n"
            config_text += (
                f"AI发送时间记录: {len(runtime_data.ai_last_sent_times)} 条\n"
            )

            # 6. 提示词配置
            config_text += "\n" + "=" * 50 + "\n"
            config_text += "💬 提示词配置\n"
            config_text += "=" * 50 + "\n"

            # 获取基础人格提示词
            base_prompt = await self.plugin.prompt_builder.get_base_system_prompt()
            config_text += f"基础人格提示词长度: {len(base_prompt)} 字符\n"
            config_text += f"基础人格提示词预览:\n{base_prompt[:200]}{'...' if len(base_prompt) > 200 else ''}\n\n"

            # 主动对话提示词列表
            prompt_list = proactive_config.get("proactive_prompt_list", [])
            config_text += f"主动对话提示词数量: {len(prompt_list)} 条\n"

            # 默认人格
            default_persona = proactive_config.get("proactive_default_persona", "")
            if default_persona:
                config_text += f"\n插件默认人格长度: {len(default_persona)} 字符\n"

            config_text += "\n💡 使用 /proactive show prompt 查看所有主动对话提示词"

            yield event.plain_result(config_text)

        except Exception as e:
            logger.error(f"显示配置失败: {e}")
            yield event.plain_result(f"❌ 显示配置失败: {e}")
