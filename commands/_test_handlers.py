"""测试与调试命令"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from ..constants import MAX_HISTORY_MESSAGE_COUNT, MIN_HISTORY_MESSAGE_COUNT
from ..core.runtime_data import runtime_data


class TestHandlersMixin:
    """测试与调试命令"""

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
            logger.error(f"心念 | ❌ 测试失败: {e}")
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
                self.context.get_config() if self.context else None,
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
                    history_count = max(
                        MIN_HISTORY_MESSAGE_COUNT,
                        min(MAX_HISTORY_MESSAGE_COUNT, history_count),
                    )
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
                    history_guidance,
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
  [历史引导语]

📨 本轮用户提示词：
{final_prompt}

📊 统计信息:
- 可用提示词数量: {len(prompt_list)}
- 人格提示词长度: {len(base_system_prompt)} 字符
- 主动对话提示词长度: {len(final_prompt)} 字符
- 历史记录条数: {len(contexts)} 条
- 最终系统提示词长度: {len(combined_system_prompt)} 字符

💡 说明:
- 系统提示词包含: 人格 + 固定时间指导 + 历史引导
- 主动对话指令作为本轮用户提示词传递，避免动态占位符污染 system_prompt
- 历史记录通过 contexts 参数传递给 LLM，而非嵌入系统提示词"""

            yield event.plain_result(result_text)

        except Exception as e:
            logger.error(f"心念 | ❌ 测试提示词构建失败: {e}")
            import traceback

            logger.error(f"心念 | 详细错误: {traceback.format_exc()}")
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
            from ..utils.time_utils import get_tz
            import datetime

            astrbot_cfg = self.context.get_config() if self.context else None
            resolved_tz = get_tz(self.config, astrbot_cfg)
            tz_display = str(resolved_tz) if resolved_tz is not None else "系统本地时区"
            tz_now = (
                datetime.datetime.now(tz=resolved_tz).strftime("%Y-%m-%d %H:%M:%S")
                if resolved_tz
                else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            result = replace_placeholders(
                test_prompt,
                session_id,
                self.config,
                self.plugin.user_info_manager.build_user_context_for_proactive,
                astrbot_cfg,
            )
            yield event.plain_result(
                f"✅ 占位符替换测试:\n[有效时区: {tz_display} | 当前时区时间: {tz_now}]\n{result}"
            )
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
            history_count = max(
                MIN_HISTORY_MESSAGE_COUNT,
                min(MAX_HISTORY_MESSAGE_COUNT, history_count),
            )  # 限制范围 1-50

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
            logger.error(f"心念 | ❌ 测试对话历史失败: {e}")
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_save_conversation(self, event: AstrMessageEvent):
        """测试对话保存"""
        yield event.plain_result("⏳ 正在测试对话保存功能...")
        try:
            session_id = event.unified_msg_origin
            from ..utils.time_utils import get_now

            test_msg = f"测试消息 {get_now(self.config, self.context.get_config() if self.context else None).strftime('%H:%M:%S')}"
            await self.plugin.conversation_manager.add_message_to_conversation_history(
                session_id, test_msg
            )
            yield event.plain_result("✅ 对话保存测试完成")
        except Exception as e:
            yield event.plain_result(f"❌ 测试失败: {e}")

    async def _test_schedule(self, event: AstrMessageEvent):
        """测试 AI 调度任务——注入一个 1 分钟后到期的任务并显示当前状态"""
        import uuid
        from datetime import timedelta
        from ..utils.time_utils import get_now

        session_id = event.unified_msg_origin
        try:
            # 1. 注入一个 1 分钟后到期的测试任务
            _now = get_now(
                self.config, self.context.get_config() if self.context else None
            ).replace(tzinfo=None)
            fire_dt = _now + timedelta(minutes=1)
            fire_time_str = fire_dt.strftime("%Y-%m-%d %H:%M:%S")
            task = {
                "task_id": str(uuid.uuid4()),
                "delay_minutes": 1,
                "fire_time": fire_time_str,
                "follow_up_prompt": "[测试] 这是通过 /proactive test schedule 注入的测试跟进消息，请据此发送一条简短的问候。",
                "created_at": _now.strftime("%Y-%m-%d %H:%M:%S"),
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
            logger.error(f"心念 | ❌ 测试调度失败: {e}")
            import traceback

            logger.error(f"心念 | {traceback.format_exc()}")
            yield event.plain_result(f"❌ 测试失败: {e}")
