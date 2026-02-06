"""
配置管理器

负责插件配置的初始化、验证和迁移

注意：默认配置从 _conf_schema.json 动态读取，确保单一数据源
"""

import json
import os
from astrbot.api import logger
from .runtime_data import runtime_data


class ConfigManager:
    """配置管理器类"""

    # 运行时数据字段（不在配置界面显示，由 PersistenceManager 独立管理）
    RUNTIME_DATA_KEYS = ["session_user_info", "last_sent_times", "ai_last_sent_times"]

    # 缓存从 schema 读取的默认配置
    _default_config_cache = None

    @classmethod
    def _load_default_config_from_schema(cls) -> dict:
        """从 _conf_schema.json 动态读取默认配置

        确保默认值只在一处定义（_conf_schema.json），避免重复维护

        Returns:
            默认配置字典
        """
        if cls._default_config_cache is not None:
            return cls._default_config_cache

        default_config = {}
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "_conf_schema.json"
        )

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)

            # 递归提取默认值
            for section_name, section_def in schema.items():
                if section_def.get("type") == "object" and "items" in section_def:
                    default_config[section_name] = cls._extract_defaults_from_items(
                        section_def["items"]
                    )

            logger.debug(f"从 schema 加载了 {len(default_config)} 个配置区块的默认值")

        except FileNotFoundError:
            logger.warning(f"配置 schema 文件不存在: {schema_path}，使用空默认配置")
        except json.JSONDecodeError as e:
            logger.error(f"配置 schema JSON 解析失败: {e}")
        except Exception as e:
            logger.error(f"加载配置 schema 失败: {e}")

        # 无论成功与否都缓存结果，避免重复读取文件
        cls._default_config_cache = default_config
        return default_config

    @classmethod
    def _extract_defaults_from_items(cls, items: dict) -> dict:
        """从 schema items 中提取默认值

        Args:
            items: schema 中的 items 定义

        Returns:
            包含默认值的字典
        """
        defaults = {}
        for key, item_def in items.items():
            if "default" in item_def:
                defaults[key] = item_def["default"]
            elif item_def.get("type") == "object" and "items" in item_def:
                # 递归处理嵌套对象
                defaults[key] = cls._extract_defaults_from_items(item_def["items"])
        return defaults

    @property
    def DEFAULT_CONFIG(self) -> dict:
        """获取默认配置（从 schema 动态读取）"""
        return self._load_default_config_from_schema()

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
                    logger.info(
                        f"成功迁移 {len(runtime_data.last_sent_times)} 条时间记录"
                    )

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
