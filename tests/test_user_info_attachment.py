import importlib.util
import asyncio
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
prompt_builder_module = _load_from_package("llm.prompt_builder", "llm/prompt_builder.py")
user_info_module = _load_from_package("core.user_info_manager", "core/user_info_manager.py")
PromptBuilder = prompt_builder_module.PromptBuilder
UserInfoManager = user_info_module.UserInfoManager


@dataclass
class MockReq:
    prompt: str = ""
    system_prompt: str = "固定人格设定"
    extra_user_content_parts: list = field(default_factory=list)
    image_urls: list = field(default_factory=list)
    audio_urls: list = field(default_factory=list)


@dataclass
class MockSender:
    nickname: str = "小明"
    user_id: str = "10001"


@dataclass
class MockMessageObj:
    sender: MockSender = field(default_factory=MockSender)
    group_id: str = ""
    timestamp: int = 1717200000


class MockEvent:
    unified_msg_origin = "aiocqhttp:FriendMessage:10001"

    def __init__(self):
        self.message_obj = MockMessageObj()

    def get_sender_name(self):
        return "小明"

    def get_sender_id(self):
        return "10001"

    def get_platform_name(self):
        return "aiocqhttp"


class TestUserInfoAttachment(unittest.TestCase):
    def setUp(self):
        self.persistence_manager = MagicMock()
        self.persistence_manager.save_persistent_data.return_value = True
        self.manager = UserInfoManager({}, None, self.persistence_manager)

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

    def test_static_prompts_append_to_system_prompt(self):
        req = MockReq(system_prompt="固定人格设定")
        self.manager._append_static_system_prompt(req, "固定时间规则\n\n固定睡眠规则")

        self.assertEqual(req.system_prompt, "固定人格设定\n\n固定时间规则\n\n固定睡眠规则")
        self.assertEqual(req.extra_user_content_parts, [])

    def test_add_user_info_keeps_sleep_prompt_out_of_system_prompt(self):
        self.manager.config = {
            "user_info": {
                "enabled": True,
                "template": "[对话信息] 用户:{username},时间:{time},相对:{user_last_message_time_ago}",
            },
            "time_awareness": {
                "time_guidance_enabled": True,
                "time_guidance_prompt": "固定时间规则",
            },
        }
        self.manager._get_sleep_prompt_if_active = lambda: "睡眠时间提示"
        req = MockReq(prompt="你好", system_prompt="固定人格设定")

        asyncio.run(self.manager.add_user_info_to_request(MockEvent(), req))

        self.assertEqual(req.prompt, "你好")
        self.assertEqual(req.system_prompt, "固定人格设定\n\n固定时间规则")
        self.assertEqual(len(req.extra_user_content_parts), 2)
        self.assertTrue(req.extra_user_content_parts[0]._no_save)
        self.assertTrue(req.extra_user_content_parts[1]._no_save)
        self.assertIn("[对话信息] 用户:小明", req.extra_user_content_parts[0].text)
        self.assertEqual(req.extra_user_content_parts[1].text, "睡眠时间提示")
        self.assertNotIn("固定时间规则", req.extra_user_content_parts[0].text)
        self.assertNotIn("固定时间规则", req.extra_user_content_parts[1].text)

    def test_user_info_wraps_existing_extra_parts_before_sleep_prompt(self):
        self.manager.config = {
            "user_info": {
                "enabled": True,
                "template": "[对话信息] 用户:{username}",
            },
            "time_awareness": {"time_guidance_enabled": False},
        }
        self.manager._get_sleep_prompt_if_active = lambda: "睡眠时间提示"
        existing = MockTextPart(text="原有附带信息")
        req = MockReq(prompt="你好", extra_user_content_parts=[existing])

        asyncio.run(self.manager.add_user_info_to_request(MockEvent(), req))

        self.assertEqual(len(req.extra_user_content_parts), 3)
        self.assertIn("[对话信息] 用户:小明", req.extra_user_content_parts[0].text)
        self.assertEqual(req.extra_user_content_parts[1].text, "原有附带信息")
        self.assertEqual(req.extra_user_content_parts[2].text, "睡眠时间提示")

    def test_time_guidance_placeholders_are_not_rendered_into_system_prompt(self):
        self.manager.config = {
            "user_info": {
                "enabled": True,
                "template": "[对话信息] 相对:{user_last_message_time_ago}",
            },
            "time_awareness": {
                "time_guidance_enabled": True,
                "time_guidance_prompt": "固定时间规则 {user_last_message_time_ago}",
            },
        }
        req = MockReq(system_prompt="固定人格设定")

        asyncio.run(self.manager.add_user_info_to_request(MockEvent(), req))

        self.assertIn("固定时间规则 系统提供的用户上次发消息相对时间", req.system_prompt)
        self.assertNotIn("{user_last_message_time_ago}", req.system_prompt)
        self.assertNotIn("固定时间规则", req.extra_user_content_parts[0].text)

    def test_legacy_default_time_guidance_is_normalized(self):
        legacy_default_time_guidance = """<TIME_GUIDE: 核心时间规则（必须严格遵守）
1. 真实性：系统提供的时间信息是你唯一可信的时间来源，禁止编造或推测。
2. 自然回应：优先使用自然口语（如"刚才"、"大半夜"、"好久不见"）替代数字报时，仅在用户明确询问时提供精确时间。
3. 状态映射：依据当前时间调整人设的生理状态（如深夜困倦、饭点饥饿）。
4. 上下文感知：根据与用户上次对话的时间差（{user_last_message_time_ago}）调整语气（如很久没见要表现出想念，刚聊过则保持连贯）。>"""
        self.manager.config = {
            "user_info": {
                "enabled": True,
                "template": "[对话信息] 相对:{user_last_message_time_ago}",
            },
            "time_awareness": {
                "time_guidance_enabled": True,
                "time_guidance_prompt": legacy_default_time_guidance,
            },
        }
        req = MockReq(system_prompt="固定人格设定")

        asyncio.run(self.manager.add_user_info_to_request(MockEvent(), req))

        self.assertIn("用户上次对话时间和相对时间", req.system_prompt)
        self.assertNotIn("{user_last_message_time_ago}", req.system_prompt)


class TestStaticPromptBuilder(unittest.TestCase):
    def test_proactive_time_guidance_uses_stable_placeholders(self):
        builder = PromptBuilder(
            {
                "time_awareness": {
                    "time_guidance_enabled": True,
                    "time_guidance_prompt": "固定时间规则 {current_time} {user_last_message_time_ago}",
                },
                "proactive_reply": {},
            },
            context=None,
        )

        system_prompt = builder.build_combined_system_prompt(
            "人格",
            "",
        )

        self.assertIn("固定时间规则 系统提供的当前时间 系统提供的用户上次发消息相对时间", system_prompt)
        self.assertNotIn("主动对话", system_prompt)
        self.assertNotIn("{current_time}", system_prompt)
        self.assertNotIn("{user_last_message_time_ago}", system_prompt)


if __name__ == "__main__":
    unittest.main()
