# AstrBot 主动回复插件

一个支持聊天附带用户信息和定时主动发送消息的 AstrBot 插件。

## 功能特性

### 聊天附带用户信息
- 自动在 AI 对话中附加用户信息（用户名、用户ID）
- 自动附加当前时间信息
- 支持自定义时间格式
- 支持自定义信息模板
- **智能追加**：不会覆盖现有人格设置，而是追加到系统提示末尾

### 智能主动对话系统
- **基于LLM的智能生成**：不再使用预设模板，而是通过LLM生成个性化主动消息
- **人格系统兼容**：自动检测并组合AstrBot人格设置与主动对话指令
- **多样化对话风格**：支持多个主动对话提示词，随机选择不同的对话风格
- **上下文感知**：基于用户信息和对话历史生成更自然的主动消息
- **🆕 对话历史记录**：AI主动发送的消息会自动添加到对话历史中
  - 解决了上下文断裂问题，用户下次发消息时AI能看到完整对话
  - 支持多种保存方式，确保历史记录的可靠性
- **支持两种时间模式**：
  - **固定间隔模式**：固定时间间隔，可选随机延迟
  - **随机间隔模式**：每次在设定范围内随机选择等待时间（如1分钟到1小时随机）
- 支持活跃时间段设置
- 支持多会话管理
- **可视化配置管理**：提示词和会话列表支持单独添加、编辑、删除

## 安装方法

1. 将插件文件放置到 AstrBot 的 `data/plugins/astrbot_proactive_reply/` 目录下
2. 重启 AstrBot 或在管理面板中重载插件
3. 在管理面板的插件管理中配置相关参数

## 配置文件位置

- **插件配置文件**：`data/config/astrbot_proactive_reply_config.json`
- **配置模式文件**：`data/plugins/astrbot_proactive_reply/_conf_schema.json`

**提示**：
- 推荐通过 AstrBot 管理面板进行配置，会自动生成和保存配置文件
- 如需手动编辑配置，请参考 `_conf_schema.json` 中的配置结构
- 配置修改后需要重载插件才能生效

## 配置说明

### 用户信息附加设置
- **时间格式**：时间显示格式（Python datetime 格式）
- **信息模板**：用户信息的显示模板，支持占位符。会追加到现有系统提示末尾，不会覆盖人格设置
  - 支持的占位符：`{username}`, `{user_id}`, `{time}`, `{platform}`, `{chat_type}`

### 智能主动对话设置
- **启用功能**：是否启用智能主动对话功能
- **主动对话默认人格**：当没有AstrBot人格时使用的默认人格设定
- **主动对话提示词列表**：多个提示词选项，系统会随机选择一个来指导LLM生成主动消息
  - 支持可视化列表管理，每个提示词可单独添加、编辑、删除
  - 支持 `{user_context}` 占位符来插入用户信息
- **时间模式**：选择时间模式
  - `fixed_interval`：固定间隔模式（传统模式）
  - `random_interval`：随机间隔模式（新增）
- **固定间隔模式设置**：
  - **发送间隔**：每隔多少分钟发送一次消息
  - **随机延迟**：在基础间隔上增加随机延迟时间
  - **延迟范围**：随机延迟的最小和最大值
- **随机间隔模式设置**：
  - **最小间隔**：随机间隔的最小时间（分钟）
  - **最大间隔**：随机间隔的最大时间（分钟）
- **目标会话列表**：需要发送消息的会话ID列表
  - 支持可视化列表管理，每个会话ID可单独添加、编辑、删除
- **活跃时间**：只在指定时间段内发送消息

## 使用指南

### 基本指令

```
/proactive help            # 显示帮助信息
/proactive status          # 查看插件状态
/proactive current_session # 显示当前会话ID和状态
/proactive add_session     # 将当前会话添加到定时发送列表
/proactive remove_session  # 将当前会话从定时发送列表移除
/proactive test            # 测试发送一条主动消息
/proactive restart         # 重启定时任务（配置更改后使用）
/proactive debug               # 调试用户信息，查看AI收到的信息
/proactive test_llm            # 测试LLM请求，实际体验用户信息附加功能
/proactive test_llm_generation # 测试LLM生成主动消息功能
/proactive test_prompt         # 测试系统提示词构建过程
/proactive debug_send          # 调试LLM主动发送功能
```

### 快速开始

1. **配置用户信息模板**：
   - 用户信息功能始终启用
   - 在管理面板中自定义信息模板
   - 通过模板控制显示哪些信息（用户名、ID、时间等）

2. **设置智能主动对话**：
   - 在管理面板中启用"智能主动对话功能"
   - 配置主动对话默认人格（当无AstrBot人格时使用）
   - 配置主动对话提示词列表（可添加多个不同风格的提示词）
   - 选择时间模式：
     - **固定间隔模式**：设置固定间隔时间，可选随机延迟
     - **随机间隔模式**：设置最小和最大间隔时间，每次随机选择
   - 设置活跃时间段（如 9:00-22:00）
   - 使用 `/proactive current_session` 查看当前会话
   - 使用 `/proactive add_session` 添加当前会话到发送列表

3. **测试功能**：
   - 使用 `/proactive debug` 查看AI收到的用户信息
   - 使用 `/proactive test_llm` 实际测试用户信息附加功能
   - 使用 `/proactive test_llm_generation` 测试LLM生成主动消息
   - 使用 `/proactive test_prompt` 查看系统提示词构建过程
   - 使用 `/proactive test` 测试主动消息发送
   - 使用 `/proactive status` 查看插件状态

## 配置示例

### 用户信息模板示例

**默认模板**（推荐）：
```
[对话信息] 用户：{username}，时间：{time}
```

**详细信息模板**：
```
[对话信息] 用户：{username}（ID：{user_id}），时间：{time}，平台：{platform}（{chat_type}）
```

**最简模板**（只显示用户名）：
```
用户：{username}
```

**重要提示**：
- 用户信息会追加到现有系统提示的末尾，不会覆盖您设置的人格
- 建议保持模板简洁，避免与人格设置产生冲突
- 不想显示某项信息？直接从模板中删除对应的占位符即可！

### 主动对话提示词示例

**基础提示词列表**：
```
主动问候用户，询问近况
分享有趣话题，发起轻松对话
关心用户情况，温暖问候
友好交流，分享今日想法
轻松聊天，询问用户心情
```

**详细提示词示例**：
```
现在你要主动向用户发起对话，就像一个朋友在问候一样。请生成一条简短（1-2句话）、自然、有趣的主动问候消息
请主动和用户聊天，询问他们的近况或分享一些有趣的话题，保持轻松友好的语调
作为朋友，请主动关心一下用户最近的情况，发起一个温暖的对话
请以轻松友好的方式主动和用户交流，可以分享一些有趣的内容或询问用户的想法
```

**使用占位符的提示词示例**：
```
现在是 {current_time}，用户 {username} 上次发消息是在 {user_last_message_time}，请主动问候用户
{username} 在 {platform} 上已经有一段时间没有活跃了，上次发消息是 {user_last_message_time_ago}，请友好地询问近况
用户 {username} 在 {chat_type} 中，{user_last_message_time_ago} 发过消息，请生成一条温暖的问候消息
根据以下用户信息主动发起对话：{user_context}
用户 {username} {user_last_message_time_ago} 活跃过，现在是 {current_time}，请主动关心一下
```

**主动对话提示词支持的占位符**：
- `{user_context}` - 完整的用户上下文信息（包含用户名、平台、时间等）
- `{user_last_message_time}` - 用户上次主动发送消息的时间
- `{user_last_message_time_ago}` - 用户上次主动发送消息的相对时间（如"5分钟前"、"1小时前"）
- `{username}` - 用户昵称
- `{platform}` - 平台名称（如：aiocqhttp、telegram等）
- `{chat_type}` - 聊天类型（群聊/私聊）
- `{ai_last_sent_time}` - AI上次发送消息的时间
- `{current_time}` - 当前时间

**用户信息模板支持的占位符**：
- `{username}` - 用户名
- `{user_id}` - 用户ID
- `{time}` - 当前时间
- `{platform}` - 平台名
- `{chat_type}` - 聊天类型（群聊/私聊）

### 时间模式配置示例

**固定间隔模式**（传统模式）：
```json
{
  "timing_mode": "fixed_interval",
  "interval_minutes": 600,
  "random_delay_enabled": true,
  "min_random_minutes": 0,
  "max_random_minutes": 30
}
```
- 每600分钟（10小时）发送一次，额外随机延迟0-30分钟
- 实际间隔：600-630分钟（10-10.5小时）

**随机间隔模式**（新功能）：
```json
{
  "timing_mode": "random_interval",
  "random_min_minutes": 600,
  "random_max_minutes": 1200
}
```
- 每次在600-1200分钟（10-20小时）之间随机选择等待时间
- 更自然的发送节奏，模拟真实用户行为

## 测试指南

### 如何测试用户信息附加功能

1. **查看调试信息**：
   ```
   /proactive debug
   ```
   这个指令会显示：
   - 当前用户的原始信息（昵称、ID等）
   - 插件配置状态
   - AI将收到的完整用户信息

2. **实际测试LLM请求**：
   ```
   /proactive test_llm
   ```
   这个指令会：
   - 发送一个测试消息给AI
   - 自动附加用户信息
   - 让您直接体验功能效果

3. **查看日志**：
   在AstrBot日志中查看详细的用户信息添加过程

### 如何测试智能主动对话功能

1. **查看当前会话**：
   ```
   /proactive current_session
   ```

2. **添加当前会话**：
   ```
   /proactive add_session
   ```

3. **测试LLM生成**：
   ```
   /proactive test_llm_generation
   ```

4. **测试系统提示词构建**：
   ```
   /proactive test_prompt
   ```

5. **测试立即发送**：
   ```
   /proactive test
   ```

6. **调试发送过程**：
   ```
   /proactive debug_send
   ```

7. **查看状态**：
   ```
   /proactive status
   ```

## 与 AstrBot 系统的兼容性

### 人格系统深度集成
- **智能人格检测**：自动检测当前会话使用的AstrBot人格设置
- **人格组合机制**：将AstrBot人格提示词与主动对话指令智能组合
- **默认人格支持**：当无AstrBot人格时，使用配置的主动对话默认人格
- **用户信息追加**：用户信息追加到系统提示末尾，保持现有人格完整性
- **支持所有人格**：无论使用默认人格还是自定义人格，都能正常工作

### 对话管理兼容
- **保持对话连续性**：不影响 AstrBot 的对话管理功能
- **支持多会话**：每个会话的用户信息独立处理
- **历史记录完整**：不影响对话历史的存储和检索

## 技术特性

- 完全符合 AstrBot 插件开发规范
- 使用官方 API，无任何非标准功能
- 支持异步处理和错误恢复
- 完整的日志记录和调试功能
- 优雅的资源清理
- **人格系统深度集成**：自动检测并组合AstrBot人格与主动对话指令
- **智能LLM调用**：使用底层LLM API生成个性化主动消息
- **多格式配置解析**：支持列表、JSON、传统换行格式的自动识别
- **可视化配置管理**：支持现代化的列表配置界面

## 开发信息

- **作者**：AstraSolis
- **版本**：v1.0.0
- **许可证**：[LICENSE](LICENSE)
- **项目地址**：https://github.com/AstraSolis/astrbot_proactive_reply
- **更新日志**：[CHANGELOG.md](CHANGELOG.md)

## 常见问题

### Q: 为什么重启AstrBot后主动发送功能停止了？
A: 请检查配置中的"启用功能"是否为true，重启后需要重新启用。

### Q: 为什么重启后用户信息丢失了？
A: 插件使用双重持久化机制保存用户信息：
1. **配置文件保存**：保存到AstrBot的配置文件中
2. **独立持久化文件**：保存到独立的数据文件中，避免配置重置影响

如果重启后信息仍然丢失，请：
1. 使用 `/proactive debug_config` 检查配置文件状态
2. 使用 `/proactive debug_persistent` 检查独立持久化文件状态
3. 使用 `/proactive force_save_config` 强制保存配置
4. 查看日志中的持久化保存状态

### Q: 为什么没有收到主动消息？
A: 请检查：
1. 是否启用了主动发送功能
2. 当前时间是否在活跃时间段内
3. 是否已添加当前会话到发送列表
4. LLM服务是否正常工作

### Q: 如何调试插件问题？
A: 使用以下调试指令：
- `/proactive status` - 查看整体状态
- `/proactive debug` - 查看用户信息处理
- `/proactive debug_config` - 检查配置文件持久化状态
- `/proactive debug_persistent` - 检查独立持久化文件状态
- `/proactive test_llm_generation` - 测试LLM生成功能
- `/proactive test_placeholders` - 测试占位符替换功能
- `/proactive task_status` - 检查定时任务状态

## 问题反馈

如果您在使用过程中遇到问题，请在 [GitHub Issues](https://github.com/AstraSolis/astrbot_proactive_reply/issues) 中反馈。

## 贡献

欢迎提交 Pull Request 来改进这个插件！
