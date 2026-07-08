import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_load_mapping_bad_root_is_archived(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("- just\n- a\n- list\n")
            self.assertIsNone(datafile.load_mapping(path))
            self.assertFalse(os.path.exists(path))
            self.assertTrue(os.path.exists(path + ".corrupt"))

    def test_load_mapping_archives_parse_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("broken: [\n")

            self.assertIsNone(datafile.load_mapping(path))

            corrupt_path = path + ".corrupt"
            self.assertFalse(os.path.exists(path))
            self.assertTrue(os.path.exists(corrupt_path))
            with open(corrupt_path, encoding="utf-8") as f:
                self.assertIn("broken", f.read())

    def test_atomic_write_keeps_old_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "safe.yaml")
            self.assertTrue(datafile.atomic_write_yaml(path, {"old": True}))

            with patch.object(datafile.os, "replace", side_effect=OSError("locked")):
                self.assertFalse(datafile.atomic_write_yaml(path, {"new": True}))

            self.assertEqual(datafile.load_mapping(path), {"old": True})
            self.assertTrue(os.path.exists(path + ".tmp"))
            self.assertEqual(datafile.load_mapping(path + ".tmp"), {"new": True})

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

    def test_save_writes_session_major_yaml(self):
        """保存应写出 session-major 嵌套格式：meta.data_version 为 3.1，含 sessions"""
        with tempfile.TemporaryDirectory() as d:
            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            self.assertTrue(pm.save_persistent_data())
            yaml_path = os.path.join(d, "persistent_data.yaml")
            self.assertTrue(os.path.exists(yaml_path))
            data = datafile.load_mapping(yaml_path)
            self.assertIn("meta", data)
            self.assertIn("sessions", data)
            self.assertIsInstance(data["sessions"], dict)
            self.assertEqual(data["meta"]["data_version"], "3.1")
            # 旧的扁平字段不再出现在顶层
            self.assertNotIn("session_user_info", data)

    def test_session_major_roundtrip_preserves_runtime_data(self):
        """内存 → session-major 文件 → 内存 应保持各会话数据一致"""
        runtime_data.clear_all()
        session = "aiocqhttp:FriendMessage:10086"
        runtime_data.session_user_info[session] = {
            "username": "小李",
            "user_id": "10086",
            "platform": "aiocqhttp",
            "chat_type": "私聊",
            "last_active_time": "2026-01-01 09:00:00",
        }
        runtime_data.ai_last_sent_times[session] = "2026-01-01 09:05:00"
        runtime_data.last_sent_times[session] = "2026-01-01 09:04:00"
        runtime_data.session_next_fire_times[session] = "2026-01-01 10:00:00"
        runtime_data.session_last_proactive_message[session] = "在吗？\n想你了～"
        runtime_data.session_unreplied_count[session] = 2
        runtime_data.timezone_signature = "Asia/Shanghai"
        runtime_data.timing_config_signature = "fixed_interval|300"

        with tempfile.TemporaryDirectory() as d:
            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            self.assertTrue(pm.save_persistent_data())

            runtime_data.clear_all()
            pm.load_persistent_data()

        info = runtime_data.session_user_info[session]
        self.assertEqual(info["username"], "小李")
        self.assertEqual(info["user_id"], "10086")
        self.assertEqual(
            runtime_data.ai_last_sent_times[session], "2026-01-01 09:05:00"
        )
        self.assertEqual(runtime_data.last_sent_times[session], "2026-01-01 09:04:00")
        self.assertEqual(
            runtime_data.session_next_fire_times[session], "2026-01-01 10:00:00"
        )
        self.assertEqual(
            runtime_data.session_last_proactive_message[session], "在吗？\n想你了～"
        )
        self.assertEqual(runtime_data.session_unreplied_count[session], 2)
        self.assertEqual(runtime_data.timezone_signature, "Asia/Shanghai")
        self.assertEqual(runtime_data.timing_config_signature, "fixed_interval|300")

    def test_multiline_message_uses_block_scalar(self):
        """无行尾空白的多行消息应以字面量块样式（|）写出，提升可读性"""
        runtime_data.clear_all()
        session = "aiocqhttp:FriendMessage:42"
        runtime_data.session_last_proactive_message[session] = "第一行\n第二行 😄"

        with tempfile.TemporaryDirectory() as d:
            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            self.assertTrue(pm.save_persistent_data())
            yaml_path = os.path.join(d, "persistent_data.yaml")
            with open(yaml_path, encoding="utf-8") as f:
                text = f.read()
        self.assertIn("last_proactive_message: |", text)
        # 块样式下中文与 emoji 不应被转义
        self.assertIn("第二行 😄", text)

    def test_load_legacy_flat_format_still_supported(self):
        """读取旧的扁平格式应仍然正常（向后兼容）"""
        runtime_data.clear_all()
        with tempfile.TemporaryDirectory() as d:
            yaml_path = os.path.join(d, "persistent_data.yaml")
            flat = {
                "session_user_info": {
                    "aiocqhttp:FriendMessage:1": {
                        "username": "老张",
                        "user_id": "1",
                    }
                },
                "ai_last_sent_times": {
                    "aiocqhttp:FriendMessage:1": "2026-01-01 09:00:00"
                },
                "last_sent_times": {},
                "session_next_fire_times": {},
                "session_sleep_remaining": {},
                "timing_config_signature": "sig",
                "session_last_proactive_message": {"aiocqhttp:FriendMessage:1": "hi"},
                "session_unreplied_count": {"aiocqhttp:FriendMessage:1": 5},
                "session_consecutive_failures": {},
                "session_ai_scheduled": {},
                "timezone_signature": "Asia/Shanghai",
                "data_version": "3.0",
            }
            self.assertTrue(datafile.atomic_write_yaml(yaml_path, flat))

            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            pm.load_persistent_data()

        self.assertEqual(
            runtime_data.session_user_info["aiocqhttp:FriendMessage:1"]["username"],
            "老张",
        )
        self.assertEqual(
            runtime_data.session_unreplied_count["aiocqhttp:FriendMessage:1"], 5
        )
        self.assertEqual(runtime_data.timezone_signature, "Asia/Shanghai")

    def test_old_location_migration_does_not_overwrite_existing_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            new_dir = os.path.join(d, "new")
            os.makedirs(new_dir)
            new_yaml = os.path.join(new_dir, "persistent_data.yaml")
            self.assertTrue(datafile.atomic_write_yaml(new_yaml, {"marker": "new"}))

            base_dir = os.path.join(d, "base")
            old_dir = os.path.join(base_dir, "plugins", "astrbot_proactive_reply")
            os.makedirs(old_dir)
            old_file = os.path.join(old_dir, "persistent_data.json")
            with open(old_file, "w", encoding="utf-8") as f:
                json.dump({"marker": "old"}, f)

            context = MagicMock()
            context.get_config.return_value = types.SimpleNamespace(data_dir=base_dir)
            pm = pm_mod.PersistenceManager(config={}, context=context)
            pm.migrate_old_persistent_data(new_dir)

            self.assertEqual(datafile.load_mapping(new_yaml), {"marker": "new"})
            self.assertTrue(os.path.exists(old_file))

    def test_corrupt_yaml_does_not_fall_back_to_legacy_json_next_start(self):
        with tempfile.TemporaryDirectory() as d:
            yaml_path = os.path.join(d, "persistent_data.yaml")
            legacy_path = os.path.join(d, "persistent_data.json")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("broken: [\n")
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump({"marker": "old"}, f)

            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d

            pm.load_persistent_data()
            self.assertFalse(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(yaml_path + ".corrupt"))
            self.assertTrue(os.path.exists(os.path.join(d, ".migrated")))

            pm.load_persistent_data()
            self.assertFalse(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(legacy_path))


class TestDebouncedPersistence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        runtime_data.clear_all()

    async def test_event_loop_saves_are_debounced(self):
        """事件循环内连续保存应合并为一次 YAML 落盘。"""
        with tempfile.TemporaryDirectory() as d:
            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            pm._save_debounce_seconds = 0.01
            session = "aiocqhttp:FriendMessage:debounce"

            with patch.object(
                pm_mod,
                "atomic_write_yaml",
                wraps=datafile.atomic_write_yaml,
            ) as writer:
                for count in range(3):
                    runtime_data.session_unreplied_count[session] = count
                    self.assertTrue(pm.save_persistent_data())

                self.assertTrue(await pm.flush_pending_save())
                self.assertEqual(writer.call_count, 1)

            data = datafile.load_mapping(os.path.join(d, "persistent_data.yaml"))
            self.assertEqual(
                data["sessions"][session]["activity"]["unreplied_count"], 2
            )

    async def test_flush_pending_save_wakes_debounce_immediately(self):
        """显式 flush 不应被防抖窗口额外阻塞。"""
        with tempfile.TemporaryDirectory() as d:
            pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
            pm.get_plugin_data_dir = lambda: d
            pm._save_debounce_seconds = 60
            session = "aiocqhttp:FriendMessage:flush"

            runtime_data.session_unreplied_count[session] = 1
            self.assertTrue(pm.save_persistent_data())
            self.assertTrue(
                await asyncio.wait_for(pm.flush_pending_save(), timeout=0.2)
            )

            data = datafile.load_mapping(os.path.join(d, "persistent_data.yaml"))
            self.assertEqual(
                data["sessions"][session]["activity"]["unreplied_count"], 1
            )

    async def test_persistent_payload_is_detached_snapshot(self):
        """线程落盘前的 payload 不应继续引用运行时嵌套对象。"""
        pm = pm_mod.PersistenceManager(config={}, context=MagicMock())
        session = "aiocqhttp:FriendMessage:snapshot"
        runtime_data.session_ai_scheduled[session] = [
            {"task_id": "a", "fire_time": "2026-01-01 10:00:00"}
        ]

        payload = pm._build_persistent_payload()
        runtime_data.session_ai_scheduled[session][0]["task_id"] = "mutated"
        runtime_data.session_ai_scheduled[session].append({"task_id": "b"})

        scheduled = payload["sessions"][session]["ai_scheduled"]
        self.assertEqual(
            scheduled,
            [{"task_id": "a", "fire_time": "2026-01-01 10:00:00"}],
        )


class TestCalendarMigration(unittest.TestCase):
    def setUp(self):
        cal_mod.calendar_store.set_events([])

    def test_corrupt_calendar_yaml_is_archived_on_load(self):
        with tempfile.TemporaryDirectory() as d:
            yaml_path = os.path.join(d, "calendar_data.yaml")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("events: [\n")

            mgr = cal_mod.CalendarManager(_FakePM(d))
            mgr.load()

            self.assertFalse(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(yaml_path + ".corrupt"))
            self.assertTrue(os.path.exists(os.path.join(d, ".calendar_migrated")))

    def test_corrupt_calendar_yaml_does_not_fall_back_to_legacy_json_next_start(self):
        with tempfile.TemporaryDirectory() as d:
            yaml_path = os.path.join(d, "calendar_data.yaml")
            legacy_path = os.path.join(d, "calendar_data.json")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("events: [\n")
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": 1,
                        "events": [
                            {
                                "id": "old",
                                "year": 2026,
                                "month": 1,
                                "day": 1,
                                "text": "旧日历",
                                "repeat": 0,
                            }
                        ],
                    },
                    f,
                    ensure_ascii=False,
                )

            mgr = cal_mod.CalendarManager(_FakePM(d))
            mgr.load()
            self.assertFalse(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(yaml_path + ".corrupt"))
            self.assertTrue(os.path.exists(os.path.join(d, ".calendar_migrated")))

            cal_mod.calendar_store.set_events(
                [
                    {
                        "id": "sentinel",
                        "year": 2026,
                        "month": 2,
                        "day": 2,
                        "text": "内存哨兵",
                        "repeat": 0,
                    }
                ]
            )
            mgr.load()

            self.assertFalse(os.path.exists(yaml_path))
            self.assertTrue(os.path.exists(legacy_path))
            self.assertEqual(cal_mod.calendar_store.events, [])

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
