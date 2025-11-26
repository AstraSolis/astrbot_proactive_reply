"""
解析工具函数

提供会话列表和提示词列表的解析功能
"""

import json
from astrbot.api import logger
from .formatters import ensure_string_encoding


def parse_sessions_list(sessions_data) -> list:
    """解析会话列表（支持列表格式、JSON格式和传统换行格式）

    Args:
        sessions_data: 会话数据，可以是列表或字符串

    Returns:
        解析后的会话列表
    """
    sessions = []

    # 如果已经是列表格式（新的配置格式）
    if isinstance(sessions_data, list):
        sessions = [s.strip() for s in sessions_data if s and s.strip()]
        return sessions

    # 如果是字符串格式（兼容旧配置）
    if isinstance(sessions_data, str):
        try:
            # 尝试解析JSON格式
            sessions = json.loads(sessions_data)
            if not isinstance(sessions, list):
                raise ValueError("不是有效的JSON数组")
            # 过滤空字符串
            sessions = [s.strip() for s in sessions if s and s.strip()]
        except (json.JSONDecodeError, ValueError):
            # 回退到传统换行格式
            sessions = [s.strip() for s in sessions_data.split("\n") if s.strip()]

    return sessions


def parse_prompt_list(prompt_list_data) -> list:
    """解析主动对话提示词列表（支持列表格式、JSON格式和传统换行格式）

    Args:
        prompt_list_data: 提示词数据，可以是列表或字符串

    Returns:
        解析后的提示词列表
    """
    prompt_list = []

    try:
        # 如果已经是列表格式（新的配置格式）
        if isinstance(prompt_list_data, list):
            prompt_list = []
            for item in prompt_list_data:
                if item and str(item).strip():
                    # 确保每个提示词的编码正确
                    cleaned_item = ensure_string_encoding(str(item).strip())
                    prompt_list.append(cleaned_item)
            return prompt_list

        # 如果是字符串格式（兼容旧配置）
        if isinstance(prompt_list_data, str):
            prompt_list_data = ensure_string_encoding(prompt_list_data)
            try:
                # 尝试解析JSON格式
                parsed_list = json.loads(prompt_list_data)
                if not isinstance(parsed_list, list):
                    raise ValueError("不是有效的JSON数组")

                # 过滤空字符串并确保编码正确
                prompt_list = []
                for item in parsed_list:
                    if item and str(item).strip():
                        cleaned_item = ensure_string_encoding(str(item).strip())
                        prompt_list.append(cleaned_item)

            except (json.JSONDecodeError, ValueError):
                # 回退到传统换行格式
                prompt_list = []
                for line in prompt_list_data.split("\n"):
                    if line.strip():
                        cleaned_line = ensure_string_encoding(line.strip())
                        prompt_list.append(cleaned_line)

    except Exception as e:
        logger.error(f"解析提示词列表失败: {e}")
        import traceback

        logger.error(f"详细错误信息: {traceback.format_exc()}")
        return []

    # 最终检查，确保所有提示词都是有效的
    valid_prompts = []
    for prompt in prompt_list:
        if prompt and len(prompt.strip()) > 0:
            valid_prompts.append(prompt)
        else:
            logger.warning(f"跳过无效的提示词: {repr(prompt)}")

    return valid_prompts
