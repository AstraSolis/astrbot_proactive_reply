"""插件国际化：加载 .astrbot-plugin/i18n 并在后端格式化文案"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_I18N_DIR = _PLUGIN_ROOT / ".astrbot-plugin" / "i18n"
_DEFAULT_LOCALE = "zh-CN"
_FALLBACK_LOCALE = "zh-CN"


def normalize_locale(locale: str | None) -> str:
    if not locale or not str(locale).strip():
        return _DEFAULT_LOCALE
    value = str(locale).strip()
    if value in ("zh", "zh_CN"):
        return "zh-CN"
    if value in ("en", "en_US"):
        return "en-US"
    return value


def _load_bundle(locale: str) -> dict[str, Any]:
    path = _I18N_DIR / f"{locale}.json"
    if not path.is_file():
        path = _I18N_DIR / f"{_FALLBACK_LOCALE}.json"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _lookup(bundle: dict[str, Any], key: str) -> Any:
    node: Any = bundle
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def t(locale: str | None, key: str, fallback: str = "", **kwargs: Any) -> str:
    """按点分 key 取文案，支持 {name} 占位符替换。"""
    loc = normalize_locale(locale)
    for candidate in (loc, _FALLBACK_LOCALE):
        bundle = _load_bundle(candidate)
        value = _lookup(bundle, key)
        if isinstance(value, str) and value:
            text = value
            break
    else:
        text = fallback or key

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def t_list(locale: str | None, key: str, fallback: list | None = None) -> list:
    """按点分 key 取「字符串数组」文案（如 select 的 labels）。

    找不到或类型不符时回退到 fallback（默认空列表）。
    """
    fb = list(fallback) if isinstance(fallback, list) else []
    loc = normalize_locale(locale)
    for candidate in (loc, _FALLBACK_LOCALE):
        bundle = _load_bundle(candidate)
        value = _lookup(bundle, key)
        if isinstance(value, list) and value:
            return [str(item) for item in value]
    return fb


def request_locale() -> str:
    """从 Quart 请求中解析 WebUI 语言（query ?locale= 或 JSON body）。"""
    try:
        from quart import request

        arg_locale = request.args.get("locale")
        if arg_locale:
            return normalize_locale(arg_locale)
        if request.is_json:
            body = request.get_json(silent=True) or {}
            if isinstance(body, dict) and body.get("locale"):
                return normalize_locale(body.get("locale"))
    except RuntimeError:
        pass
    return _DEFAULT_LOCALE
