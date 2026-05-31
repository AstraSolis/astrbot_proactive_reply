"""状态检查、间隔计算与状态信息展示"""

import random
from astrbot.api import logger
from ..utils.parsers import parse_sessions_list
from ..core.runtime_data import runtime_data


class StatusMixin:
    """状态检查、间隔计算与状态信息展示"""

    def should_terminate(self) -> bool:
        """检查是否应该终止任务"""
        if self.is_terminating_flag_getter():
            logger.info("心念 | 插件正在终止，退出定时循环")
            return True

        if self.proactive_task and self.proactive_task.cancelled():
            logger.info("心念 | 定时主动发送任务已被取消，退出循环")
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

        astrbot_config = self._get_astrbot_config()
        return check_sleep_time(self.config, astrbot_config)

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

        now = self._get_now()

        # 检查是否是 AI 调度任务
        is_ai_task = False
        ai_tasks = runtime_data.session_ai_scheduled.get(session, [])
        for task in ai_tasks:
            tf = self._get_task_fire_datetime(task)
            # 允许 1 秒误差
            if tf is not None and abs((tf - fire_time).total_seconds()) < 2:
                is_ai_task = True
                break

        suffix = " [AI调度]" if is_ai_task else ""

        if fire_time <= now:
            return f"即将发送{suffix}"

        delta = fire_time - now
        total_minutes = int(delta.total_seconds() / 60)

        if total_minutes < 60:
            return f"{total_minutes}分钟后 ({fire_time.strftime('%H:%M')}){suffix}"
        else:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            return f"{hours}小时{minutes}分钟后 ({fire_time.strftime('%H:%M')}){suffix}"

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
