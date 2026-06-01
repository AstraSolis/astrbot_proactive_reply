"""
插件 Web API

向 AstrBot 注册所有插件 REST API，供 Plugin Pages 调用
"""

import os
from datetime import datetime

from quart import jsonify, request

from astrbot.api import logger

from .core.runtime_data import runtime_data
from .llm.calendar_generator import (
    DEFAULT_MAX_GENERATE,
    build_system_prompt,
    generate_calendar_events,
)
from .llm.placeholder_utils import get_placeholder_catalog
from .utils.config_schema import (
    build_config_schema,
    coerce_section_values,
    load_conf_schema,
)
from .utils.plugin_i18n import normalize_locale, request_locale, t
from .utils.time_utils import get_now

PLUGIN_NAME = "astrbot_proactive_reply"

# 配置 schema 缓存（首次读取后复用，避免重复磁盘 IO）
_CONF_SCHEMA_CACHE: dict | None = None


def _conf_schema_path() -> str:
    """返回 ``_conf_schema.json`` 的绝对路径。"""
    return os.path.join(os.path.dirname(__file__), "_conf_schema.json")


def _get_conf_schema() -> dict:
    """读取并缓存配置 schema。"""
    global _CONF_SCHEMA_CACHE
    if _CONF_SCHEMA_CACHE is None:
        _CONF_SCHEMA_CACHE = load_conf_schema(_conf_schema_path())
    return _CONF_SCHEMA_CACHE


def _internal_error_response(locale: str):
    return jsonify(
        {
            "success": False,
            "error": t(
                locale, "api.errors.internal_error", "服务器内部错误，请稍后重试"
            ),
        }
    ), 500


def register_web_apis(context, managers: dict) -> None:
    """向 AstrBot 注册所有插件 Web API

    Args:
        context: AstrBot 上下文
        managers: 插件管理器字典
    """

    async def get_dashboard_stats():
        """获取仪表板统计信息"""
        try:
            locale = normalize_locale(request.args.get("locale"))
            stats = _build_dashboard_stats(managers, locale)
            return jsonify({"success": True, "stats": stats})
        except Exception as e:
            logger.error(f"心念 Web API | 获取仪表板统计失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    async def get_sessions_list():
        """获取会话列表"""
        try:
            locale = normalize_locale(request.args.get("locale"))
            sessions = _build_sessions_data(managers, locale)
            return jsonify(
                {"success": True, "sessions": sessions, "total": len(sessions)}
            )
        except Exception as e:
            logger.error(f"心念 Web API | 获取会话列表失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    async def add_session():
        """添加会话"""
        try:
            locale = request_locale()
            config_manager = managers.get("config_manager")
            if not config_manager:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_manager_not_found",
                            "配置管理器未找到",
                        ),
                    }
                ), 500

            data = await request.get_json()
            session_id = (data or {}).get("session_id", "").strip()
            if not session_id:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.session_id_empty", "会话 ID 不能为空"
                        ),
                    }
                ), 400

            parts = session_id.split(":")
            if len(parts) < 3:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.session_id_invalid",
                            "会话 ID 格式不正确，应为 platform:type:id",
                        ),
                    }
                ), 400

            config = config_manager.config if hasattr(config_manager, "config") else {}
            existing = _safe_sessions_list(config)

            if session_id in existing:
                return jsonify(
                    {
                        "success": False,
                        "error": t(locale, "api.errors.session_exists", "该会话已存在"),
                    }
                ), 400

            existing.append(session_id)
            config.setdefault("proactive_reply", {})["sessions"] = existing
            if not config_manager.save_config_safely():
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500

            logger.info(f"心念 Web API | 已添加会话: {session_id}")
            return jsonify(
                {
                    "success": True,
                    "message": t(
                        locale,
                        "api.messages.session_added",
                        "已添加会话: {session_id}",
                        session_id=session_id,
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 添加会话失败: {e}")
            return _internal_error_response(request_locale())

    async def remove_session():
        """移除会话"""
        try:
            locale = request_locale()
            config_manager = managers.get("config_manager")
            if not config_manager:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_manager_not_found",
                            "配置管理器未找到",
                        ),
                    }
                ), 500

            data = await request.get_json()
            session_id = (data or {}).get("session_id", "").strip()
            if not session_id:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.session_id_empty", "会话 ID 不能为空"
                        ),
                    }
                ), 400

            config = config_manager.config if hasattr(config_manager, "config") else {}
            existing = _safe_sessions_list(config)
            original_count = len(existing)
            updated = [s for s in existing if s != session_id]

            if len(updated) == original_count:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.session_not_found", "未找到该会话"
                        ),
                    }
                ), 404

            config.setdefault("proactive_reply", {})["sessions"] = updated
            if not config_manager.save_config_safely():
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500

            task_manager = managers.get("task_manager")
            if task_manager and hasattr(task_manager, "clear_session_timer"):
                task_manager.clear_session_timer(session_id)

            logger.info(f"心念 Web API | 已移除会话: {session_id}")
            return jsonify(
                {
                    "success": True,
                    "message": t(
                        locale,
                        "api.messages.session_removed",
                        "已移除会话: {session_id}",
                        session_id=session_id,
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 移除会话失败: {e}")
            return _internal_error_response(request_locale())

    async def get_ai_schedules():
        """获取 AI 约定任务列表"""
        try:
            locale = normalize_locale(request.args.get("locale"))
            config_manager = managers.get("config_manager")
            config = (
                config_manager.config
                if config_manager and hasattr(config_manager, "config")
                else {}
            )
            astrbot_config = _get_astrbot_config(managers)
            now = get_now(config, astrbot_config).replace(tzinfo=None)
            schedules = _build_ai_schedules_data(now, locale)
            return jsonify(
                {"success": True, "schedules": schedules, "total": len(schedules)}
            )
        except Exception as e:
            logger.error(f"心念 Web API | 获取 AI 约定任务失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    async def cancel_ai_schedule():
        """取消 AI 约定任务"""
        try:
            locale = request_locale()
            data = await request.get_json()
            session_id = (data or {}).get("session_id", "").strip()
            task_id = (data or {}).get("task_id", "").strip()
            fire_time = (data or {}).get("fire_time", "").strip()

            if not session_id:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.session_id_empty", "会话 ID 不能为空"
                        ),
                    }
                ), 400
            if not task_id and not fire_time:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.schedule_not_found", "未找到该约定任务"
                        ),
                    }
                ), 400

            tasks = runtime_data.session_ai_scheduled.get(session_id)
            if not tasks:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.schedule_not_found", "未找到该约定任务"
                        ),
                    }
                ), 404

            task_list = (
                tasks
                if isinstance(tasks, list)
                else [tasks]
                if isinstance(tasks, dict)
                else []
            )
            if task_id:
                updated = [task for task in task_list if task.get("task_id") != task_id]
            else:
                updated = [
                    task for task in task_list if task.get("fire_time", "") != fire_time
                ]

            if len(updated) == len(task_list):
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.schedule_not_found", "未找到该约定任务"
                        ),
                    }
                ), 404

            if updated:
                runtime_data.session_ai_scheduled[session_id] = updated
            else:
                del runtime_data.session_ai_scheduled[session_id]

            persistence_manager = managers.get("persistence_manager")
            if persistence_manager:
                persistence_manager.save_persistent_data()

            task_manager = managers.get("task_manager")
            if task_manager and hasattr(task_manager, "refresh_session_timer"):
                task_manager.refresh_session_timer(session_id)

            logger.info(
                f"心念 Web API | 已取消 AI 约定任务: {session_id} "
                f"task_id={task_id or '-'} fire_time={fire_time or '-'}"
            )
            return jsonify(
                {
                    "success": True,
                    "message": t(
                        locale, "api.messages.schedule_cancelled", "已取消约定任务"
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 取消 AI 约定任务失败: {e}")
            return _internal_error_response(request_locale())

    async def get_placeholders():
        """获取占位符目录（唯一真相源，供前端速查面板渲染）"""
        try:
            return jsonify({"success": True, "groups": get_placeholder_catalog()})
        except Exception as e:
            logger.error(f"心念 Web API | 获取占位符目录失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    # ==================== 时间表（日历事项） ====================

    def _calendar_manager_missing(locale):
        return jsonify(
            {
                "success": False,
                "error": t(
                    locale,
                    "api.errors.calendar_manager_not_found",
                    "时间表管理器未找到",
                ),
            }
        ), 500

    async def get_calendar_data():
        """获取时间表数据（开关、分隔符、空文本、全部事项）"""
        try:
            locale = normalize_locale(request.args.get("locale"))
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)
            config_manager = managers.get("config_manager")
            config = (
                config_manager.config
                if config_manager and hasattr(config_manager, "config")
                else {}
            )
            calendar_conf = config.get("calendar", {})
            return jsonify(
                {
                    "success": True,
                    "enabled": bool(calendar_conf.get("enable_calendar", False)),
                    "separator": calendar_conf.get("calendar_separator", "、"),
                    "empty_text": calendar_conf.get("calendar_empty_text", ""),
                    "events": calendar_manager.get_events(),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 获取时间表数据失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    async def save_calendar_event():
        """新增或更新一条时间表事项（无 id=新增，有 id=更新）"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            event_id = str(data.get("id") or "").strip()
            if event_id:
                event = calendar_manager.update_event(event_id, data)
                if event is None:
                    return jsonify(
                        {
                            "success": False,
                            "error": t(
                                locale,
                                "api.errors.calendar_event_not_found",
                                "未找到该事项或数据不合法",
                            ),
                        }
                    ), 404
            else:
                event = calendar_manager.add_event(data)
                if event is None:
                    return jsonify(
                        {
                            "success": False,
                            "error": t(
                                locale,
                                "api.errors.calendar_event_invalid",
                                "事项数据不合法或已达数量上限",
                            ),
                        }
                    ), 400

            return jsonify(
                {
                    "success": True,
                    "event": event,
                    "message": t(
                        locale, "api.messages.calendar_event_saved", "事项已保存"
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 保存时间表事项失败: {e}")
            return _internal_error_response(request_locale())

    async def delete_calendar_event():
        """删除一条时间表事项"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            event_id = str(data.get("id") or "").strip()
            if not calendar_manager.delete_event(event_id):
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.calendar_event_not_found",
                            "未找到该事项或数据不合法",
                        ),
                    }
                ), 404
            return jsonify(
                {
                    "success": True,
                    "message": t(
                        locale, "api.messages.calendar_event_deleted", "事项已删除"
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 删除时间表事项失败: {e}")
            return _internal_error_response(request_locale())

    async def clear_calendar():
        """批量清除时间表事项（scope: all/year/month）"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            scope = str(data.get("scope") or "all").strip()
            year = _safe_int(data.get("year"))
            month = _safe_int(data.get("month"))
            removed = calendar_manager.clear(scope=scope, year=year, month=month)
            return jsonify(
                {
                    "success": True,
                    "removed": removed,
                    "message": t(
                        locale,
                        "api.messages.calendar_cleared",
                        "已清除 {count} 条事项",
                        count=removed,
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 清除时间表失败: {e}")
            return _internal_error_response(request_locale())

    async def set_calendar_enabled():
        """页内开关：写回 calendar.enable_calendar"""
        try:
            locale = request_locale()
            config_manager = managers.get("config_manager")
            if not config_manager:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_manager_not_found",
                            "配置管理器未找到",
                        ),
                    }
                ), 500

            data = await request.get_json() or {}
            enabled = bool(data.get("enabled", False))
            config = config_manager.config if hasattr(config_manager, "config") else {}
            config.setdefault("calendar", {})["enable_calendar"] = enabled
            if not config_manager.save_config_safely():
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500
            return jsonify(
                {
                    "success": True,
                    "enabled": enabled,
                    "message": t(
                        locale,
                        "api.messages.calendar_enabled_updated",
                        "时间表开关已更新",
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 更新时间表开关失败: {e}")
            return _internal_error_response(request_locale())

    async def set_calendar_settings():
        """页内显示设置：写回 calendar.calendar_separator / calendar_empty_text"""
        try:
            locale = request_locale()
            config_manager = managers.get("config_manager")
            if not config_manager:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_manager_not_found",
                            "配置管理器未找到",
                        ),
                    }
                ), 500

            data = await request.get_json() or {}
            config = config_manager.config if hasattr(config_manager, "config") else {}
            calendar_conf = config.setdefault("calendar", {})
            if "separator" in data:
                calendar_conf["calendar_separator"] = str(data.get("separator") or "")
            if "empty_text" in data:
                calendar_conf["calendar_empty_text"] = str(data.get("empty_text") or "")
            if not config_manager.save_config_safely():
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500
            return jsonify(
                {
                    "success": True,
                    "separator": calendar_conf.get("calendar_separator", "、"),
                    "empty_text": calendar_conf.get("calendar_empty_text", ""),
                    "message": t(
                        locale,
                        "api.messages.calendar_settings_updated",
                        "时间表显示设置已更新",
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 更新时间表显示设置失败: {e}")
            return _internal_error_response(request_locale())

    async def export_calendar():
        """导出时间表为 YAML 文本（供 WebUI 下载）"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)
            return jsonify(
                {
                    "success": True,
                    "content": calendar_manager.export_yaml(),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 导出时间表失败: {e}")
            return _internal_error_response(request_locale())

    async def import_calendar():
        """导入时间表事项（mode: merge/replace）

        请求体使用 ``content`` 字段携带 YAML 文本（弃用历史的 ``events`` 数组）。
        """
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            content = data.get("content")
            mode = str(data.get("mode") or "merge").strip()
            events = calendar_manager.parse_import_content(content)
            if events is None:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.calendar_import_invalid",
                            "导入数据不合法（应为合法的 YAML 时间表文件）",
                        ),
                    }
                ), 400
            imported = calendar_manager.import_events(events, mode=mode)
            if imported < 0:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500
            return jsonify(
                {
                    "success": True,
                    "imported": imported,
                    "events": calendar_manager.get_events(),
                    "message": t(
                        locale,
                        "api.messages.calendar_imported",
                        "已导入 {count} 条事项",
                        count=imported,
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 导入时间表失败: {e}")
            return _internal_error_response(request_locale())

    # ==================== 时间表 · AI 生成 ====================

    def _calendar_ai_config():
        """读取时间表 AI 生成相关配置，返回 (provider_id, prompt)。"""
        config_manager = managers.get("config_manager")
        config = (
            config_manager.config
            if config_manager and hasattr(config_manager, "config")
            else {}
        )
        calendar_conf = config.get("calendar", {}) if isinstance(config, dict) else {}
        provider_id = str(
            calendar_conf.get("ai_generate_provider_id", "") or ""
        ).strip()
        prompt = str(calendar_conf.get("ai_generate_prompt", "") or "").strip()
        return provider_id, prompt

    def _list_providers():
        """列出可用的文本生成提供商，供 WebUI 下拉选择。"""
        providers = []
        try:
            for provider in context.get_all_providers() or []:
                try:
                    meta = provider.meta()
                    pid = getattr(meta, "id", "") or ""
                    model = getattr(meta, "model", "") or ""
                except Exception:
                    continue
                if pid:
                    providers.append({"id": pid, "model": model})
        except Exception as e:
            logger.warning(f"心念 Web API | 获取提供商列表失败: {e}")
        return providers

    async def get_calendar_ai_options():
        """返回 AI 生成时间表所需的下拉/回显数据（提供商列表、已配置模型与提示词）。"""
        try:
            locale = normalize_locale(request.args.get("locale"))
            _ = locale  # 预留：未来如需本地化错误
            provider_id, prompt = _calendar_ai_config()
            return jsonify(
                {
                    "success": True,
                    "providers": _list_providers(),
                    "provider_id": provider_id,
                    "prompt": prompt,
                    "max_events": DEFAULT_MAX_GENERATE,
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 获取 AI 生成选项失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    def _resolve_provider_id(requested: str, configured: str) -> str:
        """解析最终使用的 provider_id：请求 > 配置 > 当前主模型。"""
        requested = str(requested or "").strip()
        if requested:
            return requested
        if configured:
            return configured
        try:
            using = context.get_using_provider()
            if using is not None:
                return getattr(using.meta(), "id", "") or ""
        except Exception as e:
            logger.debug(f"心念 Web API | 获取当前主模型失败: {e}")
        return ""

    async def generate_calendar():
        """根据主题提示词调用 LLM 生成时间表事项（仅预览，不落盘）。"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            user_prompt = str(data.get("user_prompt") or "").strip()
            if not user_prompt:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.calendar_ai_prompt_empty",
                            "请输入主题提示词",
                        ),
                    }
                ), 400

            configured_provider, base_prompt = _calendar_ai_config()
            provider_id = _resolve_provider_id(
                data.get("provider_id"), configured_provider
            )

            config_manager = managers.get("config_manager")
            config = (
                config_manager.config
                if config_manager and hasattr(config_manager, "config")
                else {}
            )
            current_year = get_now(config, _get_astrbot_config(managers)).year
            system_prompt = build_system_prompt(
                base_prompt, current_year, DEFAULT_MAX_GENERATE
            )

            raw_events = await generate_calendar_events(
                context,
                provider_id=provider_id,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                current_year=current_year,
                max_events=DEFAULT_MAX_GENERATE,
            )
            if raw_events is None:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.calendar_ai_generate_failed",
                            "AI 生成失败，请检查模型配置或稍后重试",
                        ),
                    }
                ), 502

            # 经 normalize_event 校验，仅返回合法事项（预览，不落盘）
            events = []
            for raw in raw_events:
                event = calendar_manager.normalize_event(raw)
                if event is not None:
                    events.append(event)

            return jsonify(
                {
                    "success": True,
                    "events": events,
                    "message": t(
                        locale,
                        "api.messages.calendar_ai_generated",
                        "已生成 {count} 条事项",
                        count=len(events),
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | AI 生成时间表失败: {e}")
            return _internal_error_response(request_locale())

    async def apply_calendar_ai():
        """将 AI 生成的事项应用到时间表（mode: merge/replace）。"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            events = data.get("events")
            mode = str(data.get("mode") or "merge").strip()
            if not isinstance(events, list) or not events:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.calendar_ai_no_events",
                            "没有可应用的事项",
                        ),
                    }
                ), 400

            imported = calendar_manager.import_events(events, mode=mode)
            if imported < 0:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500

            return jsonify(
                {
                    "success": True,
                    "imported": imported,
                    "events": calendar_manager.get_events(),
                    "message": t(
                        locale,
                        "api.messages.calendar_ai_applied",
                        "已应用 {count} 条事项",
                        count=imported,
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 应用 AI 时间表失败: {e}")
            return _internal_error_response(request_locale())

    # ==================== 配置文件（可视化编辑） ====================

    async def get_config_schema():
        """返回配置分组结构 + 当前值（供 WebUI 配置页渲染）。"""
        try:
            locale = normalize_locale(request.args.get("locale"))
            config_manager = managers.get("config_manager")
            config = (
                config_manager.config
                if config_manager and hasattr(config_manager, "config")
                else {}
            )
            schema = _get_conf_schema()
            groups = build_config_schema(
                schema,
                config,
                providers=_list_providers(),
                translate=lambda key, fallback="": t(locale, key, fallback),
            )
            return jsonify({"success": True, "groups": groups})
        except Exception as e:
            logger.error(f"心念 Web API | 获取配置 schema 失败: {e}")
            return _internal_error_response(
                normalize_locale(request.args.get("locale"))
            )

    async def save_config():
        """保存某个配置分组的字段值。

        请求体：``{"section": "basic_settings", "values": {...}}``
        """
        try:
            locale = request_locale()
            config_manager = managers.get("config_manager")
            if not config_manager:
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_manager_not_found",
                            "配置管理器未找到",
                        ),
                    }
                ), 500

            data = await request.get_json() or {}
            section = str(data.get("section") or "").strip()
            raw_values = data.get("values")

            schema = _get_conf_schema()
            section_def = schema.get(section) if isinstance(schema, dict) else None
            if not section or not isinstance(section_def, dict):
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_section_invalid",
                            "配置分组不存在",
                        ),
                    }
                ), 400

            cleaned, errors = coerce_section_values(section_def, raw_values)
            if errors:
                bad_keys = ", ".join(item["key"] for item in errors)
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.config_value_invalid",
                            "以下配置项的值无效：{keys}",
                            keys=bad_keys,
                        ),
                        "errors": errors,
                    }
                ), 400

            config = config_manager.config if hasattr(config_manager, "config") else {}
            target = config.setdefault(section, {})
            for key, value in cleaned.items():
                target[key] = value

            if not config_manager.save_config_safely():
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale, "api.errors.config_save_failed", "配置保存失败"
                        ),
                    }
                ), 500

            logger.info(f"心念 Web API | 已更新配置分组 {section}（{len(cleaned)} 项）")
            return jsonify(
                {
                    "success": True,
                    "section": section,
                    "values": cleaned,
                    "message": t(
                        locale,
                        "api.messages.config_saved",
                        "配置已保存",
                    ),
                }
            )
        except Exception as e:
            logger.error(f"心念 Web API | 保存配置失败: {e}")
            return _internal_error_response(request_locale())

    context.register_web_api(
        f"/{PLUGIN_NAME}/dashboard/stats",
        get_dashboard_stats,
        ["GET"],
        "获取仪表板统计信息",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/config/schema",
        get_config_schema,
        ["GET"],
        "获取配置分组结构与当前值",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/config/save",
        save_config,
        ["POST"],
        "保存配置分组",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/placeholders/list",
        get_placeholders,
        ["GET"],
        "获取占位符目录",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/sessions/list",
        get_sessions_list,
        ["GET"],
        "获取会话列表",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/sessions/add",
        add_session,
        ["POST"],
        "添加会话",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/sessions/remove",
        remove_session,
        ["POST"],
        "移除会话",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/ai-schedules/list",
        get_ai_schedules,
        ["GET"],
        "获取 AI 约定任务列表",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/ai-schedules/cancel",
        cancel_ai_schedule,
        ["POST"],
        "取消 AI 约定任务",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/data",
        get_calendar_data,
        ["GET"],
        "获取时间表数据",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/event/save",
        save_calendar_event,
        ["POST"],
        "保存时间表事项",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/event/delete",
        delete_calendar_event,
        ["POST"],
        "删除时间表事项",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/clear",
        clear_calendar,
        ["POST"],
        "清除时间表事项",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/enabled",
        set_calendar_enabled,
        ["POST"],
        "更新时间表开关",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/settings",
        set_calendar_settings,
        ["POST"],
        "更新时间表显示设置",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/export",
        export_calendar,
        ["GET"],
        "导出时间表事项",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/import",
        import_calendar,
        ["POST"],
        "导入时间表事项",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/ai/options",
        get_calendar_ai_options,
        ["GET"],
        "获取 AI 生成时间表选项",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/ai/generate",
        generate_calendar,
        ["POST"],
        "AI 生成时间表（预览）",
    )
    context.register_web_api(
        f"/{PLUGIN_NAME}/calendar/ai/apply",
        apply_calendar_ai,
        ["POST"],
        "应用 AI 生成的时间表事项",
    )

    logger.info("心念 Web API | 所有 API 已注册")


def _safe_int(value):
    """将输入安全转为 int，失败返回 None"""
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_sessions_list(config: dict) -> list:
    """从配置中安全提取会话 ID 列表"""
    sessions = config.get("proactive_reply", {}).get("sessions", [])
    result = []
    if isinstance(sessions, list):
        for s in sessions:
            if isinstance(s, dict) and "session_id" in s:
                result.append(s["session_id"])
            elif isinstance(s, str) and s.strip():
                result.append(s.strip())
    return result


def _get_astrbot_config(managers: dict):
    """从 managers 中安全获取 AstrBot 全局配置"""
    try:
        mgr = managers.get("conversation_manager") or managers.get("user_info_manager")
        if mgr and hasattr(mgr, "context") and mgr.context:
            return mgr.context.get_config()
    except Exception:
        pass
    return None


def _build_dashboard_stats(managers: dict, locale: str = "zh-CN") -> dict:
    """构建仪表板统计数据"""
    config_manager = managers.get("config_manager")
    config = (
        config_manager.config
        if config_manager and hasattr(config_manager, "config")
        else {}
    )
    astrbot_config = _get_astrbot_config(managers)

    sessions = _safe_sessions_list(config)

    task_manager = managers.get("task_manager")
    proactive_running = False
    ai_schedules_count = 0
    if task_manager:
        proactive_task = getattr(task_manager, "proactive_task", None)
        proactive_running = (
            proactive_task is not None and not proactive_task.done()
            if proactive_task
            else False
        )
        for tasks in runtime_data.session_ai_scheduled.values():
            if isinstance(tasks, list):
                ai_schedules_count += len(tasks)
            elif isinstance(tasks, dict):
                ai_schedules_count += 1

    return {
        "session_count": len(sessions),
        "user_count": len(runtime_data.session_user_info),
        "ai_schedules_count": ai_schedules_count,
        "proactive_running": proactive_running,
        "proactive_enabled": config.get("proactive_reply", {}).get("enabled", False),
        "ai_schedule_enabled": config.get("ai_schedule", {}).get("enabled", False),
        "recent_activities": _build_recent_activities(config, astrbot_config, locale),
    }


def _build_recent_activities(
    config: dict, astrbot_config, locale: str = "zh-CN"
) -> list:
    """构建最近活动时间线（最多10条，按时间倒序）"""
    now = get_now(config, astrbot_config).replace(tzinfo=None)
    activities = []

    for session, time_str in runtime_data.last_sent_times.items():
        try:
            sent_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            user_info = runtime_data.session_user_info.get(session, {})
            username = user_info.get("username", "")
            if username:
                title = t(
                    locale,
                    "api.activity.proactive_send_user",
                    "向 {username} 发送了主动消息",
                    username=username,
                )
            else:
                title = t(
                    locale,
                    "api.activity.proactive_send_session",
                    "向会话发送了主动消息",
                )
            activities.append(
                {
                    "type": "send",
                    "icon": "send",
                    "color": "success",
                    "title": title,
                    "desc": _truncate_session(session),
                    "time": time_str,
                    "sort_key": sent_time,
                }
            )
        except ValueError:
            continue

    for session, tasks in runtime_data.session_ai_scheduled.items():
        task_list = (
            tasks
            if isinstance(tasks, list)
            else [tasks]
            if isinstance(tasks, dict)
            else []
        )
        for task in task_list:
            created_at = task.get("created_at", "")
            fire_time = task.get("fire_time", "")
            if created_at:
                try:
                    created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                    activities.append(
                        {
                            "type": "schedule",
                            "icon": "robot",
                            "color": "warning",
                            "title": t(
                                locale,
                                "api.activity.schedule_created",
                                "AI 调度了新任务",
                            ),
                            "desc": t(
                                locale,
                                "api.activity.schedule_desc",
                                "计划于 {fire_time} 发送 · {session}",
                                fire_time=fire_time,
                                session=_truncate_session(session),
                            ),
                            "time": created_at,
                            "sort_key": created,
                        }
                    )
                except ValueError:
                    continue

    for session, info in runtime_data.session_user_info.items():
        last_active = info.get("last_active_time", "")
        username = info.get(
            "username",
            t(locale, "api.activity.unknown_user", "未知用户"),
        )
        if last_active:
            try:
                active_time = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
                activities.append(
                    {
                        "type": "user_active",
                        "icon": "user",
                        "color": "info",
                        "title": t(
                            locale,
                            "api.activity.user_active",
                            "{username} 最后活跃",
                            username=username,
                        ),
                        "desc": _truncate_session(session),
                        "time": last_active,
                        "sort_key": active_time,
                    }
                )
            except ValueError:
                continue

    activities.sort(key=lambda x: x["sort_key"], reverse=True)
    activities = activities[:10]

    for activity in activities:
        activity["time_display"] = _format_relative_time(
            activity.pop("sort_key"), now, locale
        )

    return activities


def _truncate_session(session_id: str) -> str:
    """截断会话 ID 以便展示"""
    parts = session_id.split(":")
    if len(parts) >= 3:
        platform = parts[0]
        chat_type = parts[1]
        raw_id = ":".join(parts[2:])
        if len(raw_id) > 12:
            raw_id = raw_id[:12] + "…"
        return f"{platform}:{chat_type}:{raw_id}"
    if len(session_id) > 30:
        return session_id[:30] + "…"
    return session_id


def _format_relative_time(dt: datetime, now: datetime, locale: str = "zh-CN") -> str:
    """格式化为相对时间描述"""
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 0:
        future = abs(seconds)
        if future < 60:
            return t(locale, "api.time.soon", "即将")
        if future < 3600:
            return t(
                locale,
                "api.time.in_minutes",
                "{n} 分钟后",
                n=future // 60,
            )
        if future < 86400:
            return t(
                locale,
                "api.time.in_hours",
                "{n} 小时后",
                n=future // 3600,
            )
        return dt.strftime("%m-%d %H:%M")

    if seconds < 60:
        return t(locale, "api.time.just_now", "刚刚")
    if seconds < 3600:
        return t(
            locale,
            "api.time.minutes_ago",
            "{n} 分钟前",
            n=seconds // 60,
        )
    if seconds < 86400:
        return t(
            locale,
            "api.time.hours_ago",
            "{n} 小时前",
            n=seconds // 3600,
        )
    if seconds < 172800:
        return t(locale, "api.time.yesterday", "昨天")
    return dt.strftime("%m-%d %H:%M")


def _build_sessions_data(managers: dict, locale: str = "zh-CN") -> list:
    """构建会话列表数据"""
    config_manager = managers.get("config_manager")
    if not config_manager:
        return []

    config = config_manager.config if hasattr(config_manager, "config") else {}
    astrbot_config = _get_astrbot_config(managers)
    now = get_now(config, astrbot_config).replace(tzinfo=None)

    sessions = []
    for session_id in _safe_sessions_list(config):
        session = _build_session_entry(session_id, now, locale)
        sessions.append(session)

    return sessions


def _build_ai_schedules_data(now: datetime, locale: str = "zh-CN") -> list:
    """构建所有 AI 约定任务列表（按执行时间升序）"""
    schedules = []
    for session_id, tasks in runtime_data.session_ai_scheduled.items():
        task_list = (
            tasks
            if isinstance(tasks, list)
            else [tasks]
            if isinstance(tasks, dict)
            else []
        )
        parts = session_id.split(":")
        platform = parts[0] if len(parts) >= 3 else "unknown"

        for task in task_list:
            fire_time = task.get("fire_time", "")
            created_at = task.get("created_at", "")
            follow_up_prompt = task.get("follow_up_prompt", "")

            time_display = "—"
            fire_soon = False
            if fire_time:
                try:
                    ft = datetime.strptime(fire_time, "%Y-%m-%d %H:%M:%S")
                    delta = ft - now
                    total_seconds = int(delta.total_seconds())
                    if total_seconds <= 60:
                        time_display = t(locale, "api.time.soon", "即将")
                        fire_soon = True
                    elif total_seconds < 3600:
                        time_display = t(
                            locale,
                            "api.time.in_minutes",
                            "{n} 分钟后",
                            n=total_seconds // 60,
                        )
                    elif total_seconds < 86400:
                        time_display = t(
                            locale,
                            "api.time.in_hours",
                            "{n} 小时后",
                            n=total_seconds // 3600,
                        )
                    else:
                        time_display = fire_time
                except ValueError:
                    time_display = fire_time

            schedules.append(
                {
                    "session_id": session_id,
                    "platform": platform,
                    "task_id": task.get("task_id", ""),
                    "fire_time": fire_time,
                    "created_at": created_at,
                    "follow_up_prompt": follow_up_prompt,
                    "time_display": time_display,
                    "fire_soon": fire_soon,
                }
            )

    schedules.sort(key=lambda x: x["fire_time"] or "9999-99-99")
    return schedules


def _build_session_entry(session_id: str, now: datetime, locale: str = "zh-CN") -> dict:
    """构建单个会话条目的数据"""
    parts = session_id.split(":")
    entry = {
        "session_id": session_id,
        "platform": parts[0] if len(parts) >= 3 else "unknown",
        "chat_type": parts[1] if len(parts) >= 3 else "unknown",
        "raw_id": ":".join(parts[2:]) if len(parts) >= 3 else session_id,
    }

    next_fire_str = runtime_data.session_next_fire_times.get(session_id, "")
    if next_fire_str:
        try:
            next_fire = datetime.strptime(next_fire_str, "%Y-%m-%d %H:%M:%S")
            delta = next_fire - now
            total_minutes = int(delta.total_seconds() / 60)
            if total_minutes <= 0:
                entry["next_fire_soon"] = True
                entry["next_fire_display"] = t(
                    locale, "api.session.next_soon", "即将发送"
                )
            elif total_minutes < 60:
                entry["next_fire_soon"] = False
                entry["next_fire_display"] = t(
                    locale,
                    "api.session.next_in_minutes",
                    "{n} 分钟后",
                    n=total_minutes,
                )
            else:
                entry["next_fire_soon"] = False
                hours = total_minutes // 60
                minutes = total_minutes % 60
                entry["next_fire_display"] = t(
                    locale,
                    "api.session.next_in_hours_minutes",
                    "{hours} 小时 {minutes} 分钟后",
                    hours=hours,
                    minutes=minutes,
                )
        except ValueError:
            entry["next_fire_soon"] = False
            entry["next_fire_display"] = "—"
    else:
        entry["next_fire_soon"] = False
        entry["next_fire_display"] = t(locale, "api.session.waiting_init", "等待初始化")

    last_sent = runtime_data.last_sent_times.get(session_id, "")
    entry["last_sent_time"] = last_sent or "—"

    entry["unreplied_count"] = runtime_data.session_unreplied_count.get(session_id, 0)
    entry["consecutive_failures"] = runtime_data.session_consecutive_failures.get(
        session_id, 0
    )
    entry["last_proactive_message"] = runtime_data.session_last_proactive_message.get(
        session_id, ""
    )

    user_info = runtime_data.session_user_info.get(session_id, {})
    entry["username"] = user_info.get("username", "")
    entry["user_last_active"] = user_info.get("last_active_time", "")

    ai_tasks = runtime_data.session_ai_scheduled.get(session_id, [])
    if isinstance(ai_tasks, list):
        entry["ai_task_count"] = len(ai_tasks)
    elif isinstance(ai_tasks, dict):
        entry["ai_task_count"] = 1
    else:
        entry["ai_task_count"] = 0

    if next_fire_str:
        entry["status"] = "active"
        entry["status_display"] = t(locale, "api.session.status_active", "活跃")
    else:
        entry["status"] = "inactive"
        entry["status_display"] = t(locale, "api.session.status_waiting", "等待中")

    return entry
