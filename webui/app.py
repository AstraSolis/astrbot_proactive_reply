"""
WebUI 应用工厂

创建和配置 Quart 应用实例
"""

import os
from typing import Dict, Any

from quart import Quart, render_template
from quart_cors import cors

from astrbot.api import logger


def create_app(config: Dict[str, Any], managers: Dict[str, Any]) -> Quart:
    """创建 Quart 应用实例

    Args:
        config: 插件配置
        managers: 各个管理器的字典

    Returns:
        配置好的 Quart 应用实例
    """
    # 创建应用实例
    app = Quart(__name__)

    # 配置应用
    webui_config = config.get('webui', {})
    app.config.update({
        'SECRET_KEY': webui_config.get('webui_secret_key', 'astrbot-proactive-reply-webui-secret'),
        'TEMPLATES_AUTO_RELOAD': True,
        'JSON_AS_ASCII': False,
    })

    # 设置模板和静态文件路径
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    app.template_folder = template_dir
    app.static_folder = static_dir

    # 启用 CORS
    cors(app, allow_origin="*")

    # 将管理器注入到应用上下文
    app.managers = managers
    app.plugin_config = config

    # 注册中间件
    register_middleware(app)

    # 注册蓝图
    register_blueprints(app)

    # 注册错误处理器
    register_error_handlers(app)

    # 注册上下文处理器
    register_context_processors(app)

    logger.info("心念 WebUI | 应用工厂已创建")
    return app


def register_middleware(app: Quart):
    """注册中间件"""

    @app.after_request
    async def add_security_headers(response):
        """添加安全头"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response


def register_blueprints(app: Quart):
    """注册蓝图"""
    from .auth import auth_bp
    from .blueprints.dashboard import dashboard_bp
    from .blueprints.config import config_bp
    from .blueprints.sessions import sessions_bp
    from .blueprints.api import api_bp

    # 注册蓝图
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(config_bp, url_prefix='/config')
    app.register_blueprint(sessions_bp, url_prefix='/sessions')
    app.register_blueprint(api_bp, url_prefix='/api')


def register_error_handlers(app: Quart):
    """注册错误处理器"""

    @app.errorhandler(404)
    async def not_found(error):
        """404 错误处理"""
        return await render_template('errors/404.html'), 404

    @app.errorhandler(500)
    async def internal_error(error):
        """500 错误处理"""
        import traceback
        logger.error(f"心念 WebUI | 内部错误: {error}")
        logger.error(f"心念 WebUI | 详细堆栈:\n{traceback.format_exc()}")
        return await render_template('errors/500.html'), 500


def register_context_processors(app: Quart):
    """注册上下文处理器"""

    @app.context_processor
    async def inject_common_vars():
        """注入通用变量到模板上下文"""
        return {
            'app_name': '心念 WebUI',
            'version': app.plugin_config.get('version', 'v2.0.0'),
        }

    # 健康检查端点
    @app.route('/health')
    async def health_check():
        """健康检查端点"""
        return {'status': 'running', 'version': app.plugin_config.get('version', 'v2.0.0')}

