from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp
import asyncio
import random
import datetime
import re

@register("astrbot_proactive_reply", "AstraSolis", "一个支持聊天附带用户信息和定时主动发送消息的插件", "1.0.0", "https://github.com/AstraSolis/astrbot_proactive_reply")
class ProactiveReplyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.proactive_task = None
        logger.info("ProactiveReplyPlugin 插件已初始化")

    def _ensure_config_structure(self):
        """确保配置文件结构完整"""
        # 默认配置
        default_config = {
            "user_info": {
                "time_format": "%Y-%m-%d %H:%M:%S",
                "template": "[对话信息] 用户：{username}，时间：{time}"
            },
            "proactive_reply": {
                "enabled": False,
                "interval_minutes": 60,
                "message_templates": "\"嗨，最近怎么样？\"\n\"有什么我可以帮助你的吗？\"\n\"好久不见，有什么新鲜事吗？\"\n\"今天过得如何？\"\n\"有什么想聊的吗？\"",
                "sessions": "",
                "active_hours": "9:00-22:00"
            }
        }

        # 检查并补充缺失的配置
        config_updated = False
        for section, section_config in default_config.items():
            if section not in self.config:
                self.config[section] = section_config
                config_updated = True
                logger.info(f"添加缺失的配置节: {section}")
            else:
                # 检查子配置项
                for key, default_value in section_config.items():
                    if key not in self.config[section]:
                        self.config[section][key] = default_value
                        config_updated = True
                        logger.info(f"添加缺失的配置项: {section}.{key}")

        # 如果配置有更新，保存配置文件
        if config_updated:
            try:
                self.config.save_config()
                logger.info("配置文件已更新并保存")
            except Exception as e:
                logger.error(f"保存配置文件失败: {e}")

    async def initialize(self):
        """插件初始化方法"""
        # 确保配置结构完整
        self._ensure_config_structure()

        # 启动定时任务
        proactive_config = self.config.get("proactive_reply", {})
        if proactive_config.get("enabled", False):
            self.proactive_task = asyncio.create_task(self.proactive_message_loop())
            logger.info("定时主动发送任务已启动")
        else:
            logger.info("定时主动发送功能未启用")

    @filter.on_llm_request()
    async def add_user_info(self, event: AstrMessageEvent, req):
        """在LLM请求前添加用户信息和时间"""
        user_config = self.config.get("user_info", {})

        # 获取用户信息 - 从 message_obj.sender 获取
        username = ""
        if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
            username = event.message_obj.sender.nickname or "未知用户"
        else:
            username = event.get_sender_name() or "未知用户"

        # 获取用户ID
        user_id = ""
        if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
            user_id = event.message_obj.sender.user_id or event.get_sender_id() or "未知"
        else:
            user_id = event.get_sender_id() or "未知"

        # 获取时间信息
        time_format = user_config.get("time_format", "%Y-%m-%d %H:%M:%S")
        try:
            # 优先使用消息的时间戳
            if hasattr(event.message_obj, 'timestamp') and event.message_obj.timestamp:
                current_time = datetime.datetime.fromtimestamp(event.message_obj.timestamp).strftime(time_format)
            else:
                current_time = datetime.datetime.now().strftime(time_format)
        except Exception as e:
            logger.warning(f"时间格式错误 '{time_format}': {e}，使用默认格式")
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 获取平台信息
        platform_name = event.get_platform_name() or "未知平台"
        message_type = "群聊" if event.message_obj.group_id else "私聊"

        # 构建用户信息字符串
        template = user_config.get("template", "当前对话信息：\n用户：{username}\n时间：{time}\n平台：{platform}（{chat_type}）\n\n")
        try:
            user_info = template.format(
                username=username,
                user_id=user_id,
                time=current_time,
                platform=platform_name,
                chat_type=message_type
            )
        except Exception as e:
            logger.warning(f"用户信息模板格式错误: {e}，使用默认模板")
            user_info = f"当前对话信息：\n用户：{username}\n时间：{current_time}\n平台：{platform_name}（{message_type}）\n\n"

        # 重要：不覆盖现有的系统提示，而是追加用户信息
        # 这样可以保持用户设置的人格(Persona)和其他系统提示
        if req.system_prompt:
            # 如果已有系统提示（可能包含人格设置），在末尾追加用户信息
            req.system_prompt = req.system_prompt.rstrip() + f"\n\n{user_info}"
        else:
            # 如果没有系统提示，直接设置用户信息
            req.system_prompt = user_info

        logger.info(f"已为用户 {username}（{user_id}）追加用户信息到LLM请求")
        logger.debug(f"追加的用户信息内容：\n{user_info.strip()}")
        logger.debug(f"完整系统提示长度：{len(req.system_prompt)} 字符")

    async def proactive_message_loop(self):
        """定时主动发送消息的循环"""
        logger.info("定时主动发送消息循环已启动")
        while True:
            try:
                proactive_config = self.config.get("proactive_reply", {})
                if not proactive_config.get("enabled", False):
                    logger.debug("定时主动发送功能已禁用，等待中...")
                    await asyncio.sleep(60)
                    continue

                # 检查是否在活跃时间段内
                if not self.is_active_time():
                    logger.debug("当前不在活跃时间段内，等待中...")
                    await asyncio.sleep(60)
                    continue

                # 获取配置的会话列表
                sessions_text = proactive_config.get("sessions", "")
                sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]

                if not sessions:
                    logger.debug("未配置目标会话，等待中...")
                    await asyncio.sleep(60)
                    continue

                logger.info(f"开始向 {len(sessions)} 个会话发送主动消息")

                # 向每个会话发送消息
                sent_count = 0
                for session in sessions:
                    try:
                        await self.send_proactive_message(session)
                        sent_count += 1
                    except Exception as e:
                        logger.error(f"向会话 {session} 发送主动消息失败: {e}")

                # 等待下一次发送
                interval = proactive_config.get("interval_minutes", 60) * 60
                logger.info(f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，{interval//60} 分钟后进行下一轮")
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("定时主动发送消息循环已取消")
                break
            except Exception as e:
                logger.error(f"定时主动发送消息循环发生错误: {e}")
                await asyncio.sleep(60)

    def is_active_time(self):
        """检查当前是否在活跃时间段内"""
        proactive_config = self.config.get("proactive_reply", {})
        active_hours = proactive_config.get("active_hours", "9:00-22:00")

        try:
            start_time, end_time = active_hours.split('-')
            start_hour, start_min = map(int, start_time.split(':'))
            end_hour, end_min = map(int, end_time.split(':'))

            now = datetime.datetime.now()
            current_time = now.hour * 60 + now.minute
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            is_active = start_minutes <= current_time <= end_minutes
            logger.debug(f"活跃时间检查: 当前时间 {now.strftime('%H:%M')}, 活跃时间段 {active_hours}, 结果: {'是' if is_active else '否'}")
            return is_active
        except Exception as e:
            logger.warning(f"活跃时间解析错误: {e}，默认为活跃状态")
            return True  # 如果解析失败，默认总是活跃

    async def send_proactive_message(self, session):
        """向指定会话发送主动消息"""
        proactive_config = self.config.get("proactive_reply", {})
        templates_text = proactive_config.get("message_templates", "\"嗨，最近怎么样？\"")

        # 解析消息模板，支持带引号的格式
        templates = []
        for line in templates_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 如果模板被引号包围，去掉引号
            if line.startswith('"') and line.endswith('"'):
                templates.append(line[1:-1])
            elif line.startswith("'") and line.endswith("'"):
                templates.append(line[1:-1])
            else:
                templates.append(line)

        if not templates:
            logger.warning("未配置消息模板，无法发送主动消息")
            return

        # 随机选择一个消息模板
        message = random.choice(templates)
        logger.debug(f"为会话 {session} 选择消息模板: {message}")

        # 使用 context.send_message 发送消息
        try:
            from astrbot.api.event import MessageChain
            message_chain = MessageChain().message(message)
            success = await self.context.send_message(session, message_chain)

            if success:
                logger.info(f"成功向会话 {session} 发送主动消息: {message}")
            else:
                logger.warning(f"向会话 {session} 发送主动消息失败，可能是会话不存在或平台不支持")
        except Exception as e:
            logger.error(f"向会话 {session} 发送主动消息时发生错误: {e}")

    @filter.command_group("proactive")
    def proactive_group(self):
        """主动回复插件管理指令组"""
        pass

    @proactive_group.command("status")
    async def status(self, event: AstrMessageEvent):
        """查看插件状态"""
        user_config = self.config.get("user_info", {})
        proactive_config = self.config.get("proactive_reply", {})

        sessions_text = proactive_config.get("sessions", "")
        session_count = len([s for s in sessions_text.split('\n') if s.strip()])

        status_text = f"""📊 主动回复插件状态

🔧 用户信息附加功能：✅ 已启用
  - 时间格式：{user_config.get('time_format', '%Y-%m-%d %H:%M:%S')}
  - 模板长度：{len(user_config.get('template', ''))} 字符

🤖 定时主动发送功能：{'✅ 已启用' if proactive_config.get('enabled', False) else '❌ 已禁用'}
  - 发送间隔：{proactive_config.get('interval_minutes', 60)} 分钟
  - 活跃时间：{proactive_config.get('active_hours', '9:00-22:00')}
  - 配置会话数：{session_count}
  - 当前时间：{datetime.datetime.now().strftime('%H:%M')}
  - 是否在活跃时间：{'✅' if self.is_active_time() else '❌'}

💡 使用 /proactive help 查看更多指令"""
        yield event.plain_result(status_text)

    @proactive_group.command("add_session")
    async def add_session(self, event: AstrMessageEvent):
        """将当前会话添加到定时发送列表"""
        current_session = event.unified_msg_origin

        proactive_config = self.config.get("proactive_reply", {})
        sessions_text = proactive_config.get("sessions", "")
        sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]

        if current_session in sessions:
            yield event.plain_result("❌ 当前会话已在定时发送列表中")
            return

        sessions.append(current_session)
        new_sessions_text = '\n'.join(sessions)

        # 更新配置
        if "proactive_reply" not in self.config:
            self.config["proactive_reply"] = {}

        self.config["proactive_reply"]["sessions"] = new_sessions_text
        try:
            self.config.save_config()
            yield event.plain_result(f"✅ 已将当前会话添加到定时发送列表\n会话ID：{current_session}")
            logger.info(f"用户 {event.get_sender_name()} 将会话 {current_session} 添加到定时发送列表")
        except Exception as e:
            yield event.plain_result(f"❌ 保存配置失败：{str(e)}")
            logger.error(f"保存配置失败: {e}")

    @proactive_group.command("remove_session")
    async def remove_session(self, event: AstrMessageEvent):
        """将当前会话从定时发送列表中移除"""
        current_session = event.unified_msg_origin

        proactive_config = self.config.get("proactive_reply", {})
        sessions_text = proactive_config.get("sessions", "")
        sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]

        if current_session not in sessions:
            yield event.plain_result("❌ 当前会话不在定时发送列表中")
            return

        sessions.remove(current_session)
        new_sessions_text = '\n'.join(sessions)

        # 更新配置
        if "proactive_reply" not in self.config:
            self.config["proactive_reply"] = {}

        self.config["proactive_reply"]["sessions"] = new_sessions_text
        try:
            self.config.save_config()
            yield event.plain_result("✅ 已将当前会话从定时发送列表中移除")
            logger.info(f"用户 {event.get_sender_name()} 将会话 {current_session} 从定时发送列表中移除")
        except Exception as e:
            yield event.plain_result(f"❌ 保存配置失败：{str(e)}")
            logger.error(f"保存配置失败: {e}")

    @proactive_group.command("test")
    async def test_proactive(self, event: AstrMessageEvent):
        """测试发送一条主动消息到当前会话"""
        current_session = event.unified_msg_origin

        try:
            await self.send_proactive_message(current_session)
            yield event.plain_result("✅ 测试消息发送成功")
            logger.info(f"用户 {event.get_sender_name()} 在会话 {current_session} 中测试主动消息发送成功")
        except Exception as e:
            yield event.plain_result(f"❌ 测试消息发送失败：{str(e)}")
            logger.error(f"用户 {event.get_sender_name()} 测试主动消息发送失败: {e}")

    @proactive_group.command("debug")
    async def debug_user_info(self, event: AstrMessageEvent):
        """调试用户信息 - 显示当前会话的用户信息"""
        user_config = self.config.get("user_info", {})

        # 获取用户信息
        if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
            username = event.message_obj.sender.nickname or "未知用户"
        else:
            username = event.get_sender_name() or "未知用户"

        # 获取用户ID
        if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
            user_id = event.message_obj.sender.user_id or event.get_sender_id() or "未知"
        else:
            user_id = event.get_sender_id() or "未知"

        # 获取时间信息
        time_format = user_config.get("time_format", "%Y-%m-%d %H:%M:%S")
        try:
            if hasattr(event.message_obj, 'timestamp') and event.message_obj.timestamp:
                current_time = datetime.datetime.fromtimestamp(event.message_obj.timestamp).strftime(time_format)
            else:
                current_time = datetime.datetime.now().strftime(time_format)
        except Exception as e:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 获取平台信息
        platform_name = event.get_platform_name() or "未知平台"
        message_type = "群聊" if event.message_obj.group_id else "私聊"

        # 构建用户信息字符串
        template = user_config.get("template", "[对话信息] 用户：{username}，时间：{time}")
        try:
            user_info = template.format(
                username=username,
                user_id=user_id,
                time=current_time,
                platform=platform_name,
                chat_type=message_type
            )
        except Exception as e:
            user_info = f"[对话信息] 用户：{username}，时间：{current_time}"

        # 获取实际的发送者ID用于调试
        actual_sender_id = event.get_sender_id() or "无法获取"
        sender_from_obj = ""
        if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
            sender_from_obj = event.message_obj.sender.user_id or "空值"
        else:
            sender_from_obj = "sender对象不存在"

        debug_info = f"""🔍 用户信息调试

📊 原始数据：
- 用户昵称：{username}
- 用户ID：{user_id}
- 平台：{platform_name}
- 聊天类型：{message_type}
- 时间：{current_time}
- 会话ID：{event.unified_msg_origin}

🔧 调试信息：
- get_sender_id()：{actual_sender_id}
- sender.user_id：{sender_from_obj}
- 配置文件路径：{getattr(self.config, '_config_path', '未知')}

⚙️ 配置状态：
- 用户信息功能：✅ 始终启用（通过模板控制显示内容）
- 时间格式：{user_config.get('time_format', '%Y-%m-%d %H:%M:%S')}
- 模板长度：{len(template)} 字符

📝 AI将收到的用户信息：
{user_info}

💡 提示：这就是AI在处理您的消息时会看到的用户信息！
如需调整显示内容，请修改用户信息模板。"""

        yield event.plain_result(debug_info)

    @proactive_group.command("config")
    async def show_config(self, event: AstrMessageEvent):
        """显示完整的插件配置信息"""
        config_info = f"""⚙️ 插件配置信息

📋 完整配置：
{str(self.config)}

🔧 用户信息配置：
{str(self.config.get('user_info', {}))}

🤖 定时发送配置：
{str(self.config.get('proactive_reply', {}))}

💡 如果配置显示为空或不正确，请：
1. 在AstrBot管理面板中配置插件参数
2. 重载插件使配置生效
3. 检查配置文件是否正确保存"""

        yield event.plain_result(config_info)

    @proactive_group.command("test_llm")
    async def test_llm_request(self, event: AstrMessageEvent):
        """测试LLM请求 - 发送一个测试消息给AI，查看完整的系统提示"""
        test_message = "这是一个测试消息，请简单回复确认收到。"

        # 创建一个LLM请求来测试用户信息附加
        try:
            result = yield event.request_llm(
                prompt=test_message,
                system_prompt="",  # 让插件自动添加用户信息
            )

            # 这个请求会触发我们的 add_user_info 钩子
            logger.info(f"用户 {event.get_sender_name()} 测试了LLM请求功能")

        except Exception as e:
            yield event.plain_result(f"❌ 测试LLM请求失败：{str(e)}")
            logger.error(f"测试LLM请求失败: {e}")

    @proactive_group.command("help")
    async def help_command(self, event: AstrMessageEvent):
        """显示插件帮助信息"""
        help_text = """📖 主动回复插件帮助

🔧 指令列表：
  /proactive status - 查看插件状态
  /proactive debug - 调试用户信息，查看AI收到的信息
  /proactive config - 显示完整的插件配置信息
  /proactive test_llm - 测试LLM请求，实际体验用户信息附加功能
  /proactive add_session - 将当前会话添加到定时发送列表
  /proactive remove_session - 将当前会话从定时发送列表中移除
  /proactive test - 测试发送一条主动消息到当前会话
  /proactive help - 显示此帮助信息

📝 功能说明：
1. 用户信息附加：在与AI对话时自动附加用户信息和时间
2. 定时主动发送：定时向指定会话发送消息，保持对话活跃

⚙️ 配置：
请在AstrBot管理面板的插件管理中配置相关参数

🔗 项目地址：
https://github.com/AstraSolis/astrbot_proactive_reply"""
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件终止时的清理工作"""
        logger.info("ProactiveReplyPlugin 插件正在终止...")
        if self.proactive_task:
            self.proactive_task.cancel()
            try:
                await self.proactive_task
            except asyncio.CancelledError:
                logger.info("定时主动发送任务已成功取消")
        logger.info("ProactiveReplyPlugin 插件已完全终止")
