"""
提示词构建器

负责构建LLM系统提示词
"""

import random
from astrbot.api import logger
from .placeholder_utils import replace_placeholders
from ..utils.parsers import parse_prompt_list


class PromptBuilder:
    """提示词构建器类"""

    def __init__(self, config: dict, context):
        """初始化提示词构建器

        Args:
            config: 配置字典
            context: AstrBot上下文对象
        """
        self.config = config
        self.context = context

    def replace_placeholders(
        self, prompt: str, session: str, config: dict, build_user_context_func
    ) -> str:
        """替换提示词中的占位符（包装方法）"""
        return replace_placeholders(prompt, session, config, build_user_context_func)

    def _get_persona_name(self, persona) -> str:
        """获取人格名称（支持 dict/Personality 和 Persona SQLModel 两种形式）"""
        if isinstance(persona, dict):
            return persona.get("name", "")
        # Persona SQLModel 使用 persona_id 字段
        return getattr(persona, "persona_id", "") or getattr(persona, "name", "")

    def _get_persona_prompt(self, persona) -> str:
        """获取人格提示词（支持 dict/Personality 和 Persona SQLModel 两种形式）"""
        if isinstance(persona, dict):
            return persona.get("prompt", "")
        # Persona SQLModel 使用 system_prompt 字段
        return getattr(persona, "system_prompt", "") or getattr(persona, "prompt", "")

    def get_proactive_prompt(self, session: str, build_user_context_func) -> str:
        """获取并处理主动对话提示词

        优先使用 AI 自主调度保存的 follow_up_prompt（一次性），
        如果没有则从 proactive_prompt_list 中随机选择。

        Args:
            session: 会话ID
            build_user_context_func: 构建用户上下文的函数

        Returns:
            处理后的提示词，失败返回None
        """
        proactive_config = self.config.get("proactive_reply", {})
        prompt_list_data = proactive_config.get("proactive_prompt_list", [])

        if not prompt_list_data:
            logger.warning(f"心念 | ⚠️ 会话 {session} 没有配置主动消息提示词列表")
            return ""

        # 解析主动对话提示词列表
        prompt_list = parse_prompt_list(prompt_list_data)
        if not prompt_list:
            logger.warning("心念 | ⚠️ 主动对话提示词列表为空")
            return ""

        # 随机选择一个主动对话提示词
        selected_prompt = random.choice(prompt_list)

        # 替换提示词中的占位符
        final_prompt = replace_placeholders(
            selected_prompt, session, self.config, build_user_context_func
        )
        return final_prompt

    async def get_persona_system_prompt(self, session: str) -> str:
        """获取人格系统提示词

        Args:
            session: 会话ID

        Returns:
            人格系统提示词
        """
        base_system_prompt = ""
        try:
            # 尝试获取当前会话的人格设置
            uid = session  # session 就是 unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                uid
            )

            # 获取人格列表（通过 persona_manager 异步获取）
            personas = await self.context.persona_manager.get_all_personas() or []

            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(
                    uid, curr_cid
                )

                if (
                    conversation
                    and conversation.persona_id
                    and conversation.persona_id != "[%None]"
                ):
                    target_persona_id = conversation.persona_id

                    # 人格匹配
                    available_names = [self._get_persona_name(p) for p in personas]
                    logger.debug(
                        f"心念 | 人格匹配 - 请求: '{target_persona_id}', 可用: {available_names}"
                    )

                    if personas:
                        # 精确匹配
                        for persona in personas:
                            if self._get_persona_name(persona) == target_persona_id:
                                base_system_prompt = self._get_persona_prompt(persona)
                                logger.debug(
                                    f"心念 | 人格匹配成功 (精确): '{target_persona_id}'"
                                )
                                break

                        # 若精确匹配失败，尝试大小写不敏感匹配
                        if not base_system_prompt:
                            for persona in personas:
                                name = self._get_persona_name(persona)
                                if name and name.lower() == target_persona_id.lower():
                                    base_system_prompt = self._get_persona_prompt(
                                        persona
                                    )
                                    logger.debug(
                                        f"心念 | 人格匹配成功 (忽略大小写): '{target_persona_id}' -> '{name}'"
                                    )
                                    break

                        # 匹配失败警告
                        if not base_system_prompt:
                            logger.warning(
                                f"心念 | ⚠️ 人格匹配失败: 会话请求 '{target_persona_id}' 不在可用人格列表 {available_names} 中"
                            )

            # 如果没有获取到人格提示词，尝试从配置中获取当前默认人格
            if not base_system_prompt:
                base_system_prompt = self._get_default_persona_prompt(personas)

        except Exception as e:
            logger.warning(f"心念 | ⚠️ 获取人格系统提示词失败: {e}")

        return base_system_prompt

    def _get_default_persona_prompt(self, personas: list) -> str:
        """从 AstrBot 配置中动态获取当前设置的默认人格

        Args:
            personas: 人格列表

        Returns:
            默认人格的提示词
        """
        try:
            # 从 AstrBot 配置中读取当前设置的默认人格名称
            astrbot_config = self.context.get_config()
            default_persona_name = None

            # 尝试用字典方式获取（AstrBotConfig 支持 get 方法）
            if hasattr(astrbot_config, "get"):
                # 从 provider_settings 获取 default_personality（正确的字段名）
                provider_settings = astrbot_config.get("provider_settings", {})
                if provider_settings and isinstance(provider_settings, dict):
                    # 优先使用 default_personality 字段
                    default_persona_name = provider_settings.get("default_personality")
                    if default_persona_name:
                        logger.debug(f"心念 | 从配置获取默认人格: '{default_persona_name}'")

            # 如果获取到默认人格名称，从人格列表中查找
            if default_persona_name and personas:
                for persona in personas:
                    if self._get_persona_name(persona) == default_persona_name:
                        prompt = self._get_persona_prompt(persona)
                        logger.debug(
                            f"心念 | 使用默认人格 '{default_persona_name}' (prompt长度: {len(prompt)}字符)"
                        )
                        return prompt

                # 匹配失败
                available = [self._get_persona_name(p) for p in personas]
                logger.warning(
                    f"心念 | ⚠️ 配置的默认人格 '{default_persona_name}' 在人格列表 {available} 中未找到"
                )

            # 方法2: 如果还是没有，使用人格列表的第一个
            if personas:
                first_persona = personas[0]
                persona_name = self._get_persona_name(first_persona)
                prompt = self._get_persona_prompt(first_persona)

                if prompt:
                    logger.debug(
                        f"心念 | 使用人格列表第一个 '{persona_name}' (prompt长度: {len(prompt)}字符)"
                    )
                    return prompt

            logger.debug("心念 | 未找到任何可用人格")
            return ""

        except Exception as e:
            logger.warning(f"心念 | ⚠️ 获取默认人格失败: {e}")
            return ""

    def build_combined_system_prompt(
        self,
        base_system_prompt: str,
        final_prompt: str,
        history_guidance: str,
        session: str = None,
        build_user_context_func=None,
    ) -> str:
        """构建组合系统提示词

        Args:
            base_system_prompt: 基础人格提示词
            final_prompt: 主动对话提示词
            history_guidance: 历史记录引导
            session: 会话ID (可选，用于替换时间感知提示词中的占位符)
            build_user_context_func: 构建用户上下文的函数 (可选)

        Returns:
            组合后的系统提示词
        """
        default_persona = self.config.get("proactive_reply", {}).get(
            "proactive_default_persona", ""
        )

        # 从配置中读取时间感知增强提示词设置
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
            time_guidance_content = (
                custom_prompt if custom_prompt else default_time_guidance
            )

            # 如果提供了 session，替换占位符
            if session and build_user_context_func:
                try:
                    time_guidance_content = replace_placeholders(
                        time_guidance_content,
                        session,
                        self.config,
                        build_user_context_func,
                    )
                except Exception as e:
                    logger.warning(f"心念 | ⚠️ 时间感知提示词占位符替换失败: {e}")

            time_guidance = f"\n\n{time_guidance_content}\n"

        if base_system_prompt:
            # 有AstrBot人格：使用AstrBot人格 + 时间指导 + 主动对话提示词 + 历史记录引导
            combined_system_prompt = f"{base_system_prompt}{time_guidance}\n\n--- 主动对话指令 ---\n{final_prompt}{history_guidance}"
        else:
            # 没有AstrBot人格：使用插件默认人格 + 时间指导 + 主动对话提示词 + 历史记录引导
            if default_persona:
                combined_system_prompt = f"{default_persona}{time_guidance}\n\n--- 主动对话指令 ---\n{final_prompt}{history_guidance}"
            else:
                combined_system_prompt = (
                    f"{time_guidance}\n\n{final_prompt}{history_guidance}"
                )

        return combined_system_prompt

    async def get_base_system_prompt(self) -> str:
        """获取基础系统提示词（人格提示词）

        与 get_persona_system_prompt 使用相同的动态获取逻辑，
        确保显示的人格信息与实际使用的一致。

        Returns:
            基础系统提示词
        """
        try:
            # 通过 persona_manager 异步获取人格列表
            personas = await self.context.persona_manager.get_all_personas() or []

            # 使用与 get_persona_system_prompt 相同的动态获取逻辑
            base_system_prompt = self._get_default_persona_prompt(personas)

            # 如果还是没有获取到，使用插件默认人格
            if not base_system_prompt:
                proactive_config = self.config.get("proactive_reply", {})
                base_system_prompt = proactive_config.get(
                    "proactive_default_persona", "你是一个友好、轻松的AI助手。"
                )

            return base_system_prompt

        except Exception as e:
            logger.warning(f"心念 | ⚠️ 获取基础系统提示词失败: {e}")
            # 返回插件默认人格
            proactive_config = self.config.get("proactive_reply", {})
            return proactive_config.get(
                "proactive_default_persona", "你是一个友好、轻松的AI助手。"
            )
