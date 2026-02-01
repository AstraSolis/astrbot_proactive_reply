"""
用户信息管理器

负责记录和管理用户信息及AI消息时间
"""

import datetime
import re
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from .runtime_data import runtime_data
from ..llm.placeholder_utils import format_time_ago


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
            # 获取会话ID用于获取历史数据
            session_id = event.unified_msg_origin

            # 获取用户上次发消息时间
            stored_user_info = runtime_data.session_user_info.get(session_id, {})
            user_last_message_time = stored_user_info.get("last_active_time", "未知")

            # 获取AI上次发送时间
            ai_last_sent_time = runtime_data.ai_last_sent_times.get(
                session_id, "从未发送过"
            )

            # 计算相对时间
            user_last_message_time_ago = format_time_ago(user_last_message_time)

            # 构建占位符字典（与主动对话统一）
            placeholders = {
                "username": username,
                "user_id": user_id,
                "time": current_time,
                "platform": platform_name,
                "chat_type": message_type,
                "current_time": current_time,
                "user_last_message_time": user_last_message_time,
                "user_last_message_time_ago": user_last_message_time_ago,
                "ai_last_sent_time": ai_last_sent_time,
            }

            # 使用安全的替换方式处理模板
            user_info = self._safe_format_template(template, placeholders)
        except Exception as e:
            logger.warning(f"用户信息模板格式错误: {e}，使用默认模板")
            user_info = f"当前对话信息：\n用户：{username}\n时间：{current_time}\n平台：{platform_name}（{message_type}）\n\n"

        # 获取时间感知增强提示词配置
        time_awareness_config = self.config.get("time_awareness", {})
        time_guidance_enabled = time_awareness_config.get("time_guidance_enabled", True)

        time_guidance = ""
        if time_guidance_enabled:
            # 从配置中读取自定义提示词，如果没有则使用默认值
            default_time_guidance = """<TIME_GUIDE: 核心时间规则（必须严格遵守）
1. 真实性：系统提供的时间信息是你唯一可信的时间来源，禁止编造或推测。
2. 自然回应：优先使用自然口语（如"刚才"、"大半夜"、"好久不见"）替代数字报时，仅在用户明确询问时提供精确时间。
3. 状态映射：依据当前时间调整人设的生理状态（如深夜困倦、饭点饥饿）。
4. 上下文感知：根据与用户上次对话的时间差（{user_last_message_time_ago}）调整语气（如很久没见要表现出想念，刚聊过则保持连贯）。>"""

            custom_prompt = time_awareness_config.get("time_guidance_prompt", "")
            time_guidance = custom_prompt if custom_prompt else default_time_guidance

            # 使用现有占位符替换 time_guidance 中的变量
            try:
                time_guidance = self._safe_format_template(time_guidance, placeholders)
            except Exception as e:
                logger.warning(f"时间感知提示词占位符替换失败: {e}")

        # 追加用户信息和时间增强提示词到系统提示
        additional_prompt = user_info
        if time_guidance:
            additional_prompt = f"{time_guidance}\n\n{user_info}"

        # 检查是否处于睡眠时间，如果是则附加睡眠提示
        sleep_prompt = self._get_sleep_prompt_if_active()
        if sleep_prompt:
            additional_prompt = f"{sleep_prompt}\n\n{additional_prompt}"

        if req.system_prompt:
            req.system_prompt = req.system_prompt.rstrip() + f"\n\n{additional_prompt}"
        else:
            req.system_prompt = additional_prompt

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

            # 记录用户信息到运行时数据存储
            user_info = {
                "username": username or "未知用户",
                "user_id": user_id or "未知",
                "platform": platform_name or "未知平台",
                "chat_type": message_type or "未知",
                "last_active_time": current_time,
            }

            runtime_data.session_user_info[session_id] = user_info

            # 用户回复后重置未回复计数
            runtime_data.session_unreplied_count[session_id] = 0

            # 保存持久化数据
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not persistent_saved:
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

            # 记录AI发送消息时间到运行时数据存储
            runtime_data.ai_last_sent_times[session_id] = current_time

            # 保存持久化数据
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not persistent_saved:
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

            # 记录发送时间到运行时数据存储（同时更新两个记录）
            runtime_data.last_sent_times[session] = current_time
            runtime_data.ai_last_sent_times[session] = current_time

            # 发送主动消息后，增加未回复计数
            current_count = runtime_data.session_unreplied_count.get(session, 0)
            runtime_data.session_unreplied_count[session] = current_count + 1

            # 保存持久化数据
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not persistent_saved:
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
            user_info = runtime_data.session_user_info.get(session, {})
            last_sent_time = runtime_data.ai_last_sent_times.get(session, "从未发送过")

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

    def get_ai_last_message_time(self, session: str) -> str:
        """获取指定会话的AI最后消息时间

        Args:
            session: 会话ID

        Returns:
            时间字符串，格式为 %Y-%m-%d %H:%M:%S，如果没有记录则返回空字符串
        """
        try:
            return runtime_data.ai_last_sent_times.get(session, "")
        except Exception as e:
            logger.error(f"获取AI最后消息时间失败: {e}")
            return ""

    def get_minutes_since_ai_last_message(self, session: str) -> int:
        """计算距离AI最后消息的分钟数

        Args:
            session: 会话ID

        Returns:
            距离上次消息的分钟数，如果没有记录则返回 -1（表示从未发送）
        """
        try:
            last_time_str = self.get_ai_last_message_time(session)
            if not last_time_str:
                return -1  # 从未发送过消息

            last_time = datetime.datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            delta = now - last_time
            return int(delta.total_seconds() / 60)
        except Exception as e:
            logger.error(f"计算距离AI最后消息的分钟数失败: {e}")
            return -1

    def _safe_format_template(self, template: str, placeholders: dict) -> str:
        """安全地替换模板中的占位符

        使用正则表达式替换，避免 str.format() 的特殊字符问题

        Args:
            template: 模板字符串
            placeholders: 占位符字典

        Returns:
            替换后的字符串
        """
        result = template
        for key, value in placeholders.items():
            # 使用正则表达式替换 {key} 格式的占位符
            pattern = r"\{" + re.escape(key) + r"\}"
            result = re.sub(pattern, str(value), result)
        return result

    def _get_sleep_prompt_if_active(self) -> str:
        """检查是否处于睡眠时间，如果是则返回配置的睡眠提示

        Returns:
            睡眠提示字符串，如果不在睡眠时间则返回空字符串
        """
        from ..utils.time_utils import get_sleep_prompt_if_active

        return get_sleep_prompt_if_active(self.config)
