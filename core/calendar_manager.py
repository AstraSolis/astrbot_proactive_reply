"""
时间表（日历事项）管理器

负责 ``calendar_data.yaml`` 的读写、事项 CRUD、批量清除、导入/导出与校验。
读写完成后回填 ``calendar_store`` 单例，供占位符解析（``{calendar_today}``）使用。

数据文件与运行时持久化数据同目录（``StarTools.get_data_dir`` 解析），全局共享
一份时间表（不区分会话）。历史 ``calendar_data.json`` 会在首次加载时自动迁移为
YAML（旧文件备份为 ``.json.bak``）。
"""

import datetime
import os
import uuid

import yaml
from astrbot.api import logger

from ._datafile import (
    atomic_write_yaml,
    dump_yaml_str,
    load_mapping,
    migrate_json_to_yaml,
)
from .calendar_store import (
    MAX_EVENT_TEXT_LENGTH,
    MAX_EVENTS,
    calendar_store,
    normalize_repeat,
    valid_month_day,
)

CALENDAR_FILE_NAME = "calendar_data.yaml"
LEGACY_CALENDAR_FILE_NAME = "calendar_data.json"
CALENDAR_DATA_VERSION = 1
# 基准年合理范围（防止非法年份）
MIN_YEAR = 1970
MAX_YEAR = 9999


class CalendarManager:
    """时间表管理器类"""

    def __init__(self, persistence_manager):
        """初始化时间表管理器

        Args:
            persistence_manager: 持久化管理器（复用其数据目录解析逻辑）
        """
        self.persistence_manager = persistence_manager

    # ==================== 路径 ====================

    def _calendar_file_path(self) -> str:
        plugin_data_dir = self.persistence_manager.get_plugin_data_dir()
        return os.path.join(plugin_data_dir, CALENDAR_FILE_NAME)

    def _legacy_calendar_file_path(self) -> str:
        plugin_data_dir = self.persistence_manager.get_plugin_data_dir()
        return os.path.join(plugin_data_dir, LEGACY_CALENDAR_FILE_NAME)

    # ==================== 校验 / 规整 ====================

    def normalize_event(self, raw: dict) -> dict | None:
        """将单条原始事项规整为合法结构；非法返回 None

        - text 去空白、截断到上限，空文本视为非法。
        - month/day 必须为合法的可重复日期。
        - repeat 规整为合法取值（非法回退为不重复）。
        - year 缺失或非法时回退为当前年份（对「永久重复」无影响）。
        - id 缺失时自动生成。
        """
        if not isinstance(raw, dict):
            return None

        text = str(raw.get("text", "")).strip()
        if not text:
            return None
        if len(text) > MAX_EVENT_TEXT_LENGTH:
            text = text[:MAX_EVENT_TEXT_LENGTH]

        try:
            month = int(raw.get("month"))
            day = int(raw.get("day"))
        except (TypeError, ValueError):
            return None
        if not valid_month_day(month, day):
            return None

        repeat = normalize_repeat(raw.get("repeat", 0))

        try:
            year = int(raw.get("year"))
        except (TypeError, ValueError):
            year = datetime.datetime.now().year
        if not (MIN_YEAR <= year <= MAX_YEAR):
            year = datetime.datetime.now().year

        event_id = str(raw.get("id") or "").strip() or uuid.uuid4().hex

        return {
            "id": event_id,
            "year": year,
            "month": month,
            "day": day,
            "text": text,
            "repeat": repeat,
        }

    def _normalize_events(self, raw_events) -> list:
        """规整一组事项，丢弃非法项，去重 id，限制总量"""
        if not isinstance(raw_events, list):
            return []
        normalized = []
        seen_ids = set()
        for raw in raw_events:
            event = self.normalize_event(raw)
            if event is None:
                continue
            # 保证 id 唯一
            if event["id"] in seen_ids:
                event["id"] = uuid.uuid4().hex
            seen_ids.add(event["id"])
            normalized.append(event)
            if len(normalized) >= MAX_EVENTS:
                logger.warning(f"心念 | ⚠️ 时间表事项超过上限 {MAX_EVENTS}，已截断")
                break
        return normalized

    # ==================== 读 / 写 ====================

    def load(self) -> None:
        """从 ``calendar_data.yaml`` 加载事项到内存单例（启动时调用）

        若 YAML 不存在但存在历史 ``calendar_data.json``，先一次性迁移为 YAML。
        """
        try:
            calendar_file = self._calendar_file_path()

            # 一次性迁移：旧 JSON → 新 YAML（旧文件备份为 .json.bak）
            migrate_json_to_yaml(self._legacy_calendar_file_path(), calendar_file)

            if not os.path.exists(calendar_file):
                calendar_store.set_events([])
                logger.info("心念 | ℹ️ 暂无时间表数据文件（首次运行）")
                return

            data = load_mapping(calendar_file)
            if data is None:
                return

            events = self._normalize_events(data.get("events", []))
            calendar_store.set_events(events)
            logger.info(f"心念 | ✅ 已加载 {len(events)} 条时间表事项")
        except (FileNotFoundError, OSError) as e:
            logger.info(f"心念 | ℹ️ 时间表加载: {e}")

    def save(self) -> bool:
        """将内存单例中的事项原子性写入文件

        Returns:
            是否保存成功
        """
        try:
            calendar_file = self._calendar_file_path()
            payload = self._build_payload()
            ok = atomic_write_yaml(
                calendar_file,
                payload,
                header="心念插件时间表数据（自动生成，可手动编辑）",
            )
            if ok:
                logger.debug(f"心念 | ✅ 时间表已保存到: {calendar_file}")
            return ok
        except Exception as e:
            logger.error(f"心念 | ❌ 时间表保存错误: {e}")
            return False

    def _build_payload(self) -> dict:
        """构造写入/导出用的时间表数据结构"""
        return {
            "version": CALENDAR_DATA_VERSION,
            "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": list(calendar_store.events),
        }

    # ==================== 查询 ====================

    def get_events(self) -> list:
        """返回全部事项（内存副本）"""
        return list(calendar_store.events)

    # ==================== CRUD ====================

    def add_event(self, raw: dict) -> dict | None:
        """新增一条事项；成功返回创建后的事项，失败返回 None"""
        if len(calendar_store.events) >= MAX_EVENTS:
            logger.warning(f"心念 | ⚠️ 时间表事项已达上限 {MAX_EVENTS}，拒绝新增")
            return None
        # 新增时忽略外部传入 id，始终生成新 id
        payload = dict(raw or {})
        payload.pop("id", None)
        event = self.normalize_event(payload)
        if event is None:
            return None
        calendar_store.events.append(event)
        if not self.save():
            # 回滚内存改动，保持内存与文件一致
            calendar_store.events.pop()
            return None
        return event

    def update_event(self, event_id: str, raw: dict) -> dict | None:
        """按 id 更新事项；成功返回更新后的事项，失败/未找到返回 None"""
        event_id = str(event_id or "").strip()
        if not event_id:
            return None
        for idx, existing in enumerate(calendar_store.events):
            if existing.get("id") == event_id:
                payload = dict(raw or {})
                payload["id"] = event_id
                event = self.normalize_event(payload)
                if event is None:
                    return None
                original = calendar_store.events[idx]
                calendar_store.events[idx] = event
                if not self.save():
                    calendar_store.events[idx] = original
                    return None
                return event
        return None

    def delete_event(self, event_id: str) -> bool:
        """按 id 删除事项；成功返回 True，未找到返回 False"""
        event_id = str(event_id or "").strip()
        if not event_id:
            return False
        for idx, existing in enumerate(calendar_store.events):
            if existing.get("id") == event_id:
                removed = calendar_store.events.pop(idx)
                if not self.save():
                    calendar_store.events.insert(idx, removed)
                    return False
                return True
        return False

    def clear(
        self, scope: str = "all", year: int | None = None, month: int | None = None
    ) -> int:
        """批量清除事项

        Args:
            scope: ``all``=全部；``year``=某基准年；``month``=某基准年的某月。
            year: scope 为 year/month 时的基准年。
            month: scope 为 month 时的月份。

        Returns:
            被删除的事项数量（保存失败时返回 0 且不改动）。
        """
        before = calendar_store.events
        if scope == "all":
            kept = []
        elif scope == "year" and year is not None:
            kept = [e for e in before if e.get("year") != year]
        elif scope == "month" and year is not None and month is not None:
            kept = [
                e
                for e in before
                if not (e.get("year") == year and e.get("month") == month)
            ]
        else:
            logger.warning(f"心念 | ⚠️ 非法的清除范围: scope={scope}")
            return 0

        removed_count = len(before) - len(kept)
        if removed_count <= 0:
            return 0

        calendar_store.set_events(kept)
        if not self.save():
            calendar_store.set_events(before)
            return 0
        return removed_count

    # ==================== 导入 / 导出 ====================

    def export_yaml(self) -> str:
        """将当前全部事项导出为 YAML 文本（供 WebUI 下载）"""
        payload = {
            "version": CALENDAR_DATA_VERSION,
            "events": [
                {
                    "year": e.get("year"),
                    "month": e.get("month"),
                    "day": e.get("day"),
                    "text": e.get("text"),
                    "repeat": e.get("repeat"),
                }
                for e in calendar_store.events
            ],
        }
        return dump_yaml_str(payload, header="心念插件时间表导出文件（YAML）")

    @staticmethod
    def parse_import_content(content: str):
        """解析导入文件的 YAML 文本，返回原始事项列表

        兼容两种结构：顶层为事项数组，或含 ``events`` 字段的映射。
        解析失败或结构非法返回 ``None``（由调用方区分「空表」与「非法」）。
        """
        if not isinstance(content, str) or not content.strip():
            return None
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError:
            return None
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("events"), list):
            return parsed["events"]
        return None

    def import_events(self, raw_events, mode: str = "merge") -> int:
        """导入事项

        Args:
            raw_events: 事项列表（来自 YAML 文件解析）。
            mode: ``merge``=合并到现有；``replace``=替换全部。

        Returns:
            成功导入（规整后）的事项数量；保存失败返回 -1。
        """
        incoming = self._normalize_events(raw_events)
        # 导入的事项一律重新分配 id，避免与现有冲突
        for event in incoming:
            event["id"] = uuid.uuid4().hex

        before = calendar_store.events
        if mode == "replace":
            merged = incoming
        else:
            merged = before + incoming
            if len(merged) > MAX_EVENTS:
                merged = merged[:MAX_EVENTS]
                logger.warning(f"心念 | ⚠️ 导入后超过上限 {MAX_EVENTS}，已截断")

        calendar_store.set_events(merged)
        if not self.save():
            calendar_store.set_events(before)
            return -1
        return len(incoming)
