"""
会话管理蓝图

处理主动对话会话的查看、添加和删除
"""

from datetime import datetime
from quart import Blueprint, render_template, request, jsonify, current_app
from astrbot.api import logger
from ..auth import login_required

sessions_bp = Blueprint('sessions', __name__)


@sessions_bp.route('/')
@login_required
async def index():
    """会话管理主页"""
    try:
        managers = current_app.managers
        sessions_data = await get_sessions_data(managers)

        return await render_template('sessions/index.html', sessions=sessions_data)

    except Exception as e:
        logger.error(f"心念 WebUI | 会话管理页面加载失败: {e}")
        return await render_template('sessions/index.html', sessions=[], error=str(e))


@sessions_bp.route('/api/list')
@login_required
async def api_list_sessions():
    """获取会话列表的 API 接口"""
    try:
        managers = current_app.managers
        sessions_data = await get_sessions_data(managers)

        return jsonify({
            'success': True,
            'sessions': sessions_data,
            'total': len(sessions_data)
        })

    except Exception as e:
        logger.error(f"心念 WebUI | 获取会话列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@sessions_bp.route('/api/add', methods=['POST'])
@login_required
async def api_add_session():
    """添加会话的 API 接口"""
    try:
        managers = current_app.managers
        persistence_manager = managers.get('persistence_manager')

        if not persistence_manager:
            return jsonify({'success': False, 'error': '持久化管理器未找到'}), 500

        data = await request.get_json()
        session_id = data.get('session_id', '').strip()

        if not session_id:
            return jsonify({'success': False, 'error': '会话 ID 不能为空'}), 400

        # 解析会话 ID 格式：platform:type:id
        parts = session_id.split(':')
        if len(parts) < 3:
            return jsonify({'success': False, 'error': '会话 ID 格式不正确，应为 platform:type:id'}), 400

        platform = parts[0]
        chat_type = parts[1]
        raw_id = ':'.join(parts[2:])

        # 加载现有会话
        sessions = persistence_manager.load_data('proactive_sessions', [])

        # 检查是否已存在
        for s in sessions:
            if s.get('session_id') == session_id:
                return jsonify({'success': False, 'error': '该会话已存在'}), 400

        # 添加新会话
        new_session = {
            'session_id': session_id,
            'platform': platform,
            'chat_type': chat_type,
            'raw_id': raw_id,
            'status': 'active',
            'added_time': datetime.now().isoformat(),
        }
        sessions.append(new_session)

        # 保存
        persistence_manager.save_data('proactive_sessions', sessions)

        logger.info(f"心念 WebUI | 已添加会话: {session_id}")
        return jsonify({'success': True, 'message': f'已添加会话: {session_id}'})

    except Exception as e:
        logger.error(f"心念 WebUI | 添加会话失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@sessions_bp.route('/api/remove', methods=['POST'])
@login_required
async def api_remove_session():
    """移除会话的 API 接口"""
    try:
        managers = current_app.managers
        persistence_manager = managers.get('persistence_manager')

        if not persistence_manager:
            return jsonify({'success': False, 'error': '持久化管理器未找到'}), 500

        data = await request.get_json()
        session_id = data.get('session_id', '').strip()

        if not session_id:
            return jsonify({'success': False, 'error': '会话 ID 不能为空'}), 400

        # 加载现有会话
        sessions = persistence_manager.load_data('proactive_sessions', [])
        original_count = len(sessions)

        # 过滤掉目标会话
        sessions = [s for s in sessions if s.get('session_id') != session_id]

        if len(sessions) == original_count:
            return jsonify({'success': False, 'error': '未找到该会话'}), 404

        # 保存
        persistence_manager.save_data('proactive_sessions', sessions)

        logger.info(f"心念 WebUI | 已移除会话: {session_id}")
        return jsonify({'success': True, 'message': f'已移除会话: {session_id}'})

    except Exception as e:
        logger.error(f"心念 WebUI | 移除会话失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@sessions_bp.route('/api/stats')
@login_required
async def api_session_stats():
    """获取会话统计信息的 API 接口"""
    try:
        managers = current_app.managers
        sessions_data = await get_sessions_data(managers)

        stats = {
            'total': len(sessions_data),
            'active': len([s for s in sessions_data if s.get('status') == 'active']),
            'inactive': len([s for s in sessions_data if s.get('status') == 'inactive']),
            'by_platform': {},
            'by_chat_type': {}
        }

        for session in sessions_data:
            platform = session.get('platform', 'unknown')
            stats['by_platform'][platform] = stats['by_platform'].get(platform, 0) + 1

        for session in sessions_data:
            chat_type = session.get('chat_type', 'unknown')
            stats['by_chat_type'][chat_type] = stats['by_chat_type'].get(chat_type, 0) + 1

        return jsonify({'success': True, 'stats': stats})

    except Exception as e:
        logger.error(f"心念 WebUI | 获取会话统计失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


async def get_sessions_data(managers):
    """获取会话数据"""
    persistence_manager = managers.get('persistence_manager')
    if not persistence_manager:
        return []

    sessions = persistence_manager.load_data('proactive_sessions', [])

    enhanced_sessions = []
    for session in sessions:
        enhanced_session = session.copy()

        # 添加显示友好的时间格式
        if 'added_time' in session:
            try:
                added_time = datetime.fromisoformat(session['added_time'])
                enhanced_session['added_time_display'] = added_time.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                enhanced_session['added_time_display'] = session.get('added_time', 'N/A')

        # 添加状态显示
        status = session.get('status', 'unknown')
        enhanced_session['status_display'] = {
            'active': '活跃',
            'inactive': '非活跃',
            'unknown': '未知'
        }.get(status, status)

        enhanced_sessions.append(enhanced_session)

    return enhanced_sessions