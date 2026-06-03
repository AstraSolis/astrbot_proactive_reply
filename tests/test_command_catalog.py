"""命令目录（命令系统唯一真相源）单元测试

校验目标：
- 目录结构自洽（命令/子命令字段齐全、用法前缀正确）；
- ``main.py`` 中实际注册的命令与目录完全一致（防止注册与目录漂移）；
- 各 handler 的子命令分发分支与目录子命令一一对应（防止帮助文本与实现漂移）；
- ``/proactive help`` 与子命令帮助文本覆盖目录中的全部条目；
- zh-CN / en-US 两份 i18n 均为目录中每个分类/命令/子命令提供了文案键。
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = _load_module("command_catalog", "commands/command_catalog.py")


class TestCatalogStructure(unittest.TestCase):
    def test_categories_and_commands_well_formed(self):
        catalog = cc.get_command_catalog()
        self.assertTrue(catalog)
        for category in catalog:
            self.assertTrue(category["key"])
            self.assertTrue(category["title"])
            self.assertTrue(category["commands"])
            for command in category["commands"]:
                self.assertTrue(command["name"])
                self.assertTrue(command["desc"])
                self.assertIsInstance(command["admin"], bool)
                self.assertTrue(command["usage"].startswith(f"/{cc.COMMAND_PREFIX} "))
                for sub in command["subcommands"]:
                    self.assertTrue(sub["name"])
                    self.assertTrue(sub["desc"])

    def test_command_names_are_unique(self):
        names = [cmd["name"] for _cat, cmd in cc.iter_commands()]
        self.assertEqual(len(names), len(set(names)))


class TestCatalogMatchesRegistration(unittest.TestCase):
    def test_catalog_matches_main_py_registration(self):
        main_src = (ROOT / "main.py").read_text(encoding="utf-8")
        registered = set(
            re.findall(r'@proactive_group\.command\("([^"]+)"\)', main_src)
        )
        catalog_names = {cmd["name"] for _cat, cmd in cc.iter_commands()}
        self.assertEqual(registered, catalog_names)

    def test_subcommands_match_handler_dispatch(self):
        # 目录中带子命令的命令，其子命令集合应与对应 handler 的分发分支一致。
        cases = {
            "test": "commands/_test_handlers.py",
            "show": "commands/_display_handlers.py",
            "manage": "commands/_manage_handlers.py",
        }
        for name, rel_path in cases.items():
            command = cc.get_command(name)
            self.assertIsNotNone(command)
            catalog_subs = {s["name"] for s in command["subcommands"]}
            src = (ROOT / rel_path).read_text(encoding="utf-8")
            # 形如 ``if test_type == "basic":`` / ``elif manage_type == "clear":``
            dispatched = set(re.findall(r'_type == "([^"]+)"|action == "([^"]+)"', src))
            dispatched = {a or b for a, b in dispatched}
            # show 直接用 show_type；manage 用 manage_type/action 混合，统一抽取
            dispatched |= set(re.findall(r'show_type == "([^"]+)"', src))
            self.assertEqual(
                catalog_subs,
                dispatched,
                f"{name} 子命令与 {rel_path} 分发分支不一致",
            )


class TestHelpText(unittest.TestCase):
    def test_help_text_covers_all_commands_and_subcommands(self):
        text = cc.build_help_text()
        for category in cc.get_command_catalog():
            for command in category["commands"]:
                self.assertIn(command["usage"], text)
                for sub in command["subcommands"]:
                    self.assertIn(sub["name"], text)

    def test_subcommand_help_lists_all_subcommands(self):
        for name in ("test", "show", "manage"):
            text = cc.build_subcommand_help_text(name)
            command = cc.get_command(name)
            for sub in command["subcommands"]:
                self.assertIn(sub["name"], text)
                self.assertIn(sub["desc"], text)

    def test_subcommand_help_empty_for_plain_command(self):
        self.assertEqual(cc.build_subcommand_help_text("status"), "")
        self.assertEqual(cc.build_subcommand_help_text("nonexistent"), "")


class TestI18nCoverage(unittest.TestCase):
    def _webui_bundle(self, locale: str) -> dict:
        path = ROOT / ".astrbot-plugin" / "i18n" / f"{locale}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["pages"]["webui"]

    def test_all_locales_provide_command_keys(self):
        required = set()
        for category in cc.get_command_catalog():
            required.add("cmd_cat_" + category["key"])
            for command in category["commands"]:
                required.add("cmd_desc_" + command["name"])
                for sub in command["subcommands"]:
                    required.add(f"cmd_sub_{command['name']}_{sub['name']}")
        for locale in ("zh-CN", "en-US"):
            bundle = self._webui_bundle(locale)
            missing = [key for key in required if not bundle.get(key)]
            self.assertEqual(missing, [], f"{locale} 缺少命令文案键: {missing}")


if __name__ == "__main__":
    unittest.main()
