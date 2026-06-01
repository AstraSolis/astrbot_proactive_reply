import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_yaml_test"


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


# mock astrbot 运行时依赖
sys.modules["astrbot"] = MagicMock()
sys.modules["astrbot.api"] = MagicMock()
sys.modules["astrbot.api.star"] = MagicMock()

datafile = _load_from_package("core._datafile", "core/_datafile.py")
runtime_mod = _load_from_package("core.runtime_data", "core/runtime_data.py")
_load_from_package("core.calendar_store", "core/calendar_store.py")
_load_from_package("utils.validators", "utils/validators.py")
pm_mod = _load_from_package("core.persistence_manager", "core/persistence_manager.py")
cal_mod = _load_from_package("core.calendar_manager", "core/calendar_manager.py")

runtime_data = runtime_mod.runtime_data


class _FakePM:
    """提供 get_plugin_data_dir 的最小持久化管理器替身"""

    def __init__(self, data_dir):
        self._dir = data_dir

    def get_plugin_data_dir(self):
        return self._dir


class TestDatafileRoundTrip(unittest.TestCase):
    def test_yaml_roundtrip_preserves_types(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.yaml")
            data = {
                "aiocqhttp:GroupMessage:12345": {
                    "username": "123",
                    "user_id": "10001",
                    "flag": "true",
                    "when": "2025-01-01",
                },
                "count": {"s1": 3},
            }
            self.assertTrue(datafile.atomic_write_yaml(path, data, header="测试"))
            back = datafile.load_mapping(path)
            inner = back["aiocqhttp:GroupMessage:12345"]
            self.assertEqual(inner["username"], "123")
            self.assertIsInstance(inner["username"], str)
            self.assertIsInstance(inner["user_id"], str)
            self.assertIsInstance(inner["flag"], str)
            self.assertIsInstance(inner["when"], str)
            self.assertEqual(back["count"]["s1"], 3)
            # 头部注释存在
            with open(path, encoding="utf-8") as f:
                self.assertTrue(f.readline().startswith("# "))

    def test_load_mapping_bad_root_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("- just\n- a\n- list\n")
            self.assertIsNone(datafile.load_mapping(path))

    def test_migrate_json_to_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            json_path = os.path.join(d, "data.json")
            yaml_path = os.path.join(d, "data.yaml")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"a": 1, "b": "x"}, f)
            result = datafile.migrate_json_to_yaml(json_path, yaml_path)
            self.assertEqual(result, {"a": 1, "b": "x"})
            self.assertTrue(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(json_path + ".bak"))
            self.assertFalse(os.path.exists(json_path))
            # 幂等：再次调用不重复迁移
            self.assertIsNone(datafile.migrate_json_to_yaml(json_path, yaml_path))


class TestPersistentMigration(unittest.TestCase):
    def setUp(self):
        runtime_data.reset() if hasattr(runtime_data, "reset") else None

    def test_legacy_json_migrates_and_preserves_str_types(self):
        with tempfile.TemporaryDirectory() as d:
            legacy = os.path.join(d, "persistent_data.json")
            payload = {
                "session_user_info": {
                    "aiocqhttp:FriendMessage:10001": {
                        "username": "123",
                        "user_id": "10001",
                        "platform": "aiocqhttp",
                        "chat_type": "friend",
                    }
                },
                "ai_last_sent_times": {},
                "last_sent_times": {},
                "session_next_fire_times": {},
                "session_sleep_remaining": {},
                "timing_config_signature": "1.0",
                "session_last_proactive_message": {"s1": "no"},
                "session_unreplied_count": {"s1": 3},
                "session_consecutive_failures": {},
                "session_ai_scheduled": {},
                "timezone_signature": "8.0",
            }
            with open(legacy, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            pm.load_persistent_data()

            yaml_path = os.path.join(d, "persistent_data.yaml")
            self.assertTrue(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(legacy + ".bak"))

            info = runtime_data.session_user_info["aiocqhttp:FriendMessage:10001"]
            self.assertIsInstance(info["username"], str)
            self.assertEqual(info["username"], "123")
            self.assertIsInstance(info["user_id"], str)
            self.assertEqual(info["user_id"], "10001")
            self.assertIsInstance(runtime_data.timing_config_signature, str)
            self.assertEqual(runtime_data.session_last_proactive_message["s1"], "no")
            self.assertEqual(runtime_data.session_unreplied_count["s1"], 3)

    def test_save_writes_yaml_with_version_3(self):
        with tempfile.TemporaryDirectory() as d:
            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            self.assertTrue(pm.save_persistent_data())
            yaml_path = os.path.join(d, "persistent_data.yaml")
            self.assertTrue(os.path.exists(yaml_path))
            data = datafile.load_mapping(yaml_path)
            self.assertEqual(data["data_version"], "3.0")


class TestCalendarMigration(unittest.TestCase):
    def test_legacy_calendar_json_migrates(self):
        with tempfile.TemporaryDirectory() as d:
            legacy = os.path.join(d, "calendar_data.json")
            payload = {
                "version": 1,
                "events": [
                    {
                        "id": "a",
                        "year": 2026,
                        "month": 1,
                        "day": 1,
                        "text": "元旦",
                        "repeat": 0,
                    }
                ],
            }
            with open(legacy, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

            mgr = cal_mod.CalendarManager(_FakePM(d))
            mgr.load()
            yaml_path = os.path.join(d, "calendar_data.yaml")
            self.assertTrue(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(legacy + ".bak"))
            events = cal_mod.calendar_store.events
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["text"], "元旦")

    def test_export_import_yaml_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = cal_mod.CalendarManager(_FakePM(d))
            cal_mod.calendar_store.set_events(
                [
                    {
                        "id": "a",
                        "year": 2026,
                        "month": 5,
                        "day": 20,
                        "text": "纪念日",
                        "repeat": -1,
                    }
                ]
            )
            text = mgr.export_yaml()
            self.assertIn("纪念日", text)
            parsed = mgr.parse_import_content(text)
            self.assertIsInstance(parsed, list)
            self.assertEqual(parsed[0]["text"], "纪念日")

    def test_parse_import_content_invalid(self):
        mgr = cal_mod.CalendarManager(_FakePM("/tmp"))
        self.assertIsNone(mgr.parse_import_content(""))
        self.assertIsNone(mgr.parse_import_content("just a string"))
        self.assertIsNone(mgr.parse_import_content("key: value\n"))


class TestRuntimeTimestampNormalization(unittest.TestCase):
    """手动编辑 YAML 后，无引号时间戳会被 safe_load 转成 datetime，
    需在 load_from_dict 规整回字符串，避免下游 strptime 抛 TypeError。"""

    def setUp(self):
        runtime_data.reset() if hasattr(runtime_data, "reset") else None

    def test_timestamp_fields_coerced_back_to_str(self):
        import yaml

        text = (
            "ai_last_sent_times:\n"
            "  s1: 2025-12-29 22:00:00\n"
            "last_sent_times:\n"
            "  s1: 2025-12-29 22:00:00\n"
            "session_next_fire_times:\n"
            "  s1: 2025-12-30 09:00:00\n"
        )
        data = yaml.safe_load(text)
        # 前置：safe_load 确实把无引号时间戳转成了 datetime
        from datetime import datetime as _dt

        self.assertIsInstance(data["last_sent_times"]["s1"], _dt)

        runtime_data.load_from_dict(data)

        for field in (
            "ai_last_sent_times",
            "last_sent_times",
            "session_next_fire_times",
        ):
            value = getattr(runtime_data, field)["s1"]
            self.assertIsInstance(value, str, field)
            # 规整后应能被下游格式直接解析
            _dt.strptime(value, "%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    unittest.main()
