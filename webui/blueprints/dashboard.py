"""
仪表板蓝图

显示插件状态概览和实时统计信息
"""

import time
from datetime import datetime, timedelta
from quart import Blueprint, render_template, current_app, jsonify
from astrbot.api import logger
from ..auth import login_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
async def index():
    """仪表板主页"""
    try:
        # 获取管理器
        managers = current_app.managers
        config_manager = managers.get('config_manager')
        user_info_manager = managers.get('user_info_manager')
        task_manager = managers.get('task_manager')
        persistence_manager = managers.get('persistence_manager')

        # 获取基本统计信息
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
        'task_stats': {
            'proactive_task_status': 'unknown',
            'ai_schedules_count': 0
        },
        'config_stats': {
            'proactive_messaging_enabled': False,
            'ai_scheduling_enabled': False
        }
    }

    try:
        # 获取会话统计
        persistence_manager = managers.get('persistence_manager')
        if persistence_manager:
            sessions_data = persistence_manager.load_data('proactive_sessions', [])
            stats['session_stats']['total_sessions'] = len(sessions_data)

        # 获取任务统计
        task_manager = managers.get('task_manager')
        if task_manager:
            is_running = getattr(task_manager, 'is_running', False)
            if callable(is_running):
                is_running = is_running()
            stats['task_stats']['proactive_task_status'] = 'running' if is_running else 'stopped'

            # 获取 AI 调度统计
            if hasattr(task_manager, 'ai_schedules'):
                stats['task_stats']['ai_schedules_count'] = len(task_manager.ai_schedules)

        # 获取配置统计
        config_manager = managers.get('config_manager')
        if config_manager and hasattr(config_manager, 'config'):
            config = config_manager.config
            stats['config_stats']['proactive_messaging_enabled'] = config.get('proactive_reply', {}).get('enabled', False)
            stats['config_stats']['ai_scheduling_enabled'] = config.get('ai_schedule', {}).get('enabled', False)

    except Exception as e:
        logger.error(f"心念 WebUI | 获取统计信息时出错: {e}")

    return stats

