"""
数据文件读写助手（YAML 持久化）

集中插件持久化文件的通用读写逻辑，供 ``persistence_manager`` 与
``calendar_manager`` 复用，避免「多编码读取 + 原子写入 + 临时文件清理」逻辑分散
在多处实现而漂移。

设计要点：
- 仅使用 ``yaml.safe_load`` / ``yaml.safe_dump``，杜绝任意对象构造带来的安全风险。
- 写入采用 ``allow_unicode=True``（中文不转义）、``sort_keys=False``（保持插入顺序，
  diff 友好）、``default_flow_style=False``（块状缩进，最直观）。
- 写入沿用「``.tmp`` + ``os.rename``」原子替换，并在 Windows 下先删旧文件。
- 读取优先使用 libyaml C 扩展（``CSafeLoader``）提速；写出固定使用纯 Python
  ``SafeDumper``：libyaml 的 C emitter 会忽略按节点设置的块样式（``|``）并转义
  星平面 Unicode（如 emoji），使长消息可读性变差。持久化文件体量小、写盘不频繁，
  用 Python dumper 换取「块样式 + 不转义」的可读性更划算。
"""

import json
import os

import yaml
from astrbot.api import logger

# 读取优先使用 libyaml C 扩展（更快），不可用时回退到纯 Python 实现
try:  # pragma: no cover - 取决于运行环境是否带 libyaml
    from yaml import CSafeLoader as _SafeLoader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader as _SafeLoader

# 读取时依次尝试的编码（兼容带 BOM 的历史文件）
_READ_ENCODINGS = ("utf-8-sig", "utf-8")


def _represent_str(dumper, data):
    """多行字符串用字面量块样式（``|``）输出，单行保持默认

    主动消息（``last_proactive_message``）等长文本含换行，块样式比折行 / 转义更
    直观、可读。若文本无法以块样式无损表示（如行尾含空白），PyYAML 会自动回退到
    引号样式，不会丢失内容。
    """
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _SafeDumper(yaml.SafeDumper):
    """纯 Python SafeDumper 子类，挂载多行字符串块样式 representer

    用子类而非直接改 ``yaml.SafeDumper``，避免污染进程内其他使用方的全局 Dumper。
    """


_SafeDumper.add_representer(str, _represent_str)


def dump_yaml_str(data: dict, header: str | None = None) -> str:
    """将映射序列化为 YAML 文本（用于导出等场景）

    Args:
        data: 待序列化的字典
        header: 可选的头部注释（不含 ``#``，会自动加前缀）

    Returns:
        YAML 文本
    """
    body = yaml.dump(
        data,
        Dumper=_SafeDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    if header:
        return f"# {header}\n{body}"
    return body


def load_mapping(path: str):
    """从 YAML 文件读取一个映射（dict）

    多编码尝试读取并以 ``safe_load`` 解析。读取/解析失败或根对象不是 dict 时，
    记录日志并返回 ``None``（与历史 JSON 行为保持一致，由调用方决定回退策略）。

    Args:
        path: YAML 文件路径

    Returns:
        解析得到的 dict；失败返回 ``None``
    """
    data = None
    for encoding in _READ_ENCODINGS:
        try:
            with open(path, "r", encoding=encoding) as f:
                data = yaml.load(f, Loader=_SafeLoader)
            break
        except PermissionError:
            logger.error(f"心念 | ❌ 文件读取权限不足: {path}")
            return None
        except UnicodeDecodeError:
            continue
        except yaml.YAMLError:
            logger.error(f"心念 | ❌ YAML 解析失败，文件可能已损坏: {path}")
            return None
    else:
        logger.error(f"心念 | ❌ 无法以任何编码读取文件: {path}")
        return None

    if not isinstance(data, dict):
        logger.error(f"心念 | ❌ 文件格式错误：根对象不是字典: {path}")
        return None
    return data


def atomic_write_yaml(path: str, data: dict, header: str | None = None) -> bool:
    """原子性地将映射写入 YAML 文件

    Args:
        path: 目标文件路径
        data: 待写入的字典
        header: 可选的头部注释

    Returns:
        是否写入成功
    """
    temp_file = path + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(dump_yaml_str(data, header=header))

        # Windows 下 os.rename 不允许覆盖已存在文件
        if os.name == "nt" and os.path.exists(path):
            os.remove(path)
        os.rename(temp_file, path)
        return True
    except Exception as e:
        logger.error(f"心念 | ❌ 写入文件失败: {path}: {e}")
        return False
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass


def _load_json_mapping(path: str):
    """读取旧的 JSON 文件（多编码），返回 dict；失败返回 None"""
    for encoding in _READ_ENCODINGS:
        try:
            with open(path, "r", encoding=encoding) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.error(f"心念 | ❌ 旧 JSON 根对象不是字典: {path}")
            return None
        except PermissionError:
            logger.error(f"心念 | ❌ 旧 JSON 读取权限不足: {path}")
            return None
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    logger.error(f"心念 | ❌ 无法读取旧 JSON 文件: {path}")
    return None


def migrate_json_to_yaml(json_path: str, yaml_path: str):
    """将旧的 JSON 持久化文件一次性迁移为 YAML

    仅当目标 YAML 不存在、且旧 JSON 存在时执行迁移：读取 JSON → 写出 YAML →
    将旧 JSON 重命名为 ``<json_path>.bak`` 保留以便回滚。

    Args:
        json_path: 旧 JSON 文件路径
        yaml_path: 新 YAML 文件路径

    Returns:
        迁移成功时返回读取到的 dict（供调用方回填内存）；未迁移或失败返回 ``None``
    """
    if os.path.exists(yaml_path) or not os.path.exists(json_path):
        return None

    data = _load_json_mapping(json_path)
    if data is None:
        return None

    if not atomic_write_yaml(yaml_path, data):
        logger.error(f"心念 | ❌ JSON→YAML 迁移写入失败: {json_path} -> {yaml_path}")
        return None

    # 保留旧文件为备份（可回滚）
    try:
        backup_path = json_path + ".bak"
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.rename(json_path, backup_path)
        logger.info(
            f"心念 | ✅ 已迁移 {os.path.basename(json_path)} → "
            f"{os.path.basename(yaml_path)}（旧文件备份为 .bak）"
        )
    except OSError as e:
        logger.warning(f"心念 | ⚠️ 旧 JSON 备份失败（数据已迁移）: {e}")

    return data
