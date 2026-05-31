"""时区与时间处理"""

from datetime import datetime, timezone as _utc_tz
from typing import Optional
from astrbot.api import logger
from ..core.runtime_data import runtime_data


class TimezoneMixin:
    """时区与时间处理"""

    def _get_astrbot_config(self):
        """安全获取 AstrBot 全局配置"""
        try:
            return self.context.get_config()
        except Exception:
            return None

    def _get_now(self) -> datetime:
        """获取当前时间（naive，已转换为配置时区的本地时间）"""
        from ..utils.time_utils import get_now

        return get_now(self.config, self._get_astrbot_config()).replace(tzinfo=None)

    def _get_timezone_signature(self) -> str:
        """生成当前时区配置的签名

        用于检测时区是否发生变化。
        """
        from ..utils.time_utils import get_tz

        tz = get_tz(self.config, self._get_astrbot_config())
        return str(tz) if tz is not None else "system_local"

    def _utc_timestamp_to_local_naive(self, utc_ts: float) -> datetime:
        """将 UTC 时间戳转换为本地配置时区的 naive datetime（与 _get_now() 同源）"""
        from ..utils.time_utils import get_tz

        utc_dt = datetime.fromtimestamp(utc_ts, tz=_utc_tz.utc)
        tz = get_tz(self.config, self._get_astrbot_config())
        if tz is not None:
            return utc_dt.astimezone(tz).replace(tzinfo=None)
        return utc_dt.astimezone().replace(tzinfo=None)

    def _get_task_fire_datetime(self, task: dict) -> Optional[datetime]:
        """从任务字典中提取触发时间（优先使用 UTC 时间戳，降级到字符串解析）"""
        utc_ts = task.get("fire_time_utc")
        if utc_ts is not None:
            try:
                return self._utc_timestamp_to_local_naive(float(utc_ts))
            except Exception:
                pass
        fire_time_str = task.get("fire_time")
        if fire_time_str:
            try:
                return datetime.strptime(fire_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return None

    def _recalculate_ai_schedule_fire_times(self, old_tz_sig: str, new_tz_sig: str):
        """时区变化后重算 AI 调度任务的 fire_time

        将旧时区下的 wall-clock 时间转换为新时区下的 wall-clock 时间，
        保证任务在同一 UTC 绝对时刻触发。
        """
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            old_tz = ZoneInfo(old_tz_sig) if old_tz_sig != "system_local" else None
            new_tz = ZoneInfo(new_tz_sig) if new_tz_sig != "system_local" else None
        except (ZoneInfoNotFoundError, KeyError) as e:
            logger.warning(
                f"心念 | ⚠️ AI 调度任务 fire_time 重算失败，无法解析时区: {e}"
            )
            return

        recalc_count = 0
        for tasks in runtime_data.session_ai_scheduled.values():
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                utc_ts = task.get("fire_time_utc")
                if utc_ts is not None:
                    # 新数据：从 UTC 时间戳直接生成新时区的显示字符串
                    try:
                        utc_dt = datetime.fromtimestamp(float(utc_ts), tz=_utc_tz.utc)
                        converted = (
                            utc_dt.astimezone(new_tz) if new_tz else utc_dt.astimezone()
                        )
                        new_str = converted.strftime("%Y-%m-%d %H:%M:%S")
                        if new_str != task.get("fire_time"):
                            task["fire_time"] = new_str
                            recalc_count += 1
                    except Exception as e:
                        logger.debug(f"心念 | AI 调度任务 fire_time_utc 重算跳过: {e}")
                    continue

                # 旧数据（无 fire_time_utc）：保留原有 wall-clock 转换逻辑
                fire_time_str = task.get("fire_time")
                if not fire_time_str:
                    continue
                try:
                    naive = datetime.strptime(fire_time_str, "%Y-%m-%d %H:%M:%S")
                    aware = (
                        naive.replace(tzinfo=old_tz) if old_tz else naive.astimezone()
                    )
                    converted = (
                        aware.astimezone(new_tz) if new_tz else aware.astimezone()
                    )
                    new_str = converted.strftime("%Y-%m-%d %H:%M:%S")
                    if new_str != fire_time_str:
                        task["fire_time"] = new_str
                        recalc_count += 1
                except Exception as e:
                    logger.debug(f"心念 | AI 调度任务 fire_time 重算跳过: {e}")

        if recalc_count:
            logger.info(f"心念 | 已重算 {recalc_count} 个 AI 调度任务的触发时间")

    def _check_and_handle_timezone_change(self):
        """检测时区变化，变化时清除计时器并重算 AI 调度任务触发时间"""
        current_tz_sig = self._get_timezone_signature()
        last_tz_sig = runtime_data.timezone_signature

        # 首次运行：仅记录签名
        if not last_tz_sig:
            runtime_data.timezone_signature = current_tz_sig
            logger.info(f"心念 | 🕐 当前有效时区: {current_tz_sig}")
            if self.persistence_manager:
                self.persistence_manager.save_persistent_data()
            return

        if current_tz_sig != last_tz_sig:
            logger.info(
                f"心念 | ⚠️ 检测到时区变化 ({last_tz_sig} → {current_tz_sig})，"
                f"清除计时器并重算 AI 调度任务触发时间"
            )
            self.clear_all_session_timers()
            self._recalculate_ai_schedule_fire_times(last_tz_sig, current_tz_sig)
            runtime_data.timezone_signature = current_tz_sig
            if self.persistence_manager:
                self.persistence_manager.save_persistent_data()
            self.notify_wakeup()
