import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_test"


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
    spec = importlib.util.spec_from_file_location(f"{PKG}.{module_name}", ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = f"{PKG}.{module_name.rsplit('.', 1)[0]}"
    sys.modules[f"{PKG}.{module_name}"] = module
    spec.loader.exec_module(module)
    return module


sys.modules["astrbot"] = MagicMock()
sys.modules["astrbot.api"] = MagicMock()
sys.modules["astrbot.api.event"] = MagicMock()


class MockTextPart:
    def __init__(self, text: str = ""):
        self.text = text
        self._no_save = False

    def mark_as_temp(self):
        self._no_save = True
        return self


sys.modules["astrbot.core.agent.message"] = MagicMock()
sys.modules["astrbot.core.agent.message"].TextPart = MockTextPart

_load_from_package("core.runtime_data", "core/runtime_data.py")
_load_from_package("utils.time_utils", "utils/time_utils.py")
_load_from_package("llm.placeholder_utils", "llm/placeholder_utils.py")
user_info_module = _load_from_package("core.user_info_manager", "core/user_info_manager.py")
UserInfoManager = user_info_module.UserInfoManager


@dataclass
class MockReq:
    prompt: str = ""
    system_prompt: str = "固定人格设定"
    extra_user_content_parts: list = field(default_factory=list)
    image_urls: list = field(default_factory=list)
    audio_urls: list = field(default_factory=list)


class TestUserInfoAttachment(unittest.TestCase):
    def setUp(self):
        self.manager = UserInfoManager({}, None, None)

    def test_does_not_modify_system_prompt_or_user_prompt(self):
        req = MockReq(prompt="你好")
        self.manager._append_dynamic_user_content(req, "[对话信息] 时间:12:00")

        self.assertEqual(req.system_prompt, "固定人格设定")
        self.assertEqual(req.prompt, "你好")
        self.assertEqual(len(req.extra_user_content_parts), 1)
        self.assertTrue(req.extra_user_content_parts[0]._no_save)
        self.assertEqual(req.extra_user_content_parts[0].text, "[对话信息] 时间:12:00")

    def test_appends_after_existing_extra_parts(self):
        existing = MockTextPart(text="引用消息")
        req = MockReq(prompt="你好", extra_user_content_parts=[existing])
        self.manager._append_dynamic_user_content(req, "附带信息")

        self.assertEqual(len(req.extra_user_content_parts), 2)
        self.assertEqual(req.extra_user_content_parts[0].text, "引用消息")
        self.assertEqual(req.extra_user_content_parts[1].text, "附带信息")
        self.assertTrue(req.extra_user_content_parts[1]._no_save)

    def test_media_message_uses_same_append_path(self):
        req = MockReq(prompt="描述这张图片", image_urls=["http://example.com/a.png"])
        self.manager._append_dynamic_user_content(req, "[对话信息]")

        self.assertEqual(req.system_prompt, "固定人格设定")
        self.assertEqual(req.prompt, "描述这张图片")
        self.assertEqual(len(req.extra_user_content_parts), 1)
        self.assertEqual(req.extra_user_content_parts[0].text, "[对话信息]")

    def test_mark_as_temp_fallback_without_method(self):
        class LegacyTextPart:
            def __init__(self, text: str = ""):
                self.text = text

        req = MockReq()
        part = UserInfoManager._make_temp_text_part(LegacyTextPart, "[对话信息]")
        self.assertEqual(part.text, "[对话信息]")
        self.assertFalse(hasattr(part, "_no_save"))


if __name__ == "__main__":
    unittest.main()
