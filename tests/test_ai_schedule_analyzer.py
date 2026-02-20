import sys
import unittest
import importlib.util
from unittest.mock import MagicMock

# Mock astrbot module before anything else
sys.modules["astrbot"] = MagicMock()
sys.modules["astrbot.api"] = MagicMock()
sys.modules["astrbot.api.event"] = MagicMock()
sys.modules["astrbot.api.star"] = MagicMock()

# Load the module by file path to avoid triggering package initialization which imports other deps
spec = importlib.util.spec_from_file_location(
    "ai_schedule_analyzer", "llm/ai_schedule_analyzer.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules["ai_schedule_analyzer"] = module
spec.loader.exec_module(module)

# Now use the module
contains_time_keywords = module.contains_time_keywords
parse_schedule_response = module.parse_schedule_response


class TestAIScheduleAnalyzer(unittest.TestCase):
    def test_contains_time_keywords(self):
        # 应该匹配的 - 发送间隔
        self.assertTrue(contains_time_keywords("40分钟后找你"))
        self.assertTrue(contains_time_keywords("五分钟后叫你"))  # 中文数字
        self.assertTrue(contains_time_keywords("12:55准时轰炸"))  # 具体时间点
        self.assertTrue(contains_time_keywords("半小时后见"))

        # 应该匹配的 - 自然语言
        self.assertTrue(contains_time_keywords("我过一会再联系你"))
        self.assertTrue(contains_time_keywords("明天早上聊"))
        self.assertTrue(contains_time_keywords("下午再找你"))
        self.assertTrue(contains_time_keywords("睡醒找你"))

        # 应该匹配的 - 口语/新增场景
        self.assertTrue(contains_time_keywords("俩小时后见"))
        self.assertTrue(contains_time_keywords("等我半个钟头"))
        self.assertTrue(contains_time_keywords("忙了一整天，之后找你"))
        self.assertTrue(contains_time_keywords("明早8:30"))

        # 不应该匹配的 - 误判场景
        self.assertFalse(contains_time_keywords("有点咸"))  # "有点"
        self.assertFalse(contains_time_keywords("我有一点建议"))  # "一点"
        self.assertFalse(contains_time_keywords("比分3:2"))  # 比分
        self.assertFalse(contains_time_keywords("照片比例16:9"))  # 比例

        # 陈述性表达（目前策略：正则召回，交由 LLM 语义判断是否为约定）
        self.assertTrue(contains_time_keywords("这本书读了半天"))

        self.assertFalse(contains_time_keywords("好的，没问题"))
        self.assertFalse(contains_time_keywords("收到！🫡 (敬礼)"))
        self.assertFalse(
            contains_time_keywords("交给我吧！我可是拥有“人肉闹钟”技能的柚木小春！")
        )
        self.assertFalse(contains_time_keywords("做个只有我的梦哦..."))

    def test_parse_schedule_response(self):
        # 正常 JSON
        api_response = '{"delay_minutes": 40, "follow_up_prompt": "约定时间已到"}'
        result = parse_schedule_response(api_response)
        self.assertIsNotNone(result)
        self.assertEqual(result["delay_minutes"], 40)
        self.assertEqual(result["follow_up_prompt"], "约定时间已到")

        # 包含多余文本的 JSON
        api_response = '```json\n{"delay_minutes": 60, "follow_up_prompt": "test"}\n```'
        result = parse_schedule_response(api_response)
        self.assertIsNotNone(result)
        self.assertEqual(result["delay_minutes"], 60)

        # 无需调度 (delay_minutes=0)
        api_response = '{"delay_minutes": 0, "follow_up_prompt": ""}'
        result = parse_schedule_response(api_response)
        self.assertIsNone(result)

        # 格式错误
        api_response = "not a json"
        result = parse_schedule_response(api_response)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
