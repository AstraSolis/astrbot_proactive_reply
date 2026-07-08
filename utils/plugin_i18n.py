"""插件国际化：加载 .astrbot-plugin/i18n 并在后端格式化文案"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_I18N_DIR = _PLUGIN_ROOT / ".astrbot-plugin" / "i18n"
_DEFAULT_LOCALE = "zh-CN"
_FALLBACK_LOCALE = "zh-CN"
_LOCALE_ALIASES = {
    "zh": "zh-CN",
    "zh_cn": "zh-CN",
    "zh-cn": "zh-CN",
    "en": "en-US",
    "en_us": "en-US",
    "en-us": "en-US",
}
_SUPPORTED_LOCALES = frozenset({"zh-CN", "en-US"})


def normalize_locale(locale: str | None) -> str:
    if not locale or not str(locale).strip():
        return _DEFAULT_LOCALE
    value = str(locale).strip()
    normalized = _LOCALE_ALIASES.get(value.lower().replace("_", "-"), value)
    return normalized if normalized in _SUPPORTED_LOCALES else _DEFAULT_LOCALE


@lru_cache(maxsize=16)
def _load_bundle(locale: str) -> dict[str, Any]:
    locale = normalize_locale(locale)
    path = _I18N_DIR / f"{locale}.json"
    try:
        # locale 已经过白名单归一化；这里再限制解析后的路径必须留在 i18n 目录内。
        path.resolve().relative_to(_I18N_DIR.resolve())
    except (OSError, ValueError):
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
    for candidate in dict.fromkeys((loc, _FALLBACK_LOCALE)):
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
    for candidate in dict.fromkeys((loc, _FALLBACK_LOCALE)):
        bundle = _load_bundle(candidate)
        value = _lookup(bundle, key)
        if isinstance(value, list) and value:
            return [str(item) for item in value]
    return fb


def clear_i18n_cache() -> None:
    """清空国际化资源缓存，供测试或热更新场景使用。"""
    _load_bundle.cache_clear()


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
