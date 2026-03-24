"""
配置管理蓝图

处理插件配置的查看、修改和保存
"""

from quart import Blueprint, render_template, request, jsonify, current_app
from astrbot.api import logger
from ..auth import login_required

config_bp = Blueprint('config', __name__)


@config_bp.route('/')
@login_required
async def index():
    """配置管理主页"""
    try:
        managers = current_app.managers
        config_manager = managers.get('config_manager')

        if not config_manager:
            return await render_template('config/index.html', error="配置管理器未找到")

        # 获取当前配置
        current_config = config_manager.config if hasattr(config_manager, 'config') else {}

        # 确保所有配置区段存在，避免模板访问不存在的 key 时报错
        safe_config = ensure_config_sections(current_config)

        return await render_template('config/index.html', config=safe_config)

    except Exception as e:
        logger.error(f"心念 WebUI | 配置页面加载失败: {e}")
        return await render_template('config/index.html', error=str(e))


@config_bp.route('/api/get')
@login_required
async def api_get_config():
    """获取当前配置的 API 接口"""
    try:
        managers = current_app.managers
        config_manager = managers.get('config_manager')

        if not config_manager:
            return jsonify({'error': '配置管理器未找到'}), 500

        config = config_manager.config if hasattr(config_manager, 'config') else {}
        return jsonify({'config': config})

    except Exception as e:
        logger.error(f"心念 WebUI | 获取配置失败: {e}")
        return jsonify({'error': str(e)}), 500


@config_bp.route('/api/update', methods=['POST'])
@login_required
async def api_update_config():
    """更新配置的 API 接口"""
    try:
        managers = current_app.managers
        config_manager = managers.get('config_manager')

        if not config_manager:
            return jsonify({'error': '配置管理器未找到'}), 500

        data = await request.get_json()
        new_config = data.get('config', {})

        # 验证配置
        validation_result = validate_config(new_config)
        if not validation_result['valid']:
            return jsonify({
                'success': False,
                'error': validation_result['error']
            }), 400

        # 更新配置
        if hasattr(config_manager, 'update_config'):
            config_manager.update_config(new_config)
        elif hasattr(config_manager, 'config'):
            config_manager.config.update(new_config)

        # 保存配置
        if hasattr(config_manager, 'save_config'):
            config_manager.save_config()

        logger.info("心念 WebUI | 配置已更新")
        return jsonify({'success': True, 'message': '配置已成功更新'})

    except Exception as e:
        logger.error(f"心念 WebUI | 更新配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@config_bp.route('/api/reset', methods=['POST'])
@login_required
async def api_reset_config():
    """重置配置到默认值的 API 接口"""
    try:
        managers = current_app.managers
        config_manager = managers.get('config_manager')

        if not config_manager:
            return jsonify({'error': '配置管理器未找到'}), 500

        if hasattr(config_manager, 'reset_to_defaults'):
            config_manager.reset_to_defaults()
        elif hasattr(config_manager, 'ensure_config_structure'):
            config_manager.ensure_config_structure()

        logger.info("心念 WebUI | 配置已重置为默认值")
        return jsonify({'success': True, 'message': '配置已重置为默认值'})

    except Exception as e:
        logger.error(f"心念 WebUI | 重置配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def ensure_config_sections(config):
    """确保所有配置区段都存在，返回安全的配置字典

    避免模板中访问 config.time_awareness.xxx 时因 key 不存在而报错。
    """
    defaults = {
        'webui': {
            'webui_port': 8080,
            'webui_password': 'admin',
            'webui_secret_key': 'astrbot-proactive-reply-webui-secret',
        },
        'user_info': {
            'enabled': True,
            'time_format': '%Y-%m-%d %H:%M:%S',
            'template': '[对话信息] 用户名称:{username},时间:{time},上次聊天时间:{user_last_message_time}',
        },
        'time_awareness': {
            'time_guidance_enabled': True,
            'time_guidance_prompt': '',
            'sleep_mode_enabled': False,
            'sleep_hours': '22:00-8:00',
            'sleep_prompt': '',
            'send_on_wake_enabled': False,
            'wake_send_mode': 'immediate',
        },
        'proactive_reply': {
            'enabled': False,
            'timing_mode': 'fixed_interval',
            'interval_minutes': 600,
            'random_delay_enabled': False,
            'min_random_minutes': 0,
            'max_random_minutes': 30,
            'random_min_minutes': 600,
            'random_max_minutes': 1200,
            'duplicate_detection_enabled': True,
            'include_history_enabled': False,
            'history_message_count': 10,
            'history_save_mode': 'default',
            'custom_history_prompt': '<PROACTIVE_TRIGGER: 时间:{current_time}，用户:{username}>',
            'proactive_default_persona': '',
        },
        'message_split': {
            'enabled': True,
            'mode': 'backslash',
            'custom_pattern': '',
            'regex': '',
            'delay_ms': 500,
        },
        'ai_schedule': {
            'enabled': False,
            'provider_id': '',
            'analysis_prompt': '',
        },
    }

    safe = {}
    for section, section_defaults in defaults.items():
        section_data = config.get(section, {})
        if not isinstance(section_data, dict):
            section_data = {}
        merged = {**section_defaults, **section_data}
        safe[section] = type('ConfigSection', (), merged)()

    return type('SafeConfig', (), safe)()


def validate_config(config):
    """验证配置的有效性"""
    try:
        if not isinstance(config, dict):
            return {'valid': False, 'error': '配置必须是字典格式'}

        if 'proactive_reply' in config:
            proactive = config['proactive_reply']
            if not isinstance(proactive, dict):
                return {'valid': False, 'error': 'proactive_reply 必须是字典格式'}

            if 'interval_minutes' in proactive:
                interval = proactive['interval_minutes']
                if not isinstance(interval, (int, float)) or interval <= 0:
                    return {'valid': False, 'error': '发送间隔必须是正数'}

        if 'message_split' in config:
            split = config['message_split']
            if not isinstance(split, dict):
                return {'valid': False, 'error': 'message_split 必须是字典格式'}

            if 'delay_ms' in split:
                delay = split['delay_ms']
                if not isinstance(delay, (int, float)) or delay < 0:
                    return {'valid': False, 'error': '分割延迟不能为负数'}

        return {'valid': True}

    except Exception as e:
        return {'valid': False, 'error': f'验证配置时出错: {str(e)}'}