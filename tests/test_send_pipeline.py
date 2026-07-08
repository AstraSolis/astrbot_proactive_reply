import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_send_test"


class FakeMessageChain:
    def __init__(self):
        self.parts = []

    def message(self, text):
        self.parts.append(text)
        return self


def _install_astrbot_mocks():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = MagicMock()
    event = types.ModuleType("astrbot.api.event")
    event.MessageChain = FakeMessageChain

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event


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


_install_astrbot_mocks()
_load_from_package("constants", "constants.py")
runtime_mod = _load_from_package("core.runtime_data", "core/runtime_data.py")
_load_from_package("utils.time_utils", "utils/time_utils.py")
_load_from_package("llm.errors", "llm/errors.py")
_load_from_package("llm.ai_schedule_analyzer", "llm/ai_schedule_analyzer.py")
_load_from_package("llm.message_splitter", "llm/message_splitter.py")
message_generator_mod = _load_from_package(
    "llm.message_generator", "llm/message_generator.py"
)
send_retry_mod = _load_from_package(
    "tasks._send_retry_mixin", "tasks/_send_retry_mixin.py"
)

runtime_data = runtime_mod.runtime_data
MessageGenerator = message_generator_mod.MessageGenerator
MessageDeliveryError = sys.modules[f"{PKG}.llm.errors"].MessageDeliveryError
MessageGenerationError = sys.modules[f"{PKG}.llm.errors"].MessageGenerationError
SendRetryMixin = send_retry_mod.SendRetryMixin


class FakeContext:
    def __init__(self, send_result=True):
        self.send_result = send_result
        self.sent = []
        self.llm_calls = 0
        self.provider_calls = 0

    def get_config(self):
        return {}

    async def get_current_chat_provider_id(self, umo=None):
        self.provider_calls += 1
        return "provider"

    async def llm_generate(self, **kwargs):
        self.llm_calls += 1
        return SimpleNamespace(role="assistant", completion_text="你好")

    async def send_message(self, session, message_chain):
        self.sent.append((session, message_chain))
        return self.send_result


class FakePromptBuilder:
    def get_proactive_prompt(self, session, build_user_context_func):
        return "主动提示词"

    async def get_persona_system_prompt(self, session):
        return ""

    def build_combined_system_prompt(self, base_system_prompt, history_guidance):
        return base_system_prompt + history_guidance

    def replace_placeholders(self, prompt, session, config, build_user_context_func):
        return prompt


class FakeConversationManager:
    def __init__(self):
        self.history_records = []
        self.history_requests = []

    async def get_conversation_history(self, session, count):
        self.history_requests.append((session, count))
        return []

    async def add_message_to_conversation_history(self, session, message, **kwargs):
        self.history_records.append((session, message, kwargs))


class FakeUserInfoManager:
    def __init__(self):
        self.recorded_sessions = []

    def build_user_context_for_proactive(self, session):
        return ""

    def record_sent_time(self, session):
        self.recorded_sessions.append(session)


class RaisingUserInfoManager(FakeUserInfoManager):
    def record_sent_time(self, session):
        raise RuntimeError("记录发送时间失败")


class RaisingConversationManager(FakeConversationManager):
    async def add_message_to_conversation_history(self, session, message, **kwargs):
        raise RuntimeError("保存历史失败")


class TestMessageDelivery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        runtime_data.clear_all()

    async def test_send_false_raises_and_does_not_record_success_state(self):
        context = FakeContext(send_result=False)
        conversation = FakeConversationManager()
        user_info = FakeUserInfoManager()
        generator = MessageGenerator(
            {
                "message_split": {"enabled": False},
                "proactive_reply": {"duplicate_detection_enabled": True},
                "ai_schedule": {"enabled": False},
            },
            context,
            FakePromptBuilder(),
            conversation,
            user_info,
        )
        analyze_calls = []

        async def fake_analyze(session, message):
            analyze_calls.append((session, message))
            return None

        generator.analyze_message_for_schedule = fake_analyze

        with self.assertRaises(MessageDeliveryError) as raised:
            await generator.send_proactive_message("session-1", duplicate_max_retries=0)

        self.assertFalse(raised.exception.retryable)
        self.assertNotIn("session-1", runtime_data.session_last_proactive_message)
        self.assertEqual(user_info.recorded_sessions, [])
        self.assertEqual(conversation.history_records, [])
        self.assertEqual(analyze_calls, [])
        self.assertEqual(context.llm_calls, 1)

    async def test_post_delivery_recording_failure_does_not_retry_delivery(self):
        context = FakeContext(send_result=True)
        generator = MessageGenerator(
            {
                "message_split": {"enabled": False},
                "proactive_reply": {"duplicate_detection_enabled": True},
                "ai_schedule": {"enabled": False},
            },
            context,
            FakePromptBuilder(),
            RaisingConversationManager(),
            RaisingUserInfoManager(),
        )
        analyze_calls = []

        async def fake_analyze(session, message):
            analyze_calls.append((session, message))
            return {"delay_minutes": 5}

        generator.analyze_message_for_schedule = fake_analyze

        schedule = await generator.send_proactive_message(
            "session-1", duplicate_max_retries=0
        )

        self.assertEqual(schedule, {"delay_minutes": 5})
        self.assertEqual(len(context.sent), 1)
        self.assertEqual(
            runtime_data.session_last_proactive_message["session-1"], "你好"
        )
        self.assertEqual(analyze_calls, [("session-1", "你好")])

    async def test_schedule_analysis_failure_does_not_retry_delivery(self):
        context = FakeContext(send_result=True)
        generator = MessageGenerator(
            {
                "message_split": {"enabled": False},
                "proactive_reply": {"duplicate_detection_enabled": True},
                "ai_schedule": {"enabled": True},
            },
            context,
            FakePromptBuilder(),
            FakeConversationManager(),
            FakeUserInfoManager(),
        )

        async def fake_analyze(session, message):
            raise RuntimeError("调度分析失败")

        generator.analyze_message_for_schedule = fake_analyze

        schedule = await generator.send_proactive_message(
            "session-1", duplicate_max_retries=0
        )

        self.assertIsNone(schedule)
        self.assertEqual(len(context.sent), 1)
        self.assertEqual(
            runtime_data.session_last_proactive_message["session-1"], "你好"
        )

    async def test_schedule_precheck_skips_provider_and_history_for_daily_message(self):
        context = FakeContext(send_result=True)
        conversation = FakeConversationManager()
        generator = MessageGenerator(
            {
                "message_split": {"enabled": False},
                "proactive_reply": {
                    "include_history_enabled": True,
                    "history_message_count": 50,
                },
                "ai_schedule": {
                    "enabled": True,
                    "analysis_prompt": "固定分析规则",
                },
            },
            context,
            FakePromptBuilder(),
            conversation,
            FakeUserInfoManager(),
        )

        result = await generator.analyze_message_for_schedule(
            "session-1", "晚上好，再见"
        )

        self.assertIsNone(result)
        self.assertEqual(context.provider_calls, 0)
        self.assertEqual(context.llm_calls, 0)
        self.assertEqual(conversation.history_requests, [])

    async def test_schedule_analysis_caps_history_context(self):
        context = FakeContext(send_result=True)
        conversation = FakeConversationManager()
        generator = MessageGenerator(
            {
                "message_split": {"enabled": False},
                "proactive_reply": {
                    "include_history_enabled": True,
                    "history_message_count": 50,
                },
                "ai_schedule": {
                    "enabled": True,
                    "analysis_prompt": "固定分析规则",
                },
            },
            context,
            FakePromptBuilder(),
            conversation,
            FakeUserInfoManager(),
        )

        await generator.analyze_message_for_schedule("session-1", "明早8点再聊")

        self.assertEqual(context.provider_calls, 1)
        self.assertEqual(context.llm_calls, 1)
        self.assertEqual(conversation.history_requests, [("session-1", 6)])


class FakeRetryContext:
    def __init__(self):
        self.notifications = []

    async def send_message(self, session, message_chain):
        self.notifications.append((session, message_chain.parts))
        return True


class RaisingGenerator:
    def __init__(self, error):
        self.error = error
        self.calls = []

    async def send_proactive_message(self, session, **kwargs):
        self.calls.append((session, kwargs))
        raise self.error


class SuccessGenerator:
    def __init__(self):
        self.calls = []

    async def send_proactive_message(self, session, **kwargs):
        self.calls.append((session, kwargs))
        return {"delay_minutes": 10}


class FakeRetryManager(SendRetryMixin):
    def __init__(self, message_generator):
        self.message_generator = message_generator
        self.context = FakeRetryContext()
        self.persistence_manager = None
        self.set_times = []

    def _get_now(self):
        return datetime(2026, 1, 1, 10, 0, 0)

    def set_session_next_fire_time(self, session, fire_time):
        self.set_times.append((session, fire_time))
        runtime_data.session_next_fire_times[session] = fire_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


class TestSendRetryMixin(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        runtime_data.clear_all()

    async def test_retryable_failure_is_deferred_without_inline_sleep(self):
        error = MessageGenerationError("LLM 暂时失败", retryable=True)
        manager = FakeRetryManager(RaisingGenerator(error))

        success, schedule_info, retry_scheduled = await manager._send_with_retry(
            "session-1"
        )

        self.assertFalse(success)
        self.assertIsNone(schedule_info)
        self.assertTrue(retry_scheduled)
        self.assertEqual(
            runtime_data.session_next_fire_times["session-1"],
            "2026-01-01 10:01:00",
        )
        self.assertNotIn("session-1", runtime_data.session_consecutive_failures)
        self.assertEqual(
            manager._send_retry_attempts["session-1"],
            {"attempts": 1, "retry_fire_time": "2026-01-01 10:01:00"},
        )
        self.assertEqual(manager.context.notifications, [])
        self.assertEqual(
            manager.message_generator.calls[0][1]["duplicate_max_retries"], 0
        )
        self.assertFalse(
            manager.message_generator.calls[0][1]["allow_duplicate_on_exhausted"]
        )

    async def test_permanent_failure_does_not_schedule_short_retry(self):
        error = MessageGenerationError("主动提示词为空", retryable=False)
        manager = FakeRetryManager(RaisingGenerator(error))

        success, schedule_info, retry_scheduled = await manager._send_with_retry(
            "session-1"
        )

        self.assertFalse(success)
        self.assertIsNone(schedule_info)
        self.assertFalse(retry_scheduled)
        self.assertEqual(manager.set_times, [])
        self.assertEqual(runtime_data.session_consecutive_failures["session-1"], 1)
        self.assertEqual(len(manager.context.notifications), 1)

    async def test_retry_budget_exhaustion_records_one_failed_cycle(self):
        error = MessageGenerationError("LLM 暂时失败", retryable=True)
        manager = FakeRetryManager(RaisingGenerator(error))
        runtime_data.session_next_fire_times["session-1"] = "2026-01-01 10:00:00"
        manager._send_retry_attempts = {
            "session-1": {"attempts": 2, "retry_fire_time": "2026-01-01 10:00:00"}
        }

        success, schedule_info, retry_scheduled = await manager._send_with_retry(
            "session-1"
        )

        self.assertFalse(success)
        self.assertIsNone(schedule_info)
        self.assertFalse(retry_scheduled)
        self.assertEqual(manager.set_times, [])
        self.assertEqual(runtime_data.session_consecutive_failures["session-1"], 1)
        self.assertNotIn("session-1", manager._send_retry_attempts)
        self.assertIn("本轮已尝试 3 次", manager.context.notifications[0][1][0])

    async def test_final_attempt_allows_duplicate_fallback(self):
        manager = FakeRetryManager(SuccessGenerator())
        runtime_data.session_next_fire_times["session-1"] = "2026-01-01 10:00:00"
        manager._send_retry_attempts = {
            "session-1": {"attempts": 2, "retry_fire_time": "2026-01-01 10:00:00"}
        }

        success, schedule_info, retry_scheduled = await manager._send_with_retry(
            "session-1"
        )

        self.assertTrue(success)
        self.assertEqual(schedule_info, {"delay_minutes": 10})
        self.assertFalse(retry_scheduled)
        self.assertNotIn("session-1", runtime_data.session_consecutive_failures)
        self.assertNotIn("session-1", manager._send_retry_attempts)
        self.assertTrue(
            manager.message_generator.calls[0][1]["allow_duplicate_on_exhausted"]
        )

    async def test_stale_retry_state_is_ignored(self):
        manager = FakeRetryManager(SuccessGenerator())
        runtime_data.session_next_fire_times["session-1"] = "2026-01-01 11:00:00"
        manager._send_retry_attempts = {
            "session-1": {"attempts": 2, "retry_fire_time": "2026-01-01 10:00:00"}
        }

        success, schedule_info, retry_scheduled = await manager._send_with_retry(
            "session-1"
        )

        self.assertTrue(success)
        self.assertEqual(schedule_info, {"delay_minutes": 10})
        self.assertFalse(retry_scheduled)
        self.assertNotIn("session-1", manager._send_retry_attempts)
        self.assertFalse(
            manager.message_generator.calls[0][1]["allow_duplicate_on_exhausted"]
        )


if __name__ == "__main__":
    unittest.main()
