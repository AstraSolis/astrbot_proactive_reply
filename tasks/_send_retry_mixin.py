"""主动消息发送重试与失败通知"""

import asyncio
from astrbot.api import logger
from astrbot.api.event import MessageChain
from ..core.runtime_data import runtime_data


class SendRetryMixin:
    """主动消息发送重试与失败通知"""

    _MAX_RETRIES = 3
    _RETRY_INTERVAL_SECONDS = 60

    async def _send_with_retry(
        self, session: str, override_prompt: str = None
    ) -> tuple[bool, dict | None]:
        """带重试的消息发送

        最多尝试 _MAX_RETRIES 次，每次间隔 _RETRY_INTERVAL_SECONDS 秒。
        全部失败后发送错误通知给用户（不保存到历史记录）。

        Args:
            session: 会话ID
            override_prompt: 覆盖用的提示词（用于 AI 自主调度任务）

        Returns:
            元组 (成功标志, AI调度信息或None)
        """
        last_error = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                logger.info(
                    f"心念 | 向会话 {session} 发送主动消息"
                    f"（第 {attempt}/{self._MAX_RETRIES} 次尝试）"
                )
                schedule_info = await self.message_generator.send_proactive_message(
                    session, override_prompt=override_prompt
                )
                # 发送成功，清除连续失败计数
                runtime_data.session_consecutive_failures.pop(session, None)
                return True, schedule_info
            except Exception as e:
                last_error = e
                logger.error(
                    f"心念 | ❌ 向会话 {session} 发送主动消息失败"
                    f"（第 {attempt}/{self._MAX_RETRIES} 次）: {e}"
                )
                if attempt < self._MAX_RETRIES:
                    logger.info(
                        f"心念 | 等待 {self._RETRY_INTERVAL_SECONDS} 秒后重试..."
                    )
                    await asyncio.sleep(self._RETRY_INTERVAL_SECONDS)

        # 全部重试失败，发送错误通知给用户（不保存到历史记录）
        failures = runtime_data.session_consecutive_failures.get(session, 0) + 1
        runtime_data.session_consecutive_failures[session] = failures
        logger.error(
            f"心念 | ❌ 会话 {session} 连续 {failures} 次调度均发送失败，已通知用户"
        )
        await self._notify_user_send_failure(session, last_error, failures)
        return False, None

    async def _notify_user_send_failure(
        self, session: str, error: Exception, failures: int
    ):
        """向用户发送发送失败的错误通知（不保存到历史记录）

        Args:
            session: 会话ID
            error: 最后一次失败的异常
            failures: 连续调度失败次数
        """
        try:
            # 提取原始异常链中的根因
            root_cause = error
            while root_cause.__cause__:
                root_cause = root_cause.__cause__
            error_type = type(root_cause).__name__
            error_detail = str(root_cause)

            error_msg = (
                f"⚠️ 主动消息发送失败\n"
                f"已重试 {self._MAX_RETRIES} 次均未成功"
                f"（连续 {failures} 个调度周期失败）\n"
                f"错误类型: {error_type}\n"
                f"错误详情: {error_detail}\n"
                f"系统将在下个调度周期自动重试。"
            )
            message_chain = MessageChain().message(error_msg)
            await self.context.send_message(session, message_chain)
        except Exception as e:
            logger.error(f"心念 | ❌ 向会话 {session} 发送错误通知也失败了: {e}")
