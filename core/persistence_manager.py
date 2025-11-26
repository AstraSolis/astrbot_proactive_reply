"""
持久化管理器

负责数据的持久化存储和加载
"""

import datetime
import json
import os
import shutil
from astrbot.api import logger
from ..utils.validators import validate_persistent_data


class PersistenceManager:
    """持久化管理器类"""

    def __init__(self, config: dict, context):
        """初始化持久化管理器

        Args:
            config: 配置字典
            context: AstrBot上下文对象
        """
        self.config = config
        self.context = context

    def get_plugin_data_dir(self) -> str:
        """获取插件专用的数据目录路径

        Returns:
            数据目录路径
        """
        try:
            # 尝试从AstrBot配置中获取数据目录
            try:
                astrbot_config = self.context.get_config()
                if hasattr(astrbot_config, "data_dir") and astrbot_config.data_dir:
                    base_data_dir = astrbot_config.data_dir
                elif hasattr(astrbot_config, "_data_dir") and astrbot_config._data_dir:
                    base_data_dir = astrbot_config._data_dir
                else:
                    base_data_dir = os.path.join(os.getcwd(), "data")
            except (AttributeError, KeyError) as e:
                logger.warning(f"⚠️ AstrBot配置访问错误: {e}")
                base_data_dir = os.path.join(os.getcwd(), "data")

            # 创建插件专用的数据子目录
            plugin_data_dir = os.path.join(
                base_data_dir, "plugins", "astrbot_proactive_reply"
            )

            # 确保目录存在
            os.makedirs(plugin_data_dir, exist_ok=True)

            logger.info(f"✅ 插件数据目录: {plugin_data_dir}")
            return plugin_data_dir

        except OSError as e:
            logger.error(f"❌ 文件系统错误: {e}")
            fallback_dir = os.path.join(
                os.getcwd(), "data", "plugins", "astrbot_proactive_reply"
            )
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                logger.warning(f"⚠️ 使用回退数据目录: {fallback_dir}")
                return fallback_dir
            except OSError:
                logger.error("❌ 创建回退数据目录失败")
                return os.getcwd()

    def load_persistent_data(self):
        """从独立的持久化文件加载用户数据"""
        try:
            plugin_data_dir = self.get_plugin_data_dir()
            persistent_file = os.path.join(plugin_data_dir, "persistent_data.json")

            if os.path.exists(persistent_file):
                for encoding in ["utf-8-sig", "utf-8", "gbk"]:
                    try:
                        with open(persistent_file, "r", encoding=encoding) as f:
                            persistent_data = json.load(f)

                        if not isinstance(persistent_data, dict):
                            logger.error("持久化文件格式错误：根对象不是字典")
                            continue

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

                        logger.info("✅ 从新的持久化文件加载数据成功")
                        return
                    except (UnicodeDecodeError, json.JSONDecodeError, PermissionError):
                        continue

            # 尝试从旧的持久化文件迁移数据
            self.migrate_old_persistent_data(plugin_data_dir)

        except (FileNotFoundError, OSError, AttributeError) as e:
            logger.info(f"持久化文件加载: {e}")

    def migrate_old_persistent_data(self, new_data_dir: str):
        """迁移旧的持久化数据到新的数据目录（向后兼容）

        Args:
            new_data_dir: 新的数据目录路径
        """
        try:
            old_locations = [
                os.path.join(os.getcwd(), "astrbot_proactive_reply_persistent.json"),
            ]

            for old_file in old_locations:
                if os.path.exists(old_file):
                    try:
                        with open(old_file, "r", encoding="utf-8") as f:
                            old_data = json.load(f)

                        new_file = os.path.join(new_data_dir, "persistent_data.json")
                        with open(new_file, "w", encoding="utf-8") as f:
                            json.dump(old_data, f, ensure_ascii=False, indent=2)

                        if "proactive_reply" not in self.config:
                            self.config["proactive_reply"] = {}

                        for key in [
                            "session_user_info",
                            "ai_last_sent_times",
                            "last_sent_times",
                        ]:
                            if key in old_data:
                                self.config["proactive_reply"][key] = old_data[key]

                        logger.info(
                            f"✅ 成功迁移旧的持久化数据: {old_file} -> {new_file}"
                        )

                        backup_file = old_file + ".backup"
                        shutil.move(old_file, backup_file)
                        logger.info(f"✅ 旧文件已备份到: {backup_file}")
                        return
                    except Exception as e:
                        logger.warning(f"⚠️ 迁移旧持久化文件失败: {e}")

        except Exception as e:
            logger.error(f"❌ 迁移旧持久化数据失败: {e}")

    def save_persistent_data(self) -> bool:
        """保存用户数据到独立的持久化文件

        Returns:
            是否保存成功
        """
        try:
            plugin_data_dir = self.get_plugin_data_dir()
            persistent_file = os.path.join(plugin_data_dir, "persistent_data.json")

            proactive_config = self.config.get("proactive_reply", {})
            persistent_data = {
                "session_user_info": proactive_config.get("session_user_info", {}),
                "ai_last_sent_times": proactive_config.get("ai_last_sent_times", {}),
                "last_sent_times": proactive_config.get("last_sent_times", {}),
                "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data_version": "2.0",
            }

            if not validate_persistent_data(persistent_data):
                logger.error("持久化数据验证失败")
                return False

            # 原子性写入
            temp_file = persistent_file + ".tmp"
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(persistent_data, f, ensure_ascii=False, indent=2)

                if os.name == "nt" and os.path.exists(persistent_file):
                    os.remove(persistent_file)
                os.rename(temp_file, persistent_file)

                logger.debug(f"✅ 持久化数据已保存到: {persistent_file}")
                return True
            except Exception as e:
                logger.error(f"保存持久化数据失败: {e}")
                return False
            finally:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass

        except Exception as e:
            logger.error(f"持久化数据保存错误: {e}")
            return False

    def backup_corrupted_file(self, file_path: str):
        """备份损坏的文件

        Args:
            file_path: 文件路径
        """
        try:
            backup_path = f"{file_path}.corrupted.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(file_path, backup_path)
            logger.info(f"损坏文件已备份到: {backup_path}")
        except OSError as e:
            logger.error(f"备份损坏文件失败: {e}")
