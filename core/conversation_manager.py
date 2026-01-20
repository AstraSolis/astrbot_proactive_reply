"""
会话管理器

负责对话历史的获取和保存
"""

import asyncio
import datetime
import json
import os
import sqlite3
from astrbot.api import logger
from ..utils.validators import verify_database_schema


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

            # 优先读取 content 字段 (AstrBot v4+)，回退到 history 字段（旧版本兼容）
            # AstrBot v4+ 使用 ConversationV2.content 存储 OpenAI 格式的消息列表
            raw_history = getattr(conversation, 'content', None)
            if raw_history is None:
                raw_history = getattr(conversation, 'history', None)
            
            if not raw_history:
                logger.debug(f"会话 {session} 没有历史记录 (content 和 history 均为空)")
                return []

            try:
                # 处理不同的存储格式
                if isinstance(raw_history, list):
                    # 新版本: content 字段直接是列表
                    history = raw_history
                    logger.debug(f"会话 {session} 使用 content 字段 (列表格式)")
                elif isinstance(raw_history, str):
                    # 旧版本: history 字段是 JSON 字符串
                    history = json.loads(raw_history)
                    logger.debug(f"会话 {session} 使用 history 字段 (JSON字符串格式)")
                else:
                    logger.warning(f"会话 {session} 历史记录格式未知: {type(raw_history)}")
                    return []
                
                if not isinstance(history, list):
                    logger.warning(f"会话 {session} 的历史记录格式不正确，不是列表格式")
                    return []

                # 调试：记录原始历史记录数量
                logger.debug(f"会话 {session} 获取到 {len(history)} 条原始历史记录")

                # 限制历史记录数量
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

                    # 处理 content 字段的不同格式
                    if content is None:
                        skipped_count += 1
                        continue

                    # 格式1: content 是字符串（旧格式）
                    if isinstance(content, str):
                        valid_history.append({"role": role, "content": content})
                    # 格式2: content 是列表（新版本 AstrBot 格式，包含 TextPart 等）
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
                            # 列表格式但没有可提取的文本
                            logger.debug(
                                f"历史记录第 {idx} 条: 列表格式但无可提取文本, content={content}"
                            )
                            skipped_count += 1
                    else:
                        logger.debug(
                            f"历史记录第 {idx} 条: 未知 content 类型 {type(content)}"
                        )
                        skipped_count += 1

                if skipped_count > 0:
                    logger.debug(
                        f"会话 {session} 历史记录处理: 有效 {len(valid_history)} 条, 跳过 {skipped_count} 条"
                    )

                return valid_history

            except json.JSONDecodeError as e:
                logger.warning(f"解析会话 {session} 的历史记录JSON失败: {e}")
                return []

        except Exception as e:
            logger.error(f"获取会话 {session} 的历史记录失败: {e}")
            return []

    async def add_message_to_conversation_history(
        self, session: str, message: str, user_prompt: str = None
    ):
        """将AI主动发送的消息添加到对话历史记录中

        为解决主动消息历史未附带到 LLM 请求的问题，需要添加 user/assistant 消息对
        才能让框架正确加载历史记录到后续 LLM 请求中

        优先使用官方 add_message_pair API，如不可用则使用手动方案

        Args:
            session: 会话ID
            message: AI消息内容
            user_prompt: 对应的用户提示词（可选，默认使用占位符）
        """
        # 如果没有提供 user_prompt，使用明确的系统标记格式
        # 使用 <SYSTEM_TRIGGER> 标签让 LLM 识别为元信息，避免误解为用户实际发言
        if user_prompt is None:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_prompt = f"<SYSTEM_TRIGGER: 此条目为主动对话触发记录，非用户实际发言。AI 于 {current_time} 主动向用户发起了对话，下方的 assistant 消息即为 AI 主动发送的内容>"

        try:
            # 优先使用官方 add_message_pair API
            # API 签名: add_message_pair(cid, user_message, assistant_message)
            # 其中 cid 是 Conversation ID，不是 unified_msg_origin
            if hasattr(self.context.conversation_manager, "add_message_pair"):
                try:
                    # 先获取当前对话 ID
                    curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                        session
                    )

                    if not curr_cid:
                        # 如果没有对话，创建一个新的
                        curr_cid = (
                            await self.context.conversation_manager.new_conversation(
                                session
                            )
                        )

                    if curr_cid:
                        # 尝试使用新版本格式 (content 是列表)
                        # 官方文档使用 UserMessageSegment/AssistantMessageSegment
                        # 但为向后兼容，先尝试 {"role": ..., "content": [...]} 格式
                        try:
                            await self.context.conversation_manager.add_message_pair(
                                cid=curr_cid,
                                user_message={
                                    "role": "user",
                                    "content": [{"text": user_prompt}],
                                },
                                assistant_message={
                                    "role": "assistant",
                                    "content": [{"text": message}],
                                },
                            )
                            logger.info(
                                "✅ 使用官方 add_message_pair API (新格式) 保存消息对成功"
                            )
                            return
                        except Exception as format_err:
                            logger.debug(f"新格式失败: {format_err}，尝试旧格式")
                            # 回退到旧格式
                            await self.context.conversation_manager.add_message_pair(
                                cid=curr_cid,
                                user_message={"role": "user", "content": user_prompt},
                                assistant_message={
                                    "role": "assistant",
                                    "content": message,
                                },
                            )
                            logger.info(
                                "✅ 使用官方 add_message_pair API (旧格式) 保存消息对成功"
                            )
                            return
                    else:
                        logger.warning("⚠️ 无法获取或创建对话 ID，使用备用方案")
                except Exception as e:
                    logger.warning(
                        f"⚠️ 官方 add_message_pair API 调用失败: {e}，使用备用方案"
                    )

            # 备用方案：手动添加消息对到历史记录
            await self._fallback_add_message_pair(session, message, user_prompt)

        except Exception as e:
            logger.error(f"将消息添加到对话历史时发生错误: {e}")

    async def _fallback_add_message_pair(
        self, session: str, message: str, user_prompt: str
    ):
        """备用方案：手动添加 user/assistant 消息对到历史记录

        Args:
            session: 会话ID
            message: AI消息内容
            user_prompt: 对应的用户提示词
        """
        try:
            # 获取当前会话的对话ID
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                session
            )

            # 如果没有对话，创建一个新的对话
            if not curr_cid:
                curr_cid = await self.context.conversation_manager.new_conversation(
                    session
                )
                if not curr_cid:
                    logger.error("无法创建新对话")
                    return

            # 获取对话对象
            conversation = await self.context.conversation_manager.get_conversation(
                session, curr_cid
            )
            if not conversation:
                logger.error("无法获取对话对象")
                return

            # 解析现有的对话历史
            try:
                if conversation.history:
                    history = json.loads(conversation.history)
                else:
                    history = []
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"解析对话历史失败: {e}，使用空历史")
                history = []

            # 添加 user/assistant 消息对到历史记录
            user_message = {"role": "user", "content": user_prompt}
            ai_message = {"role": "assistant", "content": message}
            history.append(user_message)
            history.append(ai_message)

            # 更新对话历史
            conversation.history = json.dumps(history, ensure_ascii=False)

            # 尝试使用框架提供的保存方法
            saved = await self.save_conversation_safely(conversation, curr_cid, session)

            if not saved:
                logger.warning("⚠️ 框架接口保存失败，尝试备用方案")

                # 备用方案1: 尝试数据库直接操作
                database_saved = await self.fallback_database_save(
                    conversation, curr_cid
                )

                # 备用方案2: 保存到插件自己的数据文件中
                await self.backup_conversation_history(session, curr_cid, history)

                if database_saved:
                    logger.info("✅ 使用数据库回退方案保存成功")
                else:
                    logger.warning("⚠️ 数据库回退方案也失败，已保存到备份文件")
            else:
                logger.info("✅ 使用备用 update_conversation 方案保存消息对成功")

        except Exception as e:
            logger.error(f"备用方案添加消息到对话历史时发生错误: {e}")

    async def save_conversation_safely(
        self, conversation, curr_cid: str, session: str = None
    ) -> bool:
        """安全地保存对话，使用框架提供的接口

        Args:
            conversation: 对话对象
            curr_cid: 对话ID
            session: 会话ID

        Returns:
            是否保存成功
        """
        try:
            if (
                hasattr(self.context.conversation_manager, "update_conversation")
                and session
            ):
                try:
                    # 解析历史记录为列表格式
                    if conversation.history:
                        history_list = json.loads(conversation.history)
                    else:
                        history_list = []

                    if not isinstance(history_list, list):
                        logger.warning(f"⚠️ 历史记录不是列表格式: {type(history_list)}")
                        return False

                    # 使用框架接口
                    if asyncio.iscoroutinefunction(
                        self.context.conversation_manager.update_conversation
                    ):
                        await self.context.conversation_manager.update_conversation(
                            session, curr_cid, history_list
                        )
                    else:
                        self.context.conversation_manager.update_conversation(
                            session, curr_cid, history_list
                        )

                    logger.info(
                        "✅ 使用 conversation_manager.update_conversation 保存成功"
                    )
                    return True

                except json.JSONDecodeError as e:
                    logger.error(f"❌ 解析历史记录JSON失败: {e}")
                    return False
                except Exception as e:
                    logger.error(
                        f"❌ conversation_manager.update_conversation 调用失败: {e}"
                    )
                    return False
            else:
                if not session:
                    logger.warning("⚠️ 缺少 session 参数，无法调用框架接口")
                else:
                    logger.warning(
                        "⚠️ conversation_manager.update_conversation 方法不存在"
                    )
                return False

        except Exception as e:
            logger.error(f"使用框架接口保存对话失败: {e}")
            return False

    async def backup_conversation_history(
        self, session: str, curr_cid: str, history: list
    ):
        """备用的对话历史保存机制

        Args:
            session: 会话ID
            curr_cid: 对话ID
            history: 历史记录列表
        """
        try:
            plugin_data_dir = self.persistence_manager.get_plugin_data_dir()
            backup_dir = os.path.join(plugin_data_dir, "conversation_backup")
            os.makedirs(backup_dir, exist_ok=True)

            backup_file = os.path.join(backup_dir, f"{curr_cid}.json")
            backup_data = {
                "session": session,
                "conversation_id": curr_cid,
                "history": history,
                "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "backup_reason": "framework_interface_unavailable",
            }

            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 对话历史已备份到: {backup_file}")

        except Exception as e:
            logger.error(f"备份对话历史失败: {e}")

    async def fallback_database_save(self, conversation, curr_cid: str) -> bool:
        """回退方案：直接操作数据库（仅在框架接口不可用时使用）

        Args:
            conversation: 对话对象
            curr_cid: 对话ID

        Returns:
            是否保存成功
        """
        try:
            logger.warning("⚠️ 正在使用数据库直接操作作为回退方案")

            db = self.context.get_db()
            if not db or not hasattr(db, "conn"):
                logger.error("❌ 无法获取数据库连接")
                return False

            conn = db.conn
            cursor = conn.cursor()

            # 检查数据库结构
            if not verify_database_schema(cursor):
                return False

            # 执行更新操作
            try:
                cursor.execute(
                    "UPDATE webchat_conversation SET history = ?, updated_at = ? WHERE cid = ?",
                    (
                        conversation.history,
                        int(datetime.datetime.now().timestamp()),
                        curr_cid,
                    ),
                )
                affected_rows = cursor.rowcount
                conn.commit()

                if affected_rows > 0:
                    logger.debug("✅ 数据库直接操作保存成功")
                    return True
                else:
                    logger.warning("⚠️ 数据库更新未影响任何行，可能对话ID不存在")
                    return False

            except sqlite3.Error as e:
                logger.error(f"数据库错误: {e}")
                conn.rollback()
                return False

        except (AttributeError, TypeError) as e:
            logger.error(f"数据库对象错误: {e}")
            return False
