# 更新日志

所有重要的项目变更都会记录在这个文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v1.0.0] - 2025-07-21

### 新增功能
- 初始版本发布
- 实现聊天附带用户信息功能
  - 自动获取用户昵称、用户ID、时间信息
  - 支持自定义时间格式
  - 支持自定义信息模板
  - 智能追加到系统提示，不覆盖人格设置
  - 自动记录用户消息时间用于占位符
- 实现定时主动发送消息功能
  - 支持多会话管理
  - 支持多消息模板随机选择
  - 可配置发送间隔和随机延迟
  - 支持活跃时间段设置
  - 支持引号格式的消息模板解析
  - 消息模板支持时间占位符
- 占位符系统
  - 消息模板占位符：`{time}`, `{last_sent_time}`, `{user_last_message_time}`
  - 用户信息模板占位符：`{username}`, `{user_id}`, `{time}`, `{platform}`, `{chat_type}`
- 提供完整的管理指令系统
  - `/proactive status` - 查看插件状态
  - `/proactive current_session` - 显示当前会话ID和状态
  - `/proactive add_session` - 添加当前会话到定时发送列表
  - `/proactive remove_session` - 移除当前会话
  - `/proactive test` - 测试主动消息发送
  - `/proactive restart` - 重启定时任务
  - `/proactive debug` - 调试用户信息
  - `/proactive test_llm` - 测试LLM请求
  - `/proactive test_template` - 测试模板占位符替换
  - `/proactive show_user_info` - 显示记录的用户信息
  - `/proactive clear_records` - 清除记录数据
  - `/proactive task_status` - 检查定时任务状态
  - `/proactive debug_send` - 调试定时发送功能
  - `/proactive force_start` - 强制启动定时任务
  - `/proactive config` - 显示完整配置
  - `/proactive help` - 显示帮助信息

### 技术特性
- 完全符合 AstrBot 插件开发规范
- 使用官方 API，无任何非标准功能
- 支持异步处理和错误恢复
- 完整的日志记录和调试功能
- 优雅的资源清理和任务管理
- 人格系统友好，智能追加不覆盖现有设置
- 自动配置检查和补充机制
- 安全的占位符替换机制
- 强化的定时任务停止机制
- 详细的调试和诊断工具

### 兼容性
- 与 AstrBot 人格系统完全兼容
- 与 AstrBot 对话管理系统完全兼容
- 支持所有 AstrBot 支持的消息平台
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
