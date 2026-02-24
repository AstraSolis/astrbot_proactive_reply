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

# 时间相关关键词模式
# 匹配包含时间约定意图的文本
_TIME_KEYWORD_PATTERNS = [
    # 1. 相对时间 - 数字+单位
    # 包含中文数字（一到十、百、两、俩、仨）
    # 排除"有点"（"点"字前不能是"有"或"一"除非后面跟"钟"）
    # 匹配: "40分钟", "五分钟", "半小时", "俩小时", "三天"
    r"(?:[\d一二三四五六七八九十百两俩仨]+|半)\s*(?:分钟|个?半?小时|天|日|周|月|年|个?钟头?)",
    # 2. 绝对时间 - 显式时间点
    # HH:MM 格式：严格限制小时 0-23，分钟 0-59，避免匹配 "3:2" (比分/比例)
    r"(?:0?\d|1\d|2[0-3])[:：][0-5]\d",
    # 中文时间点: "3点", "下午2点半", "明早8点15"
    # 排除"三点水"、"一点建议"、"有点"等：要求"点"前面是数字或特定时间词，或者后面跟"钟/分/半"
    r"(?:(?:凌晨|早上|上午|中午|下午|晚上|明早|今晚)\s*)?"
    r"[\d一二三四五六七八九十两]+\s*(?:点|时)\s*(?:半|钟|[\d一二三四五六七八九十两]+分?)?",
    # 3. 模糊/口语时间
    r"(?:一会儿?|待会儿?|稍后|等下|过后|过一会|晚[点些]|明[天早晚]|后天|下午|晚上|早上|中午|睡醒|起床)",
    r"(?:半天|半晌|整天|一整天)",
    # 4. 动作暗示
    r"(?:之后|以后|回[来头]|到时候?|再[来找联]?)",
]

# 编译为单个正则（任意一个命中即可）
_TIME_KEYWORDS_RE = re.compile("|".join(_TIME_KEYWORD_PATTERNS))


def contains_time_keywords(text: str) -> bool:
    """检查文本是否包含时间约定相关的关键词

    这是一个轻量级预检，用于过滤不需要二次 LLM 调用的消息。

    Args:
        text: AI 生成的消息文本

    Returns:
        True 如果包含时间关键词，需要进一步分析
    """
    if not text:
        return False

    # 1. 正则匹配
    if not _TIME_KEYWORDS_RE.search(text):
        return False

    # 2. 负向排除规则 (简单启发式)

    # 排除 "有点"、"一点" (非时间用法)
    # 正则中已经尝试排除，但"一点"作为时间点(1:00)和数量词很难区分
    # 如果"一点"后面没有"钟"或"分"或"半"，且前面有"有"或"吃"等动词，则排除
    # 例: "有点咸" -> 排除; "一点见" -> 保留
    if re.search(r"(?:有|吃|喝|来)一点(?!钟|分|半|见|睡|去)", text):
        return False

    return True


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
        logger.warning(f"心念 | ⚠️ AI 调度响应 JSON 解析失败: {e}, 原文: {response_text[:200]}")
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

    if current_time_str:
        system_prompt += f"\n\n当前时间: {current_time_str}"

    # 注入已有约定，帮助 LLM 判断是否重复
    if existing_tasks:
        valid_tasks = [
            t for t in existing_tasks
            if t.get("fire_time") and t.get("follow_up_prompt")
        ]
        if valid_tasks:
            tasks_desc = "\n".join(
                f"- {t['fire_time']}：{t['follow_up_prompt']}"
                for t in valid_tasks
            )
            system_prompt += (
                f"\n\n该用户已有以下待执行的约定：\n{tasks_desc}\n"
                "如果当前消息提到的约定与上述已有约定是同一件事（相同的时间和目的），"
                "请返回 delay_minutes 为 0，不要重复创建。"
                "只有当这是一个全新的、不同的约定时才返回正数的 delay_minutes。"
            )
            logger.debug(f"心念 | 调度分析注入 {len(valid_tasks)} 条已有约定用于去重")

    # 构建用户消息：包含 AI 刚生成的消息
    user_prompt = f"请分析以下 AI 消息是否包含时间约定：\n\n{ai_message}"

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
        fire_time = datetime.now() + timedelta(minutes=result["delay_minutes"])
        result["fire_time"] = fire_time.strftime("%Y-%m-%d %H:%M:%S")
        result["task_id"] = str(uuid.uuid4())
        result["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        logger.info(
            f"心念 | 🕐 AI 调度分析结果: {result['delay_minutes']}分钟后"
            f"（{result['fire_time']}）触发主动对话 [TaskID: {result['task_id']}]"
        )

        return result

    except Exception as e:
        logger.error(f"心念 | ❌ 调度分析 LLM 调用失败: {e}")
        return None
