"""AI 自主调度任务的应用与恢复"""

import uuid
from astrbot.api import logger
from ..core.runtime_data import runtime_data


class AIScheduleMixin:
    """AI 自主调度任务的应用与恢复"""

    def apply_ai_schedule(self, session: str, schedule_info: dict):
        """应用 AI 自主调度信息

        将新任务添加到调度列表，并更新下次触发时间（如果是最早的）。

        Args:
            session: 会话ID
            schedule_info: 调度详情
        """
        # 补全 ID 和时间
        if "task_id" not in schedule_info:
            schedule_info["task_id"] = str(uuid.uuid4())
        if "created_at" not in schedule_info:
            schedule_info["created_at"] = self._get_now().strftime("%Y-%m-%d %H:%M:%S")

        # 获取或初始化列表
        if session not in runtime_data.session_ai_scheduled:
            runtime_data.session_ai_scheduled[session] = []

        # 兼容性处理：如果原来存的是 dict（旧版数据），转为 list
        current_data = runtime_data.session_ai_scheduled[session]
        if isinstance(current_data, dict):
            # 将旧数据包装进列表
            old_task = current_data
            if "task_id" not in old_task:
                old_task["task_id"] = str(uuid.uuid4())
            runtime_data.session_ai_scheduled[session] = [old_task, schedule_info]
        else:
            # 列表追加
            runtime_data.session_ai_scheduled[session].append(schedule_info)

        # 触发持久化
        if self.persistence_manager:
            self.persistence_manager.save_persistent_data()

        fire_time_str = schedule_info["fire_time"]
        delay_minutes = schedule_info["delay_minutes"]
        logger.info(
            f"心念 | 🕐 会话 {session} 添加 AI 调度任务: "
            f"{delay_minutes}分钟后（{fire_time_str}） [TaskID: {schedule_info['task_id']}]"
        )

        # 刷新计时器，确保最早的任务被排程
        self.refresh_session_timer(session)

    def _restore_ai_schedules(self):
        """恢复及迁移 AI 调度任务"""
        logger.info("心念 | 正在检查并恢复 AI 调度任务...")
        restored_count = 0

        # 遍历副本以允许修改
        all_sessions = list(runtime_data.session_ai_scheduled.items())

        for session, data in all_sessions:
            if not data:
                continue

            tasks_list = []
            # 迁移逻辑：Dict -> List
            if isinstance(data, dict):
                logger.info(f"心念 | 迁移会话 {session} 的旧版调度数据结构")
                task = data
                if "task_id" not in task:
                    task["task_id"] = str(uuid.uuid4())
                tasks_list = [task]
                runtime_data.session_ai_scheduled[session] = tasks_list
            elif isinstance(data, list):
                tasks_list = data

            if tasks_list:
                restored_count += len(tasks_list)
                # 刷新该会话的计时器，使其包含 AI 任务
                self.refresh_session_timer(session)

        if restored_count > 0:
            logger.info(f"心念 | 已恢复 {restored_count} 个 AI 调度任务")
