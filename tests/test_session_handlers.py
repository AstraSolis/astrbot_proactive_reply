import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_session_test"


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

_load_from_package("utils.parsers", "utils/parsers.py")
session_mod = _load_from_package(
    "commands._session_handlers", "commands/_session_handlers.py"
)
SessionHandlersMixin = session_mod.SessionHandlersMixin


class FakeEvent:
    unified_msg_origin = "aiocqhttp:FriendMessage:10001"

    def plain_result(self, text):
        return text


class Handler(SessionHandlersMixin):
    def __init__(self, config, save_ok):
        self.config = config
        self.plugin = SimpleNamespace(
            config_manager=SimpleNamespace(
                save_config_safely=MagicMock(return_value=save_ok)
            ),
            task_manager=SimpleNamespace(clear_session_timer=MagicMock()),
        )


async def _collect(async_iterable):
    results = []
    async for item in async_iterable:
        results.append(item)
    return results


class TestSessionHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_add_session_rolls_back_when_save_fails(self):
        config = {"proactive_reply": {"sessions": ["old"]}}
        handler = Handler(config, save_ok=False)

        results = await _collect(handler.add_session(FakeEvent()))

        self.assertEqual(config["proactive_reply"]["sessions"], ["old"])
        self.assertIn("配置保存失败", results[0])

    async def test_add_session_removes_created_section_when_save_fails(self):
        config = {}
        handler = Handler(config, save_ok=False)

        results = await _collect(handler.add_session(FakeEvent()))

        self.assertNotIn("proactive_reply", config)
        self.assertIn("配置保存失败", results[0])

    async def test_add_session_replaces_malformed_section_when_save_succeeds(self):
        config = {"proactive_reply": "bad"}
        handler = Handler(config, save_ok=True)

        results = await _collect(handler.add_session(FakeEvent()))

        self.assertEqual(
            config["proactive_reply"]["sessions"], [FakeEvent.unified_msg_origin]
        )
        self.assertIn("已添加会话", results[0])

    async def test_remove_session_rolls_back_and_keeps_timer_when_save_fails(self):
        session = FakeEvent.unified_msg_origin
        config = {"proactive_reply": {"sessions": [session]}}
        handler = Handler(config, save_ok=False)

        results = await _collect(handler.remove_session(FakeEvent()))

        self.assertEqual(config["proactive_reply"]["sessions"], [session])
        self.assertIn("配置保存失败", results[0])
        handler.plugin.task_manager.clear_session_timer.assert_not_called()

    async def test_remove_session_accepts_legacy_dict_items(self):
        session = FakeEvent.unified_msg_origin
        config = {"proactive_reply": {"sessions": [{"session_id": session}]}}
        handler = Handler(config, save_ok=True)

        results = await _collect(handler.remove_session(FakeEvent()))

        self.assertEqual(config["proactive_reply"]["sessions"], [])
        self.assertIn("已从主动对话列表移除", results[0])


if __name__ == "__main__":
    unittest.main()
