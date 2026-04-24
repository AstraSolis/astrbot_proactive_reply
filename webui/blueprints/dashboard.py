"""
仪表板蓝图

显示插件状态概览和实时统计信息
"""

from datetime import datetime
from quart import Blueprint, render_template, current_app, jsonify
from astrbot.api import logger
from ..auth import login_required
from ...core.runtime_data import runtime_data

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
async def index():
    """仪表板主页"""
    try:
        managers = current_app.managers
        stats = await get_dashboard_stats(managers)
        return await render_template('dashboard/index.html', stats=stats)

    except Exception as e:
        logger.error(f"心念 WebUI | 仪表板加载失败: {e}")
        return await render_template('dashboard/index.html', stats={}, error=str(e))


@dashboard_bp.route('/api/stats')
@login_required
async def api_stats():
    """获取统计信息的 API 接口"""
    try:
        managers = current_app.managers
        stats = await get_dashboard_stats(managers)
        return jsonify(stats)
    except Exception as e:
        logger.error(f"心念 WebUI | 获取统计信息失败: {e}")
        return jsonify({'error': str(e)}), 500


async def get_dashboard_stats(managers):
    """获取仪表板统计信息"""
    stats = {
        'plugin_info': {
            'name': '心念',
            'version': current_app.plugin_config.get('version', 'v2.0.0'),
            'status': 'running'
        },
        'session_stats': {
            'total_sessions': 0
        },
        'user_stats': {
            'total': len(runtime_data.session_user_info)
        },
        'task_stats': {
            'proactive_task_status': 'unknown',
            'ai_schedules_count': 0
        },
        'config_stats': {
            'proactive_messaging_enabled': False,
            'ai_scheduling_enabled': False
        },
        'recent_activities': []
    }

    try:
        # 获取会话统计
        config_manager = managers.get('config_manager')
        if config_manager:
            config = config_manager.config if hasattr(config_manager, 'config') else {}
            sessions_data = config.get('proactive_reply', {}).get('sessions', [])
            stats['session_stats']['total_sessions'] = len(sessions_data)

        # 获取任务统计
        task_manager = managers.get('task_manager')
        if task_manager:
            # 检查 proactive_task 是否存在且正在运行
            proactive_task = getattr(task_manager, 'proactive_task', None)
            is_running = proactive_task is not None and not proactive_task.done() if proactive_task else False
            stats['task_stats']['proactive_task_status'] = 'running' if is_running else 'stopped'

            # 获取 AI 调度统计（遍历所有会话收集任务数量）
            total_ai_tasks = 0
            for tasks in runtime_data.session_ai_scheduled.values():
                if isinstance(tasks, list):
                    total_ai_tasks += len(tasks)
                elif isinstance(tasks, dict):
                    total_ai_tasks += 1
            stats['task_stats']['ai_schedules_count'] = total_ai_tasks

        # 获取配置统计
        if config_manager and hasattr(config_manager, 'config'):
            config = config_manager.config
            stats['config_stats']['proactive_messaging_enabled'] = config.get('proactive_reply', {}).get('enabled', False)
            stats['config_stats']['ai_scheduling_enabled'] = config.get('ai_schedule', {}).get('enabled', False)

        # 构建最近活动时间线
        stats['recent_activities'] = _build_recent_activities(managers)

    except Exception as e:
        logger.error(f"心念 WebUI | 获取统计信息时出错: {e}")

    return stats


def _get_astrbot_config_from_managers(managers):
    """从 managers 中安全获取 AstrBot 全局配置"""
    try:
        mgr = managers.get('conversation_manager') or managers.get('user_info_manager')
        if mgr and hasattr(mgr, 'context') and mgr.context:
            return mgr.context.get_config()
    except Exception:
        pass
    return None


def _build_recent_activities(managers) -> list:
    """从运行时数据构建最近活动时间线"""
    from ...utils.time_utils import get_now
    config_manager = managers.get('config_manager')
    config = config_manager.config if config_manager and hasattr(config_manager, 'config') else {}
    astrbot_config = _get_astrbot_config_from_managers(managers)
    activities = []
    now = get_now(config, astrbot_config).replace(tzinfo=None)

    # 收集最近的消息发送记录
    for session, time_str in runtime_data.last_sent_times.items():
        try:
            sent_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            # 获取用户名（如果有）
            user_info = runtime_data.session_user_info.get(session, {})
            username = user_info.get('username', '')
            label = f"向 {username}" if username else "向会话"
            activities.append({
                'type': 'send',
                'icon': 'fas fa-paper-plane',
                'color': 'success',
                'title': f'{label} 发送了主动消息',
                'desc': _truncate_session_id(session),
                'time': time_str,
                'sort_key': sent_time,
            })
        except ValueError:
            continue

    # 收集 AI 调度任务
    for session, tasks in runtime_data.session_ai_scheduled.items():
        task_list = tasks if isinstance(tasks, list) else [tasks] if isinstance(tasks, dict) else []
        for task in task_list:
            created_at = task.get('created_at', '')
            fire_time = task.get('fire_time', '')
            if created_at:
                try:
                    created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                    activities.append({
                        'type': 'schedule',
                        'icon': 'fas fa-robot',
                        'color': 'warning',
                        'title': 'AI 调度了新任务',
                        'desc': f'计划于 {fire_time} 发送 · {_truncate_session_id(session)}',
                        'time': created_at,
                        'sort_key': created,
                    })
                except ValueError:
                    continue

    # 收集用户最后活跃时间
    for session, info in runtime_data.session_user_info.items():
        last_active = info.get('last_active_time', '')
        username = info.get('username', '未知用户')
        if last_active:
            try:
                active_time = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
                activities.append({
                    'type': 'user_active',
                    'icon': 'fas fa-user',
                    'color': 'info',
                    'title': f'{username} 最后活跃',
                    'desc': _truncate_session_id(session),
                    'time': last_active,
                    'sort_key': active_time,
                })
            except ValueError:
                continue

    # 按时间倒序排列，取最近 10 条
    activities.sort(key=lambda x: x['sort_key'], reverse=True)
    activities = activities[:10]

    # 转换时间为相对描述
    for activity in activities:
        activity['time_display'] = _format_relative_time(activity['sort_key'], now)
        del activity['sort_key']

    return activities


def _truncate_session_id(session_id: str) -> str:
    """截断会话 ID 以便展示"""
    parts = session_id.split(':')
    if len(parts) >= 3:
        platform = parts[0]
        chat_type = parts[1]
        raw_id = ':'.join(parts[2:])
        # 截断过长的 ID
        if len(raw_id) > 12:
            raw_id = raw_id[:12] + '…'
        return f'{platform}:{chat_type}:{raw_id}'
    if len(session_id) > 30:
        return session_id[:30] + '…'
    return session_id


def _format_relative_time(dt: datetime, now: datetime) -> str:
    """格式化为相对时间描述"""
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 0:
        # 未来时间
        future_seconds = abs(seconds)
        if future_seconds < 60:
            return '即将'
        if future_seconds < 3600:
            return f'{future_seconds // 60} 分钟后'
        if future_seconds < 86400:
            return f'{future_seconds // 3600} 小时后'
        return dt.strftime('%m-%d %H:%M')

    if seconds < 60:
        return '刚刚'
    if seconds < 3600:
        return f'{seconds // 60} 分钟前'
    if seconds < 86400:
        return f'{seconds // 3600} 小时前'
    if seconds < 172800:
        return '昨天'
    return dt.strftime('%m-%d %H:%M')
