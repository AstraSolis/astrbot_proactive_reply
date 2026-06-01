import datetime
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_cal_test"


def _ensure_package(name: str, path: Path | None = None) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    if path is not None:
        module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _load_from_package(module_name: str, rel_path: str) -> types.ModuleType:
    _ensure_package(PKG, ROOT)
    parts = module_name.split(".")
    for idx in range(1, len(parts)):
        parent = ".".join([PKG, *parts[:idx]])
        sub = "/".join(parts[:idx])
        _ensure_package(parent, ROOT / sub if sub else ROOT)
    spec = importlib.util.spec_from_file_location(
        f"{PKG}.{module_name}", ROOT / rel_path
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = f"{PKG}.{module_name.rsplit('.', 1)[0]}"
    sys.modules[f"{PKG}.{module_name}"] = module
    spec.loader.exec_module(module)
    return module


sys.modules["astrbot"] = MagicMock()
sys.modules["astrbot.api"] = MagicMock()
sys.modules["astrbot.api.event"] = MagicMock()

cal_store_module = _load_from_package("core.calendar_store", "core/calendar_store.py")
_load_from_package("core.runtime_data", "core/runtime_data.py")
_load_from_package("utils.time_utils", "utils/time_utils.py")
ph = _load_from_package("llm.placeholder_utils", "llm/placeholder_utils.py")

calendar_store = cal_store_module.calendar_store
REPEAT_FOREVER = cal_store_module.REPEAT_FOREVER

SESSION = "aiocqhttp:FriendMessage:10001"


def _event(year, month, day, text, repeat=0, eid="e"):
    return {
        "id": eid,
        "year": year,
        "month": month,
        "day": day,
        "text": text,
        "repeat": repeat,
    }


class TestRepeatHelpers(unittest.TestCase):
    def test_valid_month_day(self):
        self.assertTrue(cal_store_module.valid_month_day(1, 1))
        self.assertTrue(cal_store_module.valid_month_day(2, 29))
        self.assertTrue(cal_store_module.valid_month_day(12, 31))
        self.assertFalse(cal_store_module.valid_month_day(0, 1))
        self.assertFalse(cal_store_module.valid_month_day(13, 1))
        self.assertFalse(cal_store_module.valid_month_day(2, 30))
        self.assertFalse(cal_store_module.valid_month_day(4, 31))

    def test_normalize_repeat(self):
        self.assertEqual(cal_store_module.normalize_repeat(0), 0)
        self.assertEqual(cal_store_module.normalize_repeat(4), 4)
        self.assertEqual(cal_store_module.normalize_repeat(-1), REPEAT_FOREVER)
        # 越界 / 非法回退为不重复
        self.assertEqual(cal_store_module.normalize_repeat(5), 0)
        self.assertEqual(cal_store_module.normalize_repeat(-2), 0)
        self.assertEqual(cal_store_module.normalize_repeat("abc"), 0)

    def test_event_active_in_year_no_repeat(self):
        ev = _event(2026, 1, 1, "元旦", repeat=0)
        self.assertTrue(cal_store_module.event_active_in_year(ev, 2026))
        self.assertFalse(cal_store_module.event_active_in_year(ev, 2025))
        self.assertFalse(cal_store_module.event_active_in_year(ev, 2027))

    def test_event_active_in_year_n_years(self):
        # 基准年 + 之后 N 年，共 N+1 年生效（repeat=2 → 2026/2027/2028）
        ev = _event(2026, 5, 1, "纪念", repeat=2)
        self.assertFalse(cal_store_module.event_active_in_year(ev, 2025))
        self.assertTrue(cal_store_module.event_active_in_year(ev, 2026))
        self.assertTrue(cal_store_module.event_active_in_year(ev, 2027))
        self.assertTrue(cal_store_module.event_active_in_year(ev, 2028))
        self.assertFalse(cal_store_module.event_active_in_year(ev, 2029))

    def test_event_active_in_year_forever(self):
        ev = _event(2000, 12, 25, "圣诞", repeat=REPEAT_FOREVER)
        self.assertTrue(cal_store_module.event_active_in_year(ev, 1999))
        self.assertTrue(cal_store_module.event_active_in_year(ev, 2026))
        self.assertTrue(cal_store_module.event_active_in_year(ev, 3000))


class TestCalendarStoreQuery(unittest.TestCase):
    def setUp(self):
        calendar_store.clear()

    def tearDown(self):
        calendar_store.clear()

    def test_events_for_date_filters_by_month_day_and_year(self):
        calendar_store.set_events(
            [
                _event(2026, 1, 1, "元旦", repeat=REPEAT_FOREVER, eid="a"),
                _event(2026, 1, 1, "仅2026", repeat=0, eid="b"),
                _event(2026, 2, 2, "别的日子", repeat=REPEAT_FOREVER, eid="c"),
            ]
        )
        got_2026 = [e["id"] for e in calendar_store.events_for_date(2026, 1, 1)]
        self.assertEqual(got_2026, ["a", "b"])
        # 2027 年 1/1：一次性事项 b 失效，永久事项 a 仍生效
        got_2027 = [e["id"] for e in calendar_store.events_for_date(2027, 1, 1)]
        self.assertEqual(got_2027, ["a"])

    def test_today_text_join_and_empty(self):
        calendar_store.set_events(
            [
                _event(2026, 6, 1, "事项一", repeat=REPEAT_FOREVER, eid="a"),
                _event(2026, 6, 1, "事项二", repeat=REPEAT_FOREVER, eid="b"),
            ]
        )
        now = datetime.datetime(2026, 6, 1, 8, 0, 0)
        self.assertEqual(calendar_store.today_text(now, "、", ""), "事项一、事项二")
        self.assertEqual(calendar_store.today_text(now, " / ", ""), "事项一 / 事项二")
        # 无事项时返回可配置的默认文本
        empty_now = datetime.datetime(2026, 6, 2, 8, 0, 0)
        self.assertEqual(calendar_store.today_text(empty_now, "、", ""), "")
        self.assertEqual(
            calendar_store.today_text(empty_now, "、", "今日无特殊事项"),
            "今日无特殊事项",
        )


class TestCalendarPlaceholder(unittest.TestCase):
    def setUp(self):
        calendar_store.clear()
        ph.runtime_data.session_user_info.clear()

    def tearDown(self):
        calendar_store.clear()

    def _now(self):
        # build_placeholder_map 内部用真实「今天」匹配，故事项也按今天构造
        return datetime.datetime.now()

    def test_disabled_returns_empty(self):
        today = self._now()
        calendar_store.set_events(
            [_event(today.year, today.month, today.day, "生日", repeat=REPEAT_FOREVER)]
        )
        mapping = ph.build_placeholder_map(SESSION, {"time_awareness": {}})
        self.assertEqual(mapping["calendar_today"], "")

    def test_enabled_returns_today_events(self):
        today = self._now()
        calendar_store.set_events(
            [
                _event(
                    today.year, today.month, today.day, "生日", repeat=REPEAT_FOREVER
                ),
                _event(
                    today.year, today.month, today.day, "纪念日", repeat=REPEAT_FOREVER
                ),
            ]
        )
        config = {
            "time_awareness": {"enable_calendar": True, "calendar_separator": "、"}
        }
        mapping = ph.build_placeholder_map(SESSION, config)
        self.assertEqual(mapping["calendar_today"], "生日、纪念日")

    def test_empty_text_used_when_no_events(self):
        config = {
            "time_awareness": {
                "enable_calendar": True,
                "calendar_empty_text": "今日无特殊事项",
            }
        }
        mapping = ph.build_placeholder_map(SESSION, config)
        self.assertEqual(mapping["calendar_today"], "今日无特殊事项")

    def test_event_text_with_placeholder_is_not_double_expanded(self):
        # 安全要求 2.6：事项文本中的 {username} 不应被二次替换
        today = self._now()
        calendar_store.set_events(
            [
                _event(
                    today.year,
                    today.month,
                    today.day,
                    "{username} 的生日",
                    repeat=REPEAT_FOREVER,
                )
            ]
        )
        ph.runtime_data.session_user_info[SESSION] = {
            "username": "小明",
            "user_id": "1",
            "platform": "aiocqhttp",
            "chat_type": "私聊",
            "last_active_time": "2024-01-01 10:00:00",
        }
        config = {"time_awareness": {"enable_calendar": True}}
        mapping = ph.build_placeholder_map(SESSION, config)
        out = ph.render_template("你好 {username}，今天 {calendar_today}", mapping)
        # 模板里的 {username} 被替换为小明，但事项文本里的 {username} 保留为字面量
        self.assertEqual(out, "你好 小明，今天 {username} 的生日")


if __name__ == "__main__":
    unittest.main()
