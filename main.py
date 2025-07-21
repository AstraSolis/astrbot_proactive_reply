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
        self._initialization_task = None
        self._is_terminating = False  # 添加终止标志
        logger.info("ProactiveReplyPlugin 插件已初始化")

        # 异步初始化
        self._initialization_task = asyncio.create_task(self.initialize())

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
                "timing_mode": "fixed_interval",
                "interval_minutes": 600,
                "message_templates": "\"嗨，最近怎么样？\"\n\"有什么我可以帮助你的吗？\"\n\"好久不见，有什么新鲜事吗？\"\n\"今天过得如何？\"\n\"距离上次聊天已经过去了一段时间，AI上次发送消息是{last_sent_time}\"",
                "sessions": "",
                "active_hours": "9:00-22:00",
                "random_delay_enabled": False,
                "min_random_minutes": 0,
                "max_random_minutes": 30,
                "random_min_minutes": 600,
                "random_max_minutes": 1200,
                "session_user_info": {},
                "last_sent_times": {},  # AI主动发送消息的时间（保持向后兼容）
                "ai_last_sent_times": {}  # AI发送消息的时间（包括主动发送和回复）
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
                        # 对于数据记录类型的配置项，只在真正缺失时添加空字典
                        # 避免覆盖现有的历史数据
                        if key in ["session_user_info", "last_sent_times", "ai_last_sent_times"]:
                            self.config[section][key] = {}
                        else:
                            self.config[section][key] = default_value
                        config_updated = True
                        logger.info(f"添加缺失的配置项: {section}.{key}")

        # 数据迁移：将现有的时间记录迁移到新的配置项
        self._migrate_time_records()

        # 如果配置有更新，保存配置文件
        if config_updated:
            try:
                self.config.save_config()
                logger.info("配置文件已更新并保存")
            except Exception as e:
                logger.error(f"保存配置文件失败: {e}")

    def _migrate_time_records(self):
        """迁移时间记录数据到新的配置项"""
        try:
            proactive_config = self.config.get("proactive_reply", {})

            # 如果新的ai_last_sent_times为空，但last_sent_times有数据，则进行迁移
            ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})
            last_sent_times = proactive_config.get("last_sent_times", {})

            if not ai_last_sent_times and last_sent_times:
                logger.info("检测到历史时间记录，正在迁移数据...")
                # 将last_sent_times的数据复制到ai_last_sent_times
                self.config["proactive_reply"]["ai_last_sent_times"] = last_sent_times.copy()

                # 保存配置
                try:
                    self.config.save_config()
                    logger.info(f"成功迁移 {len(last_sent_times)} 条时间记录到新配置项")
                except Exception as e:
                    logger.warning(f"保存迁移数据失败: {e}")

        except Exception as e:
            logger.error(f"数据迁移失败: {e}")

    async def initialize(self):
        """插件初始化方法"""
        logger.info("开始执行插件初始化...")

        # 确保配置结构完整
        self._ensure_config_structure()
        logger.info("配置结构检查完成")

        # 启动定时任务
        await self.start_proactive_task()
        logger.info("插件初始化完成")

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

        # 记录用户信息到配置文件，用于主动发送消息时的占位符替换
        self.record_user_info(event, username, user_id, platform_name, message_type)

        logger.info(f"已为用户 {username}（{user_id}）追加用户信息到LLM请求")
        logger.debug(f"追加的用户信息内容：\n{user_info.strip()}")
        logger.debug(f"完整系统提示长度：{len(req.system_prompt)} 字符")

    def record_user_info(self, event: AstrMessageEvent, username: str, user_id: str, platform_name: str, message_type: str):
        """记录用户信息到配置文件，用于主动发送消息时的占位符替换"""
        try:
            session_id = event.unified_msg_origin
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 确保配置结构存在
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}
            if "session_user_info" not in self.config["proactive_reply"]:
                self.config["proactive_reply"]["session_user_info"] = {}

            # 记录用户信息
            self.config["proactive_reply"]["session_user_info"][session_id] = {
                "username": username,
                "user_id": user_id,
                "platform": platform_name,
                "chat_type": message_type,
                "last_active_time": current_time
            }

            # 保存配置（异步保存，避免阻塞）
            try:
                self.config.save_config()
                logger.debug(f"已记录会话 {session_id} 的用户信息: {username} - {current_time}")
            except Exception as e:
                logger.warning(f"保存用户信息配置失败: {e}")

        except Exception as e:
            logger.error(f"记录用户信息失败: {e}")

    @filter.after_message_sent()
    async def record_ai_message_time(self, event: AstrMessageEvent):
        """在AI发送消息后记录发送时间"""
        try:
            session_id = event.unified_msg_origin
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 确保配置结构存在
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}
            if "ai_last_sent_times" not in self.config["proactive_reply"]:
                self.config["proactive_reply"]["ai_last_sent_times"] = {}

            # 记录AI发送消息时间
            self.config["proactive_reply"]["ai_last_sent_times"][session_id] = current_time

            # 保存配置
            try:
                self.config.save_config()
                logger.debug(f"已记录会话 {session_id} 的AI发送消息时间: {current_time}")
            except Exception as e:
                logger.warning(f"保存AI发送消息时间配置失败: {e}")

        except Exception as e:
            logger.error(f"记录AI发送消息时间失败: {e}")

    async def proactive_message_loop(self):
        """定时主动发送消息的循环"""
        task_id = id(asyncio.current_task())
        logger.info(f"定时主动发送消息循环已启动 (任务ID: {task_id})")
        loop_count = 0
        while True:
            try:
                loop_count += 1
                logger.info(f"定时循环第 {loop_count} 次执行 (任务ID: {task_id})")

                # 检查插件是否正在终止
                if self._is_terminating:
                    logger.info("插件正在终止，退出定时循环")
                    break

                # 检查任务是否被取消
                if self.proactive_task and self.proactive_task.cancelled():
                    logger.info("定时主动发送任务已被取消，退出循环")
                    break

                proactive_config = self.config.get("proactive_reply", {})
                enabled = proactive_config.get("enabled", False)
                logger.info(f"定时发送功能状态: {'启用' if enabled else '禁用'}")

                if not enabled:
                    logger.info("定时主动发送功能已禁用，等待60秒后重新检查...")
                    # 检查是否在等待期间被终止
                    for i in range(60):  # 分成60次1秒的等待，便于快速响应终止
                        if self._is_terminating:
                            logger.info("插件正在终止，退出等待")
                            return
                        await asyncio.sleep(1)
                    continue

                # 检查是否在活跃时间段内
                is_active = self.is_active_time()
                logger.info(f"活跃时间检查结果: {'是' if is_active else '否'}")
                if not is_active:
                    logger.info("当前不在活跃时间段内，等待60秒后重新检查...")
                    await asyncio.sleep(60)
                    continue

                # 获取配置的会话列表
                sessions_text = proactive_config.get("sessions", "")
                sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]
                logger.info(f"配置的会话列表: {sessions}")

                if not sessions:
                    logger.info("未配置目标会话，等待60秒后重新检查...")
                    logger.info("提示：使用 /proactive add_session 指令将当前会话添加到发送列表")
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

                # 计算下一次发送的等待时间
                timing_mode = proactive_config.get("timing_mode", "fixed_interval")

                if timing_mode == "random_interval":
                    # 随机间隔模式：在最小和最大时间之间随机选择
                    random_min = proactive_config.get("random_min_minutes", 1) * 60
                    random_max = proactive_config.get("random_max_minutes", 60) * 60

                    if random_max > random_min:
                        total_interval = random.randint(random_min, random_max)
                        logger.info(f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息")
                        logger.info(f"随机间隔模式：随机等待时间 {total_interval//60} 分钟（范围：{random_min//60}-{random_max//60}分钟）")
                    else:
                        logger.warning(f"随机间隔配置错误：最大值({random_max//60}分钟) <= 最小值({random_min//60}分钟)，使用默认60分钟")
                        total_interval = 60 * 60
                        logger.info(f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，使用默认等待时间 60 分钟")
                else:
                    # 固定间隔模式（原有逻辑）
                    base_interval = proactive_config.get("interval_minutes", 60) * 60
                    total_interval = base_interval

                    if proactive_config.get("random_delay_enabled", False):
                        min_random = proactive_config.get("min_random_minutes", 0) * 60
                        max_random = proactive_config.get("max_random_minutes", 30) * 60
                        if max_random > min_random:
                            random_delay = random.randint(min_random, max_random)
                            total_interval += random_delay
                            logger.info(f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息")
                            logger.info(f"固定间隔模式：基础间隔 {base_interval//60} 分钟，随机延迟 {random_delay//60} 分钟，总等待时间 {total_interval//60} 分钟")
                        else:
                            logger.warning(f"随机延迟配置错误：最大值({max_random//60}分钟) <= 最小值({min_random//60}分钟)，使用基础间隔")
                            logger.info(f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，{base_interval//60} 分钟后进行下一轮")
                    else:
                        logger.info(f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，{base_interval//60} 分钟后进行下一轮")

                # 分段等待，定期检查状态变化
                logger.info(f"开始等待 {total_interval//60} 分钟...")
                remaining_time = total_interval
                check_interval = 60  # 每60秒检查一次状态

                while remaining_time > 0:
                    # 检查插件是否正在终止
                    if self._is_terminating:
                        logger.info("插件正在终止，退出等待")
                        return

                    # 检查任务是否被取消
                    if self.proactive_task and self.proactive_task.cancelled():
                        logger.info("定时主动发送任务已被取消，退出等待")
                        break

                    # 检查功能是否被禁用
                    current_config = self.config.get("proactive_reply", {})
                    if not current_config.get("enabled", False):
                        logger.info("定时主动发送功能已被禁用，退出等待")
                        break

                    # 等待较短的时间间隔
                    wait_time = min(check_interval, remaining_time)
                    await asyncio.sleep(wait_time)
                    remaining_time -= wait_time

                    if remaining_time > 0:
                        logger.debug(f"等待中...剩余时间: {remaining_time//60} 分钟")

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
        message_template = random.choice(templates)
        logger.debug(f"为会话 {session} 选择消息模板: {message_template}")

        # 替换模板中的占位符
        message = self.replace_template_placeholders(message_template, session)
        logger.debug(f"占位符替换后的消息: {message}")

        # 使用 context.send_message 发送消息
        try:
            from astrbot.api.event import MessageChain
            message_chain = MessageChain().message(message)
            success = await self.context.send_message(session, message_chain)

            if success:
                # 记录发送时间
                self.record_sent_time(session)
                logger.info(f"成功向会话 {session} 发送主动消息: {message}")
            else:
                logger.warning(f"向会话 {session} 发送主动消息失败，可能是会话不存在或平台不支持")
        except Exception as e:
            logger.error(f"向会话 {session} 发送主动消息时发生错误: {e}")

    def replace_template_placeholders(self, template: str, session: str) -> str:
        """替换消息模板中的占位符"""
        try:
            # 获取会话的配置信息
            proactive_config = self.config.get("proactive_reply", {})

            # 获取用户信息配置
            user_config = self.config.get("user_info", {})
            time_format = user_config.get("time_format", "%Y-%m-%d %H:%M:%S")

            # 准备占位符数据
            current_time = datetime.datetime.now().strftime(time_format)

            # 获取AI上次发送时间（优先使用新的ai_last_sent_times，向后兼容last_sent_times）
            ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})
            last_sent_times = proactive_config.get("last_sent_times", {})

            # 优先使用ai_last_sent_times，如果没有则使用last_sent_times
            last_sent_time = ai_last_sent_times.get(session) or last_sent_times.get(session, "从未发送过")

            if last_sent_time != "从未发送过":
                try:
                    # 尝试解析并重新格式化时间
                    parsed_time = datetime.datetime.strptime(last_sent_time, "%Y-%m-%d %H:%M:%S")
                    last_sent_time = parsed_time.strftime(time_format)
                except:
                    # 如果解析失败，保持原样
                    pass

            # 安全地替换占位符（只替换存在的占位符）
            message = template

            # 替换支持的占位符
            if "{time}" in message:
                message = message.replace("{time}", current_time)
            if "{last_sent_time}" in message:
                message = message.replace("{last_sent_time}", last_sent_time)

            # 移除不支持的占位符（避免发送时出错）
            unsupported_placeholders = [
                "{username}", "{user_id}", "{platform}", "{chat_type}", "{user_last_message_time}"
            ]
            for placeholder in unsupported_placeholders:
                if placeholder in message:
                    message = message.replace(placeholder, "")
                    logger.debug(f"移除了不支持的占位符: {placeholder}")

            return message

        except Exception as e:
            logger.warning(f"替换模板占位符失败: {e}，返回原始模板")
            return template

    def record_sent_time(self, session: str):
        """记录消息发送时间"""
        try:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
            try:
                self.config.save_config()
                logger.debug(f"已记录会话 {session} 的发送时间: {current_time}")
            except Exception as e:
                logger.warning(f"保存发送时间配置失败: {e}")

        except Exception as e:
            logger.error(f"记录发送时间失败: {e}")

    async def stop_proactive_task(self):
        """停止定时主动发送任务"""
        if self.proactive_task and not self.proactive_task.cancelled():
            task_id = id(self.proactive_task)
            logger.info(f"正在停止定时主动发送任务 (任务ID: {task_id})...")
            self.proactive_task.cancel()
            try:
                await self.proactive_task
            except asyncio.CancelledError:
                logger.info(f"定时主动发送任务已成功停止 (任务ID: {task_id})")
            except Exception as e:
                logger.error(f"停止定时任务时发生错误: {e}")
            self.proactive_task = None
        else:
            logger.info("没有运行中的定时主动发送任务需要停止")

    async def force_stop_all_tasks(self):
        """强制停止所有相关任务"""
        logger.info("强制停止所有相关任务...")

        # 设置终止标志
        self._is_terminating = True

        # 停止当前任务
        await self.stop_proactive_task()

        # 查找并停止所有可能的相关任务
        current_task = asyncio.current_task()
        all_tasks = asyncio.all_tasks()

        for task in all_tasks:
            if task != current_task and not task.done():
                # 检查任务是否可能是我们的定时任务
                if hasattr(task, '_coro') and task._coro:
                    coro_name = getattr(task._coro, '__name__', '')
                    if 'proactive_message_loop' in coro_name:
                        logger.info(f"发现可能的旧定时任务，正在停止 (任务ID: {id(task)})...")
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            logger.info(f"旧定时任务已停止 (任务ID: {id(task)})")
                        except Exception as e:
                            logger.error(f"停止旧定时任务时发生错误: {e}")

        # 重置终止标志
        self._is_terminating = False
        logger.info("所有相关任务已停止")

    async def start_proactive_task(self):
        """启动定时主动发送任务"""
        logger.info("尝试启动定时主动发送任务...")

        # 首先强制停止所有现有任务
        await self.force_stop_all_tasks()

        proactive_config = self.config.get("proactive_reply", {})
        enabled = proactive_config.get("enabled", False)
        logger.info(f"配置中的启用状态: {enabled}")

        if enabled:
            logger.info("创建定时任务...")
            self.proactive_task = asyncio.create_task(self.proactive_message_loop())
            logger.info("定时主动发送任务已启动")

            # 等待一小段时间确保任务开始运行
            await asyncio.sleep(0.1)

            if self.proactive_task.done():
                logger.error("定时任务启动后立即结束，可能有错误")
                try:
                    await self.proactive_task
                except Exception as e:
                    logger.error(f"定时任务错误: {e}")
            else:
                logger.info("定时任务正在运行中")
        else:
            logger.info("定时主动发送功能未启用")

    async def restart_proactive_task(self):
        """重启定时主动发送任务"""
        await self.stop_proactive_task()
        await self.start_proactive_task()

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

        # 获取用户信息记录数量
        session_user_info = proactive_config.get("session_user_info", {})
        user_info_count = len(session_user_info)

        # 获取发送时间记录数量
        last_sent_times = proactive_config.get("last_sent_times", {})
        ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})
        sent_times_count = len(last_sent_times)
        ai_sent_times_count = len(ai_last_sent_times)



        status_text = f"""📊 主动回复插件状态

🔧 用户信息附加功能：✅ 已启用
  - 时间格式：{user_config.get('time_format', '%Y-%m-%d %H:%M:%S')}
  - 模板长度：{len(user_config.get('template', ''))} 字符
  - 已记录用户信息：{user_info_count} 个会话

🤖 定时主动发送功能：{'✅ 已启用' if proactive_config.get('enabled', False) else '❌ 已禁用'}
  - 时间模式：{proactive_config.get('timing_mode', 'fixed_interval')} ({'固定间隔' if proactive_config.get('timing_mode', 'fixed_interval') == 'fixed_interval' else '随机间隔'})
  - 发送间隔：{proactive_config.get('interval_minutes', 60)} 分钟 {'(固定间隔模式)' if proactive_config.get('timing_mode', 'fixed_interval') == 'fixed_interval' else '(未使用)'}
  - 随机延迟：{'✅ 已启用' if proactive_config.get('random_delay_enabled', False) else '❌ 已禁用'} {'(固定间隔模式)' if proactive_config.get('timing_mode', 'fixed_interval') == 'fixed_interval' else '(未使用)'}
  - 随机延迟范围：{proactive_config.get('min_random_minutes', 0)}-{proactive_config.get('max_random_minutes', 30)} 分钟 {'(固定间隔模式)' if proactive_config.get('timing_mode', 'fixed_interval') == 'fixed_interval' else '(未使用)'}
  - 随机间隔范围：{proactive_config.get('random_min_minutes', 1)}-{proactive_config.get('random_max_minutes', 60)} 分钟 {'(随机间隔模式)' if proactive_config.get('timing_mode', 'fixed_interval') == 'random_interval' else '(未使用)'}
  - 活跃时间：{proactive_config.get('active_hours', '9:00-22:00')}
  - 配置会话数：{session_count}
  - AI主动发送记录数：{sent_times_count}
  - AI发送消息记录数：{ai_sent_times_count}
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

    @proactive_group.command("test_template")
    async def test_template(self, event: AstrMessageEvent):
        """测试消息模板占位符替换"""
        current_session = event.unified_msg_origin
        proactive_config = self.config.get("proactive_reply", {})
        templates_text = proactive_config.get("message_templates", "\"嗨，{username}，最近怎么样？\"")

        # 解析消息模板
        templates = []
        for line in templates_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('"') and line.endswith('"'):
                templates.append(line[1:-1])
            elif line.startswith("'") and line.endswith("'"):
                templates.append(line[1:-1])
            else:
                templates.append(line)

        if not templates:
            yield event.plain_result("❌ 未配置消息模板")
            return

        # 测试每个模板的占位符替换
        test_results = []
        for i, template in enumerate(templates, 1):
            try:
                replaced_message = self.replace_template_placeholders(template, current_session)
                test_results.append(f"模板 {i}:\n原始: {template}\n替换后: {replaced_message}")
            except Exception as e:
                test_results.append(f"模板 {i}:\n原始: {template}\n❌ 替换失败: {str(e)}")

        result_text = f"""🧪 消息模板占位符测试结果

📝 共测试 {len(templates)} 个模板：

{chr(10).join(test_results)}

💡 提示：如果某些占位符显示为"未知"，请先与机器人对话以记录用户信息"""

        yield event.plain_result(result_text)

    @proactive_group.command("show_user_info")
    async def show_user_info(self, event: AstrMessageEvent):
        """显示记录的用户信息"""
        proactive_config = self.config.get("proactive_reply", {})
        session_user_info = proactive_config.get("session_user_info", {})
        last_sent_times = proactive_config.get("last_sent_times", {})
        ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

        if not session_user_info:
            yield event.plain_result("📝 暂无记录的用户信息\n\n💡 提示：与机器人对话后会自动记录用户信息")
            return

        info_list = []
        for session_id, user_info in session_user_info.items():
            last_sent = last_sent_times.get(session_id, "从未发送")
            ai_last_sent = ai_last_sent_times.get(session_id, "从未发送")
            info_list.append(f"""会话: {session_id[:50]}{'...' if len(session_id) > 50 else ''}
用户: {user_info.get('username', '未知')} ({user_info.get('user_id', '未知')})
平台: {user_info.get('platform', '未知')} ({user_info.get('chat_type', '未知')})
最后活跃: {user_info.get('last_active_time', '未知')}
AI主动发送: {last_sent}
AI发送消息: {ai_last_sent}""")

        result_text = f"""👥 已记录的用户信息 ({len(session_user_info)} 个会话)

{chr(10).join([f"{i+1}. {info}" for i, info in enumerate(info_list)])}

💡 这些信息用于主动消息的占位符替换"""

        yield event.plain_result(result_text)

    @proactive_group.command("debug_times")
    async def debug_times(self, event: AstrMessageEvent):
        """调试时间记录数据"""
        current_session = event.unified_msg_origin
        proactive_config = self.config.get("proactive_reply", {})

        last_sent_times = proactive_config.get("last_sent_times", {})
        ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

        debug_text = f"""🔍 时间记录调试信息

当前会话: {current_session[:50]}{'...' if len(current_session) > 50 else ''}

📊 数据统计:
- AI主动发送记录总数: {len(last_sent_times)}
- AI发送消息记录总数: {len(ai_last_sent_times)}

🕐 当前会话时间记录:
- AI主动发送时间: {last_sent_times.get(current_session, '无记录')}
- AI发送消息时间: {ai_last_sent_times.get(current_session, '无记录')}

🧪 模板测试:
{self.replace_template_placeholders('测试模板：AI上次发送={last_sent_time}', current_session)}"""

        yield event.plain_result(debug_text)

    @proactive_group.command("debug_tasks")
    async def debug_tasks(self, event: AstrMessageEvent):
        """调试当前运行的任务"""
        current_task = asyncio.current_task()
        all_tasks = asyncio.all_tasks()

        task_info = []
        proactive_tasks = []

        for task in all_tasks:
            task_id = id(task)
            task_name = getattr(task, '_coro', {})
            coro_name = getattr(task_name, '__name__', 'unknown') if task_name else 'unknown'

            if 'proactive' in coro_name.lower():
                proactive_tasks.append(f"- 任务ID: {task_id}, 名称: {coro_name}, 状态: {'运行中' if not task.done() else '已完成'}")

            task_info.append(f"- 任务ID: {task_id}, 名称: {coro_name}, 状态: {'运行中' if not task.done() else '已完成'}")

        current_proactive_task = self.proactive_task
        current_task_info = f"当前记录的任务: {id(current_proactive_task) if current_proactive_task else 'None'}"

        debug_text = f"""🔍 任务调试信息

{current_task_info}

📊 相关任务统计:
找到 {len(proactive_tasks)} 个可能的定时任务:
{chr(10).join(proactive_tasks) if proactive_tasks else '- 无'}

📋 所有任务 (总计 {len(all_tasks)} 个):
{chr(10).join(task_info[:10])}
{'...(显示前10个)' if len(task_info) > 10 else ''}"""

        yield event.plain_result(debug_text)

    @proactive_group.command("force_stop")
    async def force_stop_command(self, event: AstrMessageEvent):
        """强制停止所有定时任务"""
        try:
            await self.force_stop_all_tasks()
            yield event.plain_result("✅ 已强制停止所有相关任务")
            logger.info(f"用户 {event.get_sender_name()} 强制停止了所有任务")
        except Exception as e:
            yield event.plain_result(f"❌ 强制停止任务失败：{str(e)}")
            logger.error(f"强制停止任务失败: {e}")

    @proactive_group.command("clear_records")
    async def clear_records(self, event: AstrMessageEvent):
        """清除记录的用户信息和发送时间（用于测试）"""
        try:
            if "proactive_reply" not in self.config:
                self.config["proactive_reply"] = {}

            # 清除记录
            self.config["proactive_reply"]["session_user_info"] = {}
            self.config["proactive_reply"]["last_sent_times"] = {}
            self.config["proactive_reply"]["ai_last_sent_times"] = {}

            # 保存配置
            self.config.save_config()

            yield event.plain_result("✅ 已清除所有用户信息记录和AI发送时间记录")
            logger.info(f"用户 {event.get_sender_name()} 清除了所有记录")

        except Exception as e:
            yield event.plain_result(f"❌ 清除记录失败：{str(e)}")
            logger.error(f"清除记录失败: {e}")

    @proactive_group.command("restart")
    async def restart_task(self, event: AstrMessageEvent):
        """重启定时主动发送任务"""
        try:
            await self.restart_proactive_task()
            proactive_config = self.config.get("proactive_reply", {})
            if proactive_config.get("enabled", False):
                yield event.plain_result("✅ 定时主动发送任务已重启")
            else:
                yield event.plain_result("ℹ️ 定时主动发送功能已禁用，任务已停止")
            logger.info(f"用户 {event.get_sender_name()} 重启了定时主动发送任务")
        except Exception as e:
            yield event.plain_result(f"❌ 重启任务失败：{str(e)}")
            logger.error(f"重启定时任务失败: {e}")

    @proactive_group.command("task_status")
    async def task_status(self, event: AstrMessageEvent):
        """检查定时任务状态"""
        try:
            task_info = []

            # 检查主定时任务
            if self.proactive_task:
                if self.proactive_task.cancelled():
                    task_info.append("🔴 主定时任务：已取消")
                elif self.proactive_task.done():
                    task_info.append("🟡 主定时任务：已完成")
                else:
                    task_info.append("🟢 主定时任务：运行中")
            else:
                task_info.append("⚪ 主定时任务：未创建")

            # 检查初始化任务
            if self._initialization_task:
                if self._initialization_task.cancelled():
                    task_info.append("🔴 初始化任务：已取消")
                elif self._initialization_task.done():
                    task_info.append("🟢 初始化任务：已完成")
                else:
                    task_info.append("🟡 初始化任务：运行中")
            else:
                task_info.append("⚪ 初始化任务：未创建")

            # 检查终止标志
            task_info.append(f"🏁 终止标志：{'是' if self._is_terminating else '否'}")

            # 检查配置状态
            proactive_config = self.config.get("proactive_reply", {})
            task_info.append(f"⚙️ 功能启用：{'是' if proactive_config.get('enabled', False) else '否'}")

            # 获取所有运行中的任务数量
            all_tasks = [task for task in asyncio.all_tasks() if not task.done()]
            task_info.append(f"📊 全局任务数：{len(all_tasks)}")

            status_text = f"""🔍 定时任务状态检查

{chr(10).join(task_info)}

💡 如果任务状态异常，请使用 /proactive restart 重启任务"""

            yield event.plain_result(status_text)

        except Exception as e:
            yield event.plain_result(f"❌ 检查任务状态失败：{str(e)}")
            logger.error(f"检查任务状态失败: {e}")

    @proactive_group.command("debug_send")
    async def debug_send(self, event: AstrMessageEvent):
        """调试定时发送功能 - 详细显示发送过程"""
        current_session = event.unified_msg_origin

        try:
            proactive_config = self.config.get("proactive_reply", {})

            # 检查配置
            debug_info = []
            debug_info.append(f"🔧 配置检查:")
            debug_info.append(f"  - 功能启用: {'是' if proactive_config.get('enabled', False) else '否'}")
            debug_info.append(f"  - 当前在活跃时间: {'是' if self.is_active_time() else '否'}")

            # 检查会话列表
            sessions_text = proactive_config.get("sessions", "")
            sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]
            debug_info.append(f"  - 配置的会话数: {len(sessions)}")
            debug_info.append(f"  - 当前会话在列表中: {'是' if current_session in sessions else '否'}")

            # 检查消息模板
            templates_text = proactive_config.get("message_templates", "")
            templates = []
            for line in templates_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('"') and line.endswith('"'):
                    templates.append(line[1:-1])
                elif line.startswith("'") and line.endswith("'"):
                    templates.append(line[1:-1])
                else:
                    templates.append(line)

            debug_info.append(f"  - 消息模板数: {len(templates)}")

            if templates:
                # 测试模板替换
                test_template = templates[0]
                debug_info.append(f"📝 模板测试:")
                debug_info.append(f"  - 原始模板: {test_template}")

                replaced_message = self.replace_template_placeholders(test_template, current_session)
                debug_info.append(f"  - 替换后: {replaced_message}")

                # 尝试发送测试消息
                debug_info.append(f"🚀 发送测试:")
                try:
                    from astrbot.api.event import MessageChain
                    message_chain = MessageChain().message(replaced_message)
                    success = await self.context.send_message(current_session, message_chain)

                    if success:
                        debug_info.append(f"  - 发送结果: ✅ 成功")
                        # 记录发送时间
                        self.record_sent_time(current_session)
                    else:
                        debug_info.append(f"  - 发送结果: ❌ 失败（可能是会话不存在或平台不支持）")

                except Exception as e:
                    debug_info.append(f"  - 发送结果: ❌ 异常 - {str(e)}")
            else:
                debug_info.append(f"❌ 没有可用的消息模板")

            result_text = f"""🔍 定时发送功能调试

{chr(10).join(debug_info)}

💡 如果发送失败，请检查配置和会话设置"""

            yield event.plain_result(result_text)

        except Exception as e:
            yield event.plain_result(f"❌ 调试发送功能失败：{str(e)}")
            logger.error(f"调试发送功能失败: {e}")

    @proactive_group.command("force_start")
    async def force_start_task(self, event: AstrMessageEvent):
        """强制启动定时任务（调试用）"""
        try:
            logger.info("用户请求强制启动定时任务")

            # 停止现有任务
            await self.stop_proactive_task()

            # 强制启动任务（忽略配置中的enabled状态）
            self.proactive_task = asyncio.create_task(self.proactive_message_loop())

            yield event.plain_result("✅ 已强制启动定时任务（忽略配置状态）")
            logger.info("定时任务已强制启动")

        except Exception as e:
            yield event.plain_result(f"❌ 强制启动任务失败：{str(e)}")
            logger.error(f"强制启动任务失败: {e}")

    @proactive_group.command("current_session")
    async def show_current_session(self, event: AstrMessageEvent):
        """显示当前会话ID"""
        current_session = event.unified_msg_origin

        # 检查当前会话是否在发送列表中
        proactive_config = self.config.get("proactive_reply", {})
        sessions_text = proactive_config.get("sessions", "")
        sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]

        is_in_list = current_session in sessions

        session_info = f"""📍 当前会话信息

🆔 会话ID：
{current_session}

📋 状态：
{'✅ 已在定时发送列表中' if is_in_list else '❌ 未在定时发送列表中'}

💡 操作提示：
{'使用 /proactive remove_session 移除此会话' if is_in_list else '使用 /proactive add_session 添加此会话到发送列表'}

📊 当前发送列表共有 {len(sessions)} 个会话"""

        yield event.plain_result(session_info)

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

🔧 基础指令：
  /proactive status - 查看插件状态
  /proactive debug - 调试用户信息，查看AI收到的信息
  /proactive config - 显示完整的插件配置信息
  /proactive help - 显示此帮助信息

🤖 定时发送管理：
  /proactive current_session - 显示当前会话ID和状态
  /proactive add_session - 将当前会话添加到定时发送列表
  /proactive remove_session - 将当前会话从定时发送列表中移除
  /proactive test - 测试发送一条主动消息到当前会话
  /proactive restart - 重启定时主动发送任务（配置更改后使用）

🧪 测试功能：
  /proactive test_llm - 测试LLM请求，实际体验用户信息附加功能
  /proactive test_template - 测试消息模板占位符替换
  /proactive show_user_info - 显示记录的用户信息
  /proactive clear_records - 清除记录的用户信息和发送时间
  /proactive task_status - 检查定时任务状态（调试用）
  /proactive debug_send - 调试定时发送功能（详细显示发送过程）
  /proactive force_start - 强制启动定时任务（调试用）

📝 功能说明：
1. 用户信息附加：在与AI对话时自动附加用户信息和时间
2. 定时主动发送：支持两种时间模式
   - 固定间隔模式：固定时间间隔，可选随机延迟
   - 随机间隔模式：每次在设定范围内随机选择等待时间
3. 模板占位符：支持 {time}（当前时间）, {last_sent_time}（AI上次发送消息时间）

⚙️ 配置：
请在AstrBot管理面板的插件管理中配置相关参数

🔗 项目地址：
https://github.com/AstraSolis/astrbot_proactive_reply"""
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件终止时的清理工作"""
        logger.info("ProactiveReplyPlugin 插件正在终止...")

        # 设置终止标志
        self._is_terminating = True

        # 停止初始化任务
        if self._initialization_task and not self._initialization_task.cancelled():
            logger.info("取消初始化任务...")
            self._initialization_task.cancel()
            try:
                await self._initialization_task
            except asyncio.CancelledError:
                logger.info("初始化任务已取消")

        # 停止定时任务
        await self.stop_proactive_task()
        logger.info("ProactiveReplyPlugin 插件已完全终止")
