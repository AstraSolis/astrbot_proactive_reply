"""
WebUI 管理器

负责 WebUI 服务器的启动、停止和管理
"""

import asyncio
from typing import Dict, Any, Optional

from astrbot.api import logger
from hypercorn.asyncio import serve
from hypercorn.config import Config


class WebUIManager:
    """WebUI 管理器类"""

    def __init__(self, config: Dict[str, Any], context, managers: Dict[str, Any]):
        """初始化 WebUI 管理器

        Args:
            config: 插件配置
            context: AstrBot 上下文
            managers: 各个管理器的字典
        """
        self.config = config
        self.context = context
        self.managers = managers
        self.app = None
        self.server_task = None
        self._port = None

    async def start(self):
        """启动 WebUI 服务器"""
        try:
            # 获取配置的端口，默认为 8080
            webui_config = self.config.get('webui', {})
            port = webui_config.get('webui_port', 8080)

            # 检查端口是否可用
            available_port = self._find_available_port(port)
            if available_port != port:
                logger.warning(f"心念 WebUI | 端口 {port} 被占用，使用端口 {available_port}")

            self._port = available_port

            # 创建应用
            from .app import create_app
            self.app = create_app(self.config, self.managers)

            # 配置 Hypercorn
            hypercorn_config = Config()
            hypercorn_config.bind = [f"0.0.0.0:{self._port}"]
            hypercorn_config.graceful_timeout = 5
            hypercorn_config.access_log_format = '%(h)s "%(r)s" %(s)s %(b)s "%(f)s"'

            # 启动服务器（不使用 sockets 参数）
            self.server_task = asyncio.create_task(
                serve(self.app, hypercorn_config)
            )

            logger.info(f"心念 WebUI | ✅ 已启动在端口 {self._port}")
            logger.info(f"心念 WebUI | 🌐 访问地址: http://localhost:{self._port}")

        except Exception as e:
            logger.error(f"心念 WebUI | ❌ 启动失败: {e}")
            raise

    async def stop(self):
        """停止 WebUI 服务器"""
        try:
            if self.server_task:
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass
                self.server_task = None

            logger.info("心念 WebUI | ✅ 已停止")

        except Exception as e:
            logger.error(f"心念 WebUI | ❌ 停止时出错: {e}")

    def _find_available_port(self, start_port: int, max_attempts: int = 10) -> int:
        """查找可用端口

        Args:
            start_port: 起始端口
            max_attempts: 最大尝试次数

        Returns:
            可用的端口号
        """
        import socket

        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(('localhost', port))
                    return port
            except OSError:
                continue

        # 如果都不可用，返回原端口（让系统报错）
        return start_port

    @property
    def is_running(self) -> bool:
        """检查 WebUI 是否正在运行"""
        return self.server_task is not None and not self.server_task.done()

    @property
    def port(self) -> Optional[int]:
        """获取当前使用的端口"""
        return self._port