"""信息显示命令"""

from astrbot.api.event import AstrMessageEvent
from ..core.runtime_data import runtime_data


class DisplayHandlersMixin:
    """信息显示命令"""

    async def show_info(self, event: AstrMessageEvent, show_type: str = ""):
        """显示信息 - 支持多种显示类型

        可用的显示类型：
        - prompt: 显示当前配置下会输入给LLM的组合话本（主动对话提示词列表）
        - users: 显示已记录的用户信息（包括昵称、平台等）

        使用方法: /proactive show [类型]
        例如: /proactive show prompt
        """

        if show_type == "prompt":
            prompts = self.config.get("proactive_reply", {}).get(
                "proactive_prompt_list", []
            )
            text = f"📝 主动对话提示词列表 (共{len(prompts)}条):\n\n"
            for i, prompt in enumerate(prompts, 1):
                text += (
                    f"{i}. {prompt[:100]}...\n"
                    if len(str(prompt)) > 100
                    else f"{i}. {prompt}\n"
                )
            yield event.plain_result(text)

        elif show_type == "users":
            user_info = runtime_data.session_user_info
            text = f"👥 已记录用户信息 (共{len(user_info)}个):\n\n"
            for session, info in list(user_info.items())[:10]:
                text += f"• {info.get('username', '未知')} ({info.get('platform', '未知')})\n"
            yield event.plain_result(text)

        else:
            yield event.plain_result(
                "可用的显示命令:\n- `/proactive show prompt` - 显示提示词\n- `/proactive show users` - 显示用户信息"
            )
