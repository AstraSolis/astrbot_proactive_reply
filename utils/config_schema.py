"""配置 Schema 工具

将 ``_conf_schema.json`` 解析为 WebUI 配置页可消费的结构，并对前端提交的
配置值做类型校验与规整。

本模块刻意保持「纯函数 + 仅依赖标准库」，不导入 astrbot / quart / 插件内
相对模块，便于在无框架环境下单元测试。本地化文案通过调用方注入的
``translate`` 回调获取。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

# 这些字段属于运行时数据或不应在配置页展示，统一隐藏
RUNTIME_DATA_KEYS = {"session_user_info", "last_sent_times", "ai_last_sent_times"}

# 这些分组在 WebUI 有专门页签管理（如「时间表」页），不在配置页重复展示
EXCLUDED_SECTIONS = {"calendar"}

# 受支持的字段类型（其余类型按字符串处理）
_KNOWN_TYPES = {"bool", "int", "string", "text", "list"}


def load_conf_schema(schema_path: str) -> dict:
    """读取 ``_conf_schema.json``，失败时返回空字典。"""
    try:
        with open(schema_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _translate(
    translate: Optional[Callable[[str, str], str]], key: str, fallback: str
) -> str:
    """安全调用注入的本地化回调，回退到 fallback。"""
    if translate is None:
        return fallback
    try:
        value = translate(key, fallback)
    except Exception:
        return fallback
    if isinstance(value, str) and value:
        return value
    return fallback


def _field_control(field_def: dict) -> str:
    """根据 schema 字段定义推断前端控件类型。"""
    raw_type = str(field_def.get("type", "string"))
    if field_def.get("_special") == "select_provider":
        return "provider"
    if raw_type == "bool":
        return "bool"
    if raw_type == "int":
        return "int"
    if raw_type == "list":
        return "list"
    if raw_type == "text":
        return "text"
    if raw_type == "string":
        if isinstance(field_def.get("options"), list) and field_def["options"]:
            return "select"
        return "string"
    return "string"


def _normalize_value(control: str, value: Any, default: Any) -> Any:
    """将存储值规整为前端可直接渲染的类型（用于回显当前值）。"""
    if value is None:
        value = default
    if control == "bool":
        return bool(value)
    if control == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(default)
            except (TypeError, ValueError):
                return 0
    if control == "list":
        if isinstance(value, list):
            out = []
            for item in value:
                if isinstance(item, dict) and "session_id" in item:
                    out.append(str(item["session_id"]))
                else:
                    out.append("" if item is None else str(item))
            return out
        return []
    # string / text / select / provider
    return "" if value is None else str(value)


def build_field(
    section_key: str,
    field_key: str,
    field_def: dict,
    section_config: dict,
    translate: Optional[Callable[[str, str], str]] = None,
    providers: Optional[list] = None,
) -> Optional[dict]:
    """构建单个字段的描述对象；返回 None 表示该字段应被跳过。"""
    if not isinstance(field_def, dict):
        return None
    if field_def.get("invisible"):
        return None
    if field_key in RUNTIME_DATA_KEYS:
        return None

    control = _field_control(field_def)
    default = field_def.get("default")
    if control == "list" and not isinstance(default, list):
        default = []

    raw_value = (
        section_config.get(field_key, default)
        if isinstance(section_config, dict)
        else default
    )
    value = _normalize_value(control, raw_value, default)

    description = _translate(
        translate,
        f"config.{section_key}.{field_key}.description",
        str(field_def.get("description", field_key)),
    )
    hint = _translate(
        translate,
        f"config.{section_key}.{field_key}.hint",
        str(field_def.get("hint", "")),
    )

    field: dict[str, Any] = {
        "key": field_key,
        "type": str(field_def.get("type", "string")),
        "control": control,
        "description": description,
        "hint": hint,
        "default": _normalize_value(control, default, default),
        "value": value,
        "obvious_hint": bool(field_def.get("obvious_hint", False)),
    }

    if control == "select":
        options = field_def.get("options") or []
        labels = field_def.get("labels") or []
        choices = []
        for idx, opt in enumerate(options):
            label = labels[idx] if idx < len(labels) else str(opt)
            choices.append({"value": str(opt), "label": str(label)})
        field["choices"] = choices

    if control == "provider":
        provider_choices = []
        for provider in providers or []:
            if not isinstance(provider, dict):
                continue
            pid = str(provider.get("id", "") or "")
            if not pid:
                continue
            model = str(provider.get("model", "") or "")
            label = f"{model}（{pid}）" if model else pid
            provider_choices.append({"value": pid, "label": label})
        field["providers"] = provider_choices

    return field


def build_config_schema(
    schema: dict,
    config: Any,
    providers: Optional[list] = None,
    translate: Optional[Callable[[str, str], str]] = None,
) -> list:
    """构建 WebUI 配置页所需的分组结构。

    Args:
        schema: ``_conf_schema.json`` 解析后的字典。
        config: 当前插件配置（dict 风格对象）。
        providers: 模型提供商列表（用于 select_provider 字段），形如
            ``[{"id": ..., "model": ...}]``。
        translate: 本地化回调 ``(key, fallback) -> str``，由调用方绑定 locale。

    Returns:
        分组列表，每个分组形如
        ``{"key", "title", "fields": [...], "has_provider": bool}``。
    """
    providers = providers or []
    groups = []

    for section_key, section_def in schema.items():
        if section_key in EXCLUDED_SECTIONS:
            continue
        if not isinstance(section_def, dict):
            continue
        if section_def.get("type") != "object":
            continue
        items = section_def.get("items")
        if not isinstance(items, dict):
            continue

        section_config = {}
        if isinstance(config, dict) or hasattr(config, "get"):
            try:
                section_config = config.get(section_key, {}) or {}
            except Exception:
                section_config = {}
        if not isinstance(section_config, dict):
            section_config = {}

        fields = []
        has_provider = False
        for field_key, field_def in items.items():
            field = build_field(
                section_key,
                field_key,
                field_def,
                section_config,
                translate,
                providers,
            )
            if field is None:
                continue
            if field["control"] == "provider":
                has_provider = True
            fields.append(field)

        if not fields:
            continue

        title = _translate(
            translate,
            f"config.{section_key}.description",
            str(section_def.get("description", section_key)),
        )

        group = {
            "key": section_key,
            "title": title,
            "fields": fields,
            "has_provider": has_provider,
        }
        groups.append(group)

    return groups


def coerce_value(field_def: dict, raw: Any) -> tuple[bool, Any]:
    """按字段类型校验并转换单个值。

    Returns:
        ``(ok, value)``。``ok`` 为 False 时 ``value`` 为错误原因字符串。
    """
    control = _field_control(field_def)

    if control == "bool":
        if isinstance(raw, bool):
            return True, raw
        if isinstance(raw, (int, float)):
            return True, bool(raw)
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True, True
            if lowered in ("false", "0", "no", "off", ""):
                return True, False
        return False, "invalid_bool"

    if control == "int":
        if isinstance(raw, bool):
            return False, "invalid_int"
        try:
            return True, int(raw)
        except (TypeError, ValueError):
            return False, "invalid_int"

    if control == "list":
        if not isinstance(raw, list):
            return False, "invalid_list"
        cleaned = []
        for item in raw:
            if item is None:
                continue
            text = item if isinstance(item, str) else str(item)
            text = text.strip()
            if text:
                cleaned.append(text)
        return True, cleaned

    if control == "select":
        options = [str(o) for o in (field_def.get("options") or [])]
        text = "" if raw is None else str(raw)
        if options and text not in options:
            return False, "invalid_option"
        return True, text

    # provider / string / text
    return True, "" if raw is None else str(raw)


def coerce_section_values(section_def: dict, raw_values: Any) -> tuple[dict, list]:
    """校验并规整某个分组提交的配置值。

    Returns:
        ``(cleaned, errors)``。``cleaned`` 为通过校验的字段；``errors`` 为
        ``[{"key", "reason"}]`` 列表。未知 / 隐藏 / 运行时字段会被忽略。
    """
    cleaned: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    items = section_def.get("items") if isinstance(section_def, dict) else None
    if not isinstance(items, dict):
        return cleaned, errors
    if not isinstance(raw_values, dict):
        return cleaned, errors

    for field_key, raw in raw_values.items():
        field_def = items.get(field_key)
        if not isinstance(field_def, dict):
            continue
        if field_def.get("invisible"):
            continue
        if field_key in RUNTIME_DATA_KEYS:
            continue
        ok, value = coerce_value(field_def, raw)
        if ok:
            cleaned[field_key] = value
        else:
            errors.append({"key": field_key, "reason": value})

    return cleaned, errors
