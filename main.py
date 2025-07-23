from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import asyncio
import random
import datetime

@register(
    "astrbot_proactive_reply",
    "AstraSolis",
    "一个支持聊天附带用户信息和定时主动发送消息的插件",
    "1.0.0",
    "https://github.com/AstraSolis/astrbot_proactive_reply",
)
class ProactiveReplyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.proactive_task = None
        self._initialization_task = None
        self._is_terminating = False  # 添加终止标志
        logger.info("ProactiveReplyPlugin 插件已初始化")

        # 验证配置文件加载状态
        self._verify_config_loading()

        # 异步初始化
        self._initialization_task = asyncio.create_task(self.initialize())

    def _verify_config_loading(self):
        """验证配置文件加载状态"""
        try:
            # 尝试多种方式获取配置文件路径
            config_path = None
            for attr in ["_config_path", "config_path", "_path", "path"]:
                if hasattr(self.config, attr):
                    config_path = getattr(self.config, attr)
                    if config_path:
                        break

            if not config_path:
                # 尝试通过 save_config 方法的异常来推断路径问题
                logger.warning("⚠️ 无法获取配置文件路径，可能使用内存配置")
            else:
                logger.info(f"📁 配置文件路径: {config_path}")

            # 检查是否有已保存的用户信息
            proactive_config = self.config.get("proactive_reply", {})
            session_user_info = proactive_config.get("session_user_info", {})
            ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

            logger.info(f"📊 加载的用户信息数量: {len(session_user_info)}")
            logger.info(f"📊 加载的AI发送时间记录数量: {len(ai_last_sent_times)}")

            if session_user_info:
                logger.info("✅ 检测到已保存的用户信息，配置持久化正常")
                # 显示最近的几个用户信息
                recent_sessions = list(session_user_info.keys())[:3]
                for session_id in recent_sessions:
                    user_info = session_user_info[session_id]
                    logger.debug(
                        f"  - 会话: {session_id[:50]}... 用户: {user_info.get('username', '未知')}"
                    )
            else:
                logger.info("ℹ️ 暂无已保存的用户信息（首次运行或配置已清空）")

        except Exception as e:
            logger.error(f"❌ 验证配置加载状态失败: {e}")

    def _load_persistent_data(self):
        """从独立的持久化文件加载用户数据"""
        try:
            import os
            import json

            # 使用独立的数据文件，避免被配置重置影响
            config_path = None
            for attr in ["_config_path", "config_path", "_path", "path"]:
                if hasattr(self.config, attr):
                    config_path = getattr(self.config, attr)
                    if config_path:
                        break

            if config_path:
                data_dir = os.path.dirname(config_path)
            else:
                # 如果无法获取配置路径，使用临时目录
                data_dir = "/tmp"
                logger.warning("⚠️ 无法获取配置路径，使用临时目录保存持久化数据")

            persistent_file = os.path.join(
                data_dir, "astrbot_proactive_reply_persistent.json"
            )

            if os.path.exists(persistent_file):
                for encoding in ["utf-8-sig", "utf-8", "gbk"]:
                    try:
                        with open(persistent_file, "r", encoding=encoding) as f:
                            persistent_data = json.load(f)

                        # 将持久化数据合并到配置中
                        if "proactive_reply" not in self.config:
                            self.config["proactive_reply"] = {}

                        for key in [
                            "session_user_info",
                            "ai_last_sent_times",
                            "last_sent_times",
                        ]:
                            if key in persistent_data:
                                self.config["proactive_reply"][key] = persistent_data[
                                    key
                                ]

                        logger.info(f"✅ 从持久化文件加载数据成功: {persistent_file}")
                        logger.info(
                            f"📊 加载用户信息: {len(persistent_data.get('session_user_info', {}))}"
                        )
                        return
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue

                logger.warning(f"⚠️ 无法读取持久化文件: {persistent_file}")
            else:
                logger.info(f"ℹ️ 持久化文件不存在: {persistent_file}")

        except Exception as e:
            logger.error(f"❌ 加载持久化数据失败: {e}")

    def _save_persistent_data(self):
        """保存用户数据到独立的持久化文件"""
        try:
            import os
            import json

            # 使用独立的数据文件
            config_path = None
            for attr in ["_config_path", "config_path", "_path", "path"]:
                if hasattr(self.config, attr):
                    config_path = getattr(self.config, attr)
                    if config_path:
                        break

            if config_path:
                data_dir = os.path.dirname(config_path)
            else:
                # 如果无法获取配置路径，使用临时目录
                data_dir = "/tmp"
                logger.warning("⚠️ 无法获取配置路径，使用临时目录保存持久化数据")

            persistent_file = os.path.join(
                data_dir, "astrbot_proactive_reply_persistent.json"
            )

            # 准备要保存的数据
            proactive_config = self.config.get("proactive_reply", {})
            persistent_data = {
                "session_user_info": proactive_config.get("session_user_info", {}),
                "ai_last_sent_times": proactive_config.get("ai_last_sent_times", {}),
                "last_sent_times": proactive_config.get("last_sent_times", {}),
                "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 保存到独立文件
            with open(persistent_file, "w", encoding="utf-8") as f:
                json.dump(persistent_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"✅ 数据已保存到持久化文件: {persistent_file}")
            return True

        except Exception as e:
            logger.error(f"❌ 保存持久化数据失败: {e}")
            return False

    def _ensure_config_structure(self):
        """确保配置文件结构完整"""
        # 先尝试加载持久化数据
        self._load_persistent_data()

        # 默认配置
        default_config = {
            "user_info": {
                "time_format": "%Y-%m-%d %H:%M:%S",
                "template": "[对话信息] 用户：{username}，时间：{time}",
            },
            "proactive_reply": {
                "enabled": False,
                "timing_mode": "fixed_interval",
                "interval_minutes": 600,
                "proactive_default_persona": "你是一个友好、轻松的AI助手。",
                "proactive_prompt_list": [
                    "主动问候用户，询问近况",
                    "分享有趣话题，发起轻松对话",
                    "关心用户情况，温暖问候",
                    "友好交流，分享今日想法",
                    "轻松聊天，询问用户心情",
                ],
                "include_history_enabled": False,
                "history_message_count": 10,
                "sessions": [],
                "active_hours": "9:00-22:00",
                "random_delay_enabled": False,
                "min_random_minutes": 0,
                "max_random_minutes": 30,
                "random_min_minutes": 600,
                "random_max_minutes": 1200,
                "session_user_info": {},
                "last_sent_times": {},  # AI主动发送消息的时间（保持向后兼容）
                "ai_last_sent_times": {},  # AI发送消息的时间（包括主动发送和回复）
            },
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
                        if key in [
                            "session_user_info",
                            "last_sent_times",
                            "ai_last_sent_times",
                        ]:
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
                self.config["proactive_reply"]["ai_last_sent_times"] = (
                    last_sent_times.copy()
                )

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
            # 优先使用消息的时间戳
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

    def record_user_info(
        self,
        event: AstrMessageEvent,
        username: str,
        user_id: str,
        platform_name: str,
        message_type: str,
    ):
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
                "last_active_time": current_time,
            }

            # 保存配置到文件
            config_saved = False
            try:
                self.config.save_config()
                config_saved = True
                logger.debug("✅ 配置文件保存成功")
            except Exception as e:
                logger.warning(f"⚠️ 配置文件保存失败: {e}")

            # 同时保存到独立的持久化文件
            persistent_saved = self._save_persistent_data()

            if config_saved or persistent_saved:
                logger.info(
                    f"✅ 已保存会话 {session_id} 的用户信息: {username} - {current_time}"
                )
                if persistent_saved:
                    logger.debug("✅ 持久化文件保存成功")
            else:
                logger.error("❌ 所有保存方式都失败了")

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
            self.config["proactive_reply"]["ai_last_sent_times"][session_id] = (
                current_time
            )

            # 保存配置
            config_saved = False
            try:
                self.config.save_config()
                config_saved = True
                logger.debug("✅ 配置文件保存成功")
            except Exception as e:
                logger.warning(f"⚠️ 配置文件保存失败: {e}")

            # 同时保存到独立的持久化文件
            persistent_saved = self._save_persistent_data()

            if config_saved or persistent_saved:
                logger.debug(
                    f"✅ 已保存会话 {session_id} 的AI发送消息时间: {current_time}"
                )
            else:
                logger.error("❌ AI发送时间保存失败")

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
                sessions_data = proactive_config.get("sessions", [])
                sessions = self.parse_sessions_list(sessions_data)
                logger.info(f"配置的会话列表: {sessions}")

                if not sessions:
                    logger.info("未配置目标会话，等待60秒后重新检查...")
                    logger.info(
                        "提示：使用 /proactive add_session 指令将当前会话添加到发送列表"
                    )
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
                        logger.info(
                            f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息"
                        )
                        logger.info(
                            f"随机间隔模式：随机等待时间 {total_interval // 60} 分钟（范围：{random_min // 60}-{random_max // 60}分钟）"
                        )
                    else:
                        logger.warning(
                            f"随机间隔配置错误：最大值({random_max // 60}分钟) <= 最小值({random_min // 60}分钟)，使用默认60分钟"
                        )
                        total_interval = 60 * 60
                        logger.info(
                            f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，使用默认等待时间 60 分钟"
                        )
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
                            logger.info(
                                f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息"
                            )
                            logger.info(
                                f"固定间隔模式：基础间隔 {base_interval // 60} 分钟，随机延迟 {random_delay // 60} 分钟，总等待时间 {total_interval // 60} 分钟"
                            )
                        else:
                            logger.warning(
                                f"随机延迟配置错误：最大值({max_random // 60}分钟) <= 最小值({min_random // 60}分钟)，使用基础间隔"
                            )
                            logger.info(
                                f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，{base_interval // 60} 分钟后进行下一轮"
                            )
                    else:
                        logger.info(
                            f"本轮主动消息发送完成，成功发送 {sent_count}/{len(sessions)} 条消息，{base_interval // 60} 分钟后进行下一轮"
                        )

                # 分段等待，定期检查状态变化
                logger.info(f"开始等待 {total_interval // 60} 分钟...")
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
                        logger.debug(f"等待中...剩余时间: {remaining_time // 60} 分钟")

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
            start_time, end_time = active_hours.split("-")
            start_hour, start_min = map(int, start_time.split(":"))
            end_hour, end_min = map(int, end_time.split(":"))

            now = datetime.datetime.now()
            current_time = now.hour * 60 + now.minute
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            is_active = start_minutes <= current_time <= end_minutes
            logger.debug(
                f"活跃时间检查: 当前时间 {now.strftime('%H:%M')}, 活跃时间段 {active_hours}, 结果: {'是' if is_active else '否'}"
            )
            return is_active
        except Exception as e:
            logger.warning(f"活跃时间解析错误: {e}，默认为活跃状态")
            return True  # 如果解析失败，默认总是活跃

    def _ensure_string_encoding(self, text: str) -> str:
        """确保字符串的正确编码"""
        try:
            if not isinstance(text, str):
                text = str(text)

            # 尝试编码和解码以确保字符串正确
            # 这可以帮助发现和修复编码问题
            encoded = text.encode("utf-8", errors="replace")
            decoded = encoded.decode("utf-8", errors="replace")

            return decoded
        except Exception as e:
            logger.warning(f"字符串编码处理失败: {e}, 原文本: {repr(text)}")
            return str(text)

    def _safe_string_replace(self, text: str, old: str, new: str) -> str:
        """安全的字符串替换，处理编码问题"""
        try:
            # 确保所有字符串都是正确编码的
            text = self._ensure_string_encoding(text)
            old = self._ensure_string_encoding(old)
            new = self._ensure_string_encoding(new)

            result = text.replace(old, new)
            return self._ensure_string_encoding(result)
        except Exception as e:
            logger.warning(f"字符串替换失败: {e}")
            return text

    async def generate_proactive_message_with_llm(self, session: str) -> str:
        """使用LLM生成主动消息内容"""
        try:
            # 检查LLM是否可用
            provider = self.context.get_using_provider()
            if not provider:
                logger.warning("LLM提供商不可用，无法生成主动消息")
                return None

            # 获取配置
            proactive_config = self.config.get("proactive_reply", {})
            default_persona = self._ensure_string_encoding(
                proactive_config.get("proactive_default_persona", "")
            )
            prompt_list_data = proactive_config.get("proactive_prompt_list", [])

            if not prompt_list_data:
                logger.warning("未配置主动对话提示词列表")
                return None

            # 解析主动对话提示词列表
            prompt_list = self.parse_prompt_list(prompt_list_data)
            if not prompt_list:
                logger.warning("主动对话提示词列表为空")
                return None

            # 随机选择一个主动对话提示词
            selected_prompt = random.choice(prompt_list)
            selected_prompt = self._ensure_string_encoding(selected_prompt)
            logger.debug(f"随机选择的主动对话提示词: {selected_prompt}")

            # 替换提示词中的占位符
            final_prompt = self.replace_placeholders(selected_prompt, session)
            final_prompt = self._ensure_string_encoding(final_prompt)
            logger.debug(f"占位符替换后的提示词: {final_prompt}")

            # 获取当前使用的人格系统提示词
            base_system_prompt = ""
            try:
                # 尝试获取当前会话的人格设置
                uid = session  # session 就是 unified_msg_origin
                curr_cid = (
                    await self.context.conversation_manager.get_curr_conversation_id(
                        uid
                    )
                )

                # 获取默认人格设置
                default_persona_obj = (
                    self.context.provider_manager.selected_default_persona
                )

                if curr_cid:
                    conversation = (
                        await self.context.conversation_manager.get_conversation(
                            uid, curr_cid
                        )
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
                                    base_system_prompt = self._ensure_string_encoding(
                                        getattr(persona, "prompt", "")
                                    )
                                    logger.debug(
                                        f"使用会话人格 '{conversation.persona_id}' 的系统提示词"
                                    )
                                    break

                # 如果没有获取到人格提示词，尝试使用默认人格
                if (
                    not base_system_prompt
                    and default_persona_obj
                    and default_persona_obj.get("prompt")
                ):
                    base_system_prompt = self._ensure_string_encoding(
                        default_persona_obj["prompt"]
                    )
                    logger.debug(
                        f"使用默认人格 '{default_persona_obj.get('name', '未知')}' 的系统提示词"
                    )

            except Exception as e:
                logger.warning(f"获取人格系统提示词失败: {e}")

            # 获取历史记录（如果启用）
            contexts = []
            history_info = "未启用历史记录"

            if proactive_config.get("include_history_enabled", False):
                history_count = proactive_config.get("history_message_count", 10)
                # 限制历史记录数量在合理范围内
                history_count = max(1, min(50, history_count))

                logger.debug(
                    f"正在获取会话 {session} 的历史记录，数量限制: {history_count}"
                )
                contexts = await self.get_conversation_history(session, history_count)

                if contexts:
                    history_info = f"已获取 {len(contexts)} 条历史记录"
                    logger.info(f"为主动消息生成获取到 {len(contexts)} 条历史记录")
                    # 记录历史记录的简要信息
                    for i, ctx in enumerate(contexts[-3:]):  # 只显示最后3条的简要信息
                        role = ctx.get("role", "unknown")
                        content_preview = (
                            ctx.get("content", "")[:50] + "..."
                            if len(ctx.get("content", "")) > 50
                            else ctx.get("content", "")
                        )
                        logger.debug(f"历史记录 {i + 1}: {role} - {content_preview}")
                else:
                    history_info = "历史记录为空"
                    logger.debug("未获取到历史记录，使用空上下文")
            else:
                logger.debug("历史记录功能未启用")

            # 构建历史记录引导提示词（简化版，避免与主动对话提示词冲突）
            history_guidance = ""
            if proactive_config.get("include_history_enabled", False) and contexts:
                history_guidance = "\n\n--- 上下文说明 ---\n你可以参考上述对话历史来生成更自然和连贯的回复。"

            # 组合系统提示词：人格提示词 + 主动对话提示词 + 历史记录引导
            if base_system_prompt:
                # 有AstrBot人格：使用AstrBot人格 + 主动对话提示词 + 历史记录引导
                combined_system_prompt = f"{base_system_prompt}\n\n--- 主动对话指令 ---\n{final_prompt}{history_guidance}"
                logger.debug(
                    f"使用AstrBot人格 + 主动对话提示词 + 历史记录引导: 人格({len(base_system_prompt)}字符) + 提示词({len(final_prompt)}字符) + 引导({len(history_guidance)}字符)"
                )
            else:
                # 没有AstrBot人格：使用插件默认人格 + 主动对话提示词 + 历史记录引导
                if default_persona:
                    combined_system_prompt = f"{default_persona}\n\n--- 主动对话指令 ---\n{final_prompt}{history_guidance}"
                    logger.debug(
                        f"使用插件默认人格 + 主动对话提示词 + 历史记录引导: 默认人格({len(default_persona)}字符) + 提示词({len(final_prompt)}字符) + 引导({len(history_guidance)}字符)"
                    )
                else:
                    combined_system_prompt = f"{final_prompt}{history_guidance}"
                    logger.debug(
                        f"使用主动对话提示词 + 历史记录引导: 提示词({len(final_prompt)}字符) + 引导({len(history_guidance)}字符)"
                    )

            # 确保最终系统提示词的编码正确
            combined_system_prompt = self._ensure_string_encoding(
                combined_system_prompt
            )
            logger.debug(f"最终系统提示词长度: {len(combined_system_prompt)} 字符")
            logger.debug(f"最终系统提示词前100字符: {combined_system_prompt[:100]}...")

            # 调用LLM生成主动消息
            llm_response = await provider.text_chat(
                prompt="请生成一条主动问候消息。",
                session_id=None,
                contexts=contexts,  # 传入历史记录
                image_urls=[],
                func_tool=None,
                system_prompt=combined_system_prompt,
            )

            if llm_response and llm_response.role == "assistant":
                generated_message = llm_response.completion_text
                if generated_message:
                    # 确保生成的消息编码正确
                    generated_message = self._ensure_string_encoding(
                        generated_message.strip()
                    )
                    logger.info(f"LLM生成的主动消息: {generated_message}")
                    logger.info(f"生成上下文: {history_info}")
                    logger.debug(f"生成消息的字符编码检查: {repr(generated_message)}")
                    return generated_message
                else:
                    logger.warning("LLM返回了空消息")
                    return None
            else:
                logger.warning(f"LLM响应异常: {llm_response}")
                return None

        except Exception as e:
            logger.error(f"使用LLM生成主动消息失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None

    def parse_sessions_list(self, sessions_data) -> list:
        """解析会话列表（支持列表格式、JSON格式和传统换行格式）"""
        sessions = []

        # 如果已经是列表格式（新的配置格式）
        if isinstance(sessions_data, list):
            sessions = [s.strip() for s in sessions_data if s and s.strip()]
            logger.debug(f"使用列表格式的会话列表，共 {len(sessions)} 个")
            return sessions

        # 如果是字符串格式（兼容旧配置）
        if isinstance(sessions_data, str):
            try:
                # 尝试解析JSON格式
                import json

                sessions = json.loads(sessions_data)
                if not isinstance(sessions, list):
                    raise ValueError("不是有效的JSON数组")
                # 过滤空字符串
                sessions = [s.strip() for s in sessions if s and s.strip()]
                logger.debug(f"成功解析JSON格式的会话列表，共 {len(sessions)} 个")
            except (json.JSONDecodeError, ValueError):
                # 回退到传统换行格式
                sessions = [s.strip() for s in sessions_data.split("\n") if s.strip()]
                logger.debug(f"使用传统换行格式解析会话列表，共 {len(sessions)} 个")

        return sessions

    def parse_prompt_list(self, prompt_list_data) -> list:
        """解析主动对话提示词列表（支持列表格式、JSON格式和传统换行格式）"""
        prompt_list = []

        try:
            # 如果已经是列表格式（新的配置格式）
            if isinstance(prompt_list_data, list):
                prompt_list = []
                for item in prompt_list_data:
                    if item and str(item).strip():
                        # 确保每个提示词的编码正确
                        cleaned_item = self._ensure_string_encoding(str(item).strip())
                        prompt_list.append(cleaned_item)
                logger.debug(f"使用列表格式的提示词列表，共 {len(prompt_list)} 个")
                return prompt_list

            # 如果是字符串格式（兼容旧配置）
            if isinstance(prompt_list_data, str):
                prompt_list_data = self._ensure_string_encoding(prompt_list_data)
                try:
                    # 尝试解析JSON格式
                    import json

                    parsed_list = json.loads(prompt_list_data)
                    if not isinstance(parsed_list, list):
                        raise ValueError("不是有效的JSON数组")

                    # 过滤空字符串并确保编码正确
                    prompt_list = []
                    for item in parsed_list:
                        if item and str(item).strip():
                            cleaned_item = self._ensure_string_encoding(
                                str(item).strip()
                            )
                            prompt_list.append(cleaned_item)

                    logger.debug(
                        f"成功解析JSON格式的提示词列表，共 {len(prompt_list)} 个"
                    )
                except (json.JSONDecodeError, ValueError) as json_error:
                    logger.debug(f"JSON解析失败: {json_error}，尝试传统换行格式")
                    # 回退到传统换行格式
                    prompt_list = []
                    for line in prompt_list_data.split("\n"):
                        if line.strip():
                            cleaned_line = self._ensure_string_encoding(line.strip())
                            prompt_list.append(cleaned_line)

                    logger.debug(
                        f"使用传统换行格式解析提示词列表，共 {len(prompt_list)} 个"
                    )

        except Exception as e:
            logger.error(f"解析提示词列表失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

        # 最终检查，确保所有提示词都是有效的
        valid_prompts = []
        for i, prompt in enumerate(prompt_list):
            if prompt and len(prompt.strip()) > 0:
                valid_prompts.append(prompt)
                logger.debug(f"提示词 {i + 1}: {repr(prompt[:50])}...")
            else:
                logger.warning(f"跳过无效的提示词 {i + 1}: {repr(prompt)}")

        logger.info(f"最终解析得到 {len(valid_prompts)} 个有效提示词")
        return valid_prompts

    def build_user_context_for_proactive(self, session: str) -> str:
        """为主动对话构建用户上下文信息"""
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

    def replace_placeholders(self, prompt: str, session: str) -> str:
        """替换提示词中的占位符"""
        try:
            # 确保输入参数的编码正确
            prompt = self._ensure_string_encoding(prompt)
            session = self._ensure_string_encoding(session)

            proactive_config = self.config.get("proactive_reply", {})
            session_user_info = proactive_config.get("session_user_info", {})
            ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

            user_info = session_user_info.get(session, {})
            last_sent_time = ai_last_sent_times.get(session, "从未发送过")

            # 构建占位符字典，确保所有值都是正确编码的字符串
            user_last_time = self._ensure_string_encoding(
                user_info.get("last_active_time", "未知")
            )

            placeholders = {
                "{user_context}": self._ensure_string_encoding(
                    self.build_user_context_for_proactive(session)
                ),
                "{user_last_message_time}": user_last_time,
                "{user_last_message_time_ago}": self._ensure_string_encoding(
                    self.format_time_ago(user_last_time)
                ),
                "{username}": self._ensure_string_encoding(
                    user_info.get("username", "未知用户")
                ),
                "{platform}": self._ensure_string_encoding(
                    user_info.get("platform", "未知平台")
                ),
                "{chat_type}": self._ensure_string_encoding(
                    user_info.get("chat_type", "未知")
                ),
                "{ai_last_sent_time}": self._ensure_string_encoding(last_sent_time),
                "{current_time}": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 替换所有占位符，使用安全的字符串替换
            result = prompt
            for placeholder, value in placeholders.items():
                try:
                    result = self._safe_string_replace(result, placeholder, str(value))
                    logger.debug(f"替换占位符 {placeholder} -> {repr(value)}")
                except Exception as replace_error:
                    logger.warning(f"替换占位符 {placeholder} 失败: {replace_error}")
                    continue

            logger.debug(
                f"占位符替换完成，原始长度: {len(prompt)}, 结果长度: {len(result)}"
            )
            logger.debug(f"替换结果前100字符: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"替换占位符失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return prompt  # 如果替换失败，返回原始提示词

    def format_time_ago(self, time_str: str) -> str:
        """将时间字符串转换为相对时间描述（如"5分钟前"）"""
        try:
            if not time_str or time_str == "未知":
                return "未知"

            # 解析时间字符串
            last_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            current_time = datetime.datetime.now()

            # 计算时间差
            time_diff = current_time - last_time
            total_seconds = int(time_diff.total_seconds())

            if total_seconds < 0:
                return "刚刚"
            elif total_seconds < 60:
                return f"{total_seconds}秒前"
            elif total_seconds < 3600:  # 小于1小时
                minutes = total_seconds // 60
                return f"{minutes}分钟前"
            elif total_seconds < 86400:  # 小于1天
                hours = total_seconds // 3600
                return f"{hours}小时前"
            elif total_seconds < 2592000:  # 小于30天
                days = total_seconds // 86400
                return f"{days}天前"
            elif total_seconds < 31536000:  # 小于365天
                months = total_seconds // 2592000
                return f"{months}个月前"
            else:
                years = total_seconds // 31536000
                return f"{years}年前"

        except Exception as e:
            logger.error(f"格式化相对时间失败: {e}")
            return "未知"

    async def get_conversation_history(self, session: str, max_count: int = 10) -> list:
        """安全地获取会话的对话历史记录"""
        try:
            # 获取当前会话的对话ID
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                session
            )

            if not curr_cid:
                logger.debug(f"会话 {session} 没有现有对话，返回空历史记录")
                return []

            # 获取对话对象
            conversation = await self.context.conversation_manager.get_conversation(
                session, curr_cid
            )

            if not conversation or not conversation.history:
                logger.debug(f"会话 {session} 没有历史记录，返回空历史记录")
                return []

            # 解析历史记录
            import json

            try:
                history = json.loads(conversation.history)
                if not isinstance(history, list):
                    logger.warning(f"会话 {session} 的历史记录格式不正确，不是列表格式")
                    return []

                # 限制历史记录数量，取最近的记录
                if max_count > 0 and len(history) > max_count:
                    history = history[-max_count:]
                    logger.debug(f"历史记录已截取到最近 {max_count} 条")

                # 验证历史记录格式
                valid_history = []
                for item in history:
                    if isinstance(item, dict) and "role" in item and "content" in item:
                        # 确保内容是字符串格式
                        if isinstance(item["content"], str):
                            valid_history.append(item)
                        else:
                            logger.debug(f"跳过非字符串内容的历史记录项: {item}")
                    else:
                        logger.debug(f"跳过格式不正确的历史记录项: {item}")

                logger.info(
                    f"成功获取会话 {session} 的历史记录，共 {len(valid_history)} 条"
                )
                return valid_history

            except json.JSONDecodeError as e:
                logger.warning(f"解析会话 {session} 的历史记录JSON失败: {e}")
                return []

        except Exception as e:
            logger.error(f"获取会话 {session} 的历史记录失败: {e}")
            return []

    async def send_proactive_message(self, session):
        """向指定会话发送主动消息"""
        try:
            # 确保会话ID的编码正确
            session = self._ensure_string_encoding(session)

            # 使用LLM生成主动消息
            message = await self.generate_proactive_message_with_llm(session)

            if not message:
                logger.warning(f"无法为会话 {session} 生成主动消息")
                return

            # 确保消息的编码正确
            message = self._ensure_string_encoding(message)
            logger.debug(f"为会话 {session} 生成的主动消息: {message}")
            logger.debug(f"消息编码检查: {repr(message)}")

            # 使用 context.send_message 发送消息
            from astrbot.api.event import MessageChain

            try:
                message_chain = MessageChain().message(message)
                logger.debug(f"创建消息链成功，准备发送到会话: {session}")

                success = await self.context.send_message(session, message_chain)
                logger.debug(f"消息发送结果: {success}")

                if success:
                    # 记录发送时间
                    self.record_sent_time(session)

                    # 重要：将AI主动发送的消息添加到对话历史记录中
                    await self.add_message_to_conversation_history(session, message)

                    logger.info(f"✅ 成功向会话 {session} 发送主动消息: {message}")
                else:
                    logger.warning(
                        f"⚠️ 向会话 {session} 发送主动消息失败，可能是会话不存在或平台不支持"
                    )
            except Exception as send_error:
                logger.error(f"❌ 发送消息时发生错误: {send_error}")
                import traceback

                logger.error(f"发送错误详情: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"❌ 向会话 {session} 发送主动消息时发生错误: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")

    async def add_message_to_conversation_history(self, session: str, message: str):
        """将AI主动发送的消息添加到对话历史记录中"""
        try:
            import json

            # 获取当前会话的对话ID
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                session
            )

            # 如果没有对话，创建一个新的对话
            if not curr_cid:
                logger.info(f"会话 {session} 没有现有对话，创建新对话")
                curr_cid = await self.context.conversation_manager.new_conversation(
                    session
                )
                if not curr_cid:
                    logger.error(f"无法为会话 {session} 创建新对话")
                    return

            # 获取对话对象
            conversation = await self.context.conversation_manager.get_conversation(
                session, curr_cid
            )
            if not conversation:
                logger.error(f"无法获取会话 {session} 的对话对象")
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

            # 保存对话历史到数据库
            try:
                saved = False
                db = self.context.get_db()

                if db and hasattr(db, "conn"):
                    # 使用数据库连接直接执行SQL
                    try:
                        conn = db.conn
                        cursor = conn.cursor()

                        # 直接更新webchat_conversation表
                        cursor.execute(
                            "UPDATE webchat_conversation SET history = ?, updated_at = ? WHERE cid = ?",
                            (
                                conversation.history,
                                int(datetime.datetime.now().timestamp()),
                                curr_cid,
                            ),
                        )
                        affected_rows = cursor.rowcount
                        conn.commit()  # 提交事务

                        if affected_rows > 0:
                            saved = True
                            logger.debug(
                                f"✅ 通过SQL直接更新对话历史成功（影响行数：{affected_rows}）"
                            )
                        else:
                            logger.debug("SQL更新执行成功但未影响任何行")

                    except Exception as e:
                        logger.debug(f"数据库连接操作失败: {e}")

                if saved:
                    logger.info(
                        f"✅ 已将AI主动消息添加到会话 {session} 的对话历史中并保存到数据库"
                    )
                else:
                    logger.warning("⚠️ 无法保存对话历史到数据库，消息已添加到内存中")
                    logger.debug(f"已将AI主动消息添加到会话 {session} 的内存对话历史中")

            except Exception as save_error:
                logger.error(f"保存对话历史时发生错误: {save_error}")
                # 即使保存失败，至少内存中的历史已经更新了
                logger.debug("内存中的对话历史已更新，但可能未持久化到数据库")

        except Exception as e:
            logger.error(f"将消息添加到对话历史时发生错误: {e}")

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
            config_saved = False
            try:
                self.config.save_config()
                config_saved = True
                logger.debug("✅ 配置文件保存成功")
            except Exception as e:
                logger.warning(f"⚠️ 配置文件保存失败: {e}")

            # 同时保存到独立的持久化文件
            persistent_saved = self._save_persistent_data()

            if config_saved or persistent_saved:
                logger.debug(f"✅ 已保存会话 {session} 的发送时间: {current_time}")
            else:
                logger.error("❌ 发送时间保存失败")

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
                if hasattr(task, "_coro") and task._coro:
                    coro_name = getattr(task._coro, "__name__", "")
                    if "proactive_message_loop" in coro_name:
                        logger.info(
                            f"发现可能的旧定时任务，正在停止 (任务ID: {id(task)})..."
                        )
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

        sessions_data = proactive_config.get("sessions", [])
        sessions = self.parse_sessions_list(sessions_data)
        session_count = len(sessions)

        # 获取用户信息记录数量
        session_user_info = proactive_config.get("session_user_info", {})
        user_info_count = len(session_user_info)

        # 获取发送时间记录数量
        last_sent_times = proactive_config.get("last_sent_times", {})
        ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})
        sent_times_count = len(last_sent_times)
        ai_sent_times_count = len(ai_last_sent_times)

        # 检查LLM状态
        provider = self.context.get_using_provider()
        llm_available = provider is not None
        default_persona = proactive_config.get("proactive_default_persona", "")
        prompt_list_data = proactive_config.get("proactive_prompt_list", [])
        prompt_list = self.parse_prompt_list(prompt_list_data)

        # 检查人格系统状态
        persona_info = "未知"
        try:
            default_persona = self.context.provider_manager.selected_default_persona
            if default_persona and default_persona.get("name"):
                persona_info = f"默认人格: {default_persona['name']}"
            else:
                persona_info = "无默认人格"
        except Exception as e:
            persona_info = f"获取失败: {str(e)}"

        # 检查历史记录功能状态
        history_enabled = proactive_config.get("include_history_enabled", False)
        history_count = proactive_config.get("history_message_count", 10)

        # 检查当前会话状态
        current_session = event.unified_msg_origin
        is_current_in_list = current_session in sessions

        status_text = f"""📊 主动回复插件状态

📍 当前会话：
  - 会话ID：{current_session[:50]}{"..." if len(current_session) > 50 else ""}
  - 发送状态：{"✅ 已在发送列表中" if is_current_in_list else "❌ 未在发送列表中"}
  - 操作提示：{"使用 /proactive remove_session 移除" if is_current_in_list else "使用 /proactive add_session 添加"}

🔧 用户信息附加功能：✅ 已启用
  - 时间格式：{user_config.get("time_format", "%Y-%m-%d %H:%M:%S")}
  - 模板长度：{len(user_config.get("template", ""))} 字符
  - 已记录用户信息：{user_info_count} 个会话

🤖 智能主动发送功能：{"✅ 已启用" if proactive_config.get("enabled", False) else "❌ 已禁用"}
  - LLM提供商：{"✅ 可用" if llm_available else "❌ 不可用"}
  - 人格系统：{persona_info}
  - 默认人格：{"✅ 已配置" if default_persona else "❌ 未配置"} ({len(default_persona)} 字符)
  - 主动对话提示词：{"✅ 已配置" if prompt_list else "❌ 未配置"} ({len(prompt_list)} 个)
  - 📚 历史记录功能：{"✅ 已启用" if history_enabled else "❌ 已禁用"}
  - 历史记录条数：{history_count} 条 {"(已启用)" if history_enabled else "(未启用)"}
  - 时间模式：{proactive_config.get("timing_mode", "fixed_interval")} ({"固定间隔" if proactive_config.get("timing_mode", "fixed_interval") == "fixed_interval" else "随机间隔"})
  - 发送间隔：{proactive_config.get("interval_minutes", 60)} 分钟 {"(固定间隔模式)" if proactive_config.get("timing_mode", "fixed_interval") == "fixed_interval" else "(未使用)"}
  - 随机延迟：{"✅ 已启用" if proactive_config.get("random_delay_enabled", False) else "❌ 已禁用"} {"(固定间隔模式)" if proactive_config.get("timing_mode", "fixed_interval") == "fixed_interval" else "(未使用)"}
  - 随机延迟范围：{proactive_config.get("min_random_minutes", 0)}-{proactive_config.get("max_random_minutes", 30)} 分钟 {"(固定间隔模式)" if proactive_config.get("timing_mode", "fixed_interval") == "fixed_interval" else "(未使用)"}
  - 随机间隔范围：{proactive_config.get("random_min_minutes", 1)}-{proactive_config.get("random_max_minutes", 60)} 分钟 {"(随机间隔模式)" if proactive_config.get("timing_mode", "fixed_interval") == "random_interval" else "(未使用)"}
  - 活跃时间：{proactive_config.get("active_hours", "9:00-22:00")}
  - 配置会话数：{session_count}
  - AI主动发送记录数：{sent_times_count}
  - AI发送消息记录数：{ai_sent_times_count}
  - 当前时间：{datetime.datetime.now().strftime("%H:%M")}
  - 是否在活跃时间：{"✅" if self.is_active_time() else "❌"}

💡 使用 /proactive help 查看更多指令"""
        yield event.plain_result(status_text)

    @proactive_group.command("add_session")
    async def add_session(self, event: AstrMessageEvent):
        """将当前会话添加到定时发送列表"""
        current_session = event.unified_msg_origin

        proactive_config = self.config.get("proactive_reply", {})
        sessions_data = proactive_config.get("sessions", [])
        sessions = self.parse_sessions_list(sessions_data)

        if current_session in sessions:
            yield event.plain_result("❌ 当前会话已在定时发送列表中")
            return

        sessions.append(current_session)

        # 更新配置（直接保存为列表）
        if "proactive_reply" not in self.config:
            self.config["proactive_reply"] = {}

        self.config["proactive_reply"]["sessions"] = sessions
        try:
            self.config.save_config()
            yield event.plain_result(
                f"✅ 已将当前会话添加到定时发送列表\n会话ID：{current_session}"
            )
            logger.info(
                f"用户 {event.get_sender_name()} 将会话 {current_session} 添加到定时发送列表"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 保存配置失败：{str(e)}")
            logger.error(f"保存配置失败: {e}")

    @proactive_group.command("remove_session")
    async def remove_session(self, event: AstrMessageEvent):
        """将当前会话从定时发送列表中移除"""
        current_session = event.unified_msg_origin

        proactive_config = self.config.get("proactive_reply", {})
        sessions_data = proactive_config.get("sessions", [])
        sessions = self.parse_sessions_list(sessions_data)

        if current_session not in sessions:
            yield event.plain_result("❌ 当前会话不在定时发送列表中")
            return

        sessions.remove(current_session)

        # 更新配置（直接保存为列表）
        if "proactive_reply" not in self.config:
            self.config["proactive_reply"] = {}

        self.config["proactive_reply"]["sessions"] = sessions
        try:
            self.config.save_config()
            yield event.plain_result("✅ 已将当前会话从定时发送列表中移除")
            logger.info(
                f"用户 {event.get_sender_name()} 将会话 {current_session} 从定时发送列表中移除"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 保存配置失败：{str(e)}")
            logger.error(f"保存配置失败: {e}")

    @proactive_group.command("test")
    async def test_proactive(self, event: AstrMessageEvent, test_type: str = "basic"):
        """测试功能 - 支持多种测试类型

        参数:
        - basic: 基础测试发送 (默认)
        - llm: 测试LLM请求
        - generation: 测试LLM生成主动消息
        - prompt: 测试系统提示词构建
        - placeholders: 测试占位符替换
        - history: 测试对话历史记录
        """
        test_type = test_type.lower()

        if test_type in ["basic", ""]:
            async for result in self._test_basic(event):
                yield result
        elif test_type == "llm":
            async for result in self._test_llm(event):
                yield result
        elif test_type == "generation":
            async for result in self._test_generation(event):
                yield result
        elif test_type == "prompt":
            async for result in self._test_prompt(event):
                yield result
        elif test_type == "placeholders":
            async for result in self._test_placeholders(event):
                yield result
        elif test_type == "history":
            async for result in self._test_history(event):
                yield result
        else:
            available_types = ["basic", "llm", "generation", "prompt", "placeholders", "history"]
            yield event.plain_result(f"""❌ 未知的测试类型: {test_type}

📋 可用的测试类型：
{chr(10).join([f"  • {t}" for t in available_types])}

💡 使用方法: /proactive test [类型]
例如: /proactive test llm""")

    async def _test_basic(self, event: AstrMessageEvent):
        """基础测试发送"""
        current_session = event.unified_msg_origin

        try:
            await self.send_proactive_message(current_session)
            yield event.plain_result("✅ 测试消息发送成功")
            logger.info(
                f"用户 {event.get_sender_name()} 在会话 {current_session} 中测试主动消息发送成功"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 测试消息发送失败：{str(e)}")
            logger.error(f"用户 {event.get_sender_name()} 测试主动消息发送失败: {e}")

    async def _test_llm(self, event: AstrMessageEvent):
        """测试LLM请求"""
        test_message = "这是一个测试消息，请简单回复确认收到。"

        try:
            yield event.request_llm(
                prompt=test_message,
                system_prompt="",  # 让插件自动添加用户信息
            )
            logger.info(f"用户 {event.get_sender_name()} 测试了LLM请求功能")
        except Exception as e:
            yield event.plain_result(f"❌ 测试LLM请求失败：{str(e)}")
            logger.error(f"测试LLM请求失败: {e}")

    async def _test_generation(self, event: AstrMessageEvent):
        """测试LLM生成主动消息功能"""
        current_session = event.unified_msg_origin

        try:
            provider = self.context.get_using_provider()
            if not provider:
                yield event.plain_result("❌ LLM提供商不可用，无法测试生成功能")
                return

            yield event.plain_result(
                "🧪 开始测试LLM生成主动消息...\n⏳ 正在调用LLM，请稍候..."
            )

            generated_message = await self.generate_proactive_message_with_llm(
                current_session
            )

            if generated_message:
                user_context = self.build_user_context_for_proactive(current_session)
                result_text = f"""✅ LLM生成主动消息测试成功

🤖 生成的消息：
{generated_message}

📊 使用的用户上下文：
{user_context}

💡 这就是AI会发送给用户的主动消息内容！"""
                yield event.plain_result(result_text)
                logger.info(f"用户 {event.get_sender_name()} 测试LLM生成功能成功")
            else:
                yield event.plain_result(
                    "❌ LLM生成主动消息失败，请检查配置和LLM服务状态"
                )
        except Exception as e:
            yield event.plain_result(f"❌ 测试LLM生成功能失败：{str(e)}")
            logger.error(f"测试LLM生成功能失败: {e}")

    async def _test_prompt(self, event: AstrMessageEvent):
        """测试系统提示词构建过程（包含历史记录处理）"""
        current_session = event.unified_msg_origin

        try:
            proactive_config = self.config.get("proactive_reply", {})
            prompt_list_data = proactive_config.get("proactive_prompt_list", [])

            if not prompt_list_data:
                yield event.plain_result("❌ 未配置主动对话提示词列表")
                return

            prompt_list = self.parse_prompt_list(prompt_list_data)
            if not prompt_list:
                yield event.plain_result("❌ 主动对话提示词列表为空")
                return

            selected_prompt = random.choice(prompt_list)
            final_prompt = self.replace_placeholders(selected_prompt, current_session)

            base_system_prompt = self.get_base_system_prompt()

            # 检查历史记录功能
            history_enabled = proactive_config.get("include_history_enabled", False)
            history_count = proactive_config.get("history_message_count", 10)
            history_info = ""
            history_context = ""

            if history_enabled:
                try:
                    # 使用项目中已有的get_conversation_history方法
                    contexts = await self.get_conversation_history(current_session, history_count)
                    if contexts:
                        history_context = "\n".join([f"{ctx['role']}: {ctx['content'][:50]}..." for ctx in contexts[-3:]])
                        history_info = f"✅ 已启用 (最近{len(contexts)}条记录)"
                    else:
                        history_info = "✅ 已启用 (暂无历史记录)"
                except Exception as e:
                    history_info = f"✅ 已启用 (获取失败: {str(e)[:50]}...)"
            else:
                history_info = "❌ 未启用"

            # 构建完整的系统提示词（模拟实际生成过程）
            combined_system_prompt = f"{base_system_prompt}\n\n{final_prompt}"
            if history_enabled and history_context:
                combined_system_prompt += f"\n\n--- 对话历史 ---\n{history_context}"

            result_text = f"""🧪 系统提示词构建测试

📝 原始提示词：
{selected_prompt}

🔄 占位符替换后：
{final_prompt}

🤖 基础人格提示词：
{base_system_prompt[:200] + "..." if len(base_system_prompt) > 200 else base_system_prompt}

📚 历史记录状态：{history_info}
{f"最近历史记录预览：{chr(10)}{history_context}" if history_context else ""}

🎭 最终组合系统提示词：
{combined_system_prompt[:400] + "..." if len(combined_system_prompt) > 400 else combined_system_prompt}

📊 统计信息:
- 可用提示词数量: {len(prompt_list)}
- 人格提示词长度: {len(base_system_prompt)} 字符
- 主动对话提示词长度: {len(final_prompt)} 字符
- 历史记录长度: {len(history_context)} 字符
- 最终系统提示词长度: {len(combined_system_prompt)} 字符

💡 这就是发送给LLM的完整系统提示词和历史上下文！"""

            yield event.plain_result(result_text)
        except Exception as e:
            yield event.plain_result(f"❌ 测试系统提示词构建失败：{str(e)}")
            logger.error(f"测试系统提示词构建失败: {e}")

    async def _test_placeholders(self, event: AstrMessageEvent):
        """测试占位符替换功能"""
        current_session = event.unified_msg_origin

        try:
            test_prompt = """测试占位符替换：
- 完整用户上下文：{user_context}
- 用户上次发消息时间：{user_last_message_time}
- 用户上次发消息相对时间：{user_last_message_time_ago}
- 用户昵称：{username}
- 平台：{platform}
- 聊天类型：{chat_type}
- AI上次发送时间：{ai_last_sent_time}
- 当前时间：{current_time}"""

            result = self.replace_placeholders(test_prompt, current_session)

            test_result = f"""🧪 占位符替换测试结果

📝 原始模板：
{test_prompt}

🔄 替换后结果：
{result}

💡 所有占位符都已成功替换！"""

            yield event.plain_result(test_result)
        except Exception as e:
            yield event.plain_result(f"❌ 测试占位符替换失败：{str(e)}")
            logger.error(f"测试占位符替换失败: {e}")

    async def _test_history(self, event: AstrMessageEvent):
        """测试对话历史记录功能"""
        current_session = event.unified_msg_origin

        try:
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(current_session)

            if not curr_cid:
                yield event.plain_result("❌ 当前会话没有对话ID，无法测试历史记录功能")
                return

            conversation = await self.context.conversation_manager.get_conversation(current_session, curr_cid)

            if not conversation:
                yield event.plain_result("❌ 无法获取对话对象")
                return

            import json
            history = json.loads(conversation.history) if conversation.history else []

            result_text = f"""🧪 对话历史记录测试结果

📋 基本信息：
- 对话ID: {curr_cid}
- 历史记录条数: {len(history)}
- 对话创建时间: {conversation.created_at if hasattr(conversation, 'created_at') else '未知'}

📝 最近的历史记录（最多显示5条）：
{chr(10).join([f"{i+1}. {msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}..." for i, msg in enumerate(history[-5:])]) if history else "暂无历史记录"}

💡 历史记录功能正常，AI主动发送的消息会自动添加到此对话历史中"""

            yield event.plain_result(result_text)
        except Exception as e:
            yield event.plain_result(f"❌ 测试对话历史记录功能失败：{str(e)}")
            logger.error(f"测试对话历史记录功能失败: {e}")

    @proactive_group.command("restart")
    async def restart_task(self, event: AstrMessageEvent):
        """重启定时主动发送任务（配置更改后使用）"""
        try:
            await self.restart_proactive_task()
            proactive_config = self.config.get("proactive_reply", {})

            if proactive_config.get("enabled", False):
                result_text = """✅ 定时主动发送任务已重启

🔄 任务状态：正在运行
📋 适用场景：
  • 修改了插件配置参数后
  • 更改了发送间隔或时间设置
  • 添加/删除了主动对话提示词
  • 修改了活跃时间范围
  • 任务出现异常需要重新启动

💡 提示：配置更改后必须重启任务才能生效"""
            else:
                result_text = """ℹ️ 定时主动发送功能已禁用

🔄 任务状态：已停止
💡 提示：请在AstrBot管理面板中启用"定时发送功能"，然后再次运行此指令"""

            yield event.plain_result(result_text)
            logger.info(f"用户 {event.get_sender_name()} 重启了定时主动发送任务")
        except Exception as e:
            yield event.plain_result(f"❌ 重启任务失败：{str(e)}")
            logger.error(f"重启定时任务失败: {e}")





    async def _debug_basic(self, event: AstrMessageEvent):
        """基础调试用户信息"""
        user_config = self.config.get("user_info", {})

        # 获取用户信息
        if hasattr(event.message_obj, "sender") and event.message_obj.sender:
            username = event.message_obj.sender.nickname or "未知用户"
        else:
            username = event.get_sender_name() or "未知用户"

        # 获取用户ID
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
        except Exception:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 获取平台信息
        platform_name = event.get_platform_name() or "未知平台"
        message_type = "群聊" if event.message_obj.group_id else "私聊"

        # 构建用户信息字符串
        template = user_config.get(
            "template", "[对话信息] 用户：{username}，时间：{time}"
        )
        try:
            user_info = template.format(
                username=username,
                user_id=user_id,
                time=current_time,
                platform=platform_name,
                chat_type=message_type,
            )
        except Exception:
            user_info = f"[对话信息] 用户：{username}，时间：{current_time}"

        # 获取实际的发送者ID用于调试
        actual_sender_id = event.get_sender_id() or "无法获取"
        sender_from_obj = ""
        if hasattr(event.message_obj, "sender") and event.message_obj.sender:
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
- 配置文件路径：{getattr(self.config, "_config_path", "未知")}

⚙️ 配置状态：
- 用户信息功能：✅ 始终启用（通过模板控制显示内容）
- 时间格式：{user_config.get("time_format", "%Y-%m-%d %H:%M:%S")}
- 模板长度：{len(template)} 字符

📝 AI将收到的用户信息：
{user_info}

💡 提示：这就是AI在处理您的消息时会看到的用户信息！
如需调整显示内容，请修改用户信息模板。"""

        yield event.plain_result(debug_info)

    async def _debug_times(self, event: AstrMessageEvent):
        """调试时间记录数据"""
        current_session = event.unified_msg_origin
        proactive_config = self.config.get("proactive_reply", {})

        last_sent_times = proactive_config.get("last_sent_times", {})
        ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

        debug_text = f"""🔍 时间记录调试信息

📊 当前会话: {current_session}

⏰ 用户发送时间记录:
{last_sent_times.get(current_session, "无记录")}

🤖 AI发送时间记录:
{ai_last_sent_times.get(current_session, "无记录")}

📋 所有会话的时间记录:
用户发送时间记录数: {len(last_sent_times)}
AI发送时间记录数: {len(ai_last_sent_times)}

🧪 LLM生成测试:
使用 /proactive test generation 测试LLM生成功能"""

        yield event.plain_result(debug_text)





    async def _debug_send(self, event: AstrMessageEvent):
        """调试LLM主动发送功能"""
        current_session = event.unified_msg_origin

        try:
            proactive_config = self.config.get("proactive_reply", {})

            # 检查配置
            debug_info = []
            debug_info.append("🔧 配置检查:")
            debug_info.append(
                f"  - 功能启用: {'是' if proactive_config.get('enabled', False) else '否'}"
            )
            debug_info.append(
                f"  - 当前在活跃时间: {'是' if self.is_active_time() else '否'}"
            )

            # 检查会话列表
            sessions_data = proactive_config.get("sessions", [])
            sessions = self.parse_sessions_list(sessions_data)
            debug_info.append(f"  - 配置的会话数: {len(sessions)}")
            debug_info.append(
                f"  - 当前会话在列表中: {'是' if current_session in sessions else '否'}"
            )

            # 检查LLM
            provider = self.context.get_using_provider()
            debug_info.append(f"  - LLM提供商可用: {'是' if provider else '否'}")

            yield event.plain_result("\n".join(debug_info))

            if not provider:
                yield event.plain_result("❌ LLM提供商不可用，无法继续测试")
                return

            # 测试生成消息
            yield event.plain_result("🧪 开始测试LLM生成...")
            generated_message = await self.generate_proactive_message_with_llm(current_session)

            if generated_message:
                result_text = f"""✅ LLM生成测试成功

🤖 生成的消息：
{generated_message}

💡 如果生成或发送失败，请检查LLM配置和系统提示词设置"""
                yield event.plain_result(result_text)
            else:
                yield event.plain_result("❌ LLM生成失败")

        except Exception as e:
            yield event.plain_result(f"❌ 调试LLM发送功能失败：{str(e)}")
            logger.error(f"调试LLM发送功能失败: {e}")











    @proactive_group.command("show")
    async def show_info(self, event: AstrMessageEvent, show_type: str = "prompt"):
        """显示信息 - 支持多种显示类型

        参数:
        - prompt: 显示当前配置下会输入给LLM的组合话术 (默认)
        - users: 显示记录的用户信息
        """
        show_type = show_type.lower()

        if show_type in ["prompt", ""]:
            async for result in self._show_prompt(event):
                yield result
        elif show_type == "users":
            async for result in self._show_users(event):
                yield result
        else:
            available_types = ["prompt", "users"]
            yield event.plain_result(f"""❌ 未知的显示类型: {show_type}

📋 可用的显示类型：
{chr(10).join([f"  • {t}" for t in available_types])}

💡 使用方法: /proactive show [类型]
例如: /proactive show users""")

    async def _show_prompt(self, event: AstrMessageEvent):
        """显示当前配置下会输入给LLM的组合话术"""
        try:
            target_session = event.unified_msg_origin
            proactive_config = self.config.get("proactive_reply", {})
            prompt_list_data = proactive_config.get("proactive_prompt_list", [])

            if not prompt_list_data:
                yield event.plain_result("❌ 未配置主动对话提示词列表")
                return

            prompt_list = self.parse_prompt_list(prompt_list_data)
            if not prompt_list:
                yield event.plain_result("❌ 主动对话提示词列表为空")
                return

            # 随机选择一个提示词进行演示
            selected_prompt = random.choice(prompt_list)
            final_prompt = self.replace_placeholders(selected_prompt, target_session)

            # 获取基础系统提示词
            base_system_prompt = self.get_base_system_prompt()
            combined_system_prompt = f"{base_system_prompt}\n\n{final_prompt}"

            # 获取历史记录信息
            history_info = "未启用"
            if proactive_config.get("include_history_enabled", False):
                history_count = proactive_config.get("history_message_count", 10)
                history_info = f"启用 (最近{history_count}条)"

            part1 = f"""📋 主动对话话术预览

🎯 随机选中的提示词：
{selected_prompt}

🔄 占位符替换后：
{final_prompt}

🤖 基础人格提示词：
{base_system_prompt[:300] + "..." if len(base_system_prompt) > 300 else base_system_prompt}"""

            part2 = f"""
🎭 最终组合系统提示词：
{combined_system_prompt[:500] + "..." if len(combined_system_prompt) > 500 else combined_system_prompt}

📊 统计信息:
- 可用提示词数量: {len(prompt_list)}
- 人格提示词长度: {len(base_system_prompt)} 字符
- 主动对话提示词长度: {len(final_prompt)} 字符
- 最终系统提示词长度: {len(combined_system_prompt)} 字符
- 历史记录状态: {history_info}

💡 提示: 这就是LLM会收到的完整系统提示词和历史上下文，用于生成主动消息"""

            yield event.plain_result(part1)
            yield event.plain_result(part2)

        except Exception as e:
            yield event.plain_result(f"❌ 显示主动对话话术失败: {str(e)}")
            logger.error(f"显示主动对话话术失败: {e}")

    async def _show_users(self, event: AstrMessageEvent):
        """显示记录的用户信息"""
        proactive_config = self.config.get("proactive_reply", {})
        session_user_info = proactive_config.get("session_user_info", {})
        last_sent_times = proactive_config.get("last_sent_times", {})
        ai_last_sent_times = proactive_config.get("ai_last_sent_times", {})

        if not session_user_info:
            yield event.plain_result(
                "📝 暂无记录的用户信息\n\n💡 提示：与机器人对话后会自动记录用户信息"
            )
            return

        # 构建用户信息列表
        info_list = []
        for session_id, user_data in session_user_info.items():
            user_last_time = last_sent_times.get(session_id, "无记录")
            ai_last_time = ai_last_sent_times.get(session_id, "无记录")

            info_text = f"会话: {session_id[:50]}...\n"
            info_text += f"  用户信息: {user_data}\n"
            info_text += f"  用户最后发送: {user_last_time}\n"
            info_text += f"  AI最后发送: {ai_last_time}"
            info_list.append(info_text)

        result_text = f"""📝 记录的用户信息

📊 统计信息：
- 记录的会话数：{len(session_user_info)}
- 用户发送时间记录数：{len(last_sent_times)}
- AI发送时间记录数：{len(ai_last_sent_times)}

📋 详细信息：
{chr(10).join([f"{i + 1}. {info}" for i, info in enumerate(info_list)])}

💡 这些信息用于主动消息的占位符替换"""

        yield event.plain_result(result_text)

    @proactive_group.command("manage")
    async def manage_functions(self, event: AstrMessageEvent, action: str = ""):
        """管理功能 - 支持多种管理操作

        参数:
        - clear: 清除记录的用户信息和发送时间
        - task_status: 检查定时任务状态
        - force_stop: 强制停止所有定时任务
        - force_start: 强制启动定时任务
        - save_config: 强制保存配置文件
        - debug_info: 调试用户信息（故障排查用）
        - debug_send: 调试发送功能（故障排查用）
        - debug_times: 调试时间记录（故障排查用）
        """
        action = action.lower()

        if action == "clear":
            async for result in self._manage_clear(event):
                yield result
        elif action == "task_status":
            async for result in self._manage_task_status(event):
                yield result
        elif action == "force_stop":
            async for result in self._manage_force_stop(event):
                yield result
        elif action == "force_start":
            async for result in self._manage_force_start(event):
                yield result
        elif action == "save_config":
            async for result in self._manage_save_config(event):
                yield result
        elif action == "debug_info":
            async for result in self._debug_basic(event):
                yield result
        elif action == "debug_send":
            async for result in self._debug_send(event):
                yield result
        elif action == "debug_times":
            async for result in self._debug_times(event):
                yield result
        else:
            available_actions = ["clear", "task_status", "force_stop", "force_start", "save_config",
                               "debug_info", "debug_send", "debug_times"]
            yield event.plain_result(f"""❌ 请指定管理操作类型

📋 基础管理操作：
  • clear - 清除记录的用户信息和发送时间
  • task_status - 检查定时任务状态
  • force_stop - 强制停止所有定时任务
  • force_start - 强制启动定时任务
  • save_config - 强制保存配置文件

🔧 故障排查操作：
  • debug_info - 调试用户信息（查看AI收到的信息）
  • debug_send - 调试发送功能（检查LLM生成过程）
  • debug_times - 调试时间记录（查看发送时间记录）

💡 使用方法: /proactive manage [操作]
例如: /proactive manage clear""")

    async def _manage_clear(self, event: AstrMessageEvent):
        """清除记录的用户信息和发送时间"""
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

    async def _manage_task_status(self, event: AstrMessageEvent):
        """检查定时任务状态"""
        try:
            task_info = []

            # 检查当前记录的任务
            current_task = self.proactive_task
            if current_task:
                task_info.append(f"✅ 当前记录的定时任务: ID {id(current_task)}")
                task_info.append(f"   状态: {'运行中' if not current_task.done() else '已完成'}")
                if current_task.done():
                    try:
                        result = current_task.result()
                        task_info.append(f"   结果: {result}")
                    except Exception as e:
                        task_info.append(f"   异常: {str(e)}")
            else:
                task_info.append("❌ 当前没有记录的定时任务")

            # 检查所有相关任务
            all_tasks = asyncio.all_tasks()
            proactive_tasks = []
            for task in all_tasks:
                task_name = getattr(getattr(task, "_coro", {}), "__name__", "unknown")
                if "proactive" in task_name.lower():
                    proactive_tasks.append(f"- {task_name} (ID: {id(task)})")

            task_info.append(f"\n📊 系统中的相关任务 ({len(proactive_tasks)} 个):")
            if proactive_tasks:
                task_info.extend(proactive_tasks)
            else:
                task_info.append("- 无")

            # 检查配置状态
            proactive_config = self.config.get("proactive_reply", {})
            enabled = proactive_config.get("enabled", False)
            task_info.append(f"\n⚙️ 配置状态:")
            task_info.append(f"- 定时发送功能: {'✅ 启用' if enabled else '❌ 禁用'}")

            yield event.plain_result("\n".join(task_info))

        except Exception as e:
            yield event.plain_result(f"❌ 检查任务状态失败：{str(e)}")
            logger.error(f"检查任务状态失败: {e}")

    async def _manage_force_stop(self, event: AstrMessageEvent):
        """强制停止所有定时任务"""
        try:
            await self.force_stop_all_tasks()
            yield event.plain_result("✅ 已强制停止所有相关任务")
            logger.info(f"用户 {event.get_sender_name()} 强制停止了所有任务")
        except Exception as e:
            yield event.plain_result(f"❌ 强制停止任务失败：{str(e)}")
            logger.error(f"强制停止任务失败: {e}")

    async def _manage_force_start(self, event: AstrMessageEvent):
        """强制启动定时任务"""
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

    async def _manage_save_config(self, event: AstrMessageEvent):
        """强制保存配置文件"""
        try:
            # 先尝试正常保存
            try:
                self.config.save_config()
                yield event.plain_result("✅ 配置文件保存成功")
                logger.info(f"用户 {event.get_sender_name()} 强制保存了配置文件")
                return
            except Exception as e:
                yield event.plain_result(f"⚠️ 正常保存失败，尝试其他方法: {str(e)}")

            # 尝试其他保存方法
            if hasattr(self.config, '_save'):
                self.config._save()
                yield event.plain_result("✅ 使用备用方法保存配置成功")
                return

            yield event.plain_result("❌ 所有保存方法都失败了，请检查配置文件权限")

        except Exception as e:
            yield event.plain_result(f"❌ 强制保存配置失败：{str(e)}")
            logger.error(f"强制保存配置失败: {e}")

    def get_base_system_prompt(self):
        """获取基础系统提示词（人格提示词）"""
        try:
            # 获取当前使用的人格系统提示词
            base_system_prompt = ""

            # 尝试获取人格管理器
            personas = self.context.provider_manager.personas if hasattr(self.context, 'provider_manager') else []
            default_persona_obj = None

            if hasattr(self.context, 'provider_manager') and hasattr(self.context.provider_manager, 'selected_default_persona'):
                default_persona_obj = self.context.provider_manager.selected_default_persona

            # 如果有默认人格，使用默认人格的提示词
            if default_persona_obj and default_persona_obj.get("prompt"):
                base_system_prompt = self._ensure_string_encoding(default_persona_obj["prompt"])
            elif personas:
                # 如果没有默认人格但有人格列表，使用第一个人格
                for persona in personas:
                    if hasattr(persona, "prompt") and persona.prompt:
                        base_system_prompt = self._ensure_string_encoding(persona.prompt)
                        break

            # 如果还是没有获取到，使用插件默认人格
            if not base_system_prompt:
                proactive_config = self.config.get("proactive_reply", {})
                default_persona = proactive_config.get("proactive_default_persona", "你是一个友好、轻松的AI助手。")
                base_system_prompt = self._ensure_string_encoding(default_persona)

            return base_system_prompt

        except Exception as e:
            logger.warning(f"获取基础系统提示词失败: {e}")
            # 返回插件默认人格
            proactive_config = self.config.get("proactive_reply", {})
            default_persona = proactive_config.get("proactive_default_persona", "你是一个友好、轻松的AI助手。")
            return self._ensure_string_encoding(default_persona)

    @proactive_group.command("config")
    async def show_config(self, event: AstrMessageEvent):
        """显示完整的插件配置信息"""
        config_info = f"""⚙️ 插件配置信息

📋 完整配置：
{str(self.config)}

🔧 用户信息配置：
{str(self.config.get("user_info", {}))}

🤖 定时发送配置：
{str(self.config.get("proactive_reply", {}))}

💡 如果配置显示为空或不正确，请：
1. 在AstrBot管理面板中配置插件参数
2. 重载插件使配置生效
3. 检查配置文件是否正确保存"""

        yield event.plain_result(config_info)

    @proactive_group.command("help")
    async def help_command(self, event: AstrMessageEvent):
        """显示插件帮助信息"""
        help_text = """📖 主动回复插件帮助

🔧 核心功能：
  /proactive help - 显示此帮助信息
  /proactive status - 查看插件状态和当前会话信息
  /proactive config - 显示完整的插件配置信息
  /proactive add_session - 将当前会话添加到定时发送列表
  /proactive remove_session - 将当前会话从定时发送列表中移除
  /proactive restart - 重启定时任务（配置更改后必须使用）

🧪 测试功能：
  /proactive test [type] - 测试功能
    • test 或 test basic - 基础测试发送
    • test llm - 测试LLM请求，体验用户信息附加功能
    • test generation - 测试LLM生成主动消息功能
    • test prompt - 测试系统提示词构建过程
    • test placeholders - 测试占位符替换功能
    • test history - 测试对话历史记录功能



📋 显示功能：
  /proactive show [type] - 显示信息
    • show prompt - 显示当前配置下会输入给LLM的组合话术
    • show users - 显示记录的用户信息

⚙️ 管理功能：
  /proactive manage [action] - 管理功能
    • manage clear - 清除记录的用户信息和发送时间
    • manage task_status - 检查定时任务状态
    • manage force_stop - 强制停止所有定时任务
    • manage force_start - 强制启动定时任务
    • manage save_config - 强制保存配置文件
    • manage debug_info - 调试用户信息（故障排查用）
    • manage debug_send - 调试发送功能（故障排查用）
    • manage debug_times - 调试时间记录（故障排查用）

📝 功能说明：
1. 用户信息附加：在与AI对话时自动附加用户信息和时间
2. 智能主动对话：使用LLM生成个性化的主动消息，支持两种时间模式
   - 固定间隔模式：固定时间间隔，可选随机延迟
   - 随机间隔模式：每次在设定范围内随机选择等待时间
3. 个性化生成：基于用户信息和对话历史生成更自然的主动消息
4. 🆕 对话历史记录：AI主动发送的消息会自动添加到对话历史中
   - 解决了上下文断裂问题，用户下次发消息时AI能看到完整对话
   - 支持多种保存方式，确保历史记录的可靠性

🏷️ 主动对话提示词支持的占位符：
  {user_context} - 完整的用户上下文信息
  {user_last_message_time} - 用户上次发消息时间
  {user_last_message_time_ago} - 用户上次发消息相对时间（如"5分钟前"）
  {username} - 用户昵称
  {platform} - 平台名称
  {chat_type} - 聊天类型（群聊/私聊）
  {ai_last_sent_time} - AI上次发送时间
  {current_time} - 当前时间

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
