"""
API 蓝图

提供统一的 REST API 接口
"""

from quart import Blueprint, jsonify, request, current_app
from astrbot.api import logger
from datetime import datetime
from ..auth import login_required

api_bp = Blueprint('api', __name__)


@api_bp.route('/health')
async def health():
    """健康检查接口"""
    return jsonify({
        'status': 'healthy',
        'service': '心念 WebUI',
        'version': current_app.plugin_config.get('version', 'v2.0.0'),
        'timestamp': datetime.now().isoformat()
    })


@api_bp.route('/info')
@login_required
async def info():
    """获取插件信息"""
    try:
        managers = current_app.managers

        info_data = {
            'plugin': {
                'name': '心念',
                'display_name': '心念',
                'version': current_app.plugin_config.get('version', 'v2.0.0'),
                'description': '一个支持聊天增强、时间感知和智能主动对话的AstrBot插件'
            },
            'webui': {
                'version': '1.0.0',
                'features': [
                    '基础配置管理',
                    '状态监控',
                    '会话管理',
                    '用户管理',
                    '任务管理'
                ]
            },
            'managers': {
                name: manager is not None
                for name, manager in managers.items()
            }
        }

        return jsonify({'success': True, 'info': info_data})

    except Exception as e:
        logger.error(f"心念 WebUI API | 获取插件信息失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/stats/overview')
@login_required
async def stats_overview():
    """获取概览统计信息"""
    try:
        managers = current_app.managers

        # 获取用户统计
        user_stats = {'total': 0}
        user_info_manager = managers.get('user_info_manager')
        if user_info_manager:
            user_data = user_info_manager.persistence_manager.load_data('user_info', {})
            user_stats['total'] = len(user_data)

        # 获取会话统计
        session_stats = {'total': 0}
        persistence_manager = managers.get('persistence_manager')
        if persistence_manager:
            sessions_data = persistence_manager.load_data('proactive_sessions', [])
            session_stats['total'] = len(sessions_data)

        # 获取任务统计
        task_stats = {'proactive_running': False, 'ai_schedules': 0}
        task_manager = managers.get('task_manager')
        if task_manager:
            is_running = getattr(task_manager, 'is_running', False)
            if callable(is_running):
                is_running = is_running()
            task_stats['proactive_running'] = bool(is_running)
            if hasattr(task_manager, 'ai_schedules'):
                task_stats['ai_schedules'] = len(task_manager.ai_schedules)

        overview = {
            'users': user_stats,
            'sessions': session_stats,
            'tasks': task_stats,
            'timestamp': datetime.now().isoformat()
        }

        return jsonify({'success': True, 'overview': overview})

    except Exception as e:
        logger.error(f"心念 WebUI API | 获取概览统计失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




@api_bp.errorhandler(404)
async def api_not_found(error):
    """API 404 错误处理"""
    return jsonify({
        'success': False,
        'error': 'API endpoint not found',
        'code': 404
    }), 404


@api_bp.errorhandler(500)
async def api_internal_error(error):
    """API 500 错误处理"""
    logger.error(f"心念 WebUI API | 内部错误: {error}")
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'code': 500
    }), 500