import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "proactive_reply_i18n_test"


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


i18n = _load_from_package("utils.plugin_i18n", "utils/plugin_i18n.py")


class TestPluginI18n(unittest.TestCase):
    def setUp(self):
        i18n.clear_i18n_cache()

    def test_locale_is_whitelisted(self):
        self.assertEqual(i18n.normalize_locale("en_US"), "en-US")
        self.assertEqual(i18n.normalize_locale("../../secret"), "zh-CN")
        self.assertEqual(i18n.normalize_locale("zh-CN/../../x"), "zh-CN")

    def test_bundle_is_cached(self):
        text = i18n.t("zh-CN", "pages.webui.title", "fallback")
        self.assertNotEqual(text, "fallback")
        first = i18n._load_bundle.cache_info()

        i18n.t("zh-CN", "pages.webui.title", "fallback")
        second = i18n._load_bundle.cache_info()

        self.assertGreater(second.hits, first.hits)


if __name__ == "__main__":
    unittest.main()
