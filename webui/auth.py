"""
WebUI 认证模块

简单的密码认证实现
"""

from functools import wraps
from quart import Blueprint, render_template, request, session, redirect, url_for, jsonify, current_app
from astrbot.api import logger

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """登录检查装饰器"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            if request.is_json:
                return jsonify({'error': '需要登录', 'redirect': '/auth/login'}), 401
            return redirect(url_for('auth.login'))
        return await f(*args, **kwargs)
    return decorated_function


def check_password(input_password: str) -> bool:
    """验证密码"""
    try:
        webui_config = current_app.plugin_config.get('webui', {})
        correct_password = webui_config.get('webui_password', 'admin')
        return input_password == correct_password
    except Exception as e:
        logger.error(f"心念 WebUI | 密码验证失败: {e}")
        return False


@auth_bp.route('/login', methods=['GET', 'POST'])
async def login():
    """登录页面和处理"""
    if request.method == 'GET':
        # 如果已经登录，重定向到首页
        if session.get('authenticated'):
            return redirect(url_for('dashboard.index'))
        return await render_template('auth/login.html')

    # POST 请求处理登录
    try:
        data = await request.get_json() if request.is_json else await request.form
        password = data.get('password', '').strip()

        if not password:
            error_msg = '请输入密码'
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 400
            return await render_template('auth/login.html', error=error_msg)

        if check_password(password):
            session['authenticated'] = True
            logger.info("心念 WebUI | 用户登录成功")

            if request.is_json:
                return jsonify({'success': True, 'redirect': url_for('dashboard.index')})
            return redirect(url_for('dashboard.index'))
        else:
            error_msg = '密码错误'
            logger.warning("心念 WebUI | 登录失败：密码错误")

            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 401
            return await render_template('auth/login.html', error=error_msg)

    except Exception as e:
        error_msg = f'登录处理失败: {str(e)}'
        logger.error(f"心念 WebUI | {error_msg}")

        if request.is_json:
            return jsonify({'success': False, 'error': error_msg}), 500
        return await render_template('auth/login.html', error=error_msg)


@auth_bp.route('/logout', methods=['POST'])
async def logout():
    """登出"""
    session.pop('authenticated', None)
    logger.info("心念 WebUI | 用户已登出")

    if request.is_json:
        return jsonify({'success': True, 'redirect': url_for('auth.login')})
    return redirect(url_for('auth.login'))


@auth_bp.route('/check')
async def check_auth():
    """检查认证状态的API"""
    return jsonify({
        'authenticated': bool(session.get('authenticated')),
        'login_url': url_for('auth.login')
    })