import sys
import unittest
import importlib.util
from unittest.mock import MagicMock

# Mock astrbot module before loading the target module
sys.modules["astrbot"] = MagicMock()
sys.modules["astrbot.api"] = MagicMock()

# Load the module by file path to avoid triggering package initialization
spec = importlib.util.spec_from_file_location(
    "calendar_generator", "llm/calendar_generator.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules["calendar_generator"] = module
spec.loader.exec_module(module)

parse_generated_events = module.parse_generated_events
build_system_prompt = module.build_system_prompt


class TestParseGeneratedEvents(unittest.TestCase):
    def test_plain_json_array(self):
        text = '[{"month": 1, "day": 1, "text": "新年", "repeat": -1}]'
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["month"], 1)
        self.assertEqual(events[0]["day"], 1)
        self.assertEqual(events[0]["text"], "新年")
        self.assertEqual(events[0]["repeat"], -1)

    def test_json_in_code_fence(self):
        text = '```json\n[{"month": 5, "day": 20, "text": "入学日", "repeat": -1}]\n```'
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["text"], "入学日")

    def test_json_with_surrounding_text(self):
        text = '好的，以下是生成的时间表：\n[{"month": 12, "day": 25, "text": "圣诞", "repeat": -1}]\n希望对你有帮助。'
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["month"], 12)

    def test_events_wrapper_object(self):
        text = '{"events": [{"month": 2, "day": 14, "text": "情人节", "repeat": -1}]}'
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["day"], 14)

    def test_default_repeat_when_missing(self):
        text = '[{"month": 3, "day": 8, "text": "妇女节"}]'
        events = parse_generated_events(text)
        self.assertEqual(events[0]["repeat"], -1)

    def test_filters_invalid_entries(self):
        # 缺文本、月份越界、日期越界、非对象，均应被过滤
        text = (
            "["
            '{"month": 1, "day": 1, "text": ""},'
            '{"month": 13, "day": 1, "text": "非法月"},'
            '{"month": 6, "day": 40, "text": "非法日"},'
            '"not-an-object",'
            '{"month": 7, "day": 7, "text": "七夕", "repeat": -1}'
            "]"
        )
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["text"], "七夕")

    def test_string_numbers_coerced(self):
        text = '[{"month": "8", "day": "15", "text": "中秋", "repeat": "-1"}]'
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["month"], 8)
        self.assertEqual(events[0]["day"], 15)
        self.assertEqual(events[0]["repeat"], -1)

    def test_text_truncated(self):
        long_text = "节" * 500
        text = f'[{{"month": 1, "day": 1, "text": "{long_text}", "repeat": -1}}]'
        events = parse_generated_events(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0]["text"]), 200)

    def test_invalid_repeat_falls_back(self):
        text = '[{"month": 1, "day": 1, "text": "x", "repeat": "abc"}]'
        events = parse_generated_events(text)
        self.assertEqual(events[0]["repeat"], -1)

    def test_optional_year_parsed(self):
        text = '[{"month": 1, "day": 1, "text": "x", "repeat": 0, "year": 2030}]'
        events = parse_generated_events(text)
        self.assertEqual(events[0]["year"], 2030)

    def test_no_json_returns_none(self):
        self.assertIsNone(parse_generated_events("这里没有任何 JSON 内容"))

    def test_empty_input_returns_none(self):
        self.assertIsNone(parse_generated_events(""))
        self.assertIsNone(parse_generated_events(None))

    def test_non_array_json_returns_none(self):
        self.assertIsNone(parse_generated_events('{"foo": "bar"}'))

    def test_empty_array_returns_empty_list(self):
        self.assertEqual(parse_generated_events("[]"), [])


class TestBuildSystemPrompt(unittest.TestCase):
    def test_appends_year_and_limit(self):
        result = build_system_prompt("基础提示词", 2026, 40)
        self.assertIn("基础提示词", result)
        self.assertIn("2026", result)
        self.assertIn("40", result)

    def test_handles_empty_base(self):
        result = build_system_prompt("", 2026, 10)
        self.assertIn("2026", result)
        self.assertIn("10", result)


if __name__ == "__main__":
    unittest.main()
