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
        self, config: dict, context, message_generator, user_info_manager, is_terminating_flag_getter
    ):
        """初始化任务管理器

        Args:
            config: 配置字典
            context: AstrBot上下文对象
            message_generator: 消息生成器
            user_info_manager: 用户信息管理器
            is_terminating_flag_getter: 获取终止标志的函数
        """
        self.config = config
        self.context = context
        self.message_generator = message_generator
        self.user_info_manager = user_info_manager
        self.is_terminating_flag_getter = is_terminating_flag_getter
        self.proactive_task = None

    async def proactive_message_loop(self):
        """定时主动发送消息的循环

        新逻辑：每分钟检查各会话，只对距离AI最后消息超过配置间隔的会话发送主动消息
        """
        logger.info("定时主动发送消息循环已启动（基于AI最后消息时间计时）")

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

                # 检查每个会话，只向满足条件的会话发送消息
                sent_count = 0
                for session in sessions:
                    if self.should_terminate():
                        break

                    should_send, reason = self.should_send_to_session(session)
                    if should_send:
                        try:
                            logger.info(f"向会话 {session} 发送主动消息（原因：{reason}）")
                            await self.message_generator.send_proactive_message(session)
                            # 发送成功后清除目标间隔，下次检查时会生成新的随机值
                            self._clear_session_interval(session)
                            sent_count += 1
                        except Exception as e:
                            logger.error(f"向会话 {session} 发送主动消息失败: {e}")
                    else:
                        logger.debug(f"会话 {session} 暂不发送主动消息（原因：{reason}）")

                if sent_count > 0:
                    logger.info(f"本轮检查完成，发送了 {sent_count}/{len(sessions)} 条主动消息")

                # 每分钟检查一次
                await self.wait_with_status_check(60)

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

        如果会话没有记录目标间隔，则生成一个新的随机间隔

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
            # 如果启用随机延迟，为该会话生成并记录随机延迟
            if proactive_config.get("random_delay_enabled", False):
                session_intervals = proactive_config.get("session_target_intervals", {})
                if session in session_intervals:
                    return session_intervals[session]
                else:
                    # 生成新的随机延迟
                    min_delay = proactive_config.get("min_random_minutes", 0)
                    max_delay = proactive_config.get("max_random_minutes", 30)
                    interval += random.randint(min_delay, max_delay)
                    self._save_session_interval(session, interval)
            return interval

        # 随机间隔模式：检查是否有记录的目标间隔
        session_intervals = proactive_config.get("session_target_intervals", {})
        if session in session_intervals:
            return session_intervals[session]

        # 没有记录，生成新的随机间隔
        random_min = proactive_config.get("random_min_minutes", 600)
        random_max = proactive_config.get("random_max_minutes", 1200)
        interval = random.randint(random_min, random_max)
        self._save_session_interval(session, interval)
        return interval

    def _save_session_interval(self, session: str, interval: int):
        """保存会话的目标间隔

        Args:
            session: 会话ID
            interval: 目标间隔（分钟）
        """
        if "proactive_reply" not in self.config:
            self.config["proactive_reply"] = {}
        if "session_target_intervals" not in self.config["proactive_reply"]:
            self.config["proactive_reply"]["session_target_intervals"] = {}

        self.config["proactive_reply"]["session_target_intervals"][session] = interval
        logger.debug(f"会话 {session} 的目标间隔已设置为 {interval} 分钟")

    def _clear_session_interval(self, session: str):
        """清除会话的目标间隔（发送后调用，以便下次生成新的随机值）

        Args:
            session: 会话ID
        """
        proactive_config = self.config.get("proactive_reply", {})
        session_intervals = proactive_config.get("session_target_intervals", {})
        if session in session_intervals:
            del session_intervals[session]
            logger.debug(f"已清除会话 {session} 的目标间隔")

    def should_send_to_session(self, session: str) -> tuple:
        """检查是否应该向指定会话发送主动消息

        基于AI最后一条消息的时间来判断

        Args:
            session: 会话ID

        Returns:
            (应该发送, 原因说明)
        """
        # 获取该会话的目标间隔
        interval_minutes = self.get_session_target_interval(session)
        minutes_since_last = self.user_info_manager.get_minutes_since_ai_last_message(session)

        if minutes_since_last == -1:
            # 从未发送过消息，应该发送
            return True, "首次向该会话发送主动消息"

        if minutes_since_last >= interval_minutes:
            # 距离上次消息已超过配置间隔
            return True, f"距离AI上次消息已过 {minutes_since_last} 分钟，超过目标间隔 {interval_minutes} 分钟"

        # 未到发送时间
        remaining = interval_minutes - minutes_since_last
        return False, f"距离下次发送还需 {remaining} 分钟（目标间隔 {interval_minutes} 分钟）"

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
