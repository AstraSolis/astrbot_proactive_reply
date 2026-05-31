"""通用命令（帮助/重启/配置）"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from ..core.runtime_data import runtime_data


class GeneralHandlersMixin:
    """通用命令（帮助/重启/配置）"""

    async def help_command(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """🤖 AstrBot 主动回复插件

基础命令:
- `/proactive status` - 查看状态
- `/proactive add_session` - 添加会话
- `/proactive remove_session` - 移除会话

管理员命令 (仅管理员可用):
- `/proactive config` - 查看配置
- `/proactive restart` - 重启任务

测试命令 (仅管理员可用):
- `/proactive test [类型]` - 测试功能
  类型: basic, llm, generation, prompt, placeholders, history, save, schedule

显示命令 (仅管理员可用):
- `/proactive show [类型]` - 显示信息
  类型: prompt, users

管理命令 (仅管理员可用):
- `/proactive manage [操作]` - 管理功能
  操作: clear, task_status, force_stop, force_start, save_config
  调试: debug_info, debug_send, debug_times

💡 详细配置请在 AstrBot 配置面板中修改"""
        yield event.plain_result(help_text)

    async def restart(self, event: AstrMessageEvent):
        """重启定时任务"""
        yield event.plain_result("⏳ 正在重启定时任务...")
        try:
            await self.plugin.task_manager.restart_proactive_task()
            yield event.plain_result("✅ 定时任务已重启")
        except Exception as e:
            yield event.plain_result(f"❌ 重启失败: {e}")

    async def show_config(self, event: AstrMessageEvent):
        """显示完整的插件配置"""
        try:
            user_config = self.config.get("user_info", {})
            proactive_config = self.config.get("proactive_reply", {})

            # 1. 用户信息配置
            config_text = "📋 插件完整配置\n\n"
            config_text += "=" * 50 + "\n"
            config_text += "👤 用户信息附加配置\n"
            config_text += "=" * 50 + "\n"
            config_text += (
                f"时间格式: {user_config.get('time_format', '%Y-%m-%d %H:%M:%S')}\n"
            )
            template = user_config.get(
                "template",
                "当前对话信息：\\n用户：{username}\\n时间：{time}\\n平台：{platform}（{chat_type}）\\n\\n",
            )
            config_text += (
                f"模板: {template[:100]}{'...' if len(template) > 100 else ''}\n"
            )
            config_text += "支持占位符: {username}, {user_id}, {time}, {current_time}, {platform}, {chat_type}, {user_last_message_time}, {user_last_message_time_ago}, {ai_last_sent_time}\n\n"

            # 2. 主动回复功能配置
            config_text += "=" * 50 + "\n"
            config_text += "🤖 主动回复功能配置\n"
            config_text += "=" * 50 + "\n"
            config_text += f"功能状态: {'✅ 已启用' if proactive_config.get('enabled', False) else '❌ 已禁用'}\n"
            config_text += (
                f"定时模式: {proactive_config.get('timing_mode', 'fixed_interval')}\n"
            )
            config_text += (
                f"发送间隔: {proactive_config.get('interval_minutes', 600)} 分钟\n"
            )
            config_text += f"睡眠时间: {self._get_sleep_time_status()}\n"
            config_text += f"随机延迟: {'✅ 已启用' if proactive_config.get('random_delay_enabled', False) else '❌ 未启用'}\n"

            if proactive_config.get("random_delay_enabled", False):
                config_text += f"  - 随机延迟范围: {proactive_config.get('min_random_minutes', 0)}-{proactive_config.get('max_random_minutes', 30)} 分钟\n"

            # 3. 历史记录配置
            config_text += f"\n对话历史记录: {'✅ 已启用' if proactive_config.get('include_history_enabled', False) else '❌ 未启用'}\n"
            if proactive_config.get("include_history_enabled", False):
                config_text += f"  - 历史记录条数: {proactive_config.get('history_message_count', 10)} 条\n"

            # 4. 消息分割配置
            split_config = self.config.get("message_split", {})
            config_text += f"\n消息分割功能: {'✅ 已启用' if split_config.get('enabled', True) else '❌ 未启用'}\n"
            if split_config.get("enabled", True):
                config_text += (
                    f"  - 分割模式: {split_config.get('mode', 'backslash')}\n"
                )
                config_text += (
                    f"  - 分割延迟: {split_config.get('delay_ms', 500)} 毫秒\n"
                )

            # 5. 会话和记录统计
            # 获取会话列表
            from ..utils.parsers import parse_sessions_list

            sessions_data = proactive_config.get("sessions", [])
            sessions = parse_sessions_list(sessions_data)

            config_text += "\n" + "=" * 50 + "\n"
            config_text += "📊 数据统计\n"
            config_text += "=" * 50 + "\n"
            config_text += f"配置的会话数: {len(sessions)}\n"
            config_text += f"记录的用户信息: {len(runtime_data.session_user_info)} 个\n"
            config_text += (
                f"AI发送时间记录: {len(runtime_data.ai_last_sent_times)} 条\n"
            )

            # 6. 提示词配置
            config_text += "\n" + "=" * 50 + "\n"
            config_text += "💬 提示词配置\n"
            config_text += "=" * 50 + "\n"

            # 获取基础人格提示词
            base_prompt = await self.plugin.prompt_builder.get_base_system_prompt()
            config_text += f"基础人格提示词长度: {len(base_prompt)} 字符\n"
            config_text += f"基础人格提示词预览:\n{base_prompt[:200]}{'...' if len(base_prompt) > 200 else ''}\n\n"

            # 主动对话提示词列表
            prompt_list = proactive_config.get("proactive_prompt_list", [])
            config_text += f"主动对话提示词数量: {len(prompt_list)} 条\n"

            # 备用人格
            default_persona = proactive_config.get("proactive_default_persona", "")
            if default_persona:
                config_text += f"\n插件备用人格长度: {len(default_persona)} 字符\n"

            config_text += "\n💡 使用 /proactive show prompt 查看所有主动对话提示词"

            yield event.plain_result(config_text)

        except Exception as e:
            logger.error(f"心念 | ❌ 显示配置失败: {e}")
            yield event.plain_result(f"❌ 显示配置失败: {e}")
