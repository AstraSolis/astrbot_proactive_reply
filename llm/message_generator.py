"""
消息生成器

负责使用LLM生成主动消息并处理消息发送
"""

import asyncio
import re
from datetime import datetime
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ..core.runtime_data import runtime_data
from .ai_schedule_analyzer import analyze_for_schedule


class MessageGenerator:
    """消息生成器类"""

    # 分割模式正则表达式
    SPLIT_MODE_PATTERNS = {
        "backslash": r"\\",
        "newline": r"\n",
        "comma": r",",
        "semicolon": r";",
        "punctuation": r"[,;。!?]",
    }

    def __init__(
        self,
        config: dict,
        context,
        prompt_builder,
        conversation_manager,
        user_info_manager,
    ):
        """初始化消息生成器

        Args:
            config: 配置字典
            context: AstrBot上下文对象
            prompt_builder: 提示词构建器
            conversation_manager: 会话管理器
            user_info_manager: 用户信息管理器
        """
        self.config = config
        self.context = context
        self.prompt_builder = prompt_builder
        self.conversation_manager = conversation_manager
        self.user_info_manager = user_info_manager

    def get_llm_provider(self):
        """获取LLM提供商

        Returns:
            LLM提供商对象，失败返回None
        """
        provider = self.context.get_using_provider()
        if not provider:
            logger.warning("LLM提供商不可用，无法生成主动消息")
        return provider

    def is_duplicate_message(self, session: str, message: str) -> bool:
        """检测消息是否与上次发送的重复

        Args:
            session: 会话ID
            message: 待检测的消息

        Returns:
            True 如果重复，False 如果不重复
        """
        last_message = runtime_data.session_last_proactive_message.get(session)
        if not last_message:
            return False

        # 完全相同
        if message == last_message:
            logger.debug("重复检测: 消息与上次完全相同")
            return True

        # 前50个字符相同（避免仅结尾略有不同的情况）
        check_length = 50
        if len(message) >= check_length and len(last_message) >= check_length:
            if message[:check_length] == last_message[:check_length]:
                logger.debug("重复检测: 消息前50字符与上次相同")
                return True

        return False

    def record_last_message(self, session: str, message: str):
        """记录会话最后发送的主动消息

        Args:
            session: 会话ID
            message: 发送的消息
        """
        runtime_data.session_last_proactive_message[session] = message

    async def generate_proactive_message_with_retry(
        self, session: str, max_retries: int = 3, override_prompt: str = None
    ) -> tuple:
        """生成主动消息，带重复检测和重试

        Args:
            session: 会话ID
            max_retries: 最大重试次数

        Returns:
            元组 (生成的消息, 使用的主动对话提示词)，失败返回 (None, None)
        """
        # 检查是否启用重复检测
        proactive_config = self.config.get("proactive_reply", {})
        duplicate_detection_enabled = proactive_config.get(
            "duplicate_detection_enabled", True
        )

        message = None
        final_prompt = None
        for attempt in range(max_retries + 1):
            message, final_prompt = await self.generate_proactive_message(
                session, override_prompt
            )
            if not message:
                return None, None

            # 如果未启用重复检测，直接返回
            if not duplicate_detection_enabled:
                return message, final_prompt

            # 检测重复
            if not self.is_duplicate_message(session, message):
                return message, final_prompt

            # 重复了，记录日志
            if attempt < max_retries:
                logger.warning(
                    f"🔄 检测到重复消息，重新生成 ({attempt + 1}/{max_retries})"
                )
            else:
                logger.warning("⚠️ 多次重试后仍为重复消息，使用当前消息")

        return message, final_prompt

    async def generate_proactive_message(
        self, session: str, override_prompt: str = None
    ) -> tuple:
        """使用LLM生成主动消息内容

        Args:
            session: 会话ID

        Returns:
            元组 (生成的消息, 使用的主动对话提示词)，失败返回 (None, None)
        """
        try:
            # 检查LLM是否可用
            provider = self.get_llm_provider()
            if not provider:
                return None, None

            # 获取并处理主动对话提示词
            if override_prompt:
                final_prompt = override_prompt
                # 简单替换占位符（保持一致性）
                final_prompt = self.prompt_builder.replace_placeholders(
                    final_prompt,
                    session,
                    self.config,
                    self.user_info_manager.build_user_context_for_proactive,
                )
            else:
                final_prompt = self.prompt_builder.get_proactive_prompt(
                    session, self.user_info_manager.build_user_context_for_proactive
                )

            if not final_prompt:
                return None, None

            # 获取人格系统提示词
            base_system_prompt = await self.prompt_builder.get_persona_system_prompt(
                session
            )

            # 获取历史记录（如果启用）
            contexts = []
            proactive_config = self.config.get("proactive_reply", {})

            if proactive_config.get("include_history_enabled", False):
                history_count = proactive_config.get("history_message_count", 10)
                history_count = max(1, min(50, history_count))
                contexts = await self.conversation_manager.get_conversation_history(
                    session, history_count
                )
                # 记录历史记录获取结果（使用 info 级别确保可见）
                logger.info(f"📚 主动消息生成: 获取到 {len(contexts)} 条历史记录")
                if contexts:
                    last_msg = contexts[-1]
                    content_preview = last_msg.get("content", "")[:80]
                    logger.info(
                        f"📝 最后一条历史: [{last_msg.get('role')}] {content_preview}"
                    )
            else:
                logger.info("📚 主动消息生成: 历史记录功能未启用")

            # 构建历史记录引导提示词
            history_guidance = ""
            if proactive_config.get("include_history_enabled", False) and contexts:
                history_guidance = "\n\n--- 上下文说明 ---\n你可以参考上述对话历史来生成更自然和连贯的回复。"

            # 构建组合系统提示词
            combined_system_prompt = self.prompt_builder.build_combined_system_prompt(
                base_system_prompt,
                final_prompt,
                history_guidance,
                session,
                self.user_info_manager.build_user_context_for_proactive,
            )

            # 调用LLM生成主动消息
            logger.debug(f"调用LLM生成主动消息, contexts数量: {len(contexts)}")
            llm_response = await provider.text_chat(
                prompt="[请根据上述指令生成回复]",
                session_id=None,
                contexts=contexts,
                image_urls=[],
                func_tool=None,
                system_prompt=combined_system_prompt,
            )

            if llm_response and llm_response.role == "assistant":
                generated_message = llm_response.completion_text
                if generated_message:
                    generated_message = generated_message.strip()
                    logger.info("LLM生成主动消息成功")
                    return generated_message, final_prompt
                else:
                    logger.warning("LLM返回了空消息")
                    return None, None
            else:
                logger.warning(f"LLM响应异常: {llm_response}")
                return None, None

        except Exception as e:
            logger.error(f"使用LLM生成主动消息失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            raise

    async def send_proactive_message(
        self, session: str, override_prompt: str = None
    ) -> dict | None:
        """向指定会话发送主动消息

        Args:
            session: 会话ID

        Returns:
            AI 自主调度信息 {"delay_minutes": int, "follow_up_prompt": str, "fire_time": str}
            或 None（无调度）

        Raises:
            RuntimeError: 消息生成失败时抛出
            Exception: 发送过程中的其他异常会向上传播
        """
        try:
            # 使用带重复检测的LLM生成主动消息
            (
                message,
                proactive_prompt_used,
            ) = await self.generate_proactive_message_with_retry(
                session, override_prompt=override_prompt
            )

            if not message:
                raise RuntimeError(f"无法为会话 {session} 生成主动消息")

            original_message = message  # 保存原始消息用于历史记录

            # 记录本次发送的消息（用于下次重复检测）
            self.record_last_message(session, original_message)

            # 处理消息分割和发送
            await self._send_message_with_split(
                session, message, original_message, proactive_prompt_used
            )

            # AI 自主调度分析（发送后异步执行，不影响发送本身）
            schedule_result = await self.analyze_message_for_schedule(
                session, original_message
            )
            return schedule_result

        except Exception as e:
            logger.error(f"❌ 向会话 {session} 发送主动消息时发生错误: {e}")
            raise

    async def analyze_message_for_schedule(
        self, session: str, message: str
    ) -> dict | None:
        """分析 AI 消息是否包含时间约定，发起二次 LLM 调用

        Args:
            session: 会话ID
            message: AI 生成的消息

        Returns:
            调度信息 dict 或 None
        """
        ai_schedule_config = self.config.get("ai_schedule", {})
        if not ai_schedule_config.get("enabled", False):
            return None

        provider = self.get_llm_provider()
        if not provider:
            return None

        # 获取对话历史作为分析上下文
        proactive_config = self.config.get("proactive_reply", {})
        contexts = []
        if proactive_config.get("include_history_enabled", False):
            history_count = proactive_config.get("history_message_count", 10)
            history_count = max(1, min(50, history_count))
            contexts = await self.conversation_manager.get_conversation_history(
                session, history_count
            )

        # 获取自定义分析提示词
        analysis_prompt = ai_schedule_config.get("analysis_prompt", "")

        # 当前时间
        time_format = self.config.get("user_info", {}).get(
            "time_format", "%Y-%m-%d %H:%M:%S"
        )
        current_time_str = datetime.now().strftime(time_format)

        return await analyze_for_schedule(
            provider=provider,
            ai_message=message,
            contexts=contexts,
            analysis_prompt=analysis_prompt,
            current_time_str=current_time_str,
        )

    async def _send_message_with_split(
        self,
        session: str,
        message: str,
        original_message: str,
        proactive_prompt_used: str = None,
    ):
        """处理消息分割和发送

        Args:
            session: 会话ID
            message: 待发送的消息
            original_message: 原始消息（用于历史记录）
            proactive_prompt_used: 本次使用的主动对话提示词
        """
        try:
            split_config = self.config.get("message_split", {})
            split_enabled = split_config.get("enabled", True)

            if split_enabled:
                await self._send_split_message(
                    session, message, original_message, proactive_prompt_used
                )
            else:
                await self._send_single_message(session, message, proactive_prompt_used)

        except Exception as e:
            logger.error(f"❌ 发送消息时发生错误: {e}")
            import traceback

            logger.error(f"发送错误详情: {traceback.format_exc()}")

    async def _send_split_message(
        self,
        session: str,
        message: str,
        original_message: str,
        proactive_prompt_used: str = None,
    ):
        """发送分割后的消息

        Args:
            session: 会话ID
            message: 待分割和发送的消息
            original_message: 原始消息
            proactive_prompt_used: 本次使用的主动对话提示词
        """
        split_config = self.config.get("message_split", {})
        split_mode = split_config.get("mode", "backslash")

        # 确定使用的正则表达式
        if split_mode == "custom":
            split_pattern = split_config.get("custom_pattern", "")
            if not split_pattern:
                logger.warning("custom模式下未配置正则表达式,使用默认backslash模式")
                split_pattern = self.SPLIT_MODE_PATTERNS["backslash"]
                split_mode = "backslash"
        else:
            split_pattern = self.SPLIT_MODE_PATTERNS.get(
                split_mode, self.SPLIT_MODE_PATTERNS["backslash"]
            )

        try:
            # 使用正则表达式分割
            message_parts = re.split(split_pattern, message)
            message_parts = [part.strip() for part in message_parts if part.strip()]

            if len(message_parts) > 1:
                # 分割成多个片段
                mode_display = (
                    f"{split_mode}模式"
                    if split_mode != "custom"
                    else f"自定义模式(/{split_pattern}/)"
                )
                logger.info(f"📨 使用{mode_display}分割消息,共 {len(message_parts)} 条")

                delay_ms = split_config.get("delay_ms", 500)
                delay_seconds = delay_ms / 1000.0

                sent_count = 0
                for i, part in enumerate(message_parts, 1):
                    try:
                        message_chain = MessageChain().message(part)
                        success = await self.context.send_message(
                            session, message_chain
                        )

                        if success:
                            sent_count += 1
                            logger.debug(
                                f"  ✅ 已发送第 {i}/{len(message_parts)} 条消息"
                            )
                            if i < len(message_parts):
                                await asyncio.sleep(delay_seconds)
                        else:
                            logger.warning(
                                f"  ⚠️ 第 {i}/{len(message_parts)} 条消息发送失败"
                            )

                    except Exception as part_error:
                        logger.error(
                            f"  ❌ 发送第 {i}/{len(message_parts)} 条消息时出错: {part_error}"
                        )

                if sent_count > 0:
                    self.user_info_manager.record_sent_time(session)
                    await self.conversation_manager.add_message_to_conversation_history(
                        session,
                        original_message,
                        proactive_prompt_used=proactive_prompt_used,
                        build_user_context_func=self.user_info_manager.build_user_context_for_proactive,
                    )
                    logger.info(
                        f"✅ 成功发送主动消息({sent_count}/{len(message_parts)} 条)"
                    )
                else:
                    logger.warning("⚠️ 所有消息片段都发送失败")
            else:
                # 没有被分割
                await self._send_single_message(session, message, proactive_prompt_used)

        except re.error as e:
            logger.error(
                f"❌ 正则表达式错误: {e}, 模式: {split_mode}, 表达式: {split_pattern}"
            )
            logger.error("将使用原始消息,不进行分割")
            await self._send_single_message(session, message, proactive_prompt_used)

    async def _send_single_message(
        self, session: str, message: str, proactive_prompt_used: str = None
    ):
        """发送单条消息

        Args:
            session: 会话ID
            message: 消息内容
            proactive_prompt_used: 本次使用的主动对话提示词
        """
        message_chain = MessageChain().message(message)
        success = await self.context.send_message(session, message_chain)

        if success:
            self.user_info_manager.record_sent_time(session)
            await self.conversation_manager.add_message_to_conversation_history(
                session,
                message,
                proactive_prompt_used=proactive_prompt_used,
                build_user_context_func=self.user_info_manager.build_user_context_for_proactive,
            )
            logger.info("✅ 成功发送主动消息")
        else:
            logger.warning("⚠️ 主动消息发送失败，可能是会话不存在或平台不支持")
