# 更新日志

本项目的所有重要更改都将记录在此文件中。

## [Unreleased]

## [1.5.0] - 2026-02-06

### 新增

- 添加历史记录保存模式配置
  - 新增 `history_save_mode` 配置项，支持三种模式：
    - `default`: 默认系统触发标记 `<SYSTEM_TRIGGER: ...>`
    - `proactive_prompt`: 使用当次触发的主动对话提示词（已替换占位符）
    - `custom`: 自定义内容（支持占位符）
  - 新增 `custom_history_prompt` 配置项，用于自定义模式的提示词模板
  - 支持所有标准占位符：`{username}`、`{current_time}`、`{unreplied_count}` 等

- 添加星期占位符 `{weekday}`
  - 输出格式：星期一、星期二...星期日
  - 支持场景：主动对话提示词、用户信息模板、自定义历史记录提示词

### 重构

- 统一默认配置来源为 schema 文件
  - 移除 `ConfigManager` 中硬编码的 `DEFAULT_CONFIG`
  - 新增 `_load_default_config_from_schema()` 方法从 `_conf_schema.json` 动态读取默认值
  - 确保单一数据源，避免配置默认值不一致

### 修复

- 修复混合计时器配置变化后不生效的问题
  - 新增配置签名机制，自动检测计时配置变化
  - 配置变化时自动清除计时器并重新计算
  - 配置签名持久化，支持跨插件重载的检测
  - 移除会话时同步清理对应计时器

### 其他

- 调整图标大小

## [1.4.0] - 2026-02-01

### 新增

- 添加主动消息重复检测功能
  - 检测生成的消息是否与上次发送的内容重复
  - 重复时自动重新生成（最多重试3次）
  - 新增 `duplicate_detection_enabled` 配置项（默认启用）

- 添加未回复计数器功能
  - 新增 `{unreplied_count}` 占位符，追踪用户连续未回复次数
  - Bot 发送主动消息后计数 +1，用户回复后重置为 0

### 增强

- 优化主动对话提示词与时间感知系统
  - **注意**：如果使用默认配置，请手动更新配置文件中的提示词，或删除插件配置重新安装以获取最新的提示词
  - 修改提示词：
    - 时间感知增强提示词:
      ```
      <TIME_GUIDE: 核心时间规则（必须严格遵守）
      1. 真实性：系统提供的时间信息是你唯一可信的时间来源，禁止编造或推测。
      2. 自然回应：优先使用自然口语（如"刚才"、"大半夜"、"好久不见"）替代数字报时，仅在用户明确询问时提供精确时间。
      3. 状态映射：依据当前时间调整人设的生理状态（如深夜困倦、饭点饥饿）。
      4. 上下文感知：根据与用户上次对话的时间差（{user_last_message_time_ago}）调整语气（如很久没见要表现出想念，刚聊过则保持连贯）。>
      ```
    - 用户信息模板:
      ```
      [对话信息] 用户名称:{username},时间:{time},上次聊天时间:{user_last_message_time}
      ```
    - 睡眠时间提示:
      ```
      <SLEEP_MODE: 当前处于睡眠时间段，你正处于休眠状态。若用户此时发送消息，请以符合人设的自然方式回应，可表现出困倦、迷糊等状态>
      ```
    - 主动对话提示词:
      ```
      现在是{current_time}，用户（{username}）上次发消息是{user_last_message_time_ago}（{user_last_message_time}），已连续{unreplied_count}次未回复，请主动发起自然的对话
      ```
      ```
      用户（{username}）在{user_last_message_time}发过消息，距今{user_last_message_time_ago}，当前时间{current_time}，连续未回复{unreplied_count}次，请友好地问候
      ```
      ```
      现在是{current_time}，想到了用户（{username}），上次互动是{user_last_message_time_ago}，连续{unreplied_count}次没收到回复，请主动关心一下
      ```
      ```
      用户（{username}）已经{user_last_message_time_ago}没有消息了（上次:{user_last_message_time}），当前时间{current_time}，未回复次数:{unreplied_count}，请选择一个话题聊聊
      ```
      ```
      现在是{current_time}，用户（{username}）上次活跃在{user_last_message_time}（{user_last_message_time_ago}），连续{unreplied_count}次未读，请分享一些想法或问候
      ```
      ```
      当前时间{current_time}，距离和用户（{username}）上次聊天已经{user_last_message_time_ago}，已发送{unreplied_count}条未回复消息，请轻松地发起对话
      ```
      ```
      用户（{username}）于{user_last_message_time}最后活跃，相隔{user_last_message_time_ago}，现在是{current_time}，连续未回复{unreplied_count}次，请自然地打个招呼
      ```
      ```
      用户（{username}）于{user_last_message_time}最后活跃，相隔{user_last_message_time_ago}，现在是{current_time}，连续未回复{unreplied_count}次，请自然地打个招呼
      ```

## [1.3.4] - 2026-01-21

### 修复

- 修复主动消息保存后导致 AI 无法正常回复的问题
  - 调整 `add_message_pair` 格式优先级：优先使用字符串格式，避免 Pydantic 验证失败
  - 添加 `/proactive manage fix_history` 命令，可修复旧版插件保存的列表格式历史记录

### 重要!!!如果你使用了v1.3.3版本,出现了`Error occurred while processing agent: 2 validation errors for Messagecontent.str`错误,请使用`/proactive manage fix_history`命令修复

## [1.3.3] - 2026-01-20

### 增强

- 优化主动对话历史记录的系统触发标记
  - 使用 <SYSTEM_TRIGGER> 标签格式替代简单的中括号标记
  - 明确标注"非用户实际发言"避免 AI 误解为用户消息
  - 嵌入真实触发时间戳提供精确的对话上下文

### 修复

- 主动消息无法获取真实对话历史的问题
  - 优先读取 `conversation.content` 字段 (AstrBot v4+)，回退到 `history` 字段保持向后兼容
  - 支持列表格式和 JSON 字符串格式

## [1.3.2] - 2026-01-08

### 修复

- 修复主动消息历史未附带到 LLM 请求的问题
- 解决了主动消息保存到历史后，用户对话时 AI 无法获取之前的主动消息的问题

## [1.3.1] - 2026-01-07

### 修复

- 修复人格缓存导致切换后不更新的问题，从 `provider_settings.default_personality` 动态获取默认人格
- 解决了在 AstrBot WebUI 切换全局默认人格后，主动消息仍使用旧人格的问题

## [1.3.0] - 2025-12-29

### 新增

- 重构主动消息为混合计时器模式，采用更智能的计时策略
  - AI 发消息后自动刷新计时器，避免频繁打扰
  - 智能睡眠（1~300秒），减少无效轮询
  - 新增 `session_next_fire_times` 和 `session_sleep_remaining` 运行时数据
  - `/proactive status` 现在显示各会话的下次发送时间
- 睡眠时间功能增强，重构活跃时间段为睡眠时间功能
  - 新增 `wake_send_mode` 配置项，支持三种睡眠结束模式：跳过/立即发送/延后发送
  - 延后发送模式保存并恢复睡眠前剩余计时
  - 睡眠时间内不发送主动消息
  - 睡眠时间内用户发消息时附加睡眠提示到系统提示词
- 时间感知增强提示词支持配置化，新增 `time_awareness` 配置节，支持启用/禁用时间引导
- 统一占位符支持，用户信息模板与主动对话提示词支持相同的占位符
  - 新增: `{current_time}`, `{user_last_message_time}`, `{user_last_message}`
  - 添加 `_safe_format_template()` 使用正则替换避免特殊字符问题

### 变更

- 优化主动对话提示词，改进内置的主动对话提示词质量
- 精简时间感知增强提示词，移除冗余内容

### 文档

- 添加平台配置和跨平台使用注意事项
- 将 "定时发送" 修改为 "主动对话" 以更准确表达功能
- 优化插件行为页面的命令描述格式
- 更新插件描述和标签

## [1.2.1] - 2025-12-12

### 新增

- 重构主动消息计时逻辑，从固定间隔循环改为基于 AI 最后一条消息的时间计时 ([#2](https://github.com/AstraSolis/astrbot_proactive_reply/issues/2))
  - 命令消息（以 `/` 开头）不再触发时间记录
  - 支持每个会话独立的随机间隔，发送后自动生成新的随机值
  - 新增方法：`get_session_target_interval`、`get_minutes_since_ai_last_message`
- 配置面板新增 Star 引导，在配置面板顶部添加 GitHub Star 引导

### 变更

- 分离运行时数据存储，创建 `RuntimeDataStore` 单例类，独立管理运行时数据
  - 将 `session_user_info`、`ai_last_sent_times`、`last_sent_times` 从 config 对象中分离
  - 更新 `PersistenceManager` 使用 `RuntimeDataStore` 加载/保存数据
  - 从 `_conf_schema.json` 移除动态数据项定义

### 修复

- 修复配置加载状态检测问题，解决了启动时始终提示"首次运行"的问题
- 修复 `show_config` 方法中 `sessions` 变量未定义导致 `/proactive config` 命令执行失败的问题
- 完善测试命令功能
  - `test history`: 显示详细历史记录内容而非仅显示条数
  - `test prompt`: 使用 `build_combined_system_prompt` 保持与实际生成逻辑一致

## [1.2.0] - 2025-11-27

### 重构
- 模块化重构插件架构 - 将原有单体 main.py 拆分为清晰的模块结构，提升代码可维护性和可扩展性
- 持久化数据存储路径优化 - 调整数据存储位置，提升安全性和规范性

### 修复
- 修复命令处理器参数不匹配 - 解决命令执行时参数传递错误导致的执行失败问题
- 修复命令参数错误 - 优化测试与配置显示功能，提升命令系统稳定性

### 其他
- 插件名称改为"心念"
- 更换插件 Logo 

## [1.1.0] - 2025-11-23

### 新增

- 语句分割功能
  - 使用正则表达式自定义分割规则
  - 提供了多种预设分割模式（包括反斜线分割、换行分割等）
- 时间感知功能
  - 改进了时间占位符的处理逻辑
  - 优化了提示词模板，加强了对 AI 输出时间的约束

## [1.0.1] - 2025-07-24

### 修复

- 重构 proactive_message_loop 函数
- 使用 AstrBot 标准 conversation_manager.update_conversation 接口
- 规范化数据持久化路径处理,新增 _get_plugin_data_dir() 方法使用标准插件数据目录
- 精确异常类型处理替代宽泛Exception捕获

## [1.0.0] - 2025-07-23

### 正式版上线

- **智能用户信息附加** - 自动在 AI 对话中附加用户信息，支持自定义模板和占位符
- **基于 LLM 的主动对话** - 告别预设模板，使用 LLM 生成个性化主动消息
- **人格系统深度集成** - 自动检测并组合 AstrBot 人格设置与主动对话指令
- **历史记录功能增强** - 支持基于对话历史的智能主动消息生成，保持对话连贯性
- **双时间模式** - 支持固定间隔和随机间隔两种时间模式