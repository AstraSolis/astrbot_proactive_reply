"""
WebUI 蓝图模块

包含所有功能蓝图的初始化
"""

# 导入所有蓝图，方便统一管理
from .dashboard import dashboard_bp
from .config import config_bp
from .sessions import sessions_bp
from .api import api_bp

__all__ = [
    'dashboard_bp',
    'config_bp',
    'sessions_bp',
    'api_bp'
]