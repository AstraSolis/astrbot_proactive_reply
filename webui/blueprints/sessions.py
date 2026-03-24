"""
会话管理蓝图

处理主动对话会话的查看、添加和删除
"""


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
        config_manager = managers.get('config_manager')

        if not config_manager:
            return jsonify({'success': False, 'error': '配置管理器未找到'}), 500

        data = await request.get_json()
        session_id = data.get('session_id', '').strip()

        if not session_id:
            return jsonify({'success': False, 'error': '会话 ID 不能为空'}), 400

        # 解析会话 ID 格式：platform:type:id
        parts = session_id.split(':')
        if len(parts) < 3:
            return jsonify({'success': False, 'error': '会话 ID 格式不正确，应为 platform:type:id'}), 400



        # 加载现有会话
        config = config_manager.config if hasattr(config_manager, 'config') else {}
        sessions = config.get('proactive_reply', {}).get('sessions', [])

        # 安全解析确保没有脏数据
        safe_sessions = []
        if isinstance(sessions, list):
            for s in sessions:
                if isinstance(s, dict) and 'session_id' in s:
                    safe_sessions.append(s['session_id'])
                elif isinstance(s, str):
                    safe_sessions.append(s.strip())
        
        # 检查是否已存在
        if session_id in safe_sessions:
            return jsonify({'success': False, 'error': '该会话已存在'}), 400

        # 添加新会话 (纯字符串)
        safe_sessions.append(session_id)
        sessions = safe_sessions

        # 保存
        config.setdefault('proactive_reply', {})['sessions'] = sessions
        if hasattr(config_manager, 'save_config'):
            config_manager.save_config()

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
        config_manager = managers.get('config_manager')

        if not config_manager:
            return jsonify({'success': False, 'error': '配置管理器未找到'}), 500

        data = await request.get_json()
        session_id = data.get('session_id', '').strip()

        if not session_id:
            return jsonify({'success': False, 'error': '会话 ID 不能为空'}), 400

        # 加载现有会话
        config = config_manager.config if hasattr(config_manager, 'config') else {}
        sessions = config.get('proactive_reply', {}).get('sessions', [])
        # 安全解析确保没有脏数据
        safe_sessions = []
        if isinstance(sessions, list):
            for s in sessions:
                if isinstance(s, dict) and 'session_id' in s:
                    safe_sessions.append(s['session_id'])
                elif isinstance(s, str):
                    safe_sessions.append(s.strip())

        original_count = len(safe_sessions)

        # 过滤掉目标会话
        sessions = [s for s in safe_sessions if s != session_id]

        if len(sessions) == original_count:
            return jsonify({'success': False, 'error': '未找到该会话'}), 404

        # 保存
        config.setdefault('proactive_reply', {})['sessions'] = sessions
        if hasattr(config_manager, 'save_config'):
            config_manager.save_config()

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
    from ...core.runtime_data import runtime_data
    from datetime import datetime

    config_manager = managers.get('config_manager')
    if not config_manager:
        return []

    config = config_manager.config if hasattr(config_manager, 'config') else {}
    sessions = config.get('proactive_reply', {}).get('sessions', [])

    safe_sessions = []
    if isinstance(sessions, list):
        for s in sessions:
            if isinstance(s, dict) and 'session_id' in s:
                safe_sessions.append(s['session_id'])
            elif isinstance(s, str) and s.strip():
                safe_sessions.append(s.strip())

    now = datetime.now()
    enhanced_sessions = []
    for session_id in safe_sessions:
        parts = session_id.split(':')
        enhanced_session = {
            'session_id': session_id,
            'added_time_display': 'N/A'
        }

        if len(parts) >= 3:
            enhanced_session['platform'] = parts[0]
            enhanced_session['chat_type'] = parts[1]
            enhanced_session['raw_id'] = ':'.join(parts[2:])
        else:
            enhanced_session['platform'] = 'unknown'
            enhanced_session['chat_type'] = 'unknown'
            enhanced_session['raw_id'] = session_id

        # 从 runtime_data 获取真实运行时状态
        # 下次发送时间
        next_fire_str = runtime_data.session_next_fire_times.get(session_id, '')
        if next_fire_str:
            try:
                next_fire = datetime.strptime(next_fire_str, "%Y-%m-%d %H:%M:%S")
                delta = next_fire - now
                total_minutes = int(delta.total_seconds() / 60)
                if total_minutes <= 0:
                    enhanced_session['next_fire_display'] = '即将发送'
                elif total_minutes < 60:
                    enhanced_session['next_fire_display'] = f'{total_minutes}分钟后'
                else:
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    enhanced_session['next_fire_display'] = f'{hours}小时{minutes}分钟后'
            except ValueError:
                enhanced_session['next_fire_display'] = '—'
        else:
            enhanced_session['next_fire_display'] = '等待初始化'

        # 最后发送时间
        last_sent = runtime_data.last_sent_times.get(session_id, '')
        enhanced_session['last_sent_time'] = last_sent if last_sent else '—'

        # 未回复计数
        unreplied = runtime_data.session_unreplied_count.get(session_id, 0)
        enhanced_session['unreplied_count'] = unreplied

        # 用户名
        user_info = runtime_data.session_user_info.get(session_id, {})
        enhanced_session['username'] = user_info.get('username', '')
        enhanced_session['user_last_active'] = user_info.get('last_active_time', '')

        # AI 调度任务计数
        ai_tasks = runtime_data.session_ai_scheduled.get(session_id, [])
        if isinstance(ai_tasks, list):
            enhanced_session['ai_task_count'] = len(ai_tasks)
        elif isinstance(ai_tasks, dict):
            enhanced_session['ai_task_count'] = 1
        else:
            enhanced_session['ai_task_count'] = 0

        # 状态判断：有下次发送时间的算活跃
        if next_fire_str:
            enhanced_session['status'] = 'active'
            enhanced_session['status_display'] = '活跃'
        else:
            enhanced_session['status'] = 'inactive'
            enhanced_session['status_display'] = '等待中'

        enhanced_sessions.append(enhanced_session)

    return enhanced_sessions