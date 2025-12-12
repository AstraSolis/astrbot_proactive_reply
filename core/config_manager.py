"""
配置管理器

负责插件配置的初始化、验证和迁移
"""

from astrbot.api import logger
from .runtime_data import runtime_data


class ConfigManager:
    """配置管理器类"""

    # 默认配置
    DEFAULT_CONFIG = {
        "user_info": {
            "time_format": "%Y-%m-%d %H:%M:%S",
            "template": "[对话信息] 用户：{username}，时间：{time}",
        },
        "proactive_reply": {
            "enabled": False,
            "timing_mode": "fixed_interval",
            "interval_minutes": 600,
            "proactive_default_persona": "你是一个温暖、真诚的AI朋友。你有着丰富的情感表达能力，会根据用户的状态和心情调整自己的语气。你善于倾听，乐于分享，偶尔会有些小幽默。你记得与用户的互动历史，会在合适的时候提及之前的对话。你不会过于正式，而是像一个贴心的朋友一样，用自然、温暖的方式与用户交流。你会主动关心用户的近况，分享有趣的想法，有时也会表达自己的'感受'和'想法'，让对话更加生动有趣。",
            "proactive_prompt_list": [
                "主动向{username}发起一段自然的对话",
                "想到了{username}，决定主动和他们聊聊",
                "现在是{current_time}，主动找{username}聊天",
                "距离上次和{username}聊天已经{user_last_message_time_ago}了，主动发起对话",
                "随机选择一个话题，主动和{username}交流",
                "以轻松的方式主动联系{username}",
                "主动关心{username}的近况",
                "想要分享一些想法，主动找{username}聊天",
                "主动询问{username}最近的生活状态",
                "想要陪伴{username}一会儿，主动发起对话",
                "想了解{username}的新动态，发起对话",
                "有点想念{username}，主动发起对话",
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
            "split_enabled": True,
            "split_mode": "backslash",
            "custom_split_pattern": "",
            "split_message_delay_ms": 500,
            "use_database_fallback": True,
        },
    }

    # 运行时数据字段（不在配置界面显示，由 PersistenceManager 独立管理）
    RUNTIME_DATA_KEYS = ["session_user_info", "last_sent_times", "ai_last_sent_times"]

    def __init__(self, config: dict, persistence_manager=None):
        """初始化配置管理器

        Args:
            config: 配置字典
            persistence_manager: 持久化管理器（可选）
        """
        self.config = config
        self.persistence_manager = persistence_manager

    def verify_config_loading(self):
        """验证配置文件加载状态"""
        try:
            # 从 RuntimeDataStore 获取用户信息（重构后数据存储在单例中）
            session_user_info = runtime_data.session_user_info

            if session_user_info:
                logger.info(f"✅ 已加载 {len(session_user_info)} 个用户信息记录")
            else:
                logger.info("ℹ️ 暂无已保存的用户信息（首次运行）")

        except KeyError as e:
            logger.error(f"配置键错误: {e}")
        except AttributeError as e:
            logger.error(f"配置对象属性错误: {e}")
        except TypeError as e:
            logger.error(f"配置数据类型错误: {e}")

    def _clean_runtime_data_from_config(self):
        """从配置中清理运行时数据字段

        这些字段不应该显示在 AstrBot 配置界面中，
        它们通过 PersistenceManager 独立存储在 persistent_data.json 中。
        """
        proactive_config = self.config.get("proactive_reply", {})
        cleaned = False

        for key in self.RUNTIME_DATA_KEYS:
            if key in proactive_config:
                del proactive_config[key]
                cleaned = True
                logger.debug(f"已从配置中移除运行时数据字段: {key}")

        if cleaned:
            try:
                self.config.save_config()
                logger.info("✅ 已清理配置中的运行时数据字段")
            except Exception as e:
                logger.warning(f"保存清理后的配置失败: {e}")

    def ensure_config_structure(self):
        """确保配置文件结构完整"""
        # 清理不应该在配置界面显示的运行时数据字段
        # 这些数据通过 PersistenceManager 独立存储，不需要在 AstrBot 配置中
        self._clean_runtime_data_from_config()

        # 加载持久化数据到 RuntimeDataStore
        if self.persistence_manager:
            self.persistence_manager.load_persistent_data()

        # 检查并补充缺失的配置
        config_updated = False
        for section, section_config in self.DEFAULT_CONFIG.items():
            if section not in self.config:
                self.config[section] = section_config
                config_updated = True
            else:
                # 检查子配置项
                for key, default_value in section_config.items():
                    if key not in self.config[section]:
                        self.config[section][key] = default_value
                        config_updated = True

        # 数据迁移
        self.migrate_time_records()

        # 如果配置有更新，保存配置文件
        if config_updated:
            try:
                self.config.save_config()
                logger.info("配置文件已更新")
            except Exception as e:
                logger.error(f"保存配置文件失败: {e}")

    def migrate_time_records(self):
        """迁移时间记录数据到运行时数据存储"""
        try:
            # 如果 ai_last_sent_times 为空但 last_sent_times 有数据，进行迁移
            if not runtime_data.ai_last_sent_times and runtime_data.last_sent_times:
                runtime_data.ai_last_sent_times = runtime_data.last_sent_times.copy()
                if self.persistence_manager:
                    self.persistence_manager.save_persistent_data()
                    logger.info(f"成功迁移 {len(runtime_data.last_sent_times)} 条时间记录")

        except (KeyError, ValueError, AttributeError) as e:
            logger.error(f"迁移时间记录失败: {e}")

        # 迁移 split_by_backslash 配置
        try:
            proactive_config = self.config.get("proactive_reply", {})
            if (
                "split_by_backslash" in proactive_config
                and "split_enabled" not in proactive_config
            ):
                split_value = proactive_config.get("split_by_backslash", True)
                self.config["proactive_reply"]["split_enabled"] = split_value
                if "split_mode" not in proactive_config:
                    self.config["proactive_reply"]["split_mode"] = "backslash"
                logger.info(
                    f"已将 split_by_backslash 迁移到 split_enabled (值: {split_value})"
                )

                if self.save_config_safely():
                    logger.info("分割配置迁移已保存")
                else:
                    logger.warning("分割配置迁移保存失败")
        except Exception as e:
            logger.error(f"迁移分割配置失败: {e}")

    def save_config_safely(self) -> bool:
        """安全的配置保存方法

        Returns:
            是否保存成功
        """
        try:
            self.config.save_config()
            return True
        except PermissionError as e:
            logger.error(f"配置文件权限不足: {e}")
            return False
        except OSError as e:
            logger.error(f"配置文件系统错误: {e}")
            return False
        except AttributeError as e:
            logger.error(f"配置对象方法不存在: {e}")
            return False
