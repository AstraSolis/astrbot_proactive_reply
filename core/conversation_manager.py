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

            if not conversation or not conversation.history:
                return []

            try:
                history = json.loads(conversation.history)
                if not isinstance(history, list):
                    logger.warning(f"会话 {session} 的历史记录格式不正确，不是列表格式")
                    return []

                # 限制历史记录数量
                if max_count > 0 and len(history) > max_count:
                    history = history[-max_count:]

                # 验证历史记录格式
                valid_history = []
                for item in history:
                    if isinstance(item, dict) and "role" in item and "content" in item:
                        if isinstance(item["content"], str):
                            valid_history.append(item)

                return valid_history

            except json.JSONDecodeError as e:
                logger.warning(f"解析会话 {session} 的历史记录JSON失败: {e}")
                return []

        except Exception as e:
            logger.error(f"获取会话 {session} 的历史记录失败: {e}")
            return []

    async def add_message_to_conversation_history(self, session: str, message: str):
        """将AI主动发送的消息添加到对话历史记录中

        Args:
            session: 会话ID
            message: 消息内容
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

            # 添加AI的主动消息到历史记录
            ai_message = {"role": "assistant", "content": message}
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

        except Exception as e:
            logger.error(f"将消息添加到对话历史时发生错误: {e}")

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
