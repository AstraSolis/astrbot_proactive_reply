"""
消息生成器

负责使用LLM生成主动消息并处理消息发送
"""

import asyncio
import re
from astrbot.api import logger
from astrbot.api.event import MessageChain
from ..utils.formatters import ensure_string_encoding


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

    async def generate_proactive_message(self, session: str) -> str:
        """使用LLM生成主动消息内容

        Args:
            session: 会话ID

        Returns:
            生成的消息，失败返回None
        """
        try:
            # 检查LLM是否可用
            provider = self.get_llm_provider()
            if not provider:
                return None

            # 获取并处理主动对话提示词
            final_prompt = self.prompt_builder.get_proactive_prompt(
                session, self.user_info_manager.build_user_context_for_proactive
            )
            if not final_prompt:
                return None

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

            # 构建历史记录引导提示词
            history_guidance = ""
            if proactive_config.get("include_history_enabled", False) and contexts:
                history_guidance = "\n\n--- 上下文说明 ---\n你可以参考上述对话历史来生成更自然和连贯的回复。"

            # 构建组合系统提示词
            combined_system_prompt = self.prompt_builder.build_combined_system_prompt(
                base_system_prompt, final_prompt, history_guidance
            )

            # 调用LLM生成主动消息
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
                    generated_message = ensure_string_encoding(
                        generated_message.strip()
                    )
                    logger.info("LLM生成主动消息成功")
                    return generated_message
                else:
                    logger.warning("LLM返回了空消息")
                    return None
            else:
                logger.warning(f"LLM响应异常: {llm_response}")
                return None

        except Exception as e:
            logger.error(f"使用LLM生成主动消息失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None

    async def send_proactive_message(self, session: str):
        """向指定会话发送主动消息

        Args:
            session: 会话ID
        """
        try:
            session = ensure_string_encoding(session)

            # 使用LLM生成主动消息
            message = await self.generate_proactive_message(session)

            if not message:
                logger.warning(f"无法为会话 {session} 生成主动消息")
                return

            message = ensure_string_encoding(message)
            original_message = message  # 保存原始消息用于历史记录

            # 处理消息分割和发送
            await self._send_message_with_split(session, message, original_message)

        except Exception as e:
            logger.error(f"❌ 向会话 {session} 发送主动消息时发生错误: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")

    async def _send_message_with_split(
        self, session: str, message: str, original_message: str
    ):
        """处理消息分割和发送

        Args:
            session: 会话ID
            message: 待发送的消息
            original_message: 原始消息（用于历史记录）
        """
        try:
            proactive_config = self.config.get("proactive_reply", {})
            split_enabled = proactive_config.get(
                "split_enabled", proactive_config.get("split_by_backslash", True)
            )

            if split_enabled:
                await self._send_split_message(session, message, original_message)
            else:
                await self._send_single_message(session, message)

        except Exception as e:
            logger.error(f"❌ 发送消息时发生错误: {e}")
            import traceback

            logger.error(f"发送错误详情: {traceback.format_exc()}")

    async def _send_split_message(
        self, session: str, message: str, original_message: str
    ):
        """发送分割后的消息

        Args:
            session: 会话ID
            message: 待分割和发送的消息
            original_message: 原始消息
        """
        proactive_config = self.config.get("proactive_reply", {})
        split_mode = proactive_config.get("split_mode", "backslash")

        # 确定使用的正则表达式
        if split_mode == "custom":
            split_pattern = proactive_config.get("custom_split_pattern", "")
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

                delay_ms = proactive_config.get("split_message_delay_ms", 500)
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
                        session, original_message
                    )
                    logger.info(
                        f"✅ 成功发送主动消息({sent_count}/{len(message_parts)} 条)"
                    )
                else:
                    logger.warning("⚠️ 所有消息片段都发送失败")
            else:
                # 没有被分割
                await self._send_single_message(session, message)

        except re.error as e:
            logger.error(
                f"❌ 正则表达式错误: {e}, 模式: {split_mode}, 表达式: {split_pattern}"
            )
            logger.error("将使用原始消息,不进行分割")
            await self._send_single_message(session, message)

    async def _send_single_message(self, session: str, message: str):
        """发送单条消息

        Args:
            session: 会话ID
            message: 消息内容
        """
        message_chain = MessageChain().message(message)
        success = await self.context.send_message(session, message_chain)

        if success:
            self.user_info_manager.record_sent_time(session)
            await self.conversation_manager.add_message_to_conversation_history(
                session, message
            )
            logger.info("✅ 成功发送主动消息")
        else:
            logger.warning("⚠️ 主动消息发送失败，可能是会话不存在或平台不支持")
