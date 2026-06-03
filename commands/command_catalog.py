"""命令目录（命令系统的唯一真相源）

设计目标（与 ``llm/placeholder_utils`` 的占位符目录一致）：
- ``COMMAND_CATEGORIES`` 统一声明所有命令、子命令、所属分类、是否需要管理员权限及中文说明；
- ``/proactive help``、``test`` / ``show`` / ``manage`` 的子命令帮助文本均由本目录派生，
  避免在 ``main.py`` 装饰器、各 handler docstring、帮助文本之间出现多处漂移；
- Web API（``commands/list``）与 WebUI「命令」页同样从本目录派生，保证前后端一致。

本模块刻意不依赖 AstrBot 运行时（无 ``astrbot`` 导入），既方便被插件加载，也方便被单元测试直接载入。
"""

from __future__ import annotations

# 命令前缀（指令组名）。所有命令均形如 ``/proactive <command>``。
COMMAND_PREFIX = "proactive"

# 命令目录：分类 → 命令 → 子命令。这里是命令语义的唯一声明处。
#
# 每个分类：``{"key", "title", "commands": [...]}``
# 每条命令：``{"name", "admin", "desc", "args"?, "subcommands"?}``
#   - ``admin``：是否仅管理员可用
#   - ``args``：参数占位说明（如 ``"[类型]"``），可选
#   - ``subcommands``：子命令列表 ``[{"name", "desc"}, ...]``，可选
COMMAND_CATEGORIES = [
    {
        "key": "basic",
        "title": "基础命令",
        "commands": [
            {
                "name": "status",
                "admin": False,
                "desc": "查看插件运行状态（当前会话、功能开关、定时任务、LLM 提供商、AI 调度等）",
            },
            {
                "name": "add_session",
                "admin": False,
                "desc": "将当前会话加入主动对话列表",
            },
            {
                "name": "remove_session",
                "admin": False,
                "desc": "将当前会话移出主动对话列表",
            },
            {
                "name": "help",
                "admin": False,
                "desc": "显示所有可用命令与使用说明",
            },
        ],
    },
    {
        "key": "admin",
        "title": "管理员命令",
        "commands": [
            {
                "name": "config",
                "admin": True,
                "desc": "查看完整的插件配置详情（用户信息、主动回复、消息分割、提示词等）",
            },
            {
                "name": "restart",
                "admin": True,
                "desc": "重启定时主动发送任务（修改配置后使用以应用更改）",
            },
        ],
    },
    {
        "key": "test",
        "title": "测试命令",
        "commands": [
            {
                "name": "test",
                "admin": True,
                "args": "[类型]",
                "desc": "测试插件各项功能，需指定类型（不带类型时显示可用类型列表）",
                "subcommands": [
                    {"name": "basic", "desc": "测试向当前会话发送一条主动消息"},
                    {"name": "llm", "desc": "测试当前会话的 LLM 提供商是否可用"},
                    {"name": "generation", "desc": "测试完整的主动消息生成流程"},
                    {"name": "prompt", "desc": "测试并查看系统提示词的构建结果"},
                    {"name": "placeholders", "desc": "测试占位符替换功能"},
                    {"name": "history", "desc": "测试对话历史记录的获取"},
                    {"name": "save", "desc": "测试对话保存机制"},
                    {"name": "schedule", "desc": "测试 AI 调度任务（注入并诊断）"},
                ],
            },
        ],
    },
    {
        "key": "show",
        "title": "显示命令",
        "commands": [
            {
                "name": "show",
                "admin": True,
                "args": "[类型]",
                "desc": "显示插件内部信息，需指定类型（不带类型时显示可用类型列表）",
                "subcommands": [
                    {
                        "name": "prompt",
                        "desc": "显示当前配置下输入给 LLM 的主动提示词列表",
                    },
                    {"name": "users", "desc": "显示已记录的用户信息（昵称、平台等）"},
                ],
            },
        ],
    },
    {
        "key": "manage",
        "title": "管理命令",
        "commands": [
            {
                "name": "manage",
                "admin": True,
                "args": "[操作]",
                "desc": "管理与调试插件功能，需指定操作（不带操作时显示可用操作列表）",
                "subcommands": [
                    {"name": "clear", "desc": "清除记录的用户信息和发送时间"},
                    {"name": "task_status", "desc": "查看定时任务运行状态"},
                    {"name": "force_stop", "desc": "强制停止所有定时任务"},
                    {
                        "name": "force_start",
                        "desc": "强制启动定时任务（忽略配置中的 enabled 状态）",
                    },
                    {"name": "save_config", "desc": "强制保存配置文件"},
                    {
                        "name": "debug_info",
                        "desc": "调试用户上下文信息（故障排查用）",
                    },
                    {
                        "name": "debug_send",
                        "desc": "调试 LLM 生成的消息内容（故障排查用）",
                    },
                    {
                        "name": "debug_times",
                        "desc": "调试 AI 发送时间记录（故障排查用）",
                    },
                ],
            },
        ],
    },
]


def _usage(command: dict) -> str:
    """构造命令的完整用法字符串，如 ``/proactive test [类型]``。"""
    parts = [f"/{COMMAND_PREFIX}", command["name"]]
    if command.get("args"):
        parts.append(command["args"])
    return " ".join(parts)


def iter_commands():
    """遍历所有命令，产出 ``(category, command)`` 元组。"""
    for category in COMMAND_CATEGORIES:
        for command in category["commands"]:
            yield category, command


def get_command(name: str) -> dict | None:
    """按命令名查找命令定义，未找到返回 ``None``。"""
    for _category, command in iter_commands():
        if command["name"] == name:
            return command
    return None


def get_command_catalog() -> list:
    """返回命令目录（供 Web API / WebUI「命令」页消费）。

    Returns:
        形如::

            [
                {
                    "key": "basic",
                    "title": "基础命令",
                    "commands": [
                        {
                            "name": "status",
                            "usage": "/proactive status",
                            "admin": False,
                            "desc": "...",
                            "subcommands": [{"name": "...", "desc": "..."}, ...],
                        },
                        ...
                    ],
                },
                ...
            ]
    """
    catalog = []
    for category in COMMAND_CATEGORIES:
        commands = []
        for command in category["commands"]:
            commands.append(
                {
                    "name": command["name"],
                    "usage": _usage(command),
                    "admin": bool(command.get("admin", False)),
                    "desc": command.get("desc", ""),
                    "subcommands": [
                        {"name": sub["name"], "desc": sub.get("desc", "")}
                        for sub in command.get("subcommands", [])
                    ],
                }
            )
        catalog.append(
            {
                "key": category["key"],
                "title": category["title"],
                "commands": commands,
            }
        )
    return catalog


def build_help_text() -> str:
    """构建 ``/proactive help`` 的完整帮助文本（中文）。

    完全由命令目录派生，新增/修改命令只需改动 ``COMMAND_CATEGORIES``。
    """
    lines = ["🤖 AstrBot 主动回复插件（心念）"]
    for category in COMMAND_CATEGORIES:
        # 仅当分类内全部命令需要管理员时，才在标题上标注「仅管理员」
        all_admin = all(c.get("admin") for c in category["commands"])
        suffix = "（仅管理员可用）" if all_admin else ""
        lines.append("")
        lines.append(f"{category['title']}{suffix}:")
        for command in category["commands"]:
            admin_tag = " (管理员)" if command.get("admin") and not all_admin else ""
            lines.append(
                f"- `{_usage(command)}`{admin_tag} - {command.get('desc', '')}"
            )
            subcommands = command.get("subcommands", [])
            if subcommands:
                types_text = "、".join(sub["name"] for sub in subcommands)
                lines.append(f"  类型: {types_text}")
    lines.append("")
    lines.append("💡 详细配置请在 AstrBot 配置面板或插件 WebUI 中修改")
    return "\n".join(lines)


def build_subcommand_help_text(name: str) -> str:
    """构建某条带子命令的命令（如 ``test`` / ``show`` / ``manage``）的子命令帮助文本。

    当用户未指定子命令类型时调用，列出全部可用子命令及说明。
    """
    command = get_command(name)
    if not command or not command.get("subcommands"):
        return ""
    lines = [f"{command.get('desc', '')}\n\n可用类型:"]
    for sub in command["subcommands"]:
        lines.append(f"- `/{COMMAND_PREFIX} {name} {sub['name']}` - {sub['desc']}")
    return "\n".join(lines)
