import sys
import unittest
import importlib.util
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

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
analyze_for_schedule = module.analyze_for_schedule


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


class TestFireTimeUtc(unittest.TestCase):
    """验证 fire_time_utc 与 fire_time 的一致性"""

    def test_utc_timestamp_roundtrip_with_timezone(self):
        """有时区时：从 UTC 时间戳可以还原出相同的本地时间字符串"""
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            self.skipTest("zoneinfo 不可用")

        tz = ZoneInfo("Asia/Shanghai")
        now_aware = datetime.now(tz=tz)
        fire_time = now_aware + timedelta(minutes=40)

        fire_time_str = fire_time.strftime("%Y-%m-%d %H:%M:%S")
        fire_time_utc = fire_time.timestamp()

        recovered = datetime.fromtimestamp(fire_time_utc, tz=timezone.utc).astimezone(tz)
        self.assertEqual(recovered.strftime("%Y-%m-%d %H:%M:%S"), fire_time_str)

    def test_utc_timestamp_roundtrip_without_timezone(self):
        """无时区时：naive datetime 经 astimezone() 转为 UTC 时间戳后可还原"""
        now_naive = datetime.now()
        fire_time = now_naive + timedelta(minutes=40)

        fire_time_str = fire_time.strftime("%Y-%m-%d %H:%M:%S")
        fire_time_utc = fire_time.astimezone().timestamp()

        recovered = datetime.fromtimestamp(fire_time_utc, tz=timezone.utc).astimezone()
        self.assertEqual(recovered.strftime("%Y-%m-%d %H:%M:%S"), fire_time_str)

    def test_utc_timestamp_is_float(self):
        """fire_time_utc 应该是 float 类型"""
        now = datetime.now()
        fire_time = now + timedelta(minutes=10)
        utc_ts = fire_time.astimezone().timestamp()
        self.assertIsInstance(utc_ts, float)

    def test_utc_timestamps_preserve_ordering(self):
        """UTC 时间戳保留时间顺序"""
        base = datetime.now()
        t1 = (base + timedelta(minutes=10)).astimezone().timestamp()
        t2 = (base + timedelta(minutes=20)).astimezone().timestamp()
        t3 = (base + timedelta(minutes=30)).astimezone().timestamp()
        self.assertLess(t1, t2)
        self.assertLess(t2, t3)


class TestSchedulePromptPlacement(unittest.TestCase):
    def test_dynamic_analysis_context_stays_out_of_system_prompt(self):
        context = MagicMock()
        context.llm_generate = AsyncMock(
            return_value=MagicMock(
                role="assistant",
                completion_text='{"delay_minutes": 40, "follow_up_prompt": "按约定跟进"}',
            )
        )

        result = asyncio.run(
            analyze_for_schedule(
                context=context,
                provider_id="main",
                ai_message="40分钟后找你",
                contexts=[],
                analysis_prompt="固定分析规则",
                current_time_str="2026-05-30 23:09:43",
                existing_tasks=[
                    {
                        "fire_time": "2026-05-31 00:00:00",
                        "follow_up_prompt": "已有约定",
                    }
                ],
            )
        )

        self.assertIsNotNone(result)
        call_kwargs = context.llm_generate.await_args.kwargs
        self.assertEqual(call_kwargs["system_prompt"], "固定分析规则")
        self.assertIn("当前时间: 2026-05-30 23:09:43", call_kwargs["prompt"])
        self.assertIn("已有约定", call_kwargs["prompt"])
        self.assertIn("40分钟后找你", call_kwargs["prompt"])
        self.assertNotIn("2026-05-30 23:09:43", call_kwargs["system_prompt"])
        self.assertNotIn("已有约定", call_kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
