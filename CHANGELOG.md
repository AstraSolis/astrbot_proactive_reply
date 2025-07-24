# 更新日志

所有重要的项目变更都会记录在这个文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v1.0.1] - 2025-07-24

### 重大架构改进
- **解决数据库耦合问题**：重构对话历史保存机制
  - **问题**：原始实现直接使用硬编码SQL语句操作数据库，与特定表结构紧密耦合
  - **解决方案**：实现框架抽象接口优先的多层保存机制
    - 第一层：使用 AstrBot 框架的 `conversation_manager.update_conversation` 标准接口
    - 第二层：改进的数据库直接操作（包含完整兼容性检查）
    - 第三层：备份文件保存（确保数据不丢失）
  - **技术突破**：通过方法签名分析确定正确的框架接口调用格式
  - **效果**：完全解耦数据库依赖，提高插件健壮性和兼容性

- **框架接口集成**：深度集成 AstrBot 框架标准接口
  - 发现并正确使用 `update_conversation(unified_msg_origin, conversation_id, history)` 方法
  - 实现正确的数据格式转换（JSON字符串 → List[Dict]）
  - 添加完整的错误处理和回退机制
  - 确保与框架更新的向前兼容性

### 代码质量优化
- **重构核心函数**：大幅提升代码可读性和可维护性
  - 将 `proactive_message_loop` 函数从120多行重构为52行主函数 + 6个职责单一的辅助函数
  - 拆分 `generate_proactive_message_with_llm` 函数为45行主函数 + 4个辅助函数
  - 重构 `add_message_to_conversation_history` 方法，实现多层保存机制
  - 每个函数职责明确，符合单一职责原则

- **异常处理全面改进**：提升代码稳定性和可维护性
  - **问题**：代码中存在超过30处宽泛的 `except Exception as e:` 异常捕获
  - **解决方案**：实现精确的异常类型处理
    - 文件操作：使用 `FileNotFoundError`, `PermissionError`, `OSError`, `json.JSONDecodeError` 等具体异常
    - 数据库操作：使用 `sqlite3.IntegrityError`, `sqlite3.OperationalError`, `sqlite3.DatabaseError` 等
    - 配置管理：使用 `KeyError`, `ValueError`, `AttributeError` 等
    - 异步任务：使用 `asyncio.CancelledError`, `asyncio.TimeoutError`, `RuntimeError` 等
    - 网络操作：使用 `ConnectionError`, `TimeoutError` 等
  - **新增辅助方法**：
    - `_validate_persistent_data()` - 验证持久化数据结构
    - `_backup_corrupted_file()` - 备份损坏的文件
    - `_save_config_safely()` - 安全的配置保存方法
    - `_verify_database_schema()` - 验证数据库表结构
  - **技术改进**：
    - 原子性文件写入（临时文件+重命名）
    - 超时控制和错误恢复机制
    - 输入参数验证和数据结构检查
    - 避免捕获系统级异常（KeyboardInterrupt, SystemExit）
  - **效果**：更精确的错误诊断、更容易调试、更稳定的程序运行

- **减少重复代码**：提高代码复用性
  - 添加 `_proactive_config` 和 `_user_config` 属性方法
  - 消除多处重复的配置获取代码
  - 统一配置访问模式，提高代码一致性

- **规范化数据持久化路径处理**：
  - 新增 `_get_plugin_data_dir()` 方法，使用标准的插件数据目录
  - 数据存储路径从推断配置路径改为 `data/plugins/astrbot_proactive_reply/`
  - 移除硬编码的 `/tmp` 回退路径，提供跨平台兼容的解决方案
  - 添加 `_migrate_old_persistent_data()` 方法，自动迁移现有数据
  - 持久化文件重命名为 `persistent_data.json`，添加版本标识
  - 确保数据与其他插件和系统文件隔离，提高安全性

- **函数拆分详情**：
  - `_should_terminate()` - 检查是否应该终止任务
  - `_is_proactive_enabled()` - 检查主动回复功能是否启用
  - `_get_target_sessions()` - 获取目标会话列表
  - `_send_messages_to_sessions()` - 向所有会话发送消息
  - `_calculate_wait_interval()` - 计算下一次执行的等待时间
  - `_wait_with_status_check()` - 分段等待并检查状态
  - `_get_llm_provider()` - 获取LLM提供商
  - `_get_proactive_prompt()` - 获取并处理主动对话提示词
  - `_get_persona_system_prompt()` - 获取人格系统提示词
  - `_build_combined_system_prompt()` - 构建组合系统提示词
  - `_save_conversation_safely()` - 安全保存对话（框架接口优先）
  - `_fallback_database_save()` - 数据库回退保存（包含兼容性检查）
  - `_backup_conversation_history()` - 备份对话历史到文件

## [v1.0.0] - 2025-07-23

### 核心功能
- **聊天附带用户信息**：自动在AI对话中附加用户信息
  - 自动获取用户昵称、用户ID、时间信息
  - 支持自定义时间格式和信息模板
  - 智能追加到系统提示末尾，不覆盖现有人格设置
  - 支持占位符：`{username}`, `{user_id}`, `{time}`, `{platform}`, `{chat_type}`

- **智能主动对话系统**：基于LLM的智能主动消息生成
  - 移除预设消息模板，改为LLM智能生成个性化主动消息
  - 深度集成AstrBot人格系统，自动组合人格提示词与主动对话指令
  - 支持主动对话默认人格配置，当无AstrBot人格时使用
  - 主动对话提示词列表，支持随机选择不同的对话风格
  - 基于用户信息和对话历史的上下文感知生成

- **历史记录功能增强**：基于对话历史的智能主动消息生成
  - 可配置是否附带历史记录（`include_history_enabled`）
  - 可配置历史记录条数（`history_message_count`，默认10条）
  - AI主动发送的消息自动添加到对话历史记录中，保持对话连贯性
  - 使用AstrBot官方API安全地获取聊天记录
  - 支持OpenAI格式的历史记录兼容性

### 时间管理系统
- **双时间模式支持**：
  - **固定间隔模式**：传统的固定时间间隔，可选随机延迟
  - **随机间隔模式**：完全随机的时间间隔（配置范围内随机）
- **活跃时间段设置**：只在指定时间段内发送消息
- **多会话管理**：支持多个会话的独立时间管理

### 用户界面
- **指令系统优化**：精简为9个逻辑化指令
  - **核心功能指令**（6个）：help, status, config, add_session, remove_session, restart
  - **测试功能指令**（1个指令，6种功能）：test [basic|llm|generation|prompt|placeholders|history]
  - **显示功能指令**（1个指令，2种功能）：show [prompt|users]
  - **管理功能指令**（1个指令，8种操作）：manage [clear|task_status|force_stop|force_start|save_config|debug_info|debug_send|debug_times]

- **可视化配置管理**：支持现代化的列表配置界面
  - 主动对话提示词列表：每个提示词可单独添加、编辑、删除
  - 目标会话列表：每个会话ID可单独管理
  - 支持拖拽排序和批量操作

### 技术特性
- **完全符合AstrBot插件开发规范**：使用官方API，无任何非标准功能
- **异步处理和错误恢复**：支持优雅的资源清理和任务管理
- **完整的日志记录和调试功能**：提供详细的调试和诊断工具
- **强化配置持久化**：双重持久化机制，确保用户信息在重启后不丢失
- **占位符系统**：支持丰富的占位符定制
  - 用户信息模板占位符：`{username}`, `{user_id}`, `{time}`, `{platform}`, `{chat_type}`
  - 主动对话提示词占位符：`{user_context}`, `{user_last_message_time}`, `{user_last_message_time_ago}`, `{username}`, `{platform}`, `{chat_type}`, `{ai_last_sent_time}`, `{current_time}`

### 兼容性
- 与AstrBot人格系统完全兼容
- 与AstrBot对话管理系统完全兼容
- 支持所有AstrBot支持的消息平台
- 支持可视化配置管理

---

## 版本说明

### 版本号格式
本项目使用语义化版本号：`主版本号.次版本号.修订号`

- **主版本号**：不兼容的 API 修改
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

### 更新类型
- **新增功能** - 新的功能特性
- **改进** - 对现有功能的改进
- **修复** - 错误修复
- **变更** - 可能影响兼容性的变更
- **移除** - 移除的功能
- **安全** - 安全相关的修复

---

## 贡献指南

如果您想为项目贡献代码或报告问题，请：

1. 在 [GitHub Issues](https://github.com/AstraSolis/astrbot_proactive_reply/issues) 中报告问题
2. 提交 Pull Request 时请详细说明变更内容
3. 确保新功能有相应的测试和文档

感谢您的贡献！
