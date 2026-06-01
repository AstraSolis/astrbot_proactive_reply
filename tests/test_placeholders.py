import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_ph_test"


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

runtime_module = _load_from_package("core.runtime_data", "core/runtime_data.py")
_load_from_package("utils.time_utils", "utils/time_utils.py")
ph = _load_from_package("llm.placeholder_utils", "llm/placeholder_utils.py")

runtime_data = runtime_module.runtime_data


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


SESSION = "aiocqhttp:FriendMessage:10001"


class TestPlaceholderCatalog(unittest.TestCase):
    def test_catalog_groups_and_tokens(self):
        catalog = ph.get_placeholder_catalog()
        self.assertEqual([g["key"] for g in catalog], ["user_info", "proactive"])
        for group in catalog:
            self.assertTrue(group["tokens"])
            for item in group["tokens"]:
                # 每个 token 都必须在统一注册表中声明，避免前后端漂移
                self.assertIn(item["token"], ph.PLACEHOLDER_DEFS)
                self.assertEqual(
                    item["desc"], ph.PLACEHOLDER_DEFS[item["token"]]["desc"]
                )


class TestRenderTemplate(unittest.TestCase):
    def test_replaces_known_tokens_and_keeps_unknown(self):
        out = ph.render_template("你好 {username}，未知 {nope}", {"username": "小明"})
        self.assertEqual(out, "你好 小明，未知 {nope}")

    def test_handles_regex_special_chars_in_value(self):
        # 朴素字符串替换，值含正则特殊字符不应报错或被解释
        out = ph.render_template("{x}", {"x": "a.*b$(]"})
        self.assertEqual(out, "a.*b$(]")

    def test_empty_template(self):
        self.assertEqual(ph.render_template("", {"username": "x"}), "")


class TestBuildPlaceholderMap(unittest.TestCase):
    def setUp(self):
        runtime_data.session_user_info.clear()
        runtime_data.ai_last_sent_times.clear()
        runtime_data.session_unreplied_count.clear()

    def test_without_event_uses_runtime_snapshot(self):
        runtime_data.session_user_info[SESSION] = {
            "username": "阿强",
            "user_id": "20002",
            "platform": "telegram",
            "chat_type": "群聊",
            "last_active_time": "2024-01-01 10:00:00",
        }
        runtime_data.session_unreplied_count[SESSION] = 3

        mapping = ph.build_placeholder_map(SESSION, {})

        self.assertEqual(mapping["username"], "阿强")
        # 统一后：主动提示词场景也能解析 user_id / time（历史仅「用户信息模板」有）
        self.assertEqual(mapping["user_id"], "20002")
        self.assertEqual(mapping["platform"], "telegram")
        self.assertEqual(mapping["unreplied_count"], "3")
        self.assertEqual(mapping["time"], mapping["current_time"])
        # 未提供 build_user_context_func 时不产出 user_context
        self.assertNotIn("user_context", mapping)

    def test_with_event_uses_live_identity(self):
        mapping = ph.build_placeholder_map(SESSION, {}, event=MockEvent())
        self.assertEqual(mapping["username"], "小明")
        self.assertEqual(mapping["user_id"], "10001")
        self.assertEqual(mapping["platform"], "aiocqhttp")
        self.assertEqual(mapping["chat_type"], "私聊")

    def test_user_context_included_when_builder_provided(self):
        mapping = ph.build_placeholder_map(
            SESSION, {}, build_user_context_func=lambda s: f"上下文::{s}"
        )
        self.assertEqual(mapping["user_context"], f"上下文::{SESSION}")


class TestReplacePlaceholdersUnification(unittest.TestCase):
    def setUp(self):
        runtime_data.session_user_info.clear()
        runtime_data.ai_last_sent_times.clear()
        runtime_data.session_unreplied_count.clear()
        runtime_data.session_user_info[SESSION] = {
            "username": "阿强",
            "user_id": "20002",
            "platform": "telegram",
            "chat_type": "群聊",
            "last_active_time": "2024-01-01 10:00:00",
        }

    def test_proactive_path_now_resolves_user_id_and_time(self):
        result = ph.replace_placeholders(
            "用户:{username}({user_id}) 平台:{platform} 时间:{time}",
            SESSION,
            {},
            build_user_context_func=lambda s: "ctx",
        )
        self.assertIn("用户:阿强(20002)", result)
        self.assertIn("平台:telegram", result)
        self.assertNotIn("{time}", result)
        self.assertNotIn("{user_id}", result)


class TestStabilize(unittest.TestCase):
    def test_all_registry_tokens_are_stabilized(self):
        template = " ".join("{" + tok + "}" for tok in ph.PLACEHOLDER_DEFS)
        out = ph.stabilize_static_prompt_template(template)
        for tok, meta in ph.PLACEHOLDER_DEFS.items():
            self.assertNotIn("{" + tok + "}", out)
            self.assertIn(meta["stable"], out)


if __name__ == "__main__":
    unittest.main()
