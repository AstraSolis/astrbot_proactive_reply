"""
持久化管理器

负责数据的持久化存储和加载
"""

import asyncio
import copy
import datetime
import json
import os
import shutil
from contextlib import suppress

from astrbot.api import logger
from astrbot.api.star import StarTools
from ..utils.validators import validate_persistent_data
from ._datafile import atomic_write_yaml, load_mapping, migrate_json_to_yaml
from .runtime_data import runtime_data

# 插件数据目录名(与 metadata.yaml 中的 name 保持一致)
PLUGIN_DATA_DIR_NAME = "astrbot_proactive_reply"

# 持久化文件名（YAML 为当前格式，JSON 为待迁移的历史格式）
PERSISTENT_FILE_NAME = "persistent_data.yaml"
LEGACY_PERSISTENT_FILE_NAME = "persistent_data.json"


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
        self._plugin_data_dir_cache: str | None = None
        self._save_debounce_seconds = 0.5
        self._save_generation = 0
        self._flushed_generation = 0
        self._last_save_ok = True
        self._save_task: asyncio.Task | None = None
        self._save_lock: asyncio.Lock | None = None
        self._save_lock_loop = None
        self._flush_event: asyncio.Event | None = None
        self._flush_event_loop = None

    def get_plugin_data_dir(self) -> str:
        """获取插件专用的数据目录路径

        优先使用 AstrBot 官方 API ``StarTools.get_data_dir()`` 获取标准插件数据
        目录(``data/plugin_data/astrbot_proactive_reply``)。该接口不依赖进程工作
        目录,可在非常规启动方式(工作目录非项目根)下正确定位。若官方接口不可用,
        则回退到基于配置 / 进程工作目录的手工拼接逻辑。

        Returns:
            数据目录路径
        """
        if self._plugin_data_dir_cache:
            return self._plugin_data_dir_cache

        # 优先使用官方 API(AstrBot >=4.24.0),由其负责创建并返回标准数据目录
        try:
            plugin_data_dir = str(StarTools.get_data_dir(PLUGIN_DATA_DIR_NAME))
            self._plugin_data_dir_cache = plugin_data_dir
            logger.info(f"心念 | ✅ 插件数据目录: {plugin_data_dir}")
            return plugin_data_dir
        except Exception as e:
            logger.warning(
                f"心念 | ⚠️ StarTools.get_data_dir() 不可用,回退到手工路径拼接: {e}"
            )

        # 回退逻辑:基于 AstrBot 配置或进程工作目录手工拼接
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
            plugin_data_dir = os.path.join(
                base_data_dir, "plugin_data", PLUGIN_DATA_DIR_NAME
            )

            # 确保目录存在
            os.makedirs(plugin_data_dir, exist_ok=True)

            logger.info(f"心念 | ✅ 插件数据目录: {plugin_data_dir}")
            self._plugin_data_dir_cache = plugin_data_dir
            return plugin_data_dir

        except OSError as e:
            logger.error(f"心念 | ❌ 文件系统错误: {e}")
            fallback_dir = os.path.join(
                os.getcwd(), "data", "plugin_data", PLUGIN_DATA_DIR_NAME
            )
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                logger.warning(f"心念 | ⚠️ 使用回退数据目录: {fallback_dir}")
                self._plugin_data_dir_cache = fallback_dir
                return fallback_dir
            except OSError:
                logger.error("心念 | ❌ 创建回退数据目录失败")
                cwd = os.getcwd()
                self._plugin_data_dir_cache = cwd
                return cwd

    def load_persistent_data(self):
        """从独立的持久化文件加载用户数据

        加载顺序：
        1. 无当前 YAML 且未做过迁移时，同目录历史 JSON → YAML 一次性迁移。
        2. 若当前 YAML 已存在，只读取它，不再用更旧位置的数据覆盖。
        3. 仅当当前 YAML 不存在时，首次尝试从旧的存储位置迁移数据。
        """
        try:
            plugin_data_dir = self.get_plugin_data_dir()
            persistent_file = os.path.join(plugin_data_dir, PERSISTENT_FILE_NAME)
            legacy_file = os.path.join(plugin_data_dir, LEGACY_PERSISTENT_FILE_NAME)
            migrated_marker = os.path.join(plugin_data_dir, ".migrated")

            # 1) 同目录 JSON → YAML 一次性迁移（旧文件备份为 .json.bak）。
            # 已有迁移标记时不要在 YAML 缺失后重新拉起旧 JSON，避免损坏归档后
            # 下次启动又把数据回退到旧版本。
            if not os.path.exists(persistent_file):
                if os.path.exists(migrated_marker):
                    if os.path.exists(legacy_file):
                        logger.info(
                            "心念 | ℹ️ 已存在迁移标记，跳过同目录旧 JSON 迁移: "
                            f"{legacy_file}"
                        )
                else:
                    migrated_data = migrate_json_to_yaml(legacy_file, persistent_file)
                    if migrated_data is not None:
                        self._write_migration_marker(
                            plugin_data_dir,
                            f"migrated from {legacy_file} at "
                            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        )

            # 2) 读取 YAML。只要当前 YAML 存在，就以它为准；读取失败时也不要再
            # 用旧 JSON 兜底覆盖，损坏现场会由 load_mapping 改名留档。
            if os.path.exists(persistent_file):
                persistent_data = load_mapping(persistent_file)
                if persistent_data is not None:
                    # 将持久化数据加载到运行时数据存储中（不是 config 对象）
                    runtime_data.load_from_dict(persistent_data)
                    logger.info("心念 | ✅ 从持久化文件加载数据成功")
                else:
                    self._write_migration_marker(
                        plugin_data_dir,
                        "skipped legacy migration because current YAML failed to load "
                        f"at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    )
                return

            # 3) 当前 YAML 不存在时，才尝试从旧的存储位置迁移数据（仅首次）
            if not os.path.exists(migrated_marker):
                self.migrate_old_persistent_data(plugin_data_dir)

        except (FileNotFoundError, OSError, AttributeError) as e:
            logger.info(f"心念 | ℹ️ 持久化文件加载: {e}")

    def _write_migration_marker(self, new_data_dir: str, message: str) -> None:
        """写入旧数据迁移标记；失败只影响重复扫描，不应影响主数据"""
        marker_file = os.path.join(new_data_dir, ".migrated")
        try:
            with open(marker_file, "w", encoding="utf-8") as f:
                f.write(message)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            logger.warning(f"心念 | ⚠️ 迁移标记写入失败: {marker_file}: {e}")

    def migrate_old_persistent_data(self, new_data_dir: str):
        """迁移旧的持久化数据到新的数据目录（向后兼容）

        Args:
            new_data_dir: 新的数据目录路径
        """
        try:
            new_file = os.path.join(new_data_dir, PERSISTENT_FILE_NAME)
            if os.path.exists(new_file):
                logger.info(
                    f"心念 | ℹ️ 已存在当前 YAML 持久化文件，跳过旧路径迁移: {new_file}"
                )
                self._write_migration_marker(
                    new_data_dir,
                    "skipped legacy migration because current YAML already existed "
                    f"at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                )
                return

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
                            logger.warning(
                                f"心念 | ⚠️ 旧文件格式错误（非字典）: {old_file}"
                            )
                            continue

                        if os.path.exists(new_file):
                            logger.info(
                                f"心念 | ℹ️ 当前 YAML 已创建，停止旧路径迁移: {new_file}"
                            )
                            self._write_migration_marker(
                                new_data_dir,
                                "skipped remaining legacy migration because current "
                                "YAML already existed "
                                f"at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            )
                            return

                        if not atomic_write_yaml(
                            new_file,
                            old_data,
                            header="心念插件持久化数据（自动生成）",
                        ):
                            logger.warning(
                                f"心念 | ⚠️ 迁移旧持久化文件写入失败，保留旧文件: {old_file}"
                            )
                            continue

                        # 加载到运行时数据存储中
                        runtime_data.load_from_dict(old_data)

                        logger.info(
                            f"心念 | ✅ 成功迁移旧的持久化数据: {old_file} -> {new_file}"
                        )

                        self._write_migration_marker(
                            new_data_dir,
                            f"migrated from {old_file} at "
                            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        )

                        # 将备份文件保存到新目录；备份失败时不删除旧文件。
                        backup_filename = f"persistent_data.backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        backup_file = os.path.join(new_data_dir, backup_filename)
                        old_file_removed = False
                        try:
                            shutil.copy2(old_file, backup_file)
                            logger.info(f"心念 | ✅ 旧文件已备份到: {backup_file}")

                            # 删除旧文件
                            os.remove(old_file)
                            old_file_removed = True
                            logger.info(f"心念 | ✅ 已删除旧文件: {old_file}")
                        except OSError as e:
                            logger.warning(
                                f"心念 | ⚠️ 旧文件备份或删除失败，已保留原文件: {e}"
                            )

                        # 尝试删除旧目录（如果为空且不是关键目录）
                        if old_file_removed:
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
                                    and old_dir_normalized
                                    != os.path.normpath(plugins_dir)
                                    and len(old_dir_normalized)
                                    > len(data_dir)  # 确保是子目录
                                )
                                if safe_to_delete:
                                    os.rmdir(old_dir)
                                    logger.info(f"心念 | ✅ 已删除空目录: {old_dir}")
                            except OSError:
                                pass  # 目录不为空或无法删除，忽略

                        return
                    except Exception as e:
                        logger.warning(f"心念 | ⚠️ 迁移旧持久化文件失败: {e}")

            self._write_migration_marker(
                new_data_dir,
                "no legacy persistent data found at "
                f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )

        except Exception as e:
            logger.error(f"心念 | ❌ 迁移旧持久化数据失败: {e}")

    def _build_persistent_payload(self) -> dict | None:
        """构建待落盘的持久化快照；失败时返回 None。"""
        # 写盘在线程池中执行，必须先和运行时数据断开引用，避免序列化期间
        # 主事件循环继续修改嵌套 list/dict 导致快照不一致。
        persistent_data = copy.deepcopy(runtime_data.to_persistent_dict())
        persistent_data["meta"]["last_update"] = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        persistent_data["meta"]["data_version"] = "3.1"

        if not validate_persistent_data(persistent_data):
            logger.error("心念 | ❌ 持久化数据验证失败")
            return None
        return persistent_data

    def _write_persistent_payload(self, persistent_file: str, payload: dict) -> bool:
        """执行实际 YAML 写盘。该方法可安全放入线程池运行。"""
        ok = atomic_write_yaml(
            persistent_file,
            payload,
            header="心念插件持久化数据（自动生成，一般无需手动编辑）",
        )
        if ok:
            logger.debug(f"心念 | ✅ 持久化数据已保存到: {persistent_file}")
        return ok

    def _save_persistent_data_now(self) -> bool:
        """同步立即保存；用于无事件循环场景和显式强制保存。"""
        try:
            plugin_data_dir = self.get_plugin_data_dir()
            persistent_file = os.path.join(plugin_data_dir, PERSISTENT_FILE_NAME)
            payload = self._build_persistent_payload()
            if payload is None:
                return False
            return self._write_persistent_payload(persistent_file, payload)
        except Exception as e:
            logger.error(f"心念 | ❌ 持久化数据保存错误: {e}", exc_info=True)
            return False

    def _get_save_lock(self) -> asyncio.Lock:
        """按事件循环懒创建锁，避免测试中跨 loop 复用锁对象。"""
        loop = asyncio.get_running_loop()
        if self._save_lock is None or self._save_lock_loop is not loop:
            self._save_lock = asyncio.Lock()
            self._save_lock_loop = loop
        return self._save_lock

    def _get_flush_event(self) -> asyncio.Event:
        """按事件循环懒创建防抖唤醒事件。"""
        loop = asyncio.get_running_loop()
        if self._flush_event is None or self._flush_event_loop is not loop:
            self._flush_event = asyncio.Event()
            self._flush_event_loop = loop
        return self._flush_event

    def save_persistent_data(self, *, immediate: bool = False) -> bool:
        """保存用户数据到独立的持久化文件

        在事件循环内默认只标记脏数据并防抖合并写入，实际 YAML 序列化与落盘放到
        ``asyncio.to_thread``，避免每条消息多次阻塞事件循环。无运行中的事件循环
        时保持同步写入，兼容测试与启动迁移等同步路径。

        Returns:
            同步路径返回实际保存结果；异步防抖路径返回“已接受保存请求”。
        """
        self._save_generation += 1

        if immediate:
            ok = self._save_persistent_data_now()
            self._last_save_ok = ok
            if ok:
                self._flushed_generation = self._save_generation
            return ok

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            ok = self._save_persistent_data_now()
            self._last_save_ok = ok
            if ok:
                self._flushed_generation = self._save_generation
            return ok

        if self._save_task is None or self._save_task.done():
            self._save_task = loop.create_task(self._debounced_flush())
        return True

    async def _flush_dirty_once(self) -> bool:
        """将当前代数的脏数据刷新到磁盘一次。"""
        lock = self._get_save_lock()
        async with lock:
            if self._flushed_generation >= self._save_generation:
                return self._last_save_ok

            target_generation = self._save_generation
            try:
                plugin_data_dir = self.get_plugin_data_dir()
                persistent_file = os.path.join(plugin_data_dir, PERSISTENT_FILE_NAME)
                payload = self._build_persistent_payload()
                if payload is None:
                    self._last_save_ok = False
                    return False
                ok = await asyncio.to_thread(
                    self._write_persistent_payload,
                    persistent_file,
                    payload,
                )
            except Exception as e:
                logger.error(f"心念 | ❌ 异步持久化保存错误: {e}", exc_info=True)
                ok = False

            self._last_save_ok = ok
            if ok:
                self._flushed_generation = max(
                    self._flushed_generation, target_generation
                )
            return ok

    async def _debounced_flush(self) -> bool:
        """防抖保存任务；保存期间若产生新变更，会自动再排一次。"""
        task = asyncio.current_task()
        ok = False
        try:
            flush_event = self._get_flush_event()
            try:
                await asyncio.wait_for(
                    flush_event.wait(), timeout=self._save_debounce_seconds
                )
            except asyncio.TimeoutError:
                pass
            flush_event.clear()
            ok = await self._flush_dirty_once()
            return ok
        except asyncio.CancelledError:
            raise
        finally:
            if self._save_task is task:
                self._save_task = None
                if ok and self._flushed_generation < self._save_generation:
                    self._save_task = asyncio.create_task(self._debounced_flush())

    async def flush_pending_save(self) -> bool:
        """立即唤醒防抖任务并等待所有待保存数据落盘。

        插件终止、测试或需要强一致持久化的路径可调用此方法，确保防抖队列中的
        最新运行时数据已经写入 ``persistent_data.yaml``。
        """
        task = self._save_task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            self._get_flush_event().set()
            with suppress(asyncio.CancelledError):
                await task

        ok = self._last_save_ok
        while self._flushed_generation < self._save_generation:
            ok = await self._flush_dirty_once()
            if not ok:
                break
        return ok

    def load_data(self, key: str, default=None):
        """加载特定的运行时数据"""
        if key == "user_info":
            return runtime_data.session_user_info
        return default

    def save_data(self, key: str, data):
        """保存特定的运行时数据"""
        if key == "user_info":
            runtime_data.session_user_info = data
        self.save_persistent_data()
