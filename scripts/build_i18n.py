"""生成 .astrbot-plugin/i18n 语言包。

运行: python scripts/build_i18n.py
输出: zh-CN.json / en-US.json（请勿手改 JSON，应改本脚本后重新生成）
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".astrbot-plugin" / "i18n"


def _flatten_config_items(cfg: dict) -> dict:
    """object 类型配置：i18n 中子字段直接嵌套，不能使用 _conf_schema 的 items 键。"""
    out: dict = {}
    for name, block in cfg.items():
        if not isinstance(block, dict):
            out[name] = block
            continue
        flat: dict = {}
        for key, value in block.items():
            if key == "items" and isinstance(value, dict):
                for item_key, item_val in value.items():
                    flat[item_key] = item_val
            else:
                flat[key] = value
        out[name] = flat
    return out


def main() -> None:
    zh = _zh_bundle()
    en = _en_bundle()
    zh["config"] = _flatten_config_items(zh["config"])
    en["config"] = _flatten_config_items(en["config"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "zh-CN.json").write_text(
        json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "en-US.json").write_text(
        json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {OUT / 'zh-CN.json'} and {OUT / 'en-US.json'}")


def _zh_bundle() -> dict:
    return {
        "metadata": {
            "display_name": "心念",
            "short_desc": "聊天增强、时间感知与智能主动对话。",
            "desc": "一个支持聊天增强、时间感知和智能主动对话的 AstrBot 插件。",
        },
        "config": _zh_config(),
        "pages": {"webui": _zh_pages()},
        "api": _zh_api(),
    }


def _en_bundle() -> dict:
    return {
        "metadata": {
            "display_name": "Proactive Mind",
            "short_desc": "Chat enhancement, time awareness, and smart proactive messaging.",
            "desc": "An AstrBot plugin with chat enhancement, time awareness, and intelligent proactive conversations.",
        },
        "config": _en_config(),
        "pages": {"webui": _en_pages()},
        "api": _en_api(),
    }


def _zh_pages() -> dict:
    return {
        "title": "心念管理",
        "description": "概览与会话管理",
        "heading": "心念",
        "aria_main_nav": "主导航",
        "aria_menu_toggle": "打开菜单",
        "sidebar_role": "主动回复管理",
        "sidebar_build": "心念 WebUI",
        "nav_section_main": "主菜单",
        "tab_dashboard": "概览",
        "tab_sessions": "会话",
        "section_today": "今天",
        "section_recent": "近期概览",
        "btn_refresh": "刷新",
        "btn_add_session": "添加会话",
        "search_sessions": "搜索会话 ID 或用户名…",
        "search_hint_dashboard": "切换到会话页后可搜索",
        "loading": "加载中…",
        "plugin_status": "当前状态",
        "recent_activity": "最近记录",
        "stat_total_sessions": "总会话",
        "stat_active": "活跃",
        "stat_inactive": "安静",
        "session_list": "会话列表",
        "dialog_add_title": "添加主动会话",
        "label_session_id": "会话 ID",
        "session_id_placeholder": "例如：aiocqhttp:GroupMessage:123456789",
        "session_id_format_hint": "格式：",
        "session_id_example": "示例：",
        "btn_cancel": "取消",
        "btn_add": "添加",
        "btn_adding": "添加中…",
        "btn_add_first": "添加第一个会话",
        "stat_session_count": "总会话数",
        "stat_ai_schedules": "计划任务",
        "stat_users": "记录用户",
        "stat_run_status": "运行状态",
        "status_running": "运行中",
        "status_stopped": "已停止",
        "label_plugin_name": "插件名称",
        "label_feature_status": "功能状态",
        "tag_proactive": "主动消息",
        "tag_ai_schedule": "计划任务",
        "tag_timer": "定时任务",
        "empty_activity_title": "暂无活动记录",
        "empty_activity_desc": "当插件开始工作后，活动记录将在此显示",
        "empty_sessions_title": "还没有主动会话",
        "empty_sessions_desc": "点击顶部 + 添加，或在聊天中使用",
        "empty_search_title": "未找到匹配会话",
        "empty_search_desc": "请尝试其他关键词",
        "load_sessions_failed": "加载失败，请切换页面后重试",
        "th_session_id": "会话 ID",
        "th_platform": "平台",
        "th_user": "用户",
        "th_next_send": "下次发送",
        "th_last_send": "最后发送",
        "th_unreplied": "未回复",
        "th_status": "状态",
        "th_actions": "操作",
        "remove_title": "移除",
        "platform_wechat": "微信",
        "badge_ai_tasks": "计划 ×{count}",
        "err_unknown": "未知错误",
        "err_dashboard_load": "概览加载失败：",
        "err_sessions_load": "会话列表加载失败：",
        "err_bridge_missing": "WebUI 桥接环境未就绪，请从 AstrBot 插件页面打开。",
        "toast_enter_session_id": "请输入会话 ID",
        "toast_invalid_format": "格式不正确，应为 platform:type:id",
        "toast_add_failed": "添加失败",
        "toast_session_added": "会话已添加",
        "toast_remove_failed": "移除失败",
        "toast_session_removed": "会话已移除",
        "confirm_remove": '确定要移除会话 "{session_id}" 吗？',
        "tab_schedules": "AI 约定",
        "schedule_list": "约定任务列表",
        "btn_close": "关闭",
        "search_hint_schedules": "此页面不支持搜索",
        "empty_schedules_title": "暂无 AI 约定任务",
        "empty_schedules_desc": "当 AI 在对话中约定了具体时间，任务会自动出现在此处",
        "load_schedules_failed": "加载失败，请刷新重试",
        "err_schedules_load": "约定任务加载失败：",
        "th_session": "会话",
        "th_time_left": "倒计时",
        "th_fire_time": "执行时间",
        "th_prompt": "触发提示词",
        "th_created": "创建时间",
        "cancel_title": "取消",
        "confirm_cancel_schedule": "确定要取消这个约定任务吗？",
        "toast_cancel_failed": "取消失败",
        "toast_schedule_cancelled": "约定任务已取消",
        "detail_title": "会话详情",
        "detail_basic_info": "基本信息",
        "detail_run_status": "运行状态",
        "detail_last_send": "最后发送",
        "label_failures": "连续失败",
        "label_failure_count": "次失败",
        "label_ai_tasks": "AI 约定",
        "label_task_unit": "个",
        "label_last_message": "消息内容",
        "no_message_preview": "暂无记录",
        "prompt_detail_title": "触发提示词",
        "prompt_full_content": "完整内容",
    }


def _en_pages() -> dict:
    return {
        "title": "Proactive Mind",
        "description": "Overview and session management",
        "heading": "Proactive Mind",
        "aria_main_nav": "Main navigation",
        "aria_menu_toggle": "Open menu",
        "sidebar_role": "Proactive reply management",
        "sidebar_build": "Proactive Mind WebUI",
        "nav_section_main": "Main menu",
        "tab_dashboard": "Overview",
        "tab_sessions": "Sessions",
        "section_today": "Today",
        "section_recent": "Recent overview",
        "btn_refresh": "Refresh",
        "btn_add_session": "Add session",
        "search_sessions": "Search session ID or username…",
        "search_hint_dashboard": "Switch to Sessions to search",
        "loading": "Loading…",
        "plugin_status": "Current state",
        "recent_activity": "Recent notes",
        "stat_total_sessions": "Total sessions",
        "stat_active": "Active",
        "stat_inactive": "Quiet",
        "session_list": "Sessions",
        "dialog_add_title": "Add proactive session",
        "label_session_id": "Session ID",
        "session_id_placeholder": "e.g. aiocqhttp:GroupMessage:123456789",
        "session_id_format_hint": "Format:",
        "session_id_example": "Example:",
        "btn_cancel": "Cancel",
        "btn_add": "Add",
        "btn_adding": "Adding…",
        "btn_add_first": "Add first session",
        "stat_session_count": "Total sessions",
        "stat_ai_schedules": "Planned tasks",
        "stat_users": "Users tracked",
        "stat_run_status": "Run status",
        "status_running": "Running",
        "status_stopped": "Stopped",
        "label_plugin_name": "Plugin name",
        "label_feature_status": "Features",
        "tag_proactive": "Proactive",
        "tag_ai_schedule": "Planned tasks",
        "tag_timer": "Timer",
        "empty_activity_title": "No activity yet",
        "empty_activity_desc": "Activity will appear here once the plugin starts working",
        "empty_sessions_title": "No proactive sessions yet",
        "empty_sessions_desc": "Use the + button above, or run in chat",
        "empty_search_title": "No matching sessions",
        "empty_search_desc": "Try a different keyword",
        "load_sessions_failed": "Load failed — switch views and try again",
        "th_session_id": "Session ID",
        "th_platform": "Platform",
        "th_user": "User",
        "th_next_send": "Next send",
        "th_last_send": "Last sent",
        "th_unreplied": "Unreplied",
        "th_status": "Status",
        "th_actions": "Actions",
        "remove_title": "Remove",
        "platform_wechat": "WeChat",
        "badge_ai_tasks": "Tasks ×{count}",
        "err_unknown": "Unknown error",
        "err_dashboard_load": "Failed to load overview:",
        "err_sessions_load": "Failed to load sessions:",
        "err_bridge_missing": "WebUI bridge is not ready. Open this page from AstrBot plugin pages.",
        "toast_enter_session_id": "Please enter a session ID",
        "toast_invalid_format": "Invalid format — use platform:type:id",
        "toast_add_failed": "Add failed",
        "toast_session_added": "Session added",
        "toast_remove_failed": "Remove failed",
        "toast_session_removed": "Session removed",
        "confirm_remove": 'Remove session "{session_id}"?',
        "tab_schedules": "AI Tasks",
        "schedule_list": "Scheduled tasks",
        "btn_close": "Close",
        "search_hint_schedules": "Search not available on this page",
        "empty_schedules_title": "No AI scheduled tasks",
        "empty_schedules_desc": "When AI makes a time commitment in chat, the task will appear here automatically",
        "load_schedules_failed": "Load failed — please refresh",
        "err_schedules_load": "Failed to load scheduled tasks: ",
        "th_session": "Session",
        "th_time_left": "Countdown",
        "th_fire_time": "Fire time",
        "th_prompt": "Trigger prompt",
        "th_created": "Created",
        "cancel_title": "Cancel",
        "confirm_cancel_schedule": "Cancel this scheduled task?",
        "toast_cancel_failed": "Cancel failed",
        "toast_schedule_cancelled": "Scheduled task cancelled",
        "detail_title": "Session details",
        "detail_basic_info": "Basic info",
        "detail_run_status": "Status",
        "detail_last_send": "Last sent",
        "label_failures": "Consecutive failures",
        "label_failure_count": "failures",
        "label_ai_tasks": "AI tasks",
        "label_task_unit": "",
        "label_last_message": "Message content",
        "no_message_preview": "No record",
        "prompt_detail_title": "Trigger prompt",
        "prompt_full_content": "Full content",
    }


def _zh_api() -> dict:
    return {
        "errors": {
            "config_manager_not_found": "配置管理器未找到",
            "session_id_empty": "会话 ID 不能为空",
            "session_id_invalid": "会话 ID 格式不正确，应为 platform:type:id",
            "session_exists": "该会话已存在",
            "config_save_failed": "配置保存失败",
            "session_not_found": "未找到该会话",
            "schedule_not_found": "未找到该约定任务",
            "internal_error": "服务器内部错误，请稍后重试",
            "add_failed": "添加失败",
            "remove_failed": "移除失败",
        },
        "messages": {
            "session_added": "已添加会话: {session_id}",
            "session_removed": "已移除会话: {session_id}",
            "schedule_cancelled": "已取消约定任务",
        },
        "activity": {
            "proactive_send_user": "向 {username} 发送了主动消息",
            "proactive_send_session": "向会话发送了主动消息",
            "schedule_created": "AI 调度了新任务",
            "schedule_desc": "计划于 {fire_time} 发送 · {session}",
            "user_active": "{username} 最后活跃",
            "unknown_user": "未知用户",
        },
        "time": {
            "soon": "即将",
            "in_minutes": "{n} 分钟后",
            "in_hours": "{n} 小时后",
            "just_now": "刚刚",
            "minutes_ago": "{n} 分钟前",
            "hours_ago": "{n} 小时前",
            "yesterday": "昨天",
        },
        "session": {
            "next_soon": "即将发送",
            "next_in_minutes": "{n} 分钟后",
            "next_in_hours_minutes": "{hours} 小时 {minutes} 分钟后",
            "waiting_init": "等待初始化",
            "status_active": "活跃",
            "status_waiting": "等待中",
        },
    }


def _en_api() -> dict:
    return {
        "errors": {
            "config_manager_not_found": "Config manager not found",
            "session_id_empty": "Session ID cannot be empty",
            "session_id_invalid": "Invalid session ID — use platform:type:id",
            "session_exists": "Session already exists",
            "config_save_failed": "Failed to save config",
            "session_not_found": "Session not found",
            "schedule_not_found": "Scheduled task not found",
            "internal_error": "Internal server error. Please try again later.",
            "add_failed": "Add failed",
            "remove_failed": "Remove failed",
        },
        "messages": {
            "session_added": "Session added: {session_id}",
            "session_removed": "Session removed: {session_id}",
            "schedule_cancelled": "Scheduled task cancelled",
        },
        "activity": {
            "proactive_send_user": "Sent proactive message to {username}",
            "proactive_send_session": "Sent proactive message to session",
            "schedule_created": "AI scheduled a new task",
            "schedule_desc": "Planned at {fire_time} · {session}",
            "user_active": "{username} last active",
            "unknown_user": "Unknown user",
        },
        "time": {
            "soon": "Soon",
            "in_minutes": "in {n} min",
            "in_hours": "in {n} h",
            "just_now": "Just now",
            "minutes_ago": "{n} min ago",
            "hours_ago": "{n} h ago",
            "yesterday": "Yesterday",
        },
        "session": {
            "next_soon": "Sending soon",
            "next_in_minutes": "in {n} min",
            "next_in_hours_minutes": "in {hours} h {minutes} min",
            "waiting_init": "Waiting to initialize",
            "status_active": "Active",
            "status_waiting": "Waiting",
        },
    }


def _zh_config() -> dict:
    return {
        "support_author": {
            "description": "⭐ 支持作者",
            "items": {
                "github_link": {
                    "description": "GitHub 仓库地址",
                    "hint": "如果这个插件对你有帮助，欢迎访问链接给个 Star ⭐，您的支持是我持续更新的动力！",
                }
            },
        },
        "basic_settings": {
            "description": "基础设置",
            "items": {
                "timezone": {
                    "description": "时区",
                    "hint": "IANA 时区名称，如 Asia/Shanghai。留空使用系统本地时区。启用「跟随 AstrBot 时区」后此项将被忽略",
                },
                "use_astrbot_timezone": {
                    "description": "跟随 AstrBot 时区",
                    "hint": "启用后使用 AstrBot 全局时区；未配置时回退到上方时区字段",
                },
            },
        },
        "user_info": {
            "description": "聊天附带用户信息设置",
            "items": {
                "enabled": {
                    "description": "启用聊天附带用户信息",
                    "hint": "在每次 LLM 请求前将动态用户信息追加到用户消息后；固定时间规则追加到 system_prompt，睡眠提示追加到用户消息后",
                },
                "time_format": {
                    "description": "时间格式",
                    "hint": "Python datetime 格式，如 %Y-%m-%d %H:%M:%S",
                },
                "template": {
                    "description": "用户信息模板",
                    "hint": "追加到用户消息后，支持 {username}、{user_id}、{time} 等占位符",
                },
            },
        },
        "time_awareness": {
            "description": "时间感知设置",
            "items": {
                "time_guidance_enabled": {
                    "description": "启用时间感知增强提示词",
                    "hint": "用户正常聊天时追加固定时间指南到 system_prompt 末尾；主动对话使用独立提示词",
                },
                "time_guidance_prompt": {
                    "description": "时间感知增强提示词",
                    "hint": "自定义时间使用指南，支持 \\n 换行",
                },
                "sleep_mode_enabled": {
                    "description": "启用睡眠时间功能",
                    "hint": "睡眠时段内不发送主动消息，并将睡眠提示追加到用户消息后",
                },
                "sleep_hours": {
                    "description": "睡眠时间段",
                    "hint": "格式：开始-结束（24 小时制），支持跨午夜",
                },
                "sleep_prompt": {
                    "description": "睡眠时间提示内容",
                    "hint": "睡眠时段内追加到用户消息后",
                },
                "send_on_wake_enabled": {
                    "description": "睡眠结束时发送消息",
                    "hint": "睡眠结束后向满足条件的会话发送一次主动消息",
                },
                "wake_send_mode": {
                    "description": "睡眠结束发送模式",
                    "hint": "immediate=立即发送；delayed=延后发送",
                    "labels": ["立即发送", "延后发送"],
                },
            },
        },
        "proactive_reply": {
            "description": "定时主动发送消息设置",
            "items": {
                "enabled": {
                    "description": "是否启用定时主动发送消息功能",
                    "hint": "启用后插件会定时向配置的会话发送消息",
                },
                "sessions": {
                    "description": "目标会话列表",
                    "hint": "格式 platform:type:id，可用 /proactive add_session 添加",
                },
                "timing_mode": {
                    "description": "时间模式",
                    "hint": "固定间隔或完全随机间隔",
                    "labels": ["固定间隔", "随机间隔"],
                },
                "interval_minutes": {
                    "description": "定时发送间隔（分钟）",
                    "hint": "仅固定间隔模式生效",
                },
                "random_delay_enabled": {
                    "description": "是否启用随机延迟发送",
                    "hint": "仅固定间隔模式生效",
                },
                "min_random_minutes": {
                    "description": "最小随机延迟时间（分钟）",
                    "hint": "仅固定间隔模式生效",
                },
                "max_random_minutes": {
                    "description": "最大随机延迟时间（分钟）",
                    "hint": "仅固定间隔模式生效",
                },
                "random_min_minutes": {
                    "description": "随机间隔最小时间（分钟）",
                    "hint": "仅随机间隔模式生效",
                },
                "random_max_minutes": {
                    "description": "随机间隔最大时间（分钟）",
                    "hint": "仅随机间隔模式生效",
                },
                "proactive_default_persona": {
                    "description": "主动对话备用人格",
                    "hint": "仅当 AstrBot 未返回可用人格时作为备用系统提示词",
                },
                "proactive_prompt_list": {
                    "description": "主动对话提示词列表",
                    "hint": "随机选用，支持多种占位符",
                },
                "duplicate_detection_enabled": {
                    "description": "启用重复检测",
                    "hint": "与上次内容重复时自动重试（最多 3 次）",
                },
                "include_history_enabled": {
                    "description": "是否附带历史记录",
                    "hint": "生成主动消息时参考对话历史",
                },
                "history_message_count": {
                    "description": "附带的历史记录条数",
                    "hint": "建议 5–20 条",
                },
                "history_save_mode": {
                    "description": "历史记录保存模式",
                    "hint": "保存到对话历史的用户端内容",
                    "labels": ["默认触发标记", "主动对话提示词", "自定义内容"],
                },
                "custom_history_prompt": {
                    "description": "自定义历史记录提示词",
                    "hint": "仅 custom 模式生效",
                },
                "use_database_fallback": {
                    "description": "数据库回退方案状态（信息展示）",
                    "hint": "仅状态展示，修改不影响实际行为",
                },
            },
        },
        "message_split": {
            "description": "消息分割设置",
            "items": {
                "enabled": {
                    "description": "启用消息分割",
                    "hint": "按模式分割后逐条发送",
                },
                "mode": {
                    "description": "分割模式",
                    "hint": "预设或官方风格分段",
                    "labels": [
                        "反斜线",
                        "换行符",
                        "逗号",
                        "分号",
                        "多种标点",
                        "自定义正则",
                        "分段词",
                        "正则（官方）",
                    ],
                },
                "custom_pattern": {
                    "description": "自定义分割正则表达式",
                    "hint": "仅 custom 模式",
                },
                "regex": {
                    "description": "正则表达式（regex 模式）",
                    "hint": "仅 regex 模式，与官方一致",
                },
                "split_words": {
                    "description": "分段词列表（words 模式）",
                    "hint": "仅 words 模式",
                },
                "delay_ms": {
                    "description": "分割消息延迟（毫秒）",
                    "hint": "建议 300–1000 ms",
                },
            },
        },
        "ai_schedule": {
            "description": "AI 自主调度设置",
            "items": {
                "enabled": {
                    "description": "启用 AI 自主调度",
                    "hint": "分析时间约定并设置一次性任务，额外消耗 LLM 调用",
                },
                "provider_id": {
                    "description": "调度分析模型提供商（留空使用主模型）",
                    "hint": "可选用更便宜或更快的模型",
                },
                "analysis_prompt": {
                    "description": "AI 调度分析提示词",
                    "hint": "自定义分析用系统提示词",
                },
            },
        },
    }


def _en_config() -> dict:
    return {
        "support_author": {
            "description": "⭐ Support the author",
            "items": {
                "github_link": {
                    "description": "GitHub repository URL",
                    "hint": "If this plugin helps you, please star the repo!",
                }
            },
        },
        "basic_settings": {
            "description": "Basic settings",
            "items": {
                "timezone": {
                    "description": "Timezone",
                    "hint": "IANA name, e.g. Asia/Shanghai. Empty = system local. Ignored when following AstrBot timezone",
                },
                "use_astrbot_timezone": {
                    "description": "Follow AstrBot timezone",
                    "hint": "Use global AstrBot timezone; falls back to the field above if unset",
                },
            },
        },
        "user_info": {
            "description": "User context in chat",
            "items": {
                "enabled": {
                    "description": "Append user info to chat",
                    "hint": "Appends dynamic user info after the user message; fixed time guidance is added to system_prompt and sleep hints are added after the user message",
                },
                "time_format": {
                    "description": "Time format",
                    "hint": "Python datetime format, e.g. %Y-%m-%d %H:%M:%S",
                },
                "template": {
                    "description": "User info template",
                    "hint": "Appended after the user message; supports {username}, {user_id}, {time}, etc.",
                },
            },
        },
        "time_awareness": {
            "description": "Time awareness",
            "items": {
                "time_guidance_enabled": {
                    "description": "Enable time-awareness prompt",
                    "hint": "Appends fixed time guidance to the end of system_prompt in normal chat; proactive uses separate prompts",
                },
                "time_guidance_prompt": {
                    "description": "Time-awareness prompt text",
                    "hint": "Custom guidance; supports \\n",
                },
                "sleep_mode_enabled": {
                    "description": "Enable sleep hours",
                    "hint": "No proactive messages during sleep; appends the sleep hint after the user message",
                },
                "sleep_hours": {
                    "description": "Sleep time range",
                    "hint": "start-end (24h), overnight supported",
                },
                "sleep_prompt": {
                    "description": "Sleep-time prompt",
                    "hint": "Appended after the user message during sleep hours",
                },
                "send_on_wake_enabled": {
                    "description": "Send when sleep ends",
                    "hint": "One proactive message after sleep ends",
                },
                "wake_send_mode": {
                    "description": "Wake send mode",
                    "hint": "immediate or delayed",
                    "labels": ["Send immediately", "Send delayed"],
                },
            },
        },
        "proactive_reply": {
            "description": "Scheduled proactive messages",
            "items": {
                "enabled": {
                    "description": "Enable scheduled proactive messages",
                    "hint": "Sends messages to configured sessions on a schedule",
                },
                "sessions": {
                    "description": "Target sessions",
                    "hint": "platform:type:id — use /proactive add_session in chat",
                },
                "timing_mode": {
                    "description": "Timing mode",
                    "hint": "Fixed or random interval",
                    "labels": ["Fixed interval", "Random interval"],
                },
                "interval_minutes": {
                    "description": "Send interval (minutes)",
                    "hint": "Fixed-interval mode only",
                },
                "random_delay_enabled": {
                    "description": "Enable random delay",
                    "hint": "Fixed-interval mode only",
                },
                "min_random_minutes": {
                    "description": "Min random delay (minutes)",
                    "hint": "Fixed-interval mode only",
                },
                "max_random_minutes": {
                    "description": "Max random delay (minutes)",
                    "hint": "Fixed-interval mode only",
                },
                "random_min_minutes": {
                    "description": "Min random interval (minutes)",
                    "hint": "Random-interval mode only",
                },
                "random_max_minutes": {
                    "description": "Max random interval (minutes)",
                    "hint": "Random-interval mode only",
                },
                "proactive_default_persona": {
                    "description": "Fallback proactive persona",
                    "hint": "Used as a fallback system prompt only when AstrBot returns no usable persona",
                },
                "proactive_prompt_list": {
                    "description": "Proactive prompt list",
                    "hint": "Random selection; supports placeholders",
                },
                "duplicate_detection_enabled": {
                    "description": "Enable duplicate detection",
                    "hint": "Retry up to 3 times if duplicate of last message",
                },
                "include_history_enabled": {
                    "description": "Include chat history",
                    "hint": "Use recent history when generating proactive messages",
                },
                "history_message_count": {
                    "description": "History message count",
                    "hint": "Recommended 5–20",
                },
                "history_save_mode": {
                    "description": "History save mode",
                    "hint": "User-side history entry content",
                    "labels": ["Default trigger", "Proactive prompt", "Custom content"],
                },
                "custom_history_prompt": {
                    "description": "Custom history prompt",
                    "hint": "Custom mode only",
                },
                "use_database_fallback": {
                    "description": "Database fallback status (info)",
                    "hint": "Informational only",
                },
            },
        },
        "message_split": {
            "description": "Message splitting",
            "items": {
                "enabled": {
                    "description": "Enable message splitting",
                    "hint": "Send parts with delay between them",
                },
                "mode": {
                    "description": "Split mode",
                    "hint": "Preset or official-style",
                    "labels": [
                        "Backslash",
                        "Newline",
                        "Comma",
                        "Semicolon",
                        "Punctuation",
                        "Custom regex",
                        "Word list",
                        "Regex (official)",
                    ],
                },
                "custom_pattern": {
                    "description": "Custom split regex",
                    "hint": "Custom mode only",
                },
                "regex": {
                    "description": "Regex (official style)",
                    "hint": "Regex mode only",
                },
                "split_words": {
                    "description": "Split word list",
                    "hint": "Words mode only",
                },
                "delay_ms": {
                    "description": "Delay between parts (ms)",
                    "hint": "Recommended 300–1000 ms",
                },
            },
        },
        "ai_schedule": {
            "description": "AI self-scheduling",
            "items": {
                "enabled": {
                    "description": "Enable AI self-scheduling",
                    "hint": "Schedules one-shot tasks from time mentions (extra LLM call)",
                },
                "provider_id": {
                    "description": "Schedule analysis provider (empty = main)",
                    "hint": "Optional cheaper/faster model",
                },
                "analysis_prompt": {
                    "description": "Schedule analysis prompt",
                    "hint": "System prompt for analysis",
                },
            },
        },
    }


if __name__ == "__main__":
    main()
