"""
WebUI 模块初始化文件

导入和暴露 WebUI 的主要组件
"""

from .manager import WebUIManager
from .app import create_app

__all__ = ['WebUIManager', 'create_app']

# 版本信息
__version__ = '1.0.0'
__author__ = 'AstraSolis'
__description__ = '心念插件 WebUI 管理界面'