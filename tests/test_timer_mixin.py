import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_timer_test"


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

_load_from_package("constants", "constants.py")
runtime_mod = _load_from_package("core.runtime_data", "core/runtime_data.py")
timer_mod = _load_from_package("tasks._timer_mixin", "tasks/_timer_mixin.py")

runtime_data = runtime_mod.runtime_data
TimerMixin = timer_mod.TimerMixin


class FakeTimerManager(TimerMixin):
    def __init__(self):
        self.config = {"proactive_reply": {"interval_minutes": 600}}
        self.persistence_manager = None
        self.wakeup_count = 0

    def _get_now(self):
        return datetime(2026, 1, 1, 10, 0, 0)

    def get_target_sessions(self):
        return ["session-1"]

    def get_session_target_interval(self, session: str) -> int:
        return 600

    def _get_task_fire_datetime(self, task: dict):
        return datetime.strptime(task["fire_time"], "%Y-%m-%d %H:%M:%S")

    def notify_wakeup(self):
        self.wakeup_count += 1


class TestTimerMixin(unittest.TestCase):
    def setUp(self):
        runtime_data.clear_all()

    def tearDown(self):
        runtime_data.clear_all()

    def test_ensure_all_sessions_scheduled_keeps_ai_schedule_priority(self):
        runtime_data.session_ai_scheduled["session-1"] = [
            {
                "task_id": "ai-1",
                "fire_time": "2026-01-01 10:05:00",
                "follow_up_prompt": "五分钟后提醒",
            }
        ]
        manager = FakeTimerManager()

        manager.ensure_all_sessions_scheduled()

        self.assertEqual(
            runtime_data.session_next_fire_times["session-1"],
            "2026-01-01 10:05:00",
        )
        self.assertLess(
            manager.get_session_next_fire_time("session-1"),
            manager._get_now() + timedelta(minutes=600),
        )


if __name__ == "__main__":
    unittest.main()
