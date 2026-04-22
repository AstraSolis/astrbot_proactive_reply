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
from .runtime_data import runtime_data


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
                else:
                    base_data_dir = os.path.join(os.getcwd(), "data")
            except (AttributeError, KeyError) as e:
                logger.warning(f"心念 | ⚠️ AstrBot配置访问错误: {e}")
                base_data_dir = os.path.join(os.getcwd(), "data")

            # 创建插件专用的数据子目录（在 data/plugin_data 目录下）
            # 这符合AstrBot规范，避免插件更新时数据被覆盖
            plugin_data_dir = os.path.join(base_data_dir, "plugin_data", "astrbot_proactive_reply")

            # 确保目录存在
            os.makedirs(plugin_data_dir, exist_ok=True)

            logger.info(f"心念 | ✅ 插件数据目录: {plugin_data_dir}")
            return plugin_data_dir

        except OSError as e:
            logger.error(f"心念 | ❌ 文件系统错误: {e}")
            fallback_dir = os.path.join(os.getcwd(), "data", "plugin_data", "astrbot_proactive_reply")
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                logger.warning(f"心念 | ⚠️ 使用回退数据目录: {fallback_dir}")
                return fallback_dir
            except OSError:
                logger.error("心念 | ❌ 创建回退数据目录失败")
                return os.getcwd()

    def load_persistent_data(self):
        """从独立的持久化文件加载用户数据"""
        try:
            plugin_data_dir = self.get_plugin_data_dir()
            persistent_file = os.path.join(plugin_data_dir, "persistent_data.json")

            if os.path.exists(persistent_file):
                for encoding in ["utf-8-sig", "utf-8"]:
                    try:
                        with open(persistent_file, "r", encoding=encoding) as f:
                            persistent_data = json.load(f)
                        break  # 读取成功，退出编码重试循环
                    except PermissionError:
                        logger.error("心念 | ❌ 持久化文件读取权限不足")
                        return
                    except UnicodeDecodeError:
                        continue  # 尝试下一个编码
                    except json.JSONDecodeError:
                        logger.error("心念 | ❌ 持久化文件 JSON 解析失败，文件可能已损坏")
                        return
                else:
                    logger.error("心念 | ❌ 无法以任何编码读取持久化文件")
                    return

                if not isinstance(persistent_data, dict):
                    logger.error("心念 | ❌ 持久化文件格式错误：根对象不是字典")
                    return

                # 将持久化数据加载到运行时数据存储中（不是 config 对象）
                runtime_data.load_from_dict(persistent_data)
                logger.info("心念 | ✅ 从新的持久化文件加载数据成功")

            # 尝试从旧的持久化文件迁移数据（仅首次）
            migrated_marker = os.path.join(plugin_data_dir, ".migrated")
            if not os.path.exists(migrated_marker):
                self.migrate_old_persistent_data(plugin_data_dir)

        except (FileNotFoundError, OSError, AttributeError) as e:
            logger.info(f"心念 | ℹ️ 持久化文件加载: {e}")

    def migrate_old_persistent_data(self, new_data_dir: str):
        """迁移旧的持久化数据到新的数据目录（向后兼容）

        Args:
            new_data_dir: 新的数据目录路径
        """
        try:
            # 旧的可能存在的数据文件位置
            old_locations = [
                # 最旧的位置（根目录）
                os.path.join(os.getcwd(), "astrbot_proactive_reply_persistent.json"),
                # 旧的 data 目录位置（之前的实现）
                os.path.join(
                    os.getcwd(),
                    "data",
                    "astrbot_proactive_reply",
                    "persistent_data.json",
                ),
                # 旧的插件目录位置（更早的实现）
                os.path.join(
                    os.getcwd(),
                    "data",
                    "plugins",
                    "astrbot_proactive_reply",
                    "persistent_data.json",
                ),
            ]

            # 尝试从AstrBot配置获取实际的data_dir，构建完整的旧路径
            try:
                astrbot_config = self.context.get_config()
                if hasattr(astrbot_config, "data_dir") and astrbot_config.data_dir:
                    base_data_dir = astrbot_config.data_dir
                else:
                    base_data_dir = None

                if base_data_dir:
                    # 添加旧的 data/astrbot_proactive_reply 路径
                    old_data_dir_path = os.path.join(
                        base_data_dir,
                        "astrbot_proactive_reply",
                        "persistent_data.json",
                    )
                    if old_data_dir_path not in old_locations:
                        old_locations.insert(0, old_data_dir_path)

                    # 添加旧的 data/plugins/astrbot_proactive_reply 路径
                    old_plugin_dir_path = os.path.join(
                        base_data_dir,
                        "plugins",
                        "astrbot_proactive_reply",
                        "persistent_data.json",
                    )
                    if old_plugin_dir_path not in old_locations:
                        old_locations.insert(0, old_plugin_dir_path)
            except Exception as e:
                logger.debug(f"心念 | 获取AstrBot data_dir失败: {e}")

            for old_file in old_locations:
                if os.path.exists(old_file):
                    try:
                        logger.info(f"心念 | 🔄 发现旧的持久化数据文件: {old_file}")

                        # 尝试多种编码读取旧文件（与 load_persistent_data 保持一致）
                        old_data = None
                        for encoding in ["utf-8-sig", "utf-8"]:
                            try:
                                with open(old_file, "r", encoding=encoding) as f:
                                    old_data = json.load(f)
                                break
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                continue

                        if old_data is None:
                            logger.warning(f"心念 | ⚠️ 无法读取旧文件: {old_file}")
                            continue

                        # 验证数据格式（与 load_persistent_data 保持一致）
                        if not isinstance(old_data, dict):
                            logger.warning(f"心念 | ⚠️ 旧文件格式错误（非字典）: {old_file}")
                            continue

                        new_file = os.path.join(new_data_dir, "persistent_data.json")
                        with open(new_file, "w", encoding="utf-8") as f:
                            json.dump(old_data, f, ensure_ascii=False, indent=2)

                        # 加载到运行时数据存储中
                        runtime_data.load_from_dict(old_data)

                        logger.info(
                            f"心念 | ✅ 成功迁移旧的持久化数据: {old_file} -> {new_file}"
                        )

                        # 将备份文件保存到新目录
                        backup_filename = f"persistent_data.backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        backup_file = os.path.join(new_data_dir, backup_filename)
                        shutil.copy2(old_file, backup_file)
                        logger.info(f"心念 | ✅ 旧文件已备份到: {backup_file}")

                        # 删除旧文件
                        os.remove(old_file)
                        logger.info(f"心念 | ✅ 已删除旧文件: {old_file}")

                        # 尝试删除旧目录（如果为空且不是关键目录）
                        old_dir = os.path.dirname(old_file)
                        try:
                            # 安全检查：不删除根目录、data 目录、plugins 目录等关键目录
                            cwd = os.getcwd()
                            data_dir = os.path.join(cwd, "data")
                            plugins_dir = os.path.join(cwd, "data", "plugins")

                            # 规范化路径用于比较
                            old_dir_normalized = os.path.normpath(old_dir)

                            safe_to_delete = (
                                os.path.isdir(old_dir)
                                and not os.listdir(old_dir)
                                and old_dir_normalized != os.path.normpath(cwd)
                                and old_dir_normalized != os.path.normpath(data_dir)
                                and old_dir_normalized != os.path.normpath(plugins_dir)
                                and len(old_dir_normalized) > len(data_dir)  # 确保是子目录
                            )
                            if safe_to_delete:
                                os.rmdir(old_dir)
                                logger.info(f"心念 | ✅ 已删除空目录: {old_dir}")
                        except OSError:
                            pass  # 目录不为空或无法删除，忽略

                        # 写入迁移完成标记
                        marker_file = os.path.join(new_data_dir, ".migrated")
                        with open(marker_file, "w") as f:
                            f.write(f"migrated from {old_file} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                        return
                    except Exception as e:
                        logger.warning(f"心念 | ⚠️ 迁移旧持久化文件失败: {e}")

        except Exception as e:
            logger.error(f"心念 | ❌ 迁移旧持久化数据失败: {e}")

    def save_persistent_data(self) -> bool:
        """保存用户数据到独立的持久化文件

        Returns:
            是否保存成功
        """
        try:
            plugin_data_dir = self.get_plugin_data_dir()
            persistent_file = os.path.join(plugin_data_dir, "persistent_data.json")

            # 从运行时数据存储中获取数据
            persistent_data = runtime_data.to_dict()
            persistent_data["last_update"] = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            persistent_data["data_version"] = "2.0"

            if not validate_persistent_data(persistent_data):
                logger.error("心念 | ❌ 持久化数据验证失败")
                return False

            # 原子性写入
            temp_file = persistent_file + ".tmp"
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(persistent_data, f, ensure_ascii=False, indent=2)

                if os.name == "nt" and os.path.exists(persistent_file):
                    os.remove(persistent_file)
                os.rename(temp_file, persistent_file)

                logger.debug(f"心念 | ✅ 持久化数据已保存到: {persistent_file}")
                return True
            except Exception as e:
                logger.error(f"心念 | ❌ 保存持久化数据失败: {e}")
                return False
            finally:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass

        except Exception as e:
            logger.error(f"心念 | ❌ 持久化数据保存错误: {e}")
            return False

    def load_data(self, key: str, default=None):
        """加载特定的运行时数据"""
        if key == 'user_info':
            return runtime_data.session_user_info
        return default

    def save_data(self, key: str, data):
        """保存特定的运行时数据"""
        if key == 'user_info':
            runtime_data.session_user_info = data
        self.save_persistent_data()
