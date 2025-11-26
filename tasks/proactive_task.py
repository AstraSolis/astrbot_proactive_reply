"""
定时任务管理器

负责定时主动发送消息的任务管理
"""

import asyncio
import datetime
import random
from astrbot.api import logger
from ..utils.parsers import parse_sessions_list


class ProactiveTaskManager:
    """定时任务管理器类"""

    def __init__(
        self, config: dict, context, message_generator, is_terminating_flag_getter
    ):
        """初始化任务管理器

        Args:
           config: 配置字典
            context: AstrBot上下文对象
            message_generator: 消息生成器
            is_terminating_flag_getter: 获取终止标志的函数
        """
        self.config = config
        self.context = context
        self.message_generator = message_generator
        self.is_terminating_flag_getter = is_terminating_flag_getter
        self.proactive_task = None

    async def proactive_message_loop(self):
        """定时主动发送消息的循环"""
        logger.info("定时主动发送消息循环已启动")

        while True:
            try:
                # 检查是否应该终止
                if self.should_terminate():
                    break

                # 检查功能是否启用
                if not self.is_proactive_enabled():
                    for i in range(60):
                        if self.is_terminating_flag_getter():
                            return
                        await asyncio.sleep(1)
                    continue

                # 检查是否在活跃时间段内
                if not self.is_active_time():
                    await asyncio.sleep(60)
                    continue

                # 获取目标会话列表
                sessions = self.get_target_sessions()
                if not sessions:
                    await asyncio.sleep(60)
                    continue

                # 向所有会话发送消息
                sent_count = await self.send_messages_to_sessions(sessions)

                # 计算下一次发送的等待时间
                wait_interval_minutes = self.calculate_wait_interval()

                logger.info(
                    f"发送完成 {sent_count}/{len(sessions)} 条消息，等待 {wait_interval_minutes} 分钟"
                )

                # 分段等待并检查状态变化
                wait_interval_seconds = wait_interval_minutes * 60
                should_continue = await self.wait_with_status_check(
                    wait_interval_seconds
                )

                if not should_continue:
                    break

            except asyncio.CancelledError:
                logger.info("定时主动发送消息循环已取消")
                break
            except Exception as e:
                logger.error(f"定时主动发送消息循环发生错误: {e}")
                await asyncio.sleep(60)

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

    async def send_messages_to_sessions(self, sessions: list) -> int:
        """向所有会话发送消息，返回成功发送的数量"""
        logger.info(f"开始向 {len(sessions)} 个会话发送主动消息")
        sent_count = 0

        for session in sessions:
            try:
                await self.message_generator.send_proactive_message(session)
                sent_count += 1
            except Exception as e:
                logger.error(f"向会话 {session} 发送主动消息失败: {e}")

        return sent_count

    def calculate_wait_interval(self) -> int:
        """计算下一次执行的等待时间（分钟）"""
        proactive_config = self.config.get("proactive_reply", {})
        timing_mode = proactive_config.get("timing_mode", "fixed_interval")

        if timing_mode == "random_interval":
            random_min = proactive_config.get("random_min_minutes", 600)
            random_max = proactive_config.get("random_max_minutes", 1200)
            total_interval = random.randint(random_min, random_max)
            logger.info(f"随机间隔模式：下次发送将在 {total_interval} 分钟后")
        else:
            base_interval = proactive_config.get("interval_minutes", 600)
            total_interval = base_interval

            random_delay_enabled = proactive_config.get("random_delay_enabled", False)
            if random_delay_enabled:
                min_delay = proactive_config.get("min_random_minutes", 0)
                max_delay = proactive_config.get("max_random_minutes", 30)
                random_delay = random.randint(min_delay, max_delay)
                total_interval += random_delay
                logger.info(
                    f"固定间隔模式：基础间隔 {base_interval} 分钟 + 随机延迟 {random_delay} 分钟 = {total_interval} 分钟"
                )
            else:
                logger.info(f"固定间隔模式：下次发送将在 {total_interval} 分钟后")

        return total_interval

    async def wait_with_status_check(self, total_interval: int) -> bool:
        """分段等待并检查状态变化，返回是否应该继续循环"""
        remaining_time = total_interval
        check_interval = 60

        while remaining_time > 0:
            if self.is_terminating_flag_getter():
                return False

            if self.proactive_task and self.proactive_task.cancelled():
                return False

            current_config = self.config.get("proactive_reply", {})
            if not current_config.get("enabled", False):
                return False

            wait_time = min(check_interval, remaining_time)
            await asyncio.sleep(wait_time)
            remaining_time -= wait_time

        return True

    def is_active_time(self) -> bool:
        """检查当前是否在活跃时间段内"""
        active_hours = self.config.get("proactive_reply", {}).get(
            "active_hours", "9:00-22:00"
        )

        try:
            start_time, end_time = active_hours.split("-")
            start_hour, start_min = map(int, start_time.split(":"))
            end_hour, end_min = map(int, end_time.split(":"))

            now = datetime.datetime.now()
            current_time = now.hour * 60 + now.minute
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            return start_minutes <= current_time <= end_minutes
        except Exception as e:
            logger.warning(f"活跃时间解析错误: {e}，默认为活跃状态")
            return True

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
        """重启定时主动发送任务"""
        await self.stop_proactive_task()
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
