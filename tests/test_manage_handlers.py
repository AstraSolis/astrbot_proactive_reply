import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_manage_test"


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


astrbot = types.ModuleType("astrbot")
api = types.ModuleType("astrbot.api")
api.logger = MagicMock()
event_mod = types.ModuleType("astrbot.api.event")
event_mod.AstrMessageEvent = object
sys.modules["astrbot"] = astrbot
sys.modules["astrbot.api"] = api
sys.modules["astrbot.api.event"] = event_mod

runtime_mod = _load_from_package("core.runtime_data", "core/runtime_data.py")
_load_from_package("commands.command_catalog", "commands/command_catalog.py")
manage_mod = _load_from_package(
    "commands._manage_handlers", "commands/_manage_handlers.py"
)

runtime_data = runtime_mod.runtime_data
ManageHandlersMixin = manage_mod.ManageHandlersMixin


class FakeEvent:
    def plain_result(self, text):
        return text


class FakePersistence:
    def __init__(self, save_ok=True, flush_ok=True):
        self.save_ok = save_ok
        self.flush_ok = flush_ok

    def save_persistent_data(self):
        return self.save_ok

    async def flush_pending_save(self):
        return self.flush_ok


class Handler(ManageHandlersMixin):
    def __init__(self, persistence):
        self.config = {}
        self.plugin = SimpleNamespace(
            persistence_manager=persistence,
            task_manager=SimpleNamespace(notify_wakeup=MagicMock()),
        )


async def _collect(async_iterable):
    results = []
    async for item in async_iterable:
        results.append(item)
    return results


class TestManageHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        runtime_data.clear_all()

    async def test_clear_rolls_back_when_flush_fails(self):
        runtime_data.session_user_info["session-1"] = {"username": "旧用户"}
        runtime_data.last_sent_times["session-1"] = "2026-01-01 10:00:00"
        handler = Handler(FakePersistence(save_ok=True, flush_ok=False))

        results = await _collect(handler._manage_clear(FakeEvent()))

        self.assertIn("清除失败", results[0])
        self.assertEqual(
            runtime_data.session_user_info["session-1"]["username"],
            "旧用户",
        )
        self.assertEqual(
            runtime_data.last_sent_times["session-1"],
            "2026-01-01 10:00:00",
        )
        handler.plugin.task_manager.notify_wakeup.assert_not_called()

    async def test_clear_keeps_empty_state_when_flush_succeeds(self):
        runtime_data.session_user_info["session-1"] = {"username": "旧用户"}
        handler = Handler(FakePersistence(save_ok=True, flush_ok=True))

        results = await _collect(handler._manage_clear(FakeEvent()))

        self.assertIn("已清除", results[0])
        self.assertEqual(runtime_data.session_user_info, {})
        handler.plugin.task_manager.notify_wakeup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
