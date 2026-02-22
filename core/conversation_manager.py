"""
会话管理器

负责对话历史的获取和保存
"""

import datetime
import json
from astrbot.api import logger
from .runtime_data import runtime_data
from ..llm.placeholder_utils import replace_placeholders


class ConversationManager:
    """会话管理器类"""

    def __init__(self, config: dict, context, persistence_manager):
        """初始化会话管理器

        Args:
            config: 配置字典
            context: AstrBot上下文对象
            persistence_manager: 持久化管理器
        """
        self.config = config
        self.context = context
        self.persistence_manager = persistence_manager

    def _build_history_user_prompt(
        self,
        session: str,
        proactive_prompt_used: str = None,
        build_user_context_func=None,
    ) -> str:
        """根据配置构建历史记录的用户端提示词

        Args:
            session: 会话ID
            proactive_prompt_used: 本次使用的主动对话提示词（已替换占位符）
            build_user_context_func: 构建用户上下文的函数

        Returns:
            根据配置生成的用户提示词
        """
        proactive_config = self.config.get("proactive_reply", {})
        history_save_mode = proactive_config.get("history_save_mode", "default")

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unreplied_count = runtime_data.session_unreplied_count.get(session, 0)

        if history_save_mode == "proactive_prompt":
            # 使用本次触发的主动对话提示词
            if proactive_prompt_used:
                return proactive_prompt_used
            else:
                # 回退到默认模式
                logger.warning(
                    "心念 | ⚠️ 历史记录模式为 proactive_prompt 但未提供提示词，使用默认模式"
                )
                return f"<SYSTEM_TRIGGER: 此条目为主动对话触发记录，非用户实际发言。AI 于 {current_time} 主动向用户发起了对话（当前连续未回复次数：{unreplied_count}），下方的 assistant 消息即为 AI 主动发送的内容>"

        elif history_save_mode == "custom":
            # 使用自定义提示词模板，支持占位符替换
            custom_template = proactive_config.get(
                "custom_history_prompt",
                "<PROACTIVE_TRIGGER: 时间:{current_time}，用户:{username}>",
            )
            if build_user_context_func:
                return replace_placeholders(
                    custom_template, session, self.config, build_user_context_func
                )
            else:
                # 简单替换基础占位符
                return custom_template.replace("{current_time}", current_time).replace(
                    "{unreplied_count}", str(unreplied_count)
                )

        else:
            # 默认模式：使用系统触发标记
            return f"<SYSTEM_TRIGGER: 此条目为主动对话触发记录，非用户实际发言。AI 于 {current_time} 主动向用户发起了对话（当前连续未回复次数：{unreplied_count}），下方的 assistant 消息即为 AI 主动发送的内容>"

    async def get_conversation_history(self, session: str, max_count: int = 10) -> list:
        """安全地获取会话的对话历史记录

        Args:
            session: 会话ID
            max_count: 最大记录数

        Returns:
            历史记录列表
        """
        try:
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                session
            )

            if not curr_cid:
                return []

            conversation = await self.context.conversation_manager.get_conversation(
                session, curr_cid
            )

            if not conversation:
                return []

            # AstrBot 使用 content 字段存储 OpenAI 格式的消息列表
            # 回退读取 history 字段（旧会话数据可能仍存储在此）
            raw_history = getattr(conversation, "content", None)
            if not raw_history:
                raw_history = getattr(conversation, "history", None)

            if not raw_history:
                logger.debug(f"心念 | 会话 {session} 没有历史记录")
                return []

            try:
                # content 字段是列表，history 字段是 JSON 字符串
                if isinstance(raw_history, str):
                    raw_history = json.loads(raw_history)

                if not isinstance(raw_history, list):
                    logger.warning(
                        f"心念 | ⚠️ 会话 {session} 历史记录格式未知: {type(raw_history)}"
                    )
                    return []

                logger.debug(f"心念 | 会话 {session} 获取到 {len(raw_history)} 条原始历史记录")

                # 限制历史记录数量
                history = raw_history
                if max_count > 0 and len(history) > max_count:
                    history = history[-max_count:]

                # 验证和转换历史记录格式
                valid_history = []
                skipped_count = 0
                for idx, item in enumerate(history):
                    if not isinstance(item, dict) or "role" not in item:
                        skipped_count += 1
                        continue

                    role = item.get("role")
                    content = item.get("content")

                    # 只保留 user/assistant/system 角色
                    # tool/function 等角色的消息与主动消息生成无关，
                    # 且可能缺少必要字段导致 LLM provider 崩溃
                    if role not in ("user", "assistant", "system"):
                        skipped_count += 1
                        continue

                    # 处理 content 字段的不同格式
                    if content is None:
                        skipped_count += 1
                        continue

                    # 格式1: content 是字符串
                    if isinstance(content, str):
                        valid_history.append({"role": role, "content": content})
                    # 格式2: content 是列表（包含 TextPart 等）
                    elif isinstance(content, list):
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict):
                                # 支持 {"text": "..."} 格式
                                if "text" in part:
                                    text_parts.append(str(part["text"]))
                                # 支持 {"type": "text", "content": "..."} 格式
                                elif part.get("type") == "text" and "content" in part:
                                    text_parts.append(str(part["content"]))
                            elif isinstance(part, str):
                                text_parts.append(part)
                        if text_parts:
                            combined_content = "".join(text_parts)
                            valid_history.append(
                                {"role": role, "content": combined_content}
                            )
                        else:
                            logger.debug(
                                f"心念 | 历史记录第 {idx} 条: 列表格式但无可提取文本, content={content}"
                            )
                            skipped_count += 1
                    else:
                        logger.debug(
                            f"心念 | 历史记录第 {idx} 条: 未知 content 类型 {type(content)}"
                        )
                        skipped_count += 1

                if skipped_count > 0:
                    logger.debug(
                        f"心念 | 会话 {session} 历史记录处理: 有效 {len(valid_history)} 条, 跳过 {skipped_count} 条"
                    )

                return valid_history

            except json.JSONDecodeError as e:
                logger.warning(f"心念 | ⚠️ 解析会话 {session} 的历史记录JSON失败: {e}")
                return []

        except Exception as e:
            logger.error(f"心念 | ❌ 获取会话 {session} 的历史记录失败: {e}")
            return []

    async def add_message_to_conversation_history(
        self,
        session: str,
        message: str,
        user_prompt: str = None,
        proactive_prompt_used: str = None,
        build_user_context_func=None,
    ):
        """将AI主动发送的消息添加到对话历史记录中

        使用官方 add_message_pair API

        Args:
            session: 会话ID
            message: AI消息内容
            user_prompt: 对应的用户提示词（可选，根据配置生成）
            proactive_prompt_used: 本次触发使用的主动对话提示词（已替换占位符）
            build_user_context_func: 构建用户上下文的函数（用于自定义模式占位符替换）
        """
        # 根据配置选择历史记录保存内容
        if user_prompt is None:
            user_prompt = self._build_history_user_prompt(
                session, proactive_prompt_used, build_user_context_func
            )

        try:
            # 获取当前对话 ID
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                session
            )

            if not curr_cid:
                # 如果没有对话，创建一个新的
                curr_cid = await self.context.conversation_manager.new_conversation(
                    session
                )

            if not curr_cid:
                logger.error("心念 | ❌ 无法获取或创建对话 ID")
                return

            # 使用官方 add_message_pair API
            # content 使用字符串格式
            await self.context.conversation_manager.add_message_pair(
                cid=curr_cid,
                user_message={"role": "user", "content": user_prompt},
                assistant_message={
                    "role": "assistant",
                    "content": message,
                },
            )
            logger.info("心念 | ✅ 使用 add_message_pair API 保存消息对成功")

        except Exception as e:
            logger.error(f"心念 | ❌ 将消息添加到对话历史时发生错误: {e}")
