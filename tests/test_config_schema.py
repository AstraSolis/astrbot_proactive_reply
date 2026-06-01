import importlib.util
import os
import sys
import unittest

# 以文件路径加载，避免触发包初始化（与其它测试一致）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "config_schema", os.path.join(_ROOT, "utils", "config_schema.py")
)
module = importlib.util.module_from_spec(spec)
sys.modules["config_schema"] = module
spec.loader.exec_module(module)

load_conf_schema = module.load_conf_schema
build_config_schema = module.build_config_schema
build_field = module.build_field
coerce_value = module.coerce_value
coerce_section_values = module.coerce_section_values


# 一个覆盖各种字段类型的精简 schema
SCHEMA = {
    "basic_settings": {
        "description": "基础设置",
        "type": "object",
        "items": {
            "timezone": {"description": "时区", "type": "string", "default": ""},
            "use_astrbot_timezone": {
                "description": "跟随 AstrBot 时区",
                "type": "bool",
                "default": False,
            },
        },
    },
    "proactive_reply": {
        "description": "主动发送",
        "type": "object",
        "items": {
            "enabled": {"type": "bool", "default": False, "obvious_hint": True},
            "interval_minutes": {"type": "int", "default": 600},
            "timing_mode": {
                "type": "string",
                "default": "fixed_interval",
                "options": ["fixed_interval", "random_interval"],
                "labels": ["固定间隔", "随机间隔"],
            },
            "proactive_prompt_list": {"type": "list", "default": []},
            "proactive_default_persona": {"type": "text", "default": "你好"},
            "use_database_fallback": {
                "type": "bool",
                "default": True,
                "invisible": True,
            },
        },
    },
    "ai_schedule": {
        "description": "AI 调度",
        "type": "object",
        "items": {
            "provider_id": {
                "type": "string",
                "default": "",
                "_special": "select_provider",
            },
        },
    },
    "_not_object": {"type": "string", "default": "x"},
}


class TestBuildConfigSchema(unittest.TestCase):
    def test_groups_built_and_invisible_skipped(self):
        config = {
            "basic_settings": {"timezone": "Asia/Shanghai"},
            "proactive_reply": {"enabled": True, "interval_minutes": 30},
        }
        groups = build_config_schema(SCHEMA, config)
        by_key = {g["key"]: g for g in groups}

        # 非 object 顶层节点被忽略
        self.assertNotIn("_not_object", by_key)
        self.assertIn("basic_settings", by_key)

        pr = by_key["proactive_reply"]
        field_keys = [f["key"] for f in pr["fields"]]
        # invisible 字段被隐藏
        self.assertNotIn("use_database_fallback", field_keys)
        self.assertIn("enabled", field_keys)

        # 当前值正确回显
        enabled = next(f for f in pr["fields"] if f["key"] == "enabled")
        self.assertEqual(enabled["value"], True)
        self.assertTrue(enabled["obvious_hint"])
        interval = next(f for f in pr["fields"] if f["key"] == "interval_minutes")
        self.assertEqual(interval["value"], 30)

    def test_excluded_sections_skipped(self):
        schema = {
            "basic_settings": SCHEMA["basic_settings"],
            "calendar": {
                "description": "时间表设置",
                "type": "object",
                "items": {
                    "enable_calendar": {"type": "bool", "default": False},
                },
            },
        }
        groups = build_config_schema(schema, {})
        keys = [g["key"] for g in groups]
        self.assertIn("basic_settings", keys)
        self.assertNotIn("calendar", keys)

    def test_control_types(self):
        groups = build_config_schema(SCHEMA, {})
        by_key = {g["key"]: g for g in groups}
        pr_fields = {f["key"]: f for f in by_key["proactive_reply"]["fields"]}
        self.assertEqual(pr_fields["enabled"]["control"], "bool")
        self.assertEqual(pr_fields["interval_minutes"]["control"], "int")
        self.assertEqual(pr_fields["timing_mode"]["control"], "select")
        self.assertEqual(pr_fields["proactive_prompt_list"]["control"], "list")
        self.assertEqual(pr_fields["proactive_default_persona"]["control"], "text")

        ai_fields = {f["key"]: f for f in by_key["ai_schedule"]["fields"]}
        self.assertEqual(ai_fields["provider_id"]["control"], "provider")
        self.assertTrue(by_key["ai_schedule"]["has_provider"])

    def test_select_choices_with_labels(self):
        groups = build_config_schema(SCHEMA, {})
        pr = next(g for g in groups if g["key"] == "proactive_reply")
        timing = next(f for f in pr["fields"] if f["key"] == "timing_mode")
        self.assertEqual(
            timing["choices"],
            [
                {"value": "fixed_interval", "label": "固定间隔"},
                {"value": "random_interval", "label": "随机间隔"},
            ],
        )

    def test_translate_callback_used(self):
        def translate(key, fallback):
            return f"T[{key}]"

        groups = build_config_schema(SCHEMA, {}, translate=translate)
        basic = next(g for g in groups if g["key"] == "basic_settings")
        self.assertEqual(basic["title"], "T[config.basic_settings.description]")
        tz = next(f for f in basic["fields"] if f["key"] == "timezone")
        self.assertEqual(
            tz["description"], "T[config.basic_settings.timezone.description]"
        )

    def test_sessions_dict_items_normalized(self):
        schema = {
            "proactive_reply": {
                "type": "object",
                "items": {"sessions": {"type": "list", "default": []}},
            }
        }
        config = {
            "proactive_reply": {
                "sessions": [{"session_id": "a:b:c"}, "x:y:z"],
            }
        }
        groups = build_config_schema(schema, config)
        field = groups[0]["fields"][0]
        self.assertEqual(field["value"], ["a:b:c", "x:y:z"])


class TestCoerceValue(unittest.TestCase):
    def test_bool(self):
        self.assertEqual(coerce_value({"type": "bool"}, True), (True, True))
        self.assertEqual(coerce_value({"type": "bool"}, "true"), (True, True))
        self.assertEqual(coerce_value({"type": "bool"}, "off"), (True, False))
        self.assertEqual(coerce_value({"type": "bool"}, 1), (True, True))
        ok, _ = coerce_value({"type": "bool"}, "maybe")
        self.assertFalse(ok)

    def test_int(self):
        self.assertEqual(coerce_value({"type": "int"}, "42"), (True, 42))
        self.assertEqual(coerce_value({"type": "int"}, 7), (True, 7))
        ok, _ = coerce_value({"type": "int"}, "abc")
        self.assertFalse(ok)
        # bool 不应被当作 int
        ok, _ = coerce_value({"type": "int"}, True)
        self.assertFalse(ok)

    def test_list(self):
        ok, value = coerce_value({"type": "list"}, ["a", " b ", "", None, 3])
        self.assertTrue(ok)
        self.assertEqual(value, ["a", "b", "3"])
        ok, _ = coerce_value({"type": "list"}, "notalist")
        self.assertFalse(ok)

    def test_select(self):
        field = {"type": "string", "options": ["a", "b"]}
        self.assertEqual(coerce_value(field, "a"), (True, "a"))
        ok, _ = coerce_value(field, "c")
        self.assertFalse(ok)

    def test_string_and_provider(self):
        self.assertEqual(coerce_value({"type": "string"}, 123), (True, "123"))
        self.assertEqual(coerce_value({"type": "text"}, None), (True, ""))
        prov = {"type": "string", "_special": "select_provider"}
        self.assertEqual(coerce_value(prov, "openai-1"), (True, "openai-1"))
        self.assertEqual(coerce_value(prov, ""), (True, ""))


class TestCoerceSectionValues(unittest.TestCase):
    def test_clean_and_ignore_unknown_invisible(self):
        section_def = SCHEMA["proactive_reply"]
        raw = {
            "enabled": "true",
            "interval_minutes": "15",
            "use_database_fallback": False,  # invisible -> ignored
            "unknown_key": "x",  # unknown -> ignored
        }
        cleaned, errors = coerce_section_values(section_def, raw)
        self.assertEqual(errors, [])
        self.assertEqual(cleaned, {"enabled": True, "interval_minutes": 15})

    def test_errors_collected(self):
        section_def = SCHEMA["proactive_reply"]
        raw = {"interval_minutes": "abc", "timing_mode": "bogus"}
        cleaned, errors = coerce_section_values(section_def, raw)
        self.assertEqual(cleaned, {})
        bad = {e["key"] for e in errors}
        self.assertEqual(bad, {"interval_minutes", "timing_mode"})

    def test_non_dict_inputs(self):
        self.assertEqual(coerce_section_values({}, {"a": 1}), ({}, []))
        self.assertEqual(
            coerce_section_values(SCHEMA["proactive_reply"], None), ({}, [])
        )


class TestLoadConfSchema(unittest.TestCase):
    def test_loads_real_schema(self):
        schema = load_conf_schema(os.path.join(_ROOT, "_conf_schema.json"))
        self.assertIn("proactive_reply", schema)
        self.assertEqual(schema["proactive_reply"]["type"], "object")

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_conf_schema("/no/such/file.json"), {})


if __name__ == "__main__":
    unittest.main()
