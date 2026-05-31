"""会话计时器管理与配置变化检测"""

from datetime import datetime, timedelta
from typing import Optional
from astrbot.api import logger
from ..core.runtime_data import runtime_data


class TimerMixin:
    """会话计时器管理与配置变化检测"""

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
            logger.warning(
                f"心念 | ⚠️ 会话 {session} 的下次发送时间格式错误: {time_str}"
            )
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
        return self._get_now() + timedelta(minutes=interval_minutes)

    def refresh_session_timer(self, session: str):
        """刷新会话计时器（AI 发消息后调用）

        重新计算下次发送时间：
        取 "常规周期时间" 和 "最早的 AI 调度任务时间" 中的较小值。

        Args:
            session: 会话ID
        """
        # 只刷新在目标列表中的会话
        if session not in self.get_target_sessions():
            return

        # 1. 计算常规周期的下次触发时间
        regular_next_fire = self.calculate_next_fire_time(session)

        # 2. 检查是否有更早的 AI 调度任务
        next_fire = regular_next_fire
        ai_tasks = runtime_data.session_ai_scheduled.get(session, [])
        if ai_tasks:
            # 过滤掉无效的时间
            valid_times = []
            for task in ai_tasks:
                t = self._get_task_fire_datetime(task)
                if t is not None:
                    valid_times.append(t)

            if valid_times:
                min_ai_time = min(valid_times)
                # 如果 AI 任务时间更早，则优先触发
                if min_ai_time < next_fire:
                    next_fire = min_ai_time
                    logger.debug(
                        f"心念 | 会话 {session} 存在更早的 AI 调度任务 ({min_ai_time})，优先执行"
                    )

        self.set_session_next_fire_time(session, next_fire)
        logger.debug(
            f"心念 | 会话 {session} 计时器已刷新，下次发送：{next_fire.strftime('%H:%M:%S')}"
        )
        self.notify_wakeup()

    def ensure_all_sessions_scheduled(self):
        """确保所有目标会话都有下次发送时间"""
        for session in self.get_target_sessions():
            if not self.get_session_next_fire_time(session):
                next_fire = self.calculate_next_fire_time(session)
                self.set_session_next_fire_time(session, next_fire)
                logger.info(
                    f"心念 | 会话 {session} 初始化计时器，下次发送：{next_fire.strftime('%Y-%m-%d %H:%M:%S')}"
                )

    def clear_session_timer(self, session: str):
        """清除会话的计时器和相关数据

        清除指定会话的所有运行时数据，包括计时器、AI调度任务等。

        Args:
            session: 会话ID
        """
        changed = False

        # 清除计时器相关
        if session in runtime_data.session_next_fire_times:
            del runtime_data.session_next_fire_times[session]
            changed = True
        if session in runtime_data.session_sleep_remaining:
            del runtime_data.session_sleep_remaining[session]
            changed = True

        # 清除 AI 调度任务
        if session in runtime_data.session_ai_scheduled:
            del runtime_data.session_ai_scheduled[session]
            changed = True

        # 清除其他会话相关数据（可选，根据需求决定是否清除）
        # 这些数据不影响计时器，但为了完整性可以清除
        if session in runtime_data.session_last_proactive_message:
            del runtime_data.session_last_proactive_message[session]
            changed = True
        if session in runtime_data.session_unreplied_count:
            del runtime_data.session_unreplied_count[session]
            changed = True
        if session in runtime_data.session_consecutive_failures:
            del runtime_data.session_consecutive_failures[session]
            changed = True

        if changed:
            logger.info(f"心念 | 已清除会话 {session} 的所有运行时数据")
            # 触发持久化
            if self.persistence_manager:
                self.persistence_manager.save_persistent_data()
            self.notify_wakeup()

    def clear_all_session_timers(self):
        """清除所有会话的计时器

        用于重启任务时强制使用新配置重新计算所有计时器
        """
        runtime_data.session_next_fire_times.clear()
        runtime_data.session_sleep_remaining.clear()
        logger.info("心念 | 已清除所有会话的计时器")
        # 触发持久化
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()
        self.notify_wakeup()

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

    def _check_and_handle_config_change(self, preserve_sleep_state: bool = False):
        """检测配置变化并自动清理计时器

        在主循环中调用，自动检测计时配置是否变化，
        变化时清除所有计时器以使用新配置重新计算。
        配置签名通过 runtime_data 持久化，支持跨插件重载的检测。

        Args:
            preserve_sleep_state: 是否保留睡眠状态（session_sleep_remaining 和 session_next_fire_times）。
                                 睡眠期间应设为 True，避免破坏睡眠结束时的恢复逻辑。
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
                f"心念 | 检测到计时配置变化，自动清除所有计时器 "
                f"(旧: {last_signature}, 新: {current_signature})"
            )

            if preserve_sleep_state:
                # 睡眠期间：保留 session_sleep_remaining 和 session_next_fire_times
                # 避免破坏睡眠结束时的恢复逻辑（immediate/delayed 模式）
                backup_sleep_remaining = runtime_data.session_sleep_remaining.copy()
                backup_next_fire_times = runtime_data.session_next_fire_times.copy()
                self.clear_all_session_timers()
                runtime_data.session_sleep_remaining = backup_sleep_remaining
                runtime_data.session_next_fire_times = backup_next_fire_times
                logger.debug("心念 | 睡眠期间配置变化，已保留睡眠状态和计时器")
            else:
                # 非睡眠期间：清除所有计时器
                self.clear_all_session_timers()

            runtime_data.timing_config_signature = current_signature
            self._last_timing_config_signature = current_signature
            self.notify_wakeup()
