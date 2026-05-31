"""智能睡眠计算与睡眠状态处理"""

from datetime import timedelta
from astrbot.api import logger
from ..core.runtime_data import runtime_data


class SleepMixin:
    """智能睡眠计算与睡眠状态处理"""

    def calculate_smart_sleep(self) -> int:
        """计算到下一个事件的睡眠秒数

        Returns:
            睡眠秒数，范围 [1, 300]
        """
        sessions = self.get_target_sessions()
        if not sessions:
            return 60  # 无会话时默认 60 秒检查

        now = self._get_now()
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

    def calculate_sleep_mode_smart_sleep(self) -> int:
        """计算睡眠模式下到下一个事件的睡眠秒数

        睡眠期间只关心 AI 调度任务和睡眠结束时间，忽略常规计时器。

        Returns:
            睡眠秒数，范围 [1, 300]
        """
        from ..utils.time_utils import get_seconds_until_sleep_end

        sessions = self.get_target_sessions()
        if not sessions:
            return 300  # 无会话时默认 5 分钟

        now = self._get_now()
        next_events = []

        # 1. 收集 AI 调度任务的时间
        for session in sessions:
            ai_tasks = runtime_data.session_ai_scheduled.get(session, [])
            for task in ai_tasks:
                fire_time = self._get_task_fire_datetime(task)
                if fire_time is not None and fire_time > now:
                    next_events.append(fire_time)

        # 2. 添加睡眠结束时间
        seconds_until_sleep_end = get_seconds_until_sleep_end(
            self.config, self._get_astrbot_config()
        )
        if seconds_until_sleep_end > 0:
            sleep_end_time = now + timedelta(seconds=seconds_until_sleep_end)
            next_events.append(sleep_end_time)

        if not next_events:
            return 300  # 无事件时默认 5 分钟

        earliest = min(next_events)
        seconds_to_next = (earliest - now).total_seconds()

        # 限制在 1~300 秒之间
        return max(1, min(300, int(seconds_to_next)))

    # ==================== 睡眠状态处理 ====================

    def handle_enter_sleep(self):
        """进入睡眠时保存各会话的剩余时间

        只保存未过期的计时器剩余时间，用于延后模式恢复。
        已过期的计时器不保存，退出睡眠时保持过期状态。
        """
        now = self._get_now()
        for session in self.get_target_sessions():
            fire_time = self.get_session_next_fire_time(session)
            if fire_time:
                remaining_seconds = (fire_time - now).total_seconds()
                if remaining_seconds > 0:
                    # 只保存未过期的剩余时间
                    runtime_data.session_sleep_remaining[session] = remaining_seconds
                    logger.debug(
                        f"心念 | 会话 {session} 进入睡眠，剩余 {remaining_seconds:.0f} 秒"
                    )
                else:
                    # 已过期的不保存，退出睡眠时保持过期状态
                    logger.debug(f"心念 | 会话 {session} 进入睡眠，计时器已过期")

        # 持久化保存
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()
        self.notify_wakeup()

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
        now = self._get_now()

        for session in self.get_target_sessions():
            if not send_on_wake:
                # 模式1：跳过睡眠期间的主动消息
                # 用 refresh_session_timer 而非 set_session_next_fire_time，
                # 确保 AI 调度任务的 fire_time 不被常规间隔覆盖
                self.refresh_session_timer(session)
                logger.debug(f"心念 | 会话 {session} 睡眠结束，跳过模式，刷新计时器")
            elif wake_mode == "immediate":
                # 模式2：保持原计时器，让主循环检测到过期后立即发送
                logger.debug(
                    f"心念 | 会话 {session} 睡眠结束，立即发送模式，保持原计时器"
                )
            else:
                # 模式3：恢复剩余计时，延后发送
                remaining = runtime_data.session_sleep_remaining.get(session)
                if remaining is not None and remaining > 0:
                    # 有剩余时间：延后发送
                    new_fire = now + timedelta(seconds=remaining)
                    self.set_session_next_fire_time(session, new_fire)
                    logger.debug(
                        f"心念 | 会话 {session} 睡眠结束，延后模式，恢复计时：{new_fire.strftime('%H:%M:%S')}"
                    )
                else:
                    # 无剩余时间记录（进入睡眠前已过期）：保持过期状态，立即发送
                    logger.debug(
                        f"心念 | 会话 {session} 睡眠结束，延后模式，计时器已过期，保持过期状态"
                    )

        # 清理 sleep_remaining
        runtime_data.session_sleep_remaining.clear()
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()
        self.notify_wakeup()
