"""
消息生成器

负责使用LLM生成主动消息并处理消息发送
"""

import asyncio
from datetime import datetime
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ..constants import (
    MAX_HISTORY_MESSAGE_COUNT,
    MAX_SCHEDULE_ANALYSIS_HISTORY_COUNT,
    MIN_HISTORY_MESSAGE_COUNT,
)
from ..core.runtime_data import runtime_data
from ..utils.time_utils import get_tz
from .ai_schedule_analyzer import analyze_for_schedule, contains_time_keywords
from .errors import (
    DuplicateMessageError,
    MessageDeliveryError,
    MessageGenerationError,
)
from .message_splitter import MessageSplitter


class MessageGenerator:
    """消息生成器类"""

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

        # 消息分割器（封装分段模式与正则保护）
        self.message_splitter = MessageSplitter(config)

    def _get_astrbot_config(self):
        """安全获取 AstrBot 全局配置"""
        try:
            return self.context.get_config()
        except Exception:
            return None

    async def get_provider_id(self, session: str) -> str | None:
        """获取LLM提供商ID

        Args:
            session: 会话ID (unified_msg_origin)

        Returns:
            LLM提供商ID字符串，失败返回None
        """
        try:
            return await self.context.get_current_chat_provider_id(umo=session)
        except Exception:
            logger.warning("心念 | ⚠️ LLM 提供商不可用，无法生成主动消息")
            return None

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
            logger.debug("心念 | 重复检测: 消息与上次完全相同")
            return True

        # 前50个字符相同（避免仅结尾略有不同的情况）
        check_length = 50
        if len(message) >= check_length and len(last_message) >= check_length:
            if message[:check_length] == last_message[:check_length]:
                logger.debug("心念 | 重复检测: 消息前50字符与上次相同")
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
        self,
        session: str,
        max_retries: int = 3,
        override_prompt: str = None,
        allow_duplicate_on_exhausted: bool = True,
    ) -> tuple:
        """生成主动消息，带重复检测和重试

        Args:
            session: 会话ID
            max_retries: 最大重试次数
            override_prompt: 覆盖用的提示词
            allow_duplicate_on_exhausted: 重试耗尽后是否允许发送重复消息

        Returns:
            元组 (生成的消息, 使用的主动对话提示词)

        Raises:
            MessageGenerationError: 生成失败或重复消息需要稍后重试
        """
        # 检查是否启用重复检测
        proactive_config = self.config.get("proactive_reply", {})
        duplicate_detection_enabled = proactive_config.get(
            "duplicate_detection_enabled", True
        )

        max_retries = max(0, int(max_retries or 0))
        message = None
        final_prompt = None
        for attempt in range(max_retries + 1):
            message, final_prompt = await self.generate_proactive_message(
                session, override_prompt
            )

            # 如果未启用重复检测，直接返回
            if not duplicate_detection_enabled:
                return message, final_prompt

            # 检测重复
            if not self.is_duplicate_message(session, message):
                return message, final_prompt

            # 重复了，记录日志
            if attempt < max_retries:
                logger.warning(
                    f"心念 | 🔄 检测到重复消息，重新生成 ({attempt + 1}/{max_retries})"
                )
            else:
                if allow_duplicate_on_exhausted:
                    logger.warning("心念 | ⚠️ 多次重试后仍为重复消息，使用当前消息")
                else:
                    logger.warning("心念 | ⚠️ 生成结果重复，等待下次调度重试")
                    raise DuplicateMessageError(message, final_prompt)

        return message, final_prompt

    async def generate_proactive_message(
        self, session: str, override_prompt: str = None
    ) -> tuple:
        """使用LLM生成主动消息内容

        Args:
            session: 会话ID

        Returns:
            元组 (生成的消息, 使用的主动对话提示词)

        Raises:
            MessageGenerationError: 生成失败
        """
        try:
            # 检查LLM是否可用
            provider_id = await self.get_provider_id(session)
            if not provider_id:
                raise MessageGenerationError(
                    f"会话 {session} 的 LLM 提供商不可用，无法生成主动消息",
                    retryable=False,
                )

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
                raise MessageGenerationError(
                    "主动消息提示词为空，请检查 proactive_prompt_list 或 AI 调度提示词配置",
                    retryable=False,
                )

            # 获取人格系统提示词
            base_system_prompt = await self.prompt_builder.get_persona_system_prompt(
                session
            )

            # 获取历史记录（如果启用）
            contexts = []
            proactive_config = self.config.get("proactive_reply", {})

            if proactive_config.get("include_history_enabled", False):
                history_count = proactive_config.get("history_message_count", 10)
                history_count = max(
                    MIN_HISTORY_MESSAGE_COUNT,
                    min(MAX_HISTORY_MESSAGE_COUNT, history_count),
                )
                contexts = await self.conversation_manager.get_conversation_history(
                    session, history_count
                )
                # 记录历史记录获取结果
                logger.info(f"心念 | 📚 获取到 {len(contexts)} 条历史记录")
                if contexts:
                    last_msg = contexts[-1]
                    content_preview = last_msg.get("content", "")[:80]
                    logger.debug(
                        f"心念 | 最后一条历史: [{last_msg.get('role')}] {content_preview}"
                    )
            else:
                logger.debug("心念 | 历史记录功能未启用")

            # 构建历史记录引导提示词
            history_guidance = ""
            if proactive_config.get("include_history_enabled", False) and contexts:
                history_guidance = "\n\n--- 上下文说明 ---\n你可以参考上述对话历史来生成更自然和连贯的回复。"

            # 构建组合系统提示词
            combined_system_prompt = self.prompt_builder.build_combined_system_prompt(
                base_system_prompt,
                history_guidance,
            )

            # 调用LLM生成主动消息
            logger.debug(
                f"心念 | 调用 LLM 生成主动消息, contexts 数量: {len(contexts)}"
            )
            llm_response = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=final_prompt,
                contexts=contexts,
                system_prompt=combined_system_prompt,
            )

            if llm_response and llm_response.role == "assistant":
                generated_message = (llm_response.completion_text or "").strip()
                if generated_message:
                    logger.info("心念 | ✅ LLM 生成主动消息成功")
                    return generated_message, final_prompt
                else:
                    logger.warning("心念 | ⚠️ LLM 返回了空消息")
                    raise MessageGenerationError("LLM 返回了空消息", retryable=True)
            else:
                logger.warning(f"心念 | ⚠️ LLM 响应异常: {llm_response}")
                raise MessageGenerationError("LLM 响应异常", retryable=True)

        except MessageGenerationError:
            raise
        except Exception as e:
            logger.error(f"心念 | ❌ 使用 LLM 生成主动消息失败: {e}")
            import traceback

            logger.error(f"心念 | 详细错误信息: {traceback.format_exc()}")
            raise MessageGenerationError(
                f"使用 LLM 生成主动消息失败: {e}", retryable=True
            ) from e

    async def send_proactive_message(
        self,
        session: str,
        override_prompt: str = None,
        duplicate_max_retries: int = 3,
        allow_duplicate_on_exhausted: bool = True,
    ) -> dict | None:
        """向指定会话发送主动消息

        Args:
            session: 会话ID
            override_prompt: 覆盖用的提示词
            duplicate_max_retries: 重复消息的生成端重试次数
            allow_duplicate_on_exhausted: 重复重试耗尽后是否仍发送当前消息

        Returns:
            AI 自主调度信息 {"delay_minutes": int, "follow_up_prompt": str, "fire_time": str}
            或 None（无调度）

        Raises:
            MessageGenerationError: 消息生成失败时抛出
            MessageDeliveryError: 消息投递失败时抛出
            Exception: 发送过程中的其他异常会向上传播
        """
        try:
            # 使用带重复检测的LLM生成主动消息
            (
                message,
                proactive_prompt_used,
            ) = await self.generate_proactive_message_with_retry(
                session,
                max_retries=duplicate_max_retries,
                override_prompt=override_prompt,
                allow_duplicate_on_exhausted=allow_duplicate_on_exhausted,
            )

            original_message = message  # 保存原始消息用于历史记录

            # 处理消息分割和发送
            await self._send_message_with_split(
                session, message, original_message, proactive_prompt_used
            )

            # 只有确认投递成功后，才更新重复检测基线。
            self.record_last_message(session, original_message)

            # AI 自主调度分析属于发送后的附加能力，失败不应触发消息重发。
            try:
                return await self.analyze_message_for_schedule(
                    session, original_message
                )
            except Exception as e:
                logger.error(f"心念 | ❌ AI 调度分析失败，已跳过: {e}")
                return None

        except Exception as e:
            logger.error(f"心念 | ❌ 向会话 {session} 发送主动消息时发生错误: {e}")
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

        if not contains_time_keywords(message):
            logger.debug("心念 | AI 消息未通过调度预检，跳过提供商和历史上下文获取")
            return None

        provider_id = await self.get_provider_id(session)
        if not provider_id:
            return None

        # 获取 AI 调度专用的模型提供商 ID（如果配置了）
        schedule_provider_id = ai_schedule_config.get("provider_id", "").strip()

        # 获取对话历史作为分析上下文
        proactive_config = self.config.get("proactive_reply", {})
        contexts = []
        if proactive_config.get("include_history_enabled", False):
            history_count = proactive_config.get("history_message_count", 10)
            history_count = max(
                MIN_HISTORY_MESSAGE_COUNT,
                min(MAX_HISTORY_MESSAGE_COUNT, history_count),
            )
            history_count = min(history_count, MAX_SCHEDULE_ANALYSIS_HISTORY_COUNT)
            contexts = await self.conversation_manager.get_conversation_history(
                session, history_count
            )

        # 获取自定义分析提示词
        analysis_prompt = ai_schedule_config.get("analysis_prompt", "")

        # 当前时间
        time_format = self.config.get("user_info", {}).get(
            "time_format", "%Y-%m-%d %H:%M:%S"
        )
        tz = get_tz(self.config, self._get_astrbot_config())
        current_time_str = (
            datetime.now(tz=tz).strftime(time_format)
            if tz is not None
            else datetime.now().strftime(time_format)
        )

        # 获取该会话已有的待执行调度任务（用于去重）
        existing_tasks = runtime_data.session_ai_scheduled.get(session, [])
        if isinstance(existing_tasks, dict):
            # 兼容旧版 dict 格式
            existing_tasks = [existing_tasks] if existing_tasks else []

        return await analyze_for_schedule(
            context=self.context,
            provider_id=provider_id,
            ai_message=message,
            contexts=contexts,
            analysis_prompt=analysis_prompt,
            current_time_str=current_time_str,
            schedule_provider_id=schedule_provider_id,
            existing_tasks=existing_tasks,
            tz=tz,
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

        except MessageDeliveryError:
            raise
        except Exception as e:
            logger.error(f"心念 | ❌ 发送消息时发生错误: {e}")
            import traceback

            logger.error(f"心念 | 发送错误详情: {traceback.format_exc()}")
            raise MessageDeliveryError(f"发送消息时发生错误: {e}", retryable=True) from e

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
        try:
            # 委托消息分割器按配置模式分割
            message_parts, mode_display = self.message_splitter.split_message(message)
        except Exception as e:
            logger.error(f"心念 | ❌ 消息分割失败: {e}")
            logger.error("心念 | 将使用原始消息，不进行分割")
            message_parts = [message]
            mode_display = "原始消息"

        if len(message_parts) > 1:
            # 分割成多个片段
            logger.info(
                f"心念 | 📨 使用 {mode_display} 分割消息，共 {len(message_parts)} 条"
            )

            delay_ms = split_config.get("delay_ms", 500)
            delay_seconds = delay_ms / 1000.0

            sent_count = 0
            for i, part in enumerate(message_parts, 1):
                message_chain = MessageChain().message(part)
                await self._send_chain_or_raise(
                    session, message_chain, f"第 {i}/{len(message_parts)} 条消息"
                )

                sent_count += 1
                logger.debug(f"心念 | ✅ 已发送第 {i}/{len(message_parts)} 条消息")
                if i < len(message_parts):
                    await asyncio.sleep(delay_seconds)

            await self._record_successful_delivery(
                session, original_message, proactive_prompt_used
            )
            logger.info(
                f"心念 | ✅ 成功发送主动消息 ({sent_count}/{len(message_parts)} 条)"
            )
        else:
            # 没有被分割
            await self._send_single_message(session, message, proactive_prompt_used)

    async def _send_chain_or_raise(
        self, session: str, message_chain: MessageChain, description: str
    ):
        """发送消息链，失败时抛出可分类异常。"""
        try:
            success = await self.context.send_message(session, message_chain)
        except Exception as e:
            raise MessageDeliveryError(
                f"{description}发送异常: {e}", retryable=True
            ) from e

        if not success:
            raise MessageDeliveryError(
                f"{description}发送失败，可能是会话不存在或平台不支持",
                retryable=False,
            )

    async def _record_successful_delivery(
        self, session: str, message: str, proactive_prompt_used: str = None
    ):
        """记录已确认投递的主动消息。

        投递已经成功后，发送时间和历史记录属于后置 bookkeeping。这里不再向上
        抛出异常，避免用户已收到消息却被调度层误判为投递失败并再次发送。
        """
        try:
            self.user_info_manager.record_sent_time(session)
        except Exception as e:
            logger.error(f"心念 | ❌ 记录主动消息发送时间失败: {e}")

        try:
            await self.conversation_manager.add_message_to_conversation_history(
                session,
                message,
                proactive_prompt_used=proactive_prompt_used,
                build_user_context_func=self.user_info_manager.build_user_context_for_proactive,
            )
        except Exception as e:
            logger.error(f"心念 | ❌ 保存主动消息历史失败: {e}")

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
        await self._send_chain_or_raise(session, message_chain, "主动消息")

        await self._record_successful_delivery(session, message, proactive_prompt_used)
        logger.info("心念 | ✅ 成功发送主动消息")
