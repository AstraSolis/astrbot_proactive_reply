"""
用户信息管理器

负责记录和管理用户信息及AI消息时间
"""

import datetime
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class UserInfoManager:
    """用户信息管理器类"""

    def __init__(self, config: dict, config_manager, persistence_manager):
        """初始化用户信息管理器

        Args:
            config: 配置字典
            config_manager: 配置管理器
            persistence_manager: 持久化管理器
        """
        self.config = config
        self.config_manager = config_manager
        self.persistence_manager = persistence_manager

    async def add_user_info_to_request(self, event: AstrMessageEvent, req):
        """在LLM请求前添加用户信息和时间

        Args:
            event: 消息事件
            req: LLM请求对象
        """
        user_config = self.config.get("user_info", {})

        # 获取用户信息
        username = ""
        if hasattr(event.message_obj, "sender") and event.message_obj.sender:
            username = event.message_obj.sender.nickname or "未知用户"
        else:
            username = event.get_sender_name() or "未知用户"

        # 获取用户ID
        user_id = ""
        if hasattr(event.message_obj, "sender") and event.message_obj.sender:
            user_id = (
                event.message_obj.sender.user_id or event.get_sender_id() or "未知"
            )
        else:
            user_id = event.get_sender_id() or "未知"

        # 获取时间信息
        time_format = user_config.get("time_format", "%Y-%m-%d %H:%M:%S")
        try:
            if hasattr(event.message_obj, "timestamp") and event.message_obj.timestamp:
                current_time = datetime.datetime.fromtimestamp(
                    event.message_obj.timestamp
                ).strftime(time_format)
            else:
                current_time = datetime.datetime.now().strftime(time_format)
        except Exception as e:
            logger.warning(f"时间格式错误 '{time_format}': {e}，使用默认格式")
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 获取平台信息
        platform_name = event.get_platform_name() or "未知平台"
        message_type = "群聊" if event.message_obj.group_id else "私聊"

        # 构建用户信息字符串
        template = user_config.get(
            "template",
            "当前对话信息：\n用户：{username}\n时间：{time}\n平台：{platform}（{chat_type}）\n\n",
        )
        try:
            user_info = template.format(
                username=username,
                user_id=user_id,
                time=current_time,
                platform=platform_name,
                chat_type=message_type,
            )
        except Exception as e:
            logger.warning(f"用户信息模板格式错误: {e}，使用默认模板")
            user_info = f"当前对话信息：\n用户：{username}\n时间：{current_time}\n平台：{platform_name}（{message_type}）\n\n"

        # 追加用户信息到系统提示
        if req.system_prompt:
            req.system_prompt = req.system_prompt.rstrip() + f"\n\n{user_info}"
        else:
            req.system_prompt = user_info

        # 记录用户信息
        self.record_user_info(event, username, user_id, platform_name, message_type)

    def record_user_info(
        self,
        event: AstrMessageEvent,
        username: str,
        user_id: str,
        platform_name: str,
        message_type: str,
    ):
        """记录用户信息到配置文件

        Args:
            event: 消息事件
            username: 用户名
            user_id: 用户ID
            platform_name: 平台名称
            message_type: 消息类型
        """
        try:
            session_id = event.unified_msg_origin
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not session_id:
                logger.warning("会话ID为空，跳过用户信息记录")
                return

            # 确保配置结构存在
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}
            if "session_user_info" not in self.config["proactive_reply"]:
                self.config["proactive_reply"]["session_user_info"] = {}

            # 记录用户信息
            user_info = {
                "username": username or "未知用户",
                "user_id": user_id or "未知",
                "platform": platform_name or "未知平台",
                "chat_type": message_type or "未知",
                "last_active_time": current_time,
            }

            self.config["proactive_reply"]["session_user_info"][session_id] = user_info

            # 保存配置
            config_saved = self.config_manager.save_config_safely()
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not (config_saved or persistent_saved):
                logger.error("❌ 用户信息保存失败")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"记录用户信息失败: {e}")

    async def record_ai_message_time(self, event: AstrMessageEvent):
        """在AI发送消息后记录发送时间

        Args:
            event: 消息事件
        """
        try:
            session_id = event.unified_msg_origin
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not session_id:
                logger.warning("会话ID为空，跳过AI消息时间记录")
                return

            # 确保配置结构存在
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}
            if "ai_last_sent_times" not in self.config["proactive_reply"]:
                self.config["proactive_reply"]["ai_last_sent_times"] = {}

            # 记录AI发送消息时间
            self.config["proactive_reply"]["ai_last_sent_times"][session_id] = (
                current_time
            )

            # 保存配置
            config_saved = self.config_manager.save_config_safely()
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not (config_saved or persistent_saved):
                logger.warning("⚠️ AI消息时间记录保存失败")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"记录AI消息时间失败: {e}")

    def record_sent_time(self, session: str):
        """记录消息发送时间

        Args:
            session: 会话ID
        """
        try:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not session:
                logger.warning("会话ID为空，跳过发送时间记录")
                return

            # 确保配置结构存在
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}
            if "last_sent_times" not in self.config["proactive_reply"]:
                self.config["proactive_reply"]["last_sent_times"] = {}
            if "ai_last_sent_times" not in self.config["proactive_reply"]:
                self.config["proactive_reply"]["ai_last_sent_times"] = {}

            # 记录发送时间（同时更新两个记录）
            self.config["proactive_reply"]["last_sent_times"][session] = current_time
            self.config["proactive_reply"]["ai_last_sent_times"][session] = current_time

            # 保存配置
            config_saved = self.config_manager.save_config_safely()
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not (config_saved or persistent_saved):
                logger.error("❌ 发送时间保存失败")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"记录发送时间失败: {e}")

    def build_user_context_for_proactive(self, session: str) -> str:
        """为主动对话构建用户上下文信息

        Args:
            session: 会话ID

        Returns:
            用户上下文字符串
        """
        try:
            proactive_config = self.config.get("proactive_reply", {})
            session_user_info = proactive_config.get("session_user_info", {})
            ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

            user_info = session_user_info.get(session, {})
            last_sent_time = ai_last_sent_times.get(session, "从未发送过")

            context_parts = []

            # 添加用户基本信息
            if user_info:
                username = user_info.get("username", "")
                platform = user_info.get("platform", "")
                chat_type = user_info.get("chat_type", "")
                last_active = user_info.get("last_active_time", "")

                if username:
                    context_parts.append(f"用户昵称：{username}")
                if platform:
                    context_parts.append(f"平台：{platform}")
                if chat_type:
                    context_parts.append(f"聊天类型：{chat_type}")
                if last_active:
                    context_parts.append(f"用户最后活跃时间：{last_active}")

            # 添加AI上次发送时间信息
            if last_sent_time != "从未发送过":
                context_parts.append(f"AI上次发送消息时间：{last_sent_time}")
            else:
                context_parts.append("这是AI第一次主动发起对话")

            # 添加当前时间
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            context_parts.append(f"当前时间：{current_time}")

            if context_parts:
                return "用户信息：\n" + "\n".join(context_parts)
            else:
                return "暂无用户信息记录"

        except Exception as e:
            logger.error(f"构建用户上下文失败: {e}")
            return "无法获取用户信息"
