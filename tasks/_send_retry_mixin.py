"""主动消息发送重试与失败通知"""

from datetime import timedelta
from astrbot.api import logger
from astrbot.api.event import MessageChain
from ..core.runtime_data import runtime_data


class SendRetryMixin:
    """主动消息发送重试与失败通知"""

    _MAX_RETRIES = 3
    _RETRY_INTERVAL_SECONDS = 60

    async def _send_with_retry(
        self, session: str, override_prompt: str = None
    ) -> tuple[bool, dict | None, bool]:
        """带重试的消息发送

        每次只做一次发送尝试。失败时将该会话推迟到下个重试时间点，
        不在当前到期会话循环里 sleep，避免阻塞其他会话。

        Args:
            session: 会话ID
            override_prompt: 覆盖用的提示词（用于 AI 自主调度任务）

        Returns:
            元组 (成功标志, AI调度信息或None, 是否已安排短间隔重试)
        """
        retry_attempts = self._get_retry_attempts()
        retry_state = retry_attempts.get(session) or {}
        current_fire_time = runtime_data.session_next_fire_times.get(session)
        attempts_done = 0
        if retry_state.get("retry_fire_time") == current_fire_time:
            attempts_done = int(retry_state.get("attempts", 0))
        else:
            retry_attempts.pop(session, None)

        attempt_in_budget = attempts_done + 1
        allow_duplicate_on_final_attempt = attempt_in_budget >= self._MAX_RETRIES

        try:
            logger.info(
                f"心念 | 向会话 {session} 发送主动消息"
                f"（第 {attempt_in_budget}/{self._MAX_RETRIES} 次尝试）"
            )
            schedule_info = await self.message_generator.send_proactive_message(
                session,
                override_prompt=override_prompt,
                duplicate_max_retries=0,
                allow_duplicate_on_exhausted=allow_duplicate_on_final_attempt,
            )
            # 发送成功，清除连续失败计数
            retry_attempts.pop(session, None)
            runtime_data.session_consecutive_failures.pop(session, None)
            return True, schedule_info, False
        except Exception as e:
            retryable = getattr(e, "retryable", True)

            logger.error(
                f"心念 | ❌ 向会话 {session} 发送主动消息失败"
                f"（第 {attempt_in_budget}/{self._MAX_RETRIES} 次）: {e}"
            )

            if retryable and attempt_in_budget < self._MAX_RETRIES:
                retry_time = self._get_now() + timedelta(
                    seconds=self._RETRY_INTERVAL_SECONDS
                )
                self.set_session_next_fire_time(session, retry_time)
                retry_time_str = retry_time.strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    f"心念 | 已将会话 {session} 推迟到 "
                    f"{retry_time_str} 重试，"
                    "继续处理其他到期会话"
                )
                retry_attempts[session] = {
                    "attempts": attempt_in_budget,
                    "retry_fire_time": retry_time_str,
                }
                return False, None, True

            retry_attempts.pop(session, None)
            failures = runtime_data.session_consecutive_failures.get(session, 0) + 1
            runtime_data.session_consecutive_failures[session] = failures

            if retryable:
                logger.error(
                    f"心念 | ❌ 会话 {session} 本轮重试预算已用完，"
                    f"连续失败调度周期 {failures} 次，已通知用户"
                )
            else:
                logger.error(
                    f"心念 | ❌ 会话 {session} 发生配置或会话类错误，"
                    "不进行短间隔自动重试，已通知用户"
                )

            await self._notify_user_send_failure(session, e, failures, retryable)
            return False, None, False

    def _get_retry_attempts(self) -> dict:
        """获取短间隔重试状态。

        该状态只服务于当前进程内的一轮短重试，不写入持久化数据，避免污染
        session_consecutive_failures 的「连续失败调度周期」语义。
        """
        if not hasattr(self, "_send_retry_attempts"):
            self._send_retry_attempts = {}
        return self._send_retry_attempts

    async def _notify_user_send_failure(
        self, session: str, error: Exception, failures: int, retryable: bool = True
    ):
        """向用户发送发送失败的错误通知（不保存到历史记录）

        Args:
            session: 会话ID
            error: 最后一次失败的异常
            failures: 连续失败调度周期数
            retryable: 是否为瞬时错误
        """
        try:
            # 提取原始异常链中的根因
            root_cause = error
            while root_cause.__cause__:
                root_cause = root_cause.__cause__
            error_type = type(root_cause).__name__
            error_detail = str(root_cause)

            if retryable:
                retry_text = (
                    f"本轮已尝试 {self._MAX_RETRIES} 次，重试预算已用完。\n"
                    "系统将在下个常规调度周期再次尝试。"
                )
            else:
                retry_text = (
                    "检测到配置或会话类错误，未继续短间隔重试。\n"
                    "请检查主动提示词、模型提供商或会话是否仍可用。"
                )

            error_msg = (
                f"⚠️ 主动消息发送失败\n"
                f"{retry_text}\n"
                f"连续失败调度周期: {failures}\n"
                f"错误类型: {error_type}\n"
                f"错误详情: {error_detail}"
            )
            message_chain = MessageChain().message(error_msg)
            await self.context.send_message(session, message_chain)
        except Exception as e:
            logger.error(f"心念 | ❌ 向会话 {session} 发送错误通知也失败了: {e}")
