"""
AI 时间表生成器

根据用户给出的主题/世界观提示词（如「异世界/魔法/节日」），发起一次 LLM 调用，
让 AI 输出一整套贴合主题的日历事项（JSON 数组），解析后交由调用方预览 / 落盘。

设计与 ``ai_schedule_analyzer`` 保持一致：
- 纯解析逻辑（``parse_generated_events``）不依赖 AstrBot context，便于单测。
- LLM 调用封装在 ``generate_calendar_events`` 中，失败不抛出而是返回 ``None``。
"""

import json
import re
from typing import Optional

from astrbot.api import logger

# 单次生成允许返回的最大事项数（防止 LLM 失控输出污染时间表）
DEFAULT_MAX_GENERATE = 40
# 单条事项文本上限（与 calendar_store.MAX_EVENT_TEXT_LENGTH 对齐，避免循环依赖此处硬编码）
_MAX_EVENT_TEXT_LENGTH = 200


def _coerce_event(raw: dict) -> Optional[dict]:
    """将单条原始事项粗规整为 ``{month, day, text, repeat}``。

    仅做类型/范围的初步处理，最终合法性仍由 ``CalendarManager.normalize_event`` 把关。
    非法（缺字段、月份/日期无法解析、文本为空）返回 ``None``。
    """
    if not isinstance(raw, dict):
        return None

    text = str(raw.get("text", "")).strip()
    if not text:
        return None
    if len(text) > _MAX_EVENT_TEXT_LENGTH:
        text = text[:_MAX_EVENT_TEXT_LENGTH]

    try:
        month = int(raw.get("month"))
        day = int(raw.get("day"))
    except (TypeError, ValueError):
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None

    try:
        repeat = int(raw.get("repeat", -1))
    except (TypeError, ValueError):
        repeat = -1

    event = {"month": month, "day": day, "text": text, "repeat": repeat}

    # 可选的基准年（缺失则由上层回填当前年份）
    year = raw.get("year")
    if year is not None:
        try:
            event["year"] = int(year)
        except (TypeError, ValueError):
            pass

    return event


def parse_generated_events(response_text: str) -> Optional[list]:
    """从 LLM 返回文本中解析出事项列表（JSON 数组）。

    兼容以下情况：
    - 纯 JSON 数组；
    - 被 ```json ... ``` 代码块包裹；
    - 数组前后带有多余说明文字。

    Args:
        response_text: LLM 返回的原始文本。

    Returns:
        粗规整后的事项列表（可能为空列表）；无法解析时返回 ``None``。
    """
    if not response_text or not isinstance(response_text, str):
        return None

    text = response_text.strip()

    # 去除 Markdown 代码块围栏
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    data = None
    # 优先整体解析
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 退而求其次：提取第一个 [...] 数组片段
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.warning(
                f"心念 | ⚠️ AI 生成时间表响应中未找到 JSON 数组: {text[:200]}"
            )
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            logger.warning(
                f"心念 | ⚠️ AI 生成时间表 JSON 解析失败: {e}, 原文: {text[:200]}"
            )
            return None

    # 兼容 {"events": [...]} 结构
    if isinstance(data, dict):
        data = data.get("events")
    if not isinstance(data, list):
        logger.warning("心念 | ⚠️ AI 生成时间表结果不是数组")
        return None

    events = []
    for raw in data:
        event = _coerce_event(raw)
        if event is not None:
            events.append(event)
    return events


def build_system_prompt(base_prompt: str, current_year: int, max_events: int) -> str:
    """在用户配置的系统提示词后追加运行时约束（当前年份、数量上限）。"""
    base = (base_prompt or "").strip()
    suffix = (
        f"\n\n当前年份为 {current_year}（如需填写基准年请使用该年份）。"
        f"本次最多生成 {max_events} 条事项，请勿超过。"
    )
    return base + suffix


async def generate_calendar_events(
    context,
    provider_id: str,
    user_prompt: str,
    system_prompt: str,
    current_year: int,
    max_events: int = DEFAULT_MAX_GENERATE,
) -> Optional[list]:
    """发起 LLM 调用，根据主题提示词生成时间表事项。

    Args:
        context: AstrBot 上下文对象。
        provider_id: 使用的 LLM 提供商 ID（已由上层解析，可能为空表示用默认模型）。
        user_prompt: 用户输入的主题/世界观（如「异世界/魔法/节日」）。
        system_prompt: 生成用系统提示词（已含运行时约束）。
        current_year: 当前年份（用于回填基准年）。
        max_events: 单次生成事项数上限。

    Returns:
        粗规整后的事项列表（每条含 month/day/text/repeat，并回填 year）；
        调用或解析失败返回 ``None``。
    """
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        logger.warning("心念 | ⚠️ AI 生成时间表缺少主题提示词")
        return None

    try:
        llm_response = await context.llm_generate(
            chat_provider_id=provider_id or None,
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
    except Exception as e:
        logger.error(f"心念 | ❌ AI 生成时间表 LLM 调用失败: {e}")
        return None

    if not llm_response or llm_response.role != "assistant":
        logger.warning(f"心念 | ⚠️ AI 生成时间表 LLM 响应异常: {llm_response}")
        return None

    response_text = llm_response.completion_text
    if not response_text:
        logger.warning("心念 | ⚠️ AI 生成时间表 LLM 返回空响应")
        return None

    logger.debug(f"心念 | AI 生成时间表原始响应: {response_text[:500]}")

    events = parse_generated_events(response_text)
    if events is None:
        return None

    # 截断到上限，并回填基准年（缺失时）
    if len(events) > max_events:
        logger.warning(f"心念 | ⚠️ AI 生成时间表超过上限 {max_events}，已截断")
        events = events[:max_events]
    for event in events:
        event.setdefault("year", current_year)

    logger.info(f"心念 | ✅ AI 生成时间表成功，共 {len(events)} 条事项")
    return events
