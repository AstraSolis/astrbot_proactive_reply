"""
AstrBot 主动回复插件(心念)

支持聊天附带用户信息和定时主动发送消息
"""

import asyncio
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

# 导入各个功能模块
from .core.config_manager import ConfigManager
from .core.persistence_manager import PersistenceManager
from .core.user_info_manager import UserInfoManager
from .core.conversation_manager import ConversationManager
from .llm.prompt_builder import PromptBuilder
from .llm.message_generator import MessageGenerator
from .tasks.proactive_task import ProactiveTaskManager
from .commands import CommandHandlers


class ProactiveReplyPlugin(Star):
    """主动回复插件主类

    该类整合了各个功能模块，提供统一的插件接口
    """

    def __init__(self, context: Context, config: AstrBotConfig = None):
        """初始化插件

        Args:
            context: AstrBot上下文对象
            config: AstrBot配置对象
        """
        super().__init__(context)
        self.config = config or {}
        self._is_terminating = False
        self._initialization_task = None

        # 初始化各个管理器
        self._initialize_managers()

        logger.info("ProactiveReplyPlugin 插件已初始化")

        # 异步初始化
        self._initialization_task = asyncio.create_task(self.initialize())

    def _initialize_managers(self):
        """初始化所有管理器"""
        # 核心模块
        self.persistence_manager = PersistenceManager(self.config, self.context)
        self.config_manager = ConfigManager(self.config, self.persistence_manager)
        self.user_info_manager = UserInfoManager(
            self.config, self.config_manager, self.persistence_manager
        )
        self.conversation_manager = ConversationManager(
            self.config, self.context, self.persistence_manager
        )

        # LLM模块
        self.prompt_builder = PromptBuilder(self.config, self.context)
        self.message_generator = MessageGenerator(
            self.config,
            self.context,
            self.prompt_builder,
            self.conversation_manager,
            self.user_info_manager,
        )

        # 任务模块
        self.task_manager = ProactiveTaskManager(
            self.config,
            self.context,
            self.message_generator,
            self.user_info_manager,
            lambda: self._is_terminating,
        )

        # 命令处理器
        self.command_handlers = CommandHandlers(self)

    def _verify_config_loading(self):
        """验证配置文件加载状态"""
        self.config_manager.verify_config_loading()

    async def initialize(self):
        """插件初始化方法"""
        # 确保配置结构完整（包括加载持久化数据）
        self.config_manager.ensure_config_structure()

        # 验证配置加载状态（必须在 ensure_config_structure 之后）
        self._verify_config_loading()

        # 启动定时任务
        await self.task_manager.start_proactive_task()

        logger.info("ProactiveReplyPlugin 插件初始化完成")

    # ==================== 事件过滤器 ====================

    @filter.on_llm_request()
    async def add_user_info(self, event: AstrMessageEvent, req, _ignore=None):
        """在LLM请求前添加用户信息和时间

        自动触发,在每次LLM请求前自动添加用户相关信息
        """
        await self.user_info_manager.add_user_info_to_request(event, req)

    @filter.after_message_sent()
    async def record_ai_message_time(self, event: AstrMessageEvent, _ignore=None):
        """在AI发送消息后记录发送时间

        自动触发,记录AI每次发送消息的时间
        注意：命令消息（以 / 开头）不会触发时间记录，避免影响主动消息计时
        """
        # 检查原始消息是否是命令（以 / 开头）
        original_message = event.message_str or ""
        if original_message.strip().startswith("/"):
            logger.debug(f"跳过命令消息的时间记录: {original_message[:20]}...")
            return
        await self.user_info_manager.record_ai_message_time(event)

    # ==================== 命令组定义 ====================

    @filter.command_group("proactive")
    def proactive_group(self):
        """主动回复插件管理指令组"""
        pass

    # ==================== 状态命令 ====================

    @proactive_group.command("status")
    async def status(self, event: AstrMessageEvent, _ignore=None):
        """查看插件状态

        显示插件的详细运行状态，包括：
        - 当前会话信息
        - 用户信息附加功能状态
        - 智能主动发送功能配置
        - LLM提供商状态
        - 定时任务配置信息
        """
        async for result in self.command_handlers.status(event):
            yield result

    # ==================== 会话管理命令 ====================

    @proactive_group.command("add_session")
    async def add_session(self, event: AstrMessageEvent, _ignore=None):
        """将当前会话添加到定时发送列表

        将执行此命令的会话添加到主动发送目标列表中
        """
        async for result in self.command_handlers.add_session(event):
            yield result

    @proactive_group.command("remove_session")
    async def remove_session(self, event: AstrMessageEvent, _ignore=None):
        """将当前会话从定时发送列表中移除

        从主动发送目标列表中移除当前会话
        """
        async for result in self.command_handlers.remove_session(event):
            yield result

    # ==================== 测试命令 ====================

    @proactive_group.command("test")
    async def test_proactive(self, event: AstrMessageEvent, test_type: str = "", _ignore=None):
        """测试功能 - 支持多种测试类型

        参数:
        - basic: 基础测试发送 (默认)
        - llm: 测试LLM请求
        - generation: 测试LLM生成主动消息
        - prompt: 测试系统提示词构建
        - placeholders: 测试占位符替换
        - history: 测试对话历史记录
        - save: 测试对话保存功能

        使用方法: /proactive test [类型]
        例如: /proactive test generation
        """
        if not isinstance(test_type, str):
            test_type = ""
        async for result in self.command_handlers.test_proactive(event, test_type):
            yield result

    # ==================== 显示命令 ====================

    @proactive_group.command("show")
    async def show_info(self, event: AstrMessageEvent, show_type: str = "", _ignore=None):
        """显示信息 - 支持多种显示类型

        参数:
        - prompt: 显示当前配置下会输入给LLM的组合话本（默认）
        - users: 显示已记录的用户信息

        使用方法: /proactive show [类型]
        例如: /proactive show prompt
        """
        if not isinstance(show_type, str):
            show_type = ""
        async for result in self.command_handlers.show_info(event, show_type):
            yield result

    @proactive_group.command("config")
    async def show_config_cmd(self, event: AstrMessageEvent, _ignore=None):
        """显示完整的插件配置信息

        查看当前插件的完整配置详情
        """
        async for result in self.command_handlers.show_config(event):
            yield result

    # ==================== 管理命令 ====================

    @proactive_group.command("manage")
    async def manage_functions(self, event: AstrMessageEvent, action: str = "", _ignore=None):
        """管理功能 - 支持多种管理操作

        参数:
        - clear: 清除记录的用户信息和发送时间
        - task_status: 检查定时任务状态
        - force_stop: 强制停止所有定时任务
        - force_start: 强制启动定时任务
        - save_config: 强制保存配置文件
        - debug_info: 调试用户信息（故障排查用）
        - debug_send: 调试发送功能（故障排查用）
        - debug_times: 调试时间记录（故障排查用）

        使用方法: /proactive manage [操作]
        例如: /proactive manage clear
        """
        if not isinstance(action, str):
            action = ""
        async for result in self.command_handlers.manage_functions(event, action):
            yield result

    # ==================== 通用命令 ====================

    @proactive_group.command("help")
    async def help_command(self, event: AstrMessageEvent, _ignore=None):
        """显示插件帮助信息

        显示所有可用命令和使用说明
        """
        async for result in self.command_handlers.help_command(event):
            yield result

    @proactive_group.command("restart")
    async def restart(self, event: AstrMessageEvent, _ignore=None):
        """重启定时主动发送任务（配置更改后使用）

        重启定时任务以应用新的配置更改
        """
        async for result in self.command_handlers.restart(event):
            yield result

    # ==================== 插件终止 ====================

    async def terminate(self):
        """插件终止时的清理工作"""
        logger.info("ProactiveReplyPlugin 插件正在终止...")

        # 设置终止标志
        self._is_terminating = True

        # 停止初始化任务
        if self._initialization_task and not self._initialization_task.cancelled():
            self._initialization_task.cancel()
            try:
                await self._initialization_task
            except asyncio.CancelledError:
                pass

        # 停止定时任务
        await self.task_manager.stop_proactive_task()
        logger.info("ProactiveReplyPlugin 插件已终止")
