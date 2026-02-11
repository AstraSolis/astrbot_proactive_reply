"""
定时任务管理器

负责定时主动发送消息的任务管理（混合计时器模式）
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional
from astrbot.api import logger
from astrbot.api.event import MessageChain
from ..utils.parsers import parse_sessions_list
from ..core.runtime_data import runtime_data


class ProactiveTaskManager:
    """定时任务管理器类（混合计时器模式）"""

    def __init__(
        self,
        config: dict,
        context,
        message_generator,
        user_info_manager,
        is_terminating_flag_getter,
        persistence_manager=None,
    ):
        """初始化任务管理器

        Args:
            config: 配置字典
            context: AstrBot上下文对象
            message_generator: 消息生成器
            user_info_manager: 用户信息管理器
            is_terminating_flag_getter: 获取终止标志的函数
            persistence_manager: 持久化管理器（可选）
        """
        self.config = config
        self.context = context
        self.message_generator = message_generator
        self.user_info_manager = user_info_manager
        self.is_terminating_flag_getter = is_terminating_flag_getter
        self.persistence_manager = persistence_manager
        self.proactive_task = None
        # 配置签名追踪，用于自动检测配置变化
        self._last_timing_config_signature: Optional[str] = None

    # ==================== 计时器管理方法 ====================

    def get_session_next_fire_time(self, session: str) -> Optional[datetime]:
        """获取会话的下次发送时间

        Args:
            session: 会话ID

        Returns:
            下次发送时间，如果不存在则返回 None
        """
        time_str = runtime_data.session_next_fire_times.get(session)
        if not time_str:
            return None
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"会话 {session} 的下次发送时间格式错误: {time_str}")
            return None

    def set_session_next_fire_time(self, session: str, fire_time: datetime):
        """设置会话的下次发送时间

        Args:
            session: 会话ID
            fire_time: 下次发送时间
        """
        runtime_data.session_next_fire_times[session] = fire_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        # 触发持久化
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()

    def calculate_next_fire_time(self, session: str) -> datetime:
        """计算会话的下次发送时间

        Args:
            session: 会话ID

        Returns:
            下次发送时间
        """
        interval_minutes = self.get_session_target_interval(session)
        return datetime.now() + timedelta(minutes=interval_minutes)

    def refresh_session_timer(self, session: str):
        """刷新会话计时器（AI 发消息后调用）

        重新计算下次发送时间

        Args:
            session: 会话ID
        """
        # 只刷新在目标列表中的会话
        if session not in self.get_target_sessions():
            return

        next_fire = self.calculate_next_fire_time(session)
        self.set_session_next_fire_time(session, next_fire)
        logger.debug(
            f"会话 {session} 计时器已刷新，下次发送：{next_fire.strftime('%H:%M:%S')}"
        )

    def ensure_all_sessions_scheduled(self):
        """确保所有目标会话都有下次发送时间"""
        for session in self.get_target_sessions():
            if not self.get_session_next_fire_time(session):
                next_fire = self.calculate_next_fire_time(session)
                self.set_session_next_fire_time(session, next_fire)
                logger.info(
                    f"会话 {session} 初始化计时器，下次发送：{next_fire.strftime('%Y-%m-%d %H:%M:%S')}"
                )

    def clear_session_timer(self, session: str):
        """清除会话的计时器

        Args:
            session: 会话ID
        """
        changed = False
        if session in runtime_data.session_next_fire_times:
            del runtime_data.session_next_fire_times[session]
            changed = True
        if session in runtime_data.session_sleep_remaining:
            del runtime_data.session_sleep_remaining[session]
            changed = True
        # 触发持久化
        if changed and self.persistence_manager:
            self.persistence_manager.save_persistent_data()

    def clear_all_session_timers(self):
        """清除所有会话的计时器

        用于重启任务时强制使用新配置重新计算所有计时器
        """
        runtime_data.session_next_fire_times.clear()
        runtime_data.session_sleep_remaining.clear()
        logger.info("已清除所有会话的计时器")
        # 触发持久化
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()

    def _get_timing_config_signature(self) -> str:
        """生成当前计时相关配置的签名

        用于检测配置是否发生变化

        Returns:
            配置签名字符串
        """
        proactive_config = self.config.get("proactive_reply", {})
        # 提取所有影响计时的配置项
        timing_mode = proactive_config.get("timing_mode", "fixed_interval")
        interval_minutes = proactive_config.get("interval_minutes", 600)
        random_min = proactive_config.get("random_min_minutes", 600)
        random_max = proactive_config.get("random_max_minutes", 1200)
        random_delay_enabled = proactive_config.get("random_delay_enabled", False)
        min_random = proactive_config.get("min_random_minutes", 0)
        max_random = proactive_config.get("max_random_minutes", 30)

        return f"{timing_mode}|{interval_minutes}|{random_min}|{random_max}|{random_delay_enabled}|{min_random}|{max_random}"

    def _check_and_handle_config_change(self):
        """检测配置变化并自动清理计时器

        在主循环中调用，自动检测计时配置是否变化，
        变化时清除所有计时器以使用新配置重新计算。
        配置签名通过 runtime_data 持久化，支持跨插件重载的检测。
        """
        current_signature = self._get_timing_config_signature()
        last_signature = runtime_data.timing_config_signature

        # 首次运行（无持久化签名）时记录签名，不清理
        if not last_signature:
            runtime_data.timing_config_signature = current_signature
            self._last_timing_config_signature = current_signature
            if self.persistence_manager:
                self.persistence_manager.save_persistent_data()
            return

        # 签名变化时清理计时器
        if current_signature != last_signature:
            logger.info(
                f"检测到计时配置变化，自动清除所有计时器 "
                f"(旧: {last_signature}, 新: {current_signature})"
            )
            self.clear_all_session_timers()
            runtime_data.timing_config_signature = current_signature
            self._last_timing_config_signature = current_signature

    # ==================== 智能睡眠计算 ====================

    def calculate_smart_sleep(self) -> int:
        """计算到下一个事件的睡眠秒数

        Returns:
            睡眠秒数，范围 [1, 300]
        """
        sessions = self.get_target_sessions()
        if not sessions:
            return 60  # 无会话时默认 60 秒检查

        now = datetime.now()
        next_fires = []
        for session in sessions:
            fire_time = self.get_session_next_fire_time(session)
            if fire_time:
                next_fires.append(fire_time)

        if not next_fires:
            return 60

        earliest = min(next_fires)
        seconds_to_next = (earliest - now).total_seconds()

        # 如果已经过期，返回 1 秒立即处理
        if seconds_to_next <= 0:
            return 1

        # 限制在 1~300 秒之间
        return max(1, min(300, int(seconds_to_next)))

    # ==================== 睡眠状态处理 ====================

    def handle_enter_sleep(self):
        """进入睡眠时保存各会话的剩余时间"""
        now = datetime.now()
        for session in self.get_target_sessions():
            fire_time = self.get_session_next_fire_time(session)
            if fire_time and fire_time > now:
                remaining_seconds = (fire_time - now).total_seconds()
                runtime_data.session_sleep_remaining[session] = remaining_seconds
                logger.debug(
                    f"会话 {session} 进入睡眠，剩余 {remaining_seconds:.0f} 秒"
                )

        # 持久化保存
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()

    def handle_exit_sleep(self):
        """退出睡眠时处理计时器

        三种模式：
        1. send_on_wake_enabled=False → 跳过，重新计算下次发送时间
        2. send_on_wake_enabled=True + wake_send_mode=immediate → 保持原计时器，过期立即发送
        3. send_on_wake_enabled=True + wake_send_mode=delayed → 恢复剩余计时，延后发送
        """
        time_awareness = self.config.get("time_awareness", {})
        send_on_wake = time_awareness.get("send_on_wake_enabled", False)
        wake_mode = time_awareness.get("wake_send_mode", "immediate")
        now = datetime.now()

        for session in self.get_target_sessions():
            if not send_on_wake:
                # 模式1：跳过睡眠期间的主动消息，重新计算
                new_fire = self.calculate_next_fire_time(session)
                self.set_session_next_fire_time(session, new_fire)
                logger.debug(
                    f"会话 {session} 睡眠结束，跳过模式，重新计时：{new_fire.strftime('%H:%M:%S')}"
                )
            elif wake_mode == "immediate":
                # 模式2：保持原计时器，让主循环检测到过期后立即发送
                logger.debug(f"会话 {session} 睡眠结束，立即发送模式，保持原计时器")
            else:
                # 模式3：恢复剩余计时，延后发送
                remaining = runtime_data.session_sleep_remaining.get(session)
                if remaining is not None and remaining > 0:
                    new_fire = now + timedelta(seconds=remaining)
                    self.set_session_next_fire_time(session, new_fire)
                    logger.debug(
                        f"会话 {session} 睡眠结束，延后模式，恢复计时：{new_fire.strftime('%H:%M:%S')}"
                    )
                else:
                    # 没有记录剩余时间，重新计算
                    new_fire = self.calculate_next_fire_time(session)
                    self.set_session_next_fire_time(session, new_fire)
                    logger.debug(
                        f"会话 {session} 睡眠结束，延后模式，重新计时：{new_fire.strftime('%H:%M:%S')}"
                    )

        # 清理 sleep_remaining
        runtime_data.session_sleep_remaining.clear()
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()

    # ==================== 主循环 ====================

    async def proactive_message_loop(self):
        """定时主动发送消息的循环（混合计时器模式）

        核心逻辑：预计算下次发送时间 + 智能睡眠
        """
        logger.info("定时主动发送消息循环已启动（混合计时器模式）")

        # 追踪睡眠状态
        was_sleeping = False

        while True:
            try:
                # 检查是否应该终止
                if self.should_terminate():
                    break

                # 检查功能是否启用
                if not self.is_proactive_enabled():
                    await asyncio.sleep(60)
                    continue

                # 睡眠状态检测与处理
                is_sleeping = self.is_sleep_time()

                if is_sleeping and not was_sleeping:
                    # 刚进入睡眠
                    logger.info("进入睡眠时间段，暂停主动消息发送")
                    self.handle_enter_sleep()
                    was_sleeping = True

                if is_sleeping:
                    await asyncio.sleep(60)
                    continue

                if was_sleeping and not is_sleeping:
                    # 刚退出睡眠
                    logger.info("睡眠时间结束，恢复主动消息发送")
                    self.handle_exit_sleep()
                    was_sleeping = False

                # 检测配置变化，变化时自动清理计时器
                self._check_and_handle_config_change()

                # 确保所有会话都有计时器
                self.ensure_all_sessions_scheduled()

                # 智能睡眠
                sleep_seconds = self.calculate_smart_sleep()
                logger.debug(f"智能睡眠 {sleep_seconds} 秒")

                should_continue = await self.interruptible_sleep(sleep_seconds)
                if not should_continue:
                    continue  # 被中断，重新检查状态

                # 处理到期的会话
                await self.process_due_sessions()

            except asyncio.CancelledError:
                logger.info("定时主动发送消息循环已取消")
                break
            except Exception as e:
                logger.error(f"定时主动发送消息循环发生错误: {e}")
                await asyncio.sleep(60)

    async def interruptible_sleep(self, total_seconds: int) -> bool:
        """可中断的睡眠

        每 10 秒检查状态，允许提前退出

        Args:
            total_seconds: 总睡眠秒数

        Returns:
            True 如果正常完成睡眠，False 如果被中断
        """
        remaining = total_seconds
        while remaining > 0:
            if self.should_terminate() or not self.is_proactive_enabled():
                return False
            # 检查是否进入睡眠时间
            if self.is_sleep_time():
                return False

            chunk = min(10, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk

        return True

    async def process_due_sessions(self):
        """处理所有到期的会话"""
        now = datetime.now()
        sent_count = 0
        sessions = self.get_target_sessions()

        for session in sessions:
            if self.should_terminate():
                break

            fire_time = self.get_session_next_fire_time(session)
            if fire_time and fire_time <= now:
                success = await self._send_with_retry(session)
                # 无论成功失败，都重排程下次触发时间，避免高频循环
                next_fire = self.calculate_next_fire_time(session)
                self.set_session_next_fire_time(session, next_fire)
                logger.info(
                    f"会话 {session} 下次发送时间：{next_fire.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                if success:
                    sent_count += 1

        if sent_count > 0:
            logger.info(f"本轮发送了 {sent_count}/{len(sessions)} 条主动消息")

    # ==================== 发送重试 ====================

    _MAX_RETRIES = 3
    _RETRY_INTERVAL_SECONDS = 60

    async def _send_with_retry(self, session: str) -> bool:
        """带重试的消息发送

        最多尝试 _MAX_RETRIES 次，每次间隔 _RETRY_INTERVAL_SECONDS 秒。
        全部失败后发送错误通知给用户（不保存到历史记录）。

        Args:
            session: 会话ID

        Returns:
            True 发送成功，False 全部重试失败
        """
        last_error = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                logger.info(
                    f"向会话 {session} 发送主动消息"
                    f"（第 {attempt}/{self._MAX_RETRIES} 次尝试）"
                )
                await self.message_generator.send_proactive_message(session)
                # 发送成功，清除连续失败计数
                runtime_data.session_consecutive_failures.pop(session, None)
                return True
            except Exception as e:
                last_error = e
                logger.error(
                    f"向会话 {session} 发送主动消息失败"
                    f"（第 {attempt}/{self._MAX_RETRIES} 次）: {e}"
                )
                if attempt < self._MAX_RETRIES:
                    logger.info(
                        f"等待 {self._RETRY_INTERVAL_SECONDS} 秒后重试..."
                    )
                    await asyncio.sleep(self._RETRY_INTERVAL_SECONDS)

        # 全部重试失败，发送错误通知给用户（不保存到历史记录）
        failures = runtime_data.session_consecutive_failures.get(session, 0) + 1
        runtime_data.session_consecutive_failures[session] = failures
        logger.error(
            f"会话 {session} 连续 {failures} 次调度均发送失败，已通知用户"
        )
        await self._notify_user_send_failure(session, last_error, failures)
        return False

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
            logger.error(f"向会话 {session} 发送错误通知也失败了: {e}")

    # ==================== 状态检查方法 ====================

    def should_terminate(self) -> bool:
        """检查是否应该终止任务"""
        if self.is_terminating_flag_getter():
            logger.info("插件正在终止，退出定时循环")
            return True

        if self.proactive_task and self.proactive_task.cancelled():
            logger.info("定时主动发送任务已被取消，退出循环")
            return True

        return False

    def is_proactive_enabled(self) -> bool:
        """检查主动回复功能是否启用"""
        return self.config.get("proactive_reply", {}).get("enabled", False)

    def get_target_sessions(self) -> list:
        """获取目标会话列表"""
        sessions_data = self.config.get("proactive_reply", {}).get("sessions", [])
        return parse_sessions_list(sessions_data)

    def is_sleep_time(self) -> bool:
        """检查当前是否在睡眠时间段内"""
        from ..utils.time_utils import is_sleep_time as check_sleep_time

        return check_sleep_time(self.config)

    # ==================== 间隔计算方法 ====================

    def get_base_interval(self) -> int:
        """获取基础间隔时间（分钟），不包含随机因素

        Returns:
            基础间隔时间（分钟）
        """
        proactive_config = self.config.get("proactive_reply", {})
        timing_mode = proactive_config.get("timing_mode", "fixed_interval")

        if timing_mode == "random_interval":
            return proactive_config.get("random_min_minutes", 600)
        else:
            return proactive_config.get("interval_minutes", 600)

    def get_session_target_interval(self, session: str) -> int:
        """获取指定会话的目标间隔时间

        Args:
            session: 会话ID

        Returns:
            目标间隔时间（分钟）
        """
        proactive_config = self.config.get("proactive_reply", {})
        timing_mode = proactive_config.get("timing_mode", "fixed_interval")

        # 固定间隔模式
        if timing_mode != "random_interval":
            interval = proactive_config.get("interval_minutes", 600)
            # 如果启用随机延迟，添加随机值
            if proactive_config.get("random_delay_enabled", False):
                min_delay = proactive_config.get("min_random_minutes", 0)
                max_delay = proactive_config.get("max_random_minutes", 30)
                interval += random.randint(min_delay, max_delay)
            return interval

        # 随机间隔模式
        random_min = proactive_config.get("random_min_minutes", 600)
        random_max = proactive_config.get("random_max_minutes", 1200)
        return random.randint(random_min, random_max)

    # ==================== 状态信息方法 ====================

    def get_next_fire_info(self, session: str) -> str:
        """获取会话下次发送时间的展示信息

        Args:
            session: 会话ID

        Returns:
            展示信息字符串
        """
        fire_time = self.get_session_next_fire_time(session)

        # 如果没有计划时间，尝试基于 AI 最后消息时间估算
        if not fire_time:
            minutes_since_last = (
                self.user_info_manager.get_minutes_since_ai_last_message(session)
            )
            if minutes_since_last == -1:
                return "等待初始化"

            interval = self.get_session_target_interval(session)
            remaining_minutes = interval - minutes_since_last

            if remaining_minutes <= 0:
                return "即将发送"

            if remaining_minutes < 60:
                return f"约{remaining_minutes}分钟后"
            else:
                hours = remaining_minutes // 60
                minutes = remaining_minutes % 60
                return f"约{hours}小时{minutes}分钟后"

        now = datetime.now()
        if fire_time <= now:
            return "即将发送"

        delta = fire_time - now
        total_minutes = int(delta.total_seconds() / 60)

        if total_minutes < 60:
            return f"{total_minutes}分钟后 ({fire_time.strftime('%H:%M')})"
        else:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            return f"{hours}小时{minutes}分钟后 ({fire_time.strftime('%H:%M')})"

    def get_all_sessions_status(self) -> list:
        """获取所有会话的状态信息

        Returns:
            [(session, next_fire_info), ...]
        """
        result = []
        for session in self.get_target_sessions():
            info = self.get_next_fire_info(session)
            result.append((session, info))
        return result

    # ==================== 任务控制方法 ====================

    async def stop_proactive_task(self):
        """停止定时主动发送任务"""
        if not self.proactive_task or self.proactive_task.cancelled():
            logger.debug("定时任务已停止或不存在")
            return

        logger.info("正在停止定时主动发送任务...")
        self.proactive_task.cancel()

        try:
            await asyncio.wait_for(self.proactive_task, timeout=5.0)
        except asyncio.CancelledError:
            logger.info("定时主动发送任务已停止")
        except asyncio.TimeoutError:
            logger.warning("停止定时任务超时，任务可能仍在运行")
        except RuntimeError as e:
            logger.error(f"任务运行时错误: {e}")
        finally:
            self.proactive_task = None

    async def start_proactive_task(self):
        """启动定时主动发送任务"""
        # 首先停止所有现有任务
        await self.force_stop_all_tasks()

        proactive_config = self.config.get("proactive_reply", {})
        enabled = proactive_config.get("enabled", False)

        if enabled:
            self.proactive_task = asyncio.create_task(self.proactive_message_loop())
            logger.info("定时主动发送任务已启动")

            await asyncio.sleep(0.1)

            if self.proactive_task.done():
                logger.error("定时任务启动后立即结束，可能有错误")
                try:
                    await self.proactive_task
                except Exception as e:
                    logger.error(f"定时任务错误: {e}")
        else:
            logger.info("定时主动发送功能未启用")

    async def restart_proactive_task(self):
        """重启定时主动发送任务

        重启时会清除所有会话的计时器，确保新配置的间隔时间立即生效
        """
        await self.stop_proactive_task()
        # 清除所有会话的计时器，强制使用新配置重新计算
        self.clear_all_session_timers()
        # 重置配置签名，避免后续误判为配置变化
        runtime_data.timing_config_signature = ""
        self._last_timing_config_signature = None
        await self.start_proactive_task()

    async def force_stop_all_tasks(self):
        """强制停止所有相关任务"""
        logger.info("强制停止所有相关任务...")

        await self.stop_proactive_task()

        # 查找并停止所有可能的相关任务
        current_task = asyncio.current_task()
        all_tasks = asyncio.all_tasks()

        for task in all_tasks:
            if task != current_task and not task.done():
                if hasattr(task, "_coro") and task._coro:
                    coro_name = getattr(task._coro, "__name__", "")
                    if "proactive_message_loop" in coro_name:
                        task.cancel()
                        try:
                            await task
                        except (
                            asyncio.CancelledError,
                            asyncio.TimeoutError,
                            RuntimeError,
                        ):
                            pass
