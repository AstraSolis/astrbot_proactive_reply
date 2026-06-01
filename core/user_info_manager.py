"""
用户信息管理器

负责记录和管理用户信息及AI消息时间
"""

import datetime
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from .runtime_data import runtime_data
from ..constants import (
    DEFAULT_TIME_GUIDANCE_PROMPT,
    LEGACY_DEFAULT_TIME_GUIDANCE_PROMPT,
)
from ..llm.placeholder_utils import (
    build_placeholder_map,
    render_template,
    resolve_event_identity,
    stabilize_static_prompt_template,
)
from ..utils.time_utils import (
    get_now,
    get_sleep_prompt_if_active as _check_sleep_prompt,
)

# 用户信息模板默认值（占位符由统一注册表解析）
DEFAULT_USER_INFO_TEMPLATE = "当前对话信息：\n用户：{username}\n时间：{time}\n平台：{platform}（{chat_type}）\n\n"


class UserInfoManager:
    """用户信息管理器类"""

    def __init__(self, config: dict, config_manager, persistence_manager, context=None):
        """初始化用户信息管理器

        Args:
            config: 配置字典
            config_manager: 配置管理器
            persistence_manager: 持久化管理器
        """
        self.config = config
        self.config_manager = config_manager
        self.persistence_manager = persistence_manager
        self.context = context

    def _get_astrbot_config(self):
        """安全获取 AstrBot 全局配置"""
        try:
            if self.context is not None:
                return self.context.get_config()
        except Exception:
            pass
        return None

    async def add_user_info_to_request(self, event: AstrMessageEvent, req):
        """在 LLM 请求前通过 extra_user_content_parts 追加动态附带信息

        Args:
            event: 消息事件
            req: LLM请求对象
        """
        user_config = self.config.get("user_info", {})

        # 检查是否启用用户信息附加功能
        if not user_config.get("enabled", True):
            logger.debug("心念 | 用户信息附加功能已关闭")
            return

        # 获取时间格式与会话ID
        time_format = user_config.get("time_format", "%Y-%m-%d %H:%M:%S")
        astrbot_config = self._get_astrbot_config()
        session_id = event.unified_msg_origin

        # 构建用户信息字符串（占位符由统一注册表解析）
        template = user_config.get("template", DEFAULT_USER_INFO_TEMPLATE)
        try:
            mapping = build_placeholder_map(
                session_id,
                self.config,
                astrbot_config,
                event=event,
                time_format=time_format,
                build_user_context_func=self.build_user_context_for_proactive,
            )
            user_info = render_template(template, mapping)
        except Exception as e:
            logger.warning(f"心念 | ⚠️ 用户信息模板格式错误: {e}，使用默认模板")
            try:
                fallback_map = build_placeholder_map(
                    session_id,
                    self.config,
                    astrbot_config,
                    event=event,
                    time_format=time_format,
                )
                user_info = render_template(DEFAULT_USER_INFO_TEMPLATE, fallback_map)
            except Exception as fallback_error:
                logger.error(f"心念 | ❌ 构建默认用户信息失败: {fallback_error}")
                user_info = ""

        # 获取时间感知增强提示词配置
        time_awareness_config = self.config.get("time_awareness", {})
        time_guidance_enabled = time_awareness_config.get("time_guidance_enabled", True)

        static_system_prompts = []
        if time_guidance_enabled:
            # 从配置中读取自定义提示词，如果没有则使用默认值
            custom_prompt = time_awareness_config.get("time_guidance_prompt", "")
            time_guidance = (
                custom_prompt
                if custom_prompt
                and custom_prompt != LEGACY_DEFAULT_TIME_GUIDANCE_PROMPT
                else DEFAULT_TIME_GUIDANCE_PROMPT
            )
            time_guidance = stabilize_static_prompt_template(time_guidance)
            if time_guidance:
                static_system_prompts.append(time_guidance)

        sleep_prompt = self._get_sleep_prompt_if_active()

        # 固定提示词放在 system_prompt 末尾，条件性上下文放在本轮用户消息后。
        self._append_static_system_prompt(req, "\n\n".join(static_system_prompts))
        self._prepend_dynamic_user_content(req, user_info)
        if sleep_prompt:
            self._append_dynamic_user_content(req, sleep_prompt)

        # 记录用户信息
        self.record_user_info(event)

    def record_user_info(self, event: AstrMessageEvent):
        """记录用户信息到运行时数据存储

        Args:
            event: 消息事件（用户名/ID/平台/聊天类型由统一身份解析得出）
        """
        try:
            session_id = event.unified_msg_origin
            current_time = get_now(self.config, self._get_astrbot_config()).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            if not session_id:
                logger.warning("心念 | ⚠️ 会话ID为空，跳过用户信息记录")
                return

            # 记录用户信息到运行时数据存储
            identity = resolve_event_identity(event)
            user_info = {
                "username": identity["username"],
                "user_id": identity["user_id"],
                "platform": identity["platform"],
                "chat_type": identity["chat_type"],
                "last_active_time": current_time,
            }

            runtime_data.session_user_info[session_id] = user_info

            # 用户回复后重置未回复计数
            runtime_data.session_unreplied_count[session_id] = 0

            # 保存持久化数据
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not persistent_saved:
                logger.error("心念 | ❌ 用户信息保存失败")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"心念 | ❌ 记录用户信息失败: {e}")

    async def record_ai_message_time(self, event: AstrMessageEvent):
        """在AI发送消息后记录发送时间

        Args:
            event: 消息事件
        """
        try:
            session_id = event.unified_msg_origin
            current_time = get_now(self.config, self._get_astrbot_config()).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            if not session_id:
                logger.warning("心念 | ⚠️ 会话ID为空，跳过AI消息时间记录")
                return

            # 记录AI发送消息时间到运行时数据存储
            runtime_data.ai_last_sent_times[session_id] = current_time

            # 保存持久化数据
            persistent_saved = self.persistence_manager.save_persistent_data()

            if not persistent_saved:
                logger.warning("心念 | ⚠️ AI消息时间记录保存失败")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"心念 | ❌ 记录AI消息时间失败: {e}")

    def record_sent_time(self, session: str):
        """记录消息发送时间

        Args:
            session: 会话ID
        """
        try:
            current_time = get_now(self.config, self._get_astrbot_config()).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            if not session:
                logger.warning("心念 | ⚠️ 会话ID为空，跳过发送时间记录")
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
                logger.error("心念 | ❌ 发送时间保存失败")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"心念 | ❌ 记录发送时间失败: {e}")

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
            current_time = get_now(self.config, self._get_astrbot_config()).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            context_parts.append(f"当前时间：{current_time}")

            if context_parts:
                return "用户信息：\n" + "\n".join(context_parts)
            else:
                return "暂无用户信息记录"

        except Exception as e:
            logger.error(f"心念 | ❌ 构建用户上下文失败: {e}")
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
            logger.error(f"心念 | ❌ 获取AI最后消息时间失败: {e}")
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
            now = get_now(self.config, self._get_astrbot_config()).replace(tzinfo=None)
            delta = now - last_time
            return int(delta.total_seconds() / 60)
        except Exception as e:
            logger.error(f"心念 | ❌ 计算距离AI最后消息的分钟数失败: {e}")
            return -1

    def _append_dynamic_user_content(self, req, additional_prompt: str) -> None:
        """将动态附带信息追加到 extra_user_content_parts，不修改 system_prompt

        遵循 AstrBot 官方推荐：动态上下文放在本轮用户输入之后，并标记为临时内容。
        """
        self._insert_dynamic_user_content(
            req, additional_prompt, len(req.extra_user_content_parts)
        )

    def _prepend_dynamic_user_content(self, req, additional_prompt: str) -> None:
        """将动态附带信息插入到 extra_user_content_parts 最前面，不修改 system_prompt"""
        self._insert_dynamic_user_content(req, additional_prompt, 0)

    def _insert_dynamic_user_content(
        self, req, additional_prompt: str, index: int
    ) -> None:
        try:
            from astrbot.core.agent.message import TextPart
        except ImportError:
            logger.warning("心念 | ⚠️ 无法导入 TextPart，跳过附带信息注入")
            return

        req.extra_user_content_parts.insert(
            index,
            self._make_temp_text_part(TextPart, additional_prompt),
        )

    def _append_static_system_prompt(self, req, additional_prompt: str) -> None:
        """将固定提示词追加到 system_prompt 末尾"""
        additional_prompt = (additional_prompt or "").strip()
        if not additional_prompt:
            return

        system_prompt = getattr(req, "system_prompt", "") or ""
        if system_prompt.strip():
            req.system_prompt = f"{system_prompt.rstrip()}\n\n{additional_prompt}"
        else:
            req.system_prompt = additional_prompt

    @staticmethod
    def _make_temp_text_part(text_part_cls, text: str):
        """创建临时 TextPart，兼容 mark_as_temp 尚未可用的旧版 AstrBot"""
        part = text_part_cls(text=text)
        mark_as_temp = getattr(part, "mark_as_temp", None)
        if callable(mark_as_temp):
            return mark_as_temp()
        return part

    def _get_sleep_prompt_if_active(self) -> str:
        """检查是否处于睡眠时间，如果是则返回配置的睡眠提示

        Returns:
            睡眠提示字符串，如果不在睡眠时间则返回空字符串
        """
        return _check_sleep_prompt(self.config, self._get_astrbot_config())
