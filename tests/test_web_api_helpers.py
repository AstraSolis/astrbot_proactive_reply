import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_web_api_test"
_MISSING = object()


def _module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _ensure_package(name: str, path: Path | None = None) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    if path is not None:
        module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _load_web_api():
    _ensure_package(PKG, ROOT)
    for sub in ("commands", "core", "llm", "utils"):
        _ensure_package(f"{PKG}.{sub}", ROOT / sub)

    _module("quart", jsonify=lambda payload: payload, request=MagicMock())
    _module("astrbot", api=MagicMock())
    _module("astrbot.api", logger=MagicMock())

    _module(
        f"{PKG}.commands.command_catalog",
        get_command_catalog=lambda: [],
    )
    _module(f"{PKG}.constants", DEFAULT_TIME_GUIDANCE_ENABLED=True)
    _module(
        f"{PKG}.core.runtime_data",
        runtime_data=types.SimpleNamespace(
            session_ai_scheduled={},
            session_next_fire_times={},
            session_unreplied_count={},
            last_sent_times={},
            session_user_info={},
        ),
    )
    _module(
        f"{PKG}.llm.calendar_generator",
        DEFAULT_MAX_GENERATE=20,
        build_system_prompt=lambda *args, **kwargs: "",
        generate_calendar_events=lambda *args, **kwargs: [],
    )
    _module(
        f"{PKG}.llm.placeholder_utils",
        get_placeholder_catalog=lambda: [],
    )
    _module(
        f"{PKG}.utils.config_schema",
        build_config_schema=lambda *args, **kwargs: [],
        coerce_section_values=lambda *args, **kwargs: ({}, []),
        load_conf_schema=lambda *args, **kwargs: {},
    )
    _module(
        f"{PKG}.utils.plugin_i18n",
        normalize_locale=lambda locale=None: locale or "zh-CN",
        request_locale=lambda: "zh-CN",
        t=lambda locale, key, fallback="", **kwargs: fallback.format(**kwargs),
        t_list=lambda locale, key, fallback=None: fallback or [],
    )
    _module(
        f"{PKG}.utils.time_utils",
        get_now=lambda *args, **kwargs: datetime(2026, 1, 1, 0, 0, 0),
    )

    spec = importlib.util.spec_from_file_location(f"{PKG}.web_api", ROOT / "web_api.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PKG
    sys.modules[f"{PKG}.web_api"] = module
    spec.loader.exec_module(module)
    return module


class DictLikeConfig:
    """模拟 AstrBotConfig 这类 dict-like 对象。"""

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def setdefault(self, key, default=None):
        return self._data.setdefault(key, default)

    def items(self):
        return self._data.items()


class TestWebApiHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_modules = {
            name: sys.modules.get(name, _MISSING)
            for name in ("quart", "astrbot", "astrbot.api")
        }
        cls.web_api = _load_web_api()

    @classmethod
    def tearDownClass(cls):
        for name, module in cls._saved_modules.items():
            if module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_get_config_accepts_dict_like_config(self):
        config = DictLikeConfig({"proactive_reply": {"enabled": True}})
        managers = {"config_manager": types.SimpleNamespace(config=config)}

        self.assertIs(self.web_api._get_config(managers), config)

    def test_config_version_uses_dict_like_items(self):
        left = DictLikeConfig({"b": 2, "a": {"x": 1}})
        right = {"a": {"x": 1}, "b": 2}

        self.assertEqual(
            self.web_api._config_version(left),
            self.web_api._config_version(right),
        )

    def test_save_config_false_rolls_back_existing_section(self):
        config = {"proactive_reply": {"sessions": ["old"], "enabled": True}}
        existed, snapshot = self.web_api._snapshot_config_section(
            config, "proactive_reply"
        )
        config["proactive_reply"]["sessions"] = ["new"]
        manager = types.SimpleNamespace(
            save_config_safely=MagicMock(return_value=False)
        )

        self.assertFalse(
            self.web_api._save_config_or_rollback(
                manager, config, "proactive_reply", existed, snapshot
            )
        )

        self.assertEqual(
            config["proactive_reply"], {"sessions": ["old"], "enabled": True}
        )

    def test_save_config_false_removes_created_section(self):
        config = {}
        existed, snapshot = self.web_api._snapshot_config_section(
            config, "proactive_reply"
        )
        self.web_api._ensure_config_section(config, "proactive_reply")[
            "sessions"
        ] = ["new"]
        manager = types.SimpleNamespace(
            save_config_safely=MagicMock(return_value=False)
        )

        self.assertFalse(
            self.web_api._save_config_or_rollback(
                manager, config, "proactive_reply", existed, snapshot
            )
        )

        self.assertNotIn("proactive_reply", config)

    def test_save_config_exception_rolls_back_before_reraising(self):
        config = {"proactive_reply": {"sessions": ["old"]}}
        existed, snapshot = self.web_api._snapshot_config_section(
            config, "proactive_reply"
        )
        config["proactive_reply"]["sessions"] = ["new"]
        manager = types.SimpleNamespace(
            save_config_safely=MagicMock(side_effect=RuntimeError("disk full"))
        )

        with self.assertRaises(RuntimeError):
            self.web_api._save_config_or_rollback(
                manager, config, "proactive_reply", existed, snapshot
            )

        self.assertEqual(config["proactive_reply"], {"sessions": ["old"]})

    def test_ensure_config_section_rejects_unreplaceable_bad_section(self):
        config = DictLikeConfig({"proactive_reply": "bad"})

        with self.assertRaises(TypeError):
            self.web_api._ensure_config_section(config, "proactive_reply")


if __name__ == "__main__":
    unittest.main()
