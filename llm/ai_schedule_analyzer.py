"""
AI 自主调度分析器

在 AI 生成消息后，检测消息中是否包含时间约定相关的关键词。
如果包含，发起二次 LLM 调用让 AI 决定下次联系时间和跟进提示词。
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from astrbot.api import logger


# 时间约定预检不再做“任意关键词命中即可”的宽召回。
# 只有时间表达与联系/提醒动作组合出现时，才值得发起二次 LLM 分析。
_NUM = r"[\d一二三四五六七八九十百两俩仨]+"
_DURATION_RE = re.compile(
    rf"(?:{_NUM}|半)\s*(?:分钟|个?半?小时|天|日|周|月|年|个?钟头?)"
    r"|(?:半天|半晌|整天|一整天)"
)

# HH:MM 格式严格限制小时和分钟，避免把比分/比例当时间。
_CLOCK_RE = re.compile(r"(?:0?\d|1\d|2[0-3])[:：][0-5]\d")
_CHINESE_TIME_POINT_RE = re.compile(
    r"(?:(?:凌晨|早上|上午|中午|下午|晚上|明早|明晚|今晚)\s*)?"
    r"(?:[01]?\d|2[0-3]|[一二三四五六七八九十两]+)\s*(?:点|时)"
    r"\s*(?:半|钟|[0-5]?\d分?|[一二三四五六七八九十两]+分?)?"
)
_FUTURE_DATE_RE = re.compile(
    r"(?:明天\s*(?:早上|上午|中午|下午|晚上)?|"
    r"后天\s*(?:早上|上午|中午|下午|晚上)?|"
    r"今天\s*(?:早上|上午|中午|下午|晚上)|"
    r"明早|明晚|今晚|今早)"
)
_DAYPART_RE = re.compile(r"(?:凌晨|早上|上午|中午|下午|晚上)")
_VAGUE_TIME_RE = re.compile(
    r"(?:一会儿?|待会儿?|稍后|等下|过一会|晚[点些]|睡醒|起床)"
)

_SCHEDULE_ACTION_RE = re.compile(
    r"(?:"
    r"(?:再\s*)?(?:找|联系|叫|喊|提醒|通知|约|催|陪)(?:你|我|一下)?"
    r"|(?:再\s*)?聊(?:聊|天)?(?![了过得])"
    r"|(?:再\s*)?见(?:面|你|我)"
    r"|(?<!再)见(?!到|过|识|证)"
    r"|(?:回复|回)(?:你|我|消息|信息|信|话)"
    r"|发(?:个)?(?:消息|信息)(?:给你|给我)?"
    r"|敲(?:你|我)?|戳(?:你|我)?|问(?:你|我)?"
    r"|同步|汇报|确认|准时|到点|轰炸"
    r"|继续\s*(?:聊(?:聊|天)?|说|讨论|同步|确认|汇报)"
    r")"
)
_DAYPART_COMMITMENT_RE = re.compile(
    r"(?:"
    r"(?:再\s*)?(?:找|联系|叫|喊|提醒|通知|约|催)(?:你|我|一下)?"
    r"|(?:回复|回)(?:你|我|消息|信息|信|话)"
    r"|发(?:个)?(?:消息|信息)(?:给你|给我)?"
    r"|敲(?:你|我)?|戳(?:你|我)?|问(?:你|我)?"
    r"|同步|汇报|确认|准时|到点|轰炸"
    r"|(?:再|会|要|到时|到时候|继续)\s*(?:聊(?:聊|天)?|见(?:面|你|我))"
    r")"
)
_WAIT_INTENT_RE = re.compile(
    r"(?:等(?:我|你)?(?![了过])|等等|等一下|等会儿?|待命)"
)
_DURATION_FUTURE_HINT_RE = re.compile(
    r"(?:后|以后|之后|内|再|等|待|稍后|准时|到点|记得|别忘|会)"
)


def _nearby_text(
    text: str, start: int, end: int, before: int = 8, after: int = 18
) -> str:
    """取命中片段附近的短窗口，避免远距离词语互相误伤。"""
    return text[max(0, start - before) : min(len(text), end + after)]


def _has_schedule_action(text: str) -> bool:
    return bool(_SCHEDULE_ACTION_RE.search(text))


def _contains_duration_schedule(text: str) -> bool:
    for match in _DURATION_RE.finditer(text):
        window = _nearby_text(text, match.start(), match.end(), after=20)
        if _WAIT_INTENT_RE.search(window):
            return True
        if _has_schedule_action(window) and _DURATION_FUTURE_HINT_RE.search(window):
            return True
    return False


def _contains_clock_schedule(text: str) -> bool:
    for regex in (_CLOCK_RE, _CHINESE_TIME_POINT_RE):
        for match in regex.finditer(text):
            window = _nearby_text(text, match.start(), match.end())
            if _FUTURE_DATE_RE.search(window) or _has_schedule_action(window):
                return True
    return False


def _contains_future_date_schedule(text: str) -> bool:
    for match in _FUTURE_DATE_RE.finditer(text):
        window = _nearby_text(text, match.start(), match.end(), after=20)
        if (
            _has_schedule_action(window)
            or _CLOCK_RE.search(window)
            or _CHINESE_TIME_POINT_RE.search(window)
        ):
            return True
    return False


def _contains_daypart_schedule(text: str) -> bool:
    for match in _DAYPART_RE.finditer(text):
        window_after = text[match.end() : min(len(text), match.end() + 18)]
        if _DAYPART_COMMITMENT_RE.search(window_after):
            return True
    return False


def _contains_vague_time_schedule(text: str) -> bool:
    for match in _VAGUE_TIME_RE.finditer(text):
        window = _nearby_text(text, match.start(), match.end(), after=20)
        if _WAIT_INTENT_RE.search(window) or _has_schedule_action(window):
            return True
    return False


def contains_time_keywords(text: str) -> bool:
    """检查文本是否包含值得进一步分析的时间约定

    这是一个轻量级预检，用于过滤不需要二次 LLM 调用的消息。它刻意
    偏向“时间 + 未来联系/提醒动作”的组合，避免“早上好”“再见”
    这类日常表达把完整历史上下文带进调度分析。

    Args:
        text: AI 生成的消息文本

    Returns:
        True 如果包含时间关键词，需要进一步分析
    """
    if not text:
        return False

    return (
        _contains_duration_schedule(text)
        or _contains_clock_schedule(text)
        or _contains_future_date_schedule(text)
        or _contains_daypart_schedule(text)
        or _contains_vague_time_schedule(text)
    )


def parse_schedule_response(response_text: str) -> Optional[dict]:
    """解析 LLM 返回的调度决策 JSON

    Args:
        response_text: LLM 返回的原始文本

    Returns:
        解析后的字典 {"delay_minutes": int, "follow_up_prompt": str}，
        解析失败或 delay_minutes <= 0 返回 None
    """
    if not response_text:
        return None

    try:
        # 尝试从文本中提取 JSON（处理 LLM 可能添加的多余内容）
        json_match = re.search(r"\{[^}]+\}", response_text, re.DOTALL)
        if not json_match:
            logger.warning(f"心念 | ⚠️ AI 调度响应中未找到 JSON: {response_text[:200]}")
            return None

        data = json.loads(json_match.group())

        delay_minutes = data.get("delay_minutes", 0)
        follow_up_prompt = data.get("follow_up_prompt", "")

        # delay_minutes 必须是正整数
        if not isinstance(delay_minutes, (int, float)) or delay_minutes <= 0:
            logger.debug("心念 | AI 判断不需要自定义调度 (delay_minutes <= 0)")
            return None

        delay_minutes = int(delay_minutes)

        if not follow_up_prompt or not isinstance(follow_up_prompt, str):
            logger.warning("心念 | ⚠️ AI 调度响应缺少 follow_up_prompt")
            return None

        return {
            "delay_minutes": delay_minutes,
            "follow_up_prompt": follow_up_prompt.strip(),
        }

    except json.JSONDecodeError as e:
        logger.warning(
            f"心念 | ⚠️ AI 调度响应 JSON 解析失败: {e}, 原文: {response_text[:200]}"
        )
        return None
    except Exception as e:
        logger.error(f"心念 | ❌ 解析 AI 调度响应时发生错误: {e}")
        return None


async def analyze_for_schedule(
    context,
    provider_id: str,
    ai_message: str,
    contexts: list,
    analysis_prompt: str = "",
    current_time_str: str = "",
    schedule_provider_id: str = "",
    existing_tasks: list | None = None,
    tz=None,
) -> Optional[dict]:
    """发起二次 LLM 调用，分析 AI 是否约定了下次联系时间

    Args:
        context: AstrBot 上下文对象
        provider_id: 默认 LLM 提供商 ID（主模型）
        ai_message: AI 生成的消息
        contexts: 对话历史（用于上下文）
        analysis_prompt: 自定义分析提示词（空则使用默认）
        current_time_str: 当前时间字符串
        schedule_provider_id: AI 调度专用的 LLM 提供商 ID（可选，留空则使用 provider_id）
        existing_tasks: 该会话已有的待执行调度任务列表（用于去重判断）

    Returns:
        调度信息 {"delay_minutes": int, "follow_up_prompt": str, "fire_time": str}，
        或 None（不需要自定义调度）
    """
    # 阶段1：关键词预检
    if not contains_time_keywords(ai_message):
        logger.debug("心念 | AI 消息未包含时间关键词，跳过调度分析")
        return None

    logger.info("心念 | 🕐 AI 消息包含时间关键词，发起调度分析...")

    # 构建分析提示词
    # 如果未提供 analysis_prompt，则在上层配置中应该已经处理了默认值，
    # 但为了安全起见，这里也可以保留一个简单的 fallback，或者直接报错/跳过
    if not analysis_prompt:
        logger.warning("心念 | ⚠️ 未配置调度分析提示词，无法进行分析")
        return None

    system_prompt = analysis_prompt
    user_prompt_parts = []

    if current_time_str:
        user_prompt_parts.append(f"当前时间: {current_time_str}")

    # 注入已有约定，帮助 LLM 判断是否重复
    if existing_tasks:
        valid_tasks = [
            t
            for t in existing_tasks
            if t.get("fire_time") and t.get("follow_up_prompt")
        ]
        if valid_tasks:
            tasks_desc = "\n".join(
                f"- {t['fire_time']}：{t['follow_up_prompt']}" for t in valid_tasks
            )
            user_prompt_parts.append(
                f"该用户已有以下待执行的约定：\n{tasks_desc}\n"
                "如果当前消息提到的约定与上述已有约定是同一件事（相同的时间和目的），"
                "请返回 delay_minutes 为 0，不要重复创建。"
                "只有当这是一个全新的、不同的约定时才返回正数的 delay_minutes。"
            )
            logger.debug(f"心念 | 调度分析注入 {len(valid_tasks)} 条已有约定用于去重")

    # 构建用户消息：动态分析上下文和 AI 刚生成的消息放在本轮用户 prompt，
    # 保持 system_prompt 只包含稳定分析规则。
    user_prompt_parts.append(f"请分析以下 AI 消息是否包含时间约定：\n\n{ai_message}")
    user_prompt = "\n\n".join(user_prompt_parts)

    # 确定使用的 provider_id
    actual_provider_id = schedule_provider_id if schedule_provider_id else provider_id

    if schedule_provider_id:
        logger.info(f"心念 | 🔧 AI 调度分析使用独立模型: {schedule_provider_id}")
    else:
        logger.debug(f"心念 | AI 调度分析使用主模型: {provider_id}")

    try:
        # 二次 LLM 调用（轻量级，只需输出 JSON）
        llm_response = await context.llm_generate(
            chat_provider_id=actual_provider_id,
            prompt=user_prompt,
            contexts=contexts,
            system_prompt=system_prompt,
        )

        if not llm_response or llm_response.role != "assistant":
            logger.warning(f"心念 | ⚠️ 调度分析 LLM 响应异常: {llm_response}")
            return None

        response_text = llm_response.completion_text
        if not response_text:
            logger.warning("心念 | ⚠️ 调度分析 LLM 返回空响应")
            return None

        logger.debug(f"心念 | 调度分析 LLM 原始响应: {response_text}")

        # 阶段2：解析 JSON 结果
        result = parse_schedule_response(response_text)
        if not result:
            return None

        # 计算绝对触发时间
        _now = datetime.now(tz=tz) if tz is not None else datetime.now()
        fire_time = _now + timedelta(minutes=result["delay_minutes"])
        result["fire_time"] = fire_time.strftime("%Y-%m-%d %H:%M:%S")
        # UTC 时间戳：用于精确比较，彻底规避时区转换问题
        result["fire_time_utc"] = (
            fire_time.timestamp()
            if tz is not None
            else fire_time.astimezone().timestamp()
        )
        result["task_id"] = str(uuid.uuid4())
        result["created_at"] = _now.strftime("%Y-%m-%d %H:%M:%S")

        logger.info(
            f"心念 | 🕐 AI 调度分析结果: {result['delay_minutes']}分钟后"
            f"（{result['fire_time']}）触发主动对话 [TaskID: {result['task_id']}]"
        )

        return result

    except Exception as e:
        logger.error(f"心念 | ❌ 调度分析 LLM 调用失败: {e}")
        return None
