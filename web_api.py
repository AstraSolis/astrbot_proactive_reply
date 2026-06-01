"""
插件 Web API

向 AstrBot 注册所有插件 REST API，供 Plugin Pages 调用
"""

from datetime import datetime

from quart import jsonify, request

from astrbot.api import logger

from .core.runtime_data import runtime_data
from .llm.placeholder_utils import get_placeholder_catalog
from .utils.plugin_i18n import normalize_locale, request_locale, t
from .utils.time_utils import get_now

PLUGIN_NAME = "astrbot_proactive_reply"


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
            time_awareness = config.get("time_awareness", {})
            return jsonify(
                {
                    "success": True,
                    "enabled": bool(time_awareness.get("enable_calendar", False)),
                    "separator": time_awareness.get("calendar_separator", "、"),
                    "empty_text": time_awareness.get("calendar_empty_text", ""),
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
        """页内开关：写回 time_awareness.enable_calendar"""
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
            config.setdefault("time_awareness", {})["enable_calendar"] = enabled
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

    async def import_calendar():
        """导入时间表事项（mode: merge/replace）"""
        try:
            locale = request_locale()
            calendar_manager = managers.get("calendar_manager")
            if not calendar_manager:
                return _calendar_manager_missing(locale)

            data = await request.get_json() or {}
            events = data.get("events")
            mode = str(data.get("mode") or "merge").strip()
            if not isinstance(events, list):
                return jsonify(
                    {
                        "success": False,
                        "error": t(
                            locale,
                            "api.errors.calendar_import_invalid",
                            "导入数据不合法（应为事项数组）",
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

    context.register_web_api(
        f"/{PLUGIN_NAME}/dashboard/stats",
        get_dashboard_stats,
        ["GET"],
        "获取仪表板统计信息",
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
        f"/{PLUGIN_NAME}/calendar/import",
        import_calendar,
        ["POST"],
        "导入时间表事项",
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
