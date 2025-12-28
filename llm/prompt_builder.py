"""
提示词构建器

负责构建LLM系统提示词
"""

import random
from astrbot.api import logger
from ..utils.formatters import ensure_string_encoding
from ..utils.parsers import parse_prompt_list
from .placeholder_utils import replace_placeholders


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

    def get_proactive_prompt(self, session: str, build_user_context_func) -> str:
        """获取并处理主动对话提示词

        Args:
            session: 会话ID
            build_user_context_func: 构建用户上下文的函数

        Returns:
            处理后的提示词，失败返回None
        """
        proactive_config = self.config.get("proactive_reply", {})
        prompt_list_data = proactive_config.get("proactive_prompt_list", [])

        if not prompt_list_data:
            logger.warning("未配置主动对话提示词列表")
            return None

        # 解析主动对话提示词列表
        prompt_list = parse_prompt_list(prompt_list_data)
        if not prompt_list:
            logger.warning("主动对话提示词列表为空")
            return None

        # 随机选择一个主动对话提示词
        selected_prompt = random.choice(prompt_list)
        selected_prompt = ensure_string_encoding(selected_prompt)

        # 替换提示词中的占位符
        final_prompt = replace_placeholders(
            selected_prompt, session, self.config, build_user_context_func
        )
        return ensure_string_encoding(final_prompt)

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

            # 获取默认人格设置
            default_persona_obj = self.context.provider_manager.selected_default_persona

            if curr_cid:
                conversation = await self.context.conversation_manager.get_conversation(
                    uid, curr_cid
                )

                if (
                    conversation
                    and conversation.persona_id
                    and conversation.persona_id != "[%None]"
                ):
                    # 有指定人格，尝试获取人格的系统提示词
                    personas = self.context.provider_manager.personas
                    if personas:
                        for persona in personas:
                            if (
                                hasattr(persona, "name")
                                and persona.name == conversation.persona_id
                            ):
                                base_system_prompt = ensure_string_encoding(
                                    getattr(persona, "prompt", "")
                                )
                                break

            # 如果没有获取到人格提示词，尝试使用默认人格
            if (
                not base_system_prompt
                and default_persona_obj
                and default_persona_obj.get("prompt")
            ):
                base_system_prompt = ensure_string_encoding(
                    default_persona_obj["prompt"]
                )

        except Exception as e:
            logger.warning(f"获取人格系统提示词失败: {e}")

        return base_system_prompt

    def build_combined_system_prompt(
        self, base_system_prompt: str, final_prompt: str, history_guidance: str
    ) -> str:
        """构建组合系统提示词

        Args:
            base_system_prompt: 基础人格提示词
            final_prompt: 主动对话提示词
            history_guidance: 历史记录引导

        Returns:
            组合后的系统提示词
        """
        default_persona = ensure_string_encoding(
            self.config.get("proactive_reply", {}).get("proactive_default_persona", "")
        )

        # 从配置中读取时间感知增强提示词设置
        time_awareness_config = self.config.get("time_awareness", {})
        time_guidance_enabled = time_awareness_config.get("time_guidance_enabled", True)
        
        time_guidance = ""
        if time_guidance_enabled:
            # 从配置中读取自定义提示词，如果没有则使用默认值
            default_time_guidance = """--- 核心规则（必须严格遵守）---
1. 根据提供的时间信息自然地回应
2. 系统提供的时间信息是你唯一可信的时间来源
3. 绝对禁止推测、计算或编造任何时间信息，违反此规则将导致严重后果
4. 模糊化表达：默认使用自然口语（如"刚才"、"大半夜的"、"好久不见"）替代数字报时。仅在用户明确询问时间时提供精确数值
5. 状态映射：必须依据时间调整人设的生理状态（如深夜困倦、饭点饥饿）
6. 间隔感知：根据当前与上一次对话的时间差调整语气"""
            
            custom_prompt = time_awareness_config.get("time_guidance_prompt", "")
            time_guidance_content = custom_prompt if custom_prompt else default_time_guidance
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

        return ensure_string_encoding(combined_system_prompt)

    def get_base_system_prompt(self) -> str:
        """获取基础系统提示词（人格提示词）

        Returns:
            基础系统提示词
        """
        try:
            # 获取当前使用的人格系统提示词
            base_system_prompt = ""

            # 尝试获取人格管理器
            personas = (
                self.context.provider_manager.personas
                if hasattr(self.context, "provider_manager")
                else []
            )
            default_persona_obj = None

            if hasattr(self.context, "provider_manager") and hasattr(
                self.context.provider_manager, "selected_default_persona"
            ):
                default_persona_obj = (
                    self.context.provider_manager.selected_default_persona
                )

            # 如果有默认人格，使用默认人格的提示词
            if default_persona_obj and default_persona_obj.get("prompt"):
                base_system_prompt = ensure_string_encoding(
                    default_persona_obj["prompt"]
                )
            elif personas:
                # 如果没有默认人格但有人格列表，使用第一个人格
                for persona in personas:
                    if hasattr(persona, "prompt") and persona.prompt:
                        base_system_prompt = ensure_string_encoding(persona.prompt)
                        break

            # 如果还是没有获取到，使用插件默认人格
            if not base_system_prompt:
                proactive_config = self.config.get("proactive_reply", {})
                default_persona = proactive_config.get(
                    "proactive_default_persona", "你是一个友好、轻松的AI助手。"
                )
                base_system_prompt = ensure_string_encoding(default_persona)

            return base_system_prompt

        except AttributeError as e:
            logger.warning(f"获取人格对象属性失败: {e}")
            # 返回插件默认人格
            proactive_config = self.config.get("proactive_reply", {})
            default_persona = proactive_config.get(
                "proactive_default_persona", "你是一个友好、轻松的AI助手。"
            )
            return ensure_string_encoding(default_persona)
        except KeyError as e:
            logger.warning(f"人格配置键不存在: {e}")
            return ensure_string_encoding("你是一个友好、轻松的AI助手。")
        except TypeError as e:
            logger.warning(f"人格数据类型错误: {e}")
            return ensure_string_encoding("你是一个友好、轻松的AI助手。")
