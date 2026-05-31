import importlib.util
import sys
import types
import unittest
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
constants = sys.modules[f"{PKG}.constants"]
splitter_module = _load_from_package("llm.message_splitter", "llm/message_splitter.py")
MessageSplitter = splitter_module.MessageSplitter


class TestMessageSplitter(unittest.TestCase):
    def _make(self, message_split: dict) -> MessageSplitter:
        return MessageSplitter({"message_split": message_split})

    def test_backslash_mode_splits(self):
        splitter = self._make({"mode": "backslash"})
        parts, mode_display = splitter.split_message("第一句\\第二句\\第三句")
        self.assertEqual(parts, ["第一句", "第二句", "第三句"])
        self.assertIn("backslash", mode_display)

    def test_words_mode_splits_on_punctuation(self):
        splitter = self._make({"mode": "words", "split_words": ["。", "！"]})
        parts, _ = splitter.split_message("你好。在吗！")
        self.assertEqual(parts, ["你好", "在吗"])

    def test_regex_mode_splits(self):
        splitter = self._make({"mode": "regex", "regex": r".*?[，。]"})
        parts, mode_display = splitter.split_message("早上好，吃了吗。")
        self.assertEqual(parts, ["早上好，", "吃了吗。"])
        self.assertIn("正则模式", mode_display)

    def test_custom_mode_splits(self):
        splitter = self._make({"mode": "custom", "custom_pattern": r"\|"})
        parts, mode_display = splitter.split_message("a|b|c")
        self.assertEqual(parts, ["a", "b", "c"])
        self.assertIn("自定义模式", mode_display)

    def test_no_split_returns_whole_text(self):
        splitter = self._make({"mode": "backslash"})
        parts, _ = splitter.split_message("一句没有分隔符的话")
        self.assertEqual(parts, ["一句没有分隔符的话"])

    def test_redos_length_guard_skips_split_for_custom(self):
        # 超过长度上限的文本在 custom 模式下应跳过正则分割、整条返回
        splitter = self._make({"mode": "custom", "custom_pattern": r"\|"})
        long_text = "a|" * (constants.MAX_SPLIT_TEXT_LENGTH + 10)
        parts, _ = splitter.split_message(long_text)
        self.assertEqual(parts, [long_text])

    def test_redos_length_guard_skips_split_for_regex(self):
        splitter = self._make({"mode": "regex", "regex": r".*?[，。]"})
        long_text = "字，" * (constants.MAX_SPLIT_TEXT_LENGTH)
        parts, _ = splitter.split_message(long_text)
        self.assertEqual(parts, [long_text])

    def test_builtin_mode_not_length_guarded(self):
        # 内置（非 custom）模式正则简单，不应触发长度保护
        splitter = self._make({"mode": "backslash"})
        long_text = "a\\b" + "c" * (constants.MAX_SPLIT_TEXT_LENGTH)
        parts, _ = splitter.split_message(long_text)
        self.assertEqual(parts[0], "a")

    def test_invalid_regex_falls_back_to_whole_text(self):
        splitter = self._make({"mode": "regex", "regex": r"([unclosed"})
        # 非法正则编译失败 -> split_regex_pattern 为 None -> 返回整条
        self.assertIsNone(splitter.split_regex_pattern)
        parts, _ = splitter.split_message("任意文本")
        self.assertEqual(parts, ["任意文本"])

    def test_risky_regex_emits_warning(self):
        # 嵌套量词应触发复杂度提示日志（不阻断编译）
        splitter_module.logger.reset_mock()
        self._make({"mode": "regex", "regex": r"(a+)+b"})
        self.assertTrue(splitter_module.logger.warning.called)


if __name__ == "__main__":
    unittest.main()
