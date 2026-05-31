"""
定时任务管理器

负责定时主动发送消息的任务管理（混合计时器模式）。
核心编排（主循环/任务控制）留在本类，时区、计时器、睡眠、AI 调度、发送重试、状态查询等职责拆分到各 Mixin。
"""

import asyncio
from typing import Optional
from astrbot.api import logger
from ..core.runtime_data import runtime_data
from ._timezone_mixin import TimezoneMixin
from ._timer_mixin import TimerMixin
from ._sleep_mixin import SleepMixin
from ._ai_schedule_mixin import AIScheduleMixin
from ._send_retry_mixin import SendRetryMixin
from ._status_mixin import StatusMixin


class ProactiveTaskManager(
    TimezoneMixin,
    TimerMixin,
    SleepMixin,
    AIScheduleMixin,
    SendRetryMixin,
    StatusMixin,
):
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
        # 主循环可中断睡眠的唤醒事件（在 proactive_message_loop 启动时创建）
        self._wakeup_event: Optional[asyncio.Event] = None

    def notify_wakeup(self):
        """有新任务或配置变化时唤醒主循环，使其立即重新调度"""
        if self._wakeup_event is not None and not self._wakeup_event.is_set():
            self._wakeup_event.set()

    def _should_abort_sleep(self, check_sleep_time: bool = True) -> bool:
        """是否应中断当前睡眠并回到主循环"""
        if self.should_terminate() or not self.is_proactive_enabled():
            return True
        if check_sleep_time and self.is_sleep_time():
            return True
        return False

    # ==================== 主循环 ====================

    async def proactive_message_loop(self):
        """定时主动发送消息的循环（混合计时器模式）

        核心逻辑：预计算下次发送时间 + 智能睡眠
        """
        logger.info("心念 | 定时主动发送消息循环已启动（混合计时器模式）")

        self._wakeup_event = asyncio.Event()

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
                    logger.info("心念 | 进入睡眠时间段，暂停主动消息发送")
                    self.handle_enter_sleep()
                    was_sleeping = True

                if is_sleeping:
                    # 睡眠期间也需要检测配置变化，但保留睡眠状态
                    self._check_and_handle_timezone_change()
                    self._check_and_handle_config_change(preserve_sleep_state=True)

                    # 确保所有会话都有计时器（处理会话列表变化）
                    self.ensure_all_sessions_scheduled()

                    # 睡眠期间仍检查 AI 调度任务（有约定则穿透发送）
                    await self.process_due_sessions(sleep_mode=True)

                    # 智能睡眠：只关心AI调度任务，忽略常规计时器
                    sleep_duration = self.calculate_sleep_mode_smart_sleep()
                    logger.debug(f"心念 | 睡眠模式智能睡眠 {sleep_duration} 秒")
                    await self.interruptible_sleep(
                        sleep_duration, check_sleep_time=False
                    )
                    continue

                if was_sleeping and not is_sleeping:
                    # 刚退出睡眠
                    logger.info("心念 | 睡眠时间结束，恢复主动消息发送")
                    self.handle_exit_sleep()
                    was_sleeping = False

                # 检测时区和配置变化
                self._check_and_handle_timezone_change()
                self._check_and_handle_config_change()

                # 确保所有会话都有计时器
                self.ensure_all_sessions_scheduled()

                # 智能睡眠
                sleep_seconds = self.calculate_smart_sleep()
                logger.debug(f"心念 | 智能睡眠 {sleep_seconds} 秒")

                should_continue = await self.interruptible_sleep(sleep_seconds)
                if not should_continue:
                    continue  # 被中断，重新检查状态

                # 处理到期的会话
                await self.process_due_sessions()

            except asyncio.CancelledError:
                logger.info("心念 | 定时主动发送消息循环已取消")
                break
            except Exception as e:
                logger.error(f"心念 | ❌ 定时主动发送消息循环发生错误: {e}")
                await asyncio.sleep(60)

    async def interruptible_sleep(
        self, total_seconds: int, *, check_sleep_time: bool = True
    ) -> bool:
        """可中断的睡眠

        通过 Event 即时响应 AI 调度/配置变化；每段等待最长 10 秒以便检查终止等状态。

        Args:
            total_seconds: 总睡眠秒数
            check_sleep_time: 是否在进入睡眠时段时中断（睡眠模式主循环应传 False）

        Returns:
            True 如果正常完成睡眠，False 如果被提前唤醒或状态变化
        """
        if total_seconds <= 0:
            return not self._should_abort_sleep(check_sleep_time)

        if self._wakeup_event is None:
            self._wakeup_event = asyncio.Event()

        if self._wakeup_event.is_set():
            self._wakeup_event.clear()
            return False

        loop = asyncio.get_running_loop()
        deadline = loop.time() + total_seconds

        while True:
            if self._wakeup_event.is_set():
                self._wakeup_event.clear()
                return False

            if self._should_abort_sleep(check_sleep_time):
                return False

            remaining = deadline - loop.time()
            if remaining <= 0:
                return True

            chunk = min(10.0, remaining)
            try:
                await asyncio.wait_for(self._wakeup_event.wait(), timeout=chunk)
            except asyncio.TimeoutError:
                continue

            self._wakeup_event.clear()
            if self._should_abort_sleep(check_sleep_time):
                return False
            return False

    async def process_due_sessions(self, sleep_mode: bool = False):
        """处理所有到期的会话

        Args:
            sleep_mode: 睡眠模式。为 True 时跳过常规消息，只处理 AI 调度任务。
        """
        now = self._get_now()
        sent_count = 0
        sessions = self.get_target_sessions()

        for session in sessions:
            if self.should_terminate():
                break

            fire_time = self.get_session_next_fire_time(session)
            if fire_time and fire_time <= now:
                # 检查是否是 AI 调度任务触发
                ai_tasks = runtime_data.session_ai_scheduled.get(session, [])
                due_ai_task = None

                # 按时间排序找到最早的到期任务
                sorted_tasks = []
                for task in ai_tasks:
                    t = self._get_task_fire_datetime(task)
                    if t is not None:
                        sorted_tasks.append((t, task))
                sorted_tasks.sort(key=lambda x: x[0])

                # 查找已到期的任务
                for t, task in sorted_tasks:
                    if t <= now:
                        due_ai_task = task
                        break

                # 睡眠模式：跳过常规消息，只处理 AI 调度任务
                if sleep_mode and not due_ai_task:
                    continue

                # 执行发送
                override_prompt = None
                if due_ai_task:
                    override_prompt = due_ai_task.get("follow_up_prompt")
                    if sleep_mode:
                        # 睡眠时段内穿透发送，附加此背景让 LLM 知晓当前场景
                        sleep_ctx = "[系统提示：当前处于夜间休眠时段, 但有预约的跟进任务需要执行, 请据此生成合适的消息]\n"
                        override_prompt = sleep_ctx + (override_prompt or "")
                    logger.info(
                        f"心念 | 触发 AI 调度任务 [TaskID: {due_ai_task.get('task_id')}]"
                        f"{'（睡眠时段穿透）' if sleep_mode else ''}"
                    )

                success, schedule_info = await self._send_with_retry(
                    session, override_prompt=override_prompt
                )

                if success:
                    sent_count += 1
                    # 如果是 AI 任务成功执行，从列表中移除
                    if due_ai_task:
                        try:
                            # 重新获取引用以确保线程安全（虽然这里是单线程 async）
                            current_tasks = runtime_data.session_ai_scheduled.get(
                                session, []
                            )
                            # 使用 task_id 匹配删除，更稳健
                            task_id_to_remove = due_ai_task.get("task_id")
                            if task_id_to_remove:
                                runtime_data.session_ai_scheduled[session] = [
                                    t
                                    for t in current_tasks
                                    if t.get("task_id") != task_id_to_remove
                                ]
                            elif due_ai_task in current_tasks:
                                # 兼容无 ID 的旧数据
                                current_tasks.remove(due_ai_task)

                            # 触发持久化
                            if self.persistence_manager:
                                self.persistence_manager.save_persistent_data()

                        except Exception as e:
                            logger.error(f"心念 | ❌ 移除 AI 调度任务失败: {e}")

                    # 如果生成了新的 AI 调度（套娃），应用它
                    if schedule_info:
                        self.apply_ai_schedule(session, schedule_info)

                    # 刷新计时器（取常规间隔和剩余 AI 任务中的最小值）
                    self.refresh_session_timer(session)
                else:
                    # 失败逻辑：按理说应该重试或推迟？
                    # 当前 _send_with_retry 已经重试过了。
                    # 如果还是失败，暂时重置为默认间隔，避免死循环
                    next_fire = self.calculate_next_fire_time(session)
                    self.set_session_next_fire_time(session, next_fire)

        if sent_count > 0:
            logger.info(f"心念 | 本轮发送了 {sent_count}/{len(sessions)} 条主动消息")

    # ==================== 任务控制方法 ====================

    async def stop_proactive_task(self):
        """停止定时主动发送任务"""
        if not self.proactive_task or self.proactive_task.cancelled():
            logger.debug("心念 | 定时任务已停止或不存在")
            return

        logger.info("心念 | 正在停止定时主动发送任务...")
        self.proactive_task.cancel()

        try:
            await asyncio.wait_for(self.proactive_task, timeout=5.0)
        except asyncio.CancelledError:
            logger.info("心念 | ✅ 定时主动发送任务已停止")
        except asyncio.TimeoutError:
            logger.warning("心念 | ⚠️ 停止定时任务超时，任务可能仍在运行")
        except RuntimeError as e:
            logger.error(f"心念 | ❌ 任务运行时错误: {e}")
        finally:
            self.proactive_task = None
            if self._wakeup_event is not None:
                self._wakeup_event.set()
            self._wakeup_event = None

    async def start_proactive_task(self):
        """启动定时主动发送任务"""
        # 首先停止所有现有任务
        await self.force_stop_all_tasks()

        proactive_config = self.config.get("proactive_reply", {})
        enabled = proactive_config.get("enabled", False)

        if enabled:
            # 恢复 AI 调度任务
            self._restore_ai_schedules()

            self.proactive_task = asyncio.create_task(self.proactive_message_loop())
            logger.info("心念 | ✅ 定时主动发送任务已启动")

            await asyncio.sleep(0.1)

            if self.proactive_task.done():
                logger.error("心念 | ❌ 定时任务启动后立即结束，可能有错误")
                try:
                    await self.proactive_task
                except Exception as e:
                    logger.error(f"心念 | ❌ 定时任务错误: {e}")
        else:
            logger.info("心念 | 定时主动发送功能未启用")

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
        logger.info("心念 | 强制停止所有相关任务...")

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
