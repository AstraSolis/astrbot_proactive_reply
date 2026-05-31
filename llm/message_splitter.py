"""
消息分割器

负责将 LLM 生成的主动消息按配置的模式分割为多条（模拟人类分段发送）。

同时对管理员配置的用户正则（custom / regex 模式）提供复杂度提示与长度保护，
以缓解灾难性回溯（ReDoS）风险：用户正则由管理员配置、待分割文本为有限的 LLM 输出，
因此采用"长度保护 + 复杂度日志提示"的轻量策略，而非引入额外依赖或执行超时。
"""

import re
from astrbot.api import logger

from ..constants import (
    MAX_SPLIT_TEXT_LENGTH,
    MAX_USER_REGEX_LENGTH,
    REDOS_RISK_PATTERN_HINTS,
)


class MessageSplitter:
    """消息分割器类（官方风格）"""

    # 旧版（legacy）分割模式正则表达式
    SPLIT_MODE_PATTERNS = {
        "backslash": r"\\",
        "newline": r"\n",
        "comma": r",",
        "semicolon": r";",
        "punctuation": r"[,;。!?]",
    }

    def __init__(self, config: dict):
        """初始化消息分割器

        Args:
            config: 配置字典
        """
        self.config = config
        self.split_words_pattern = None
        self.split_words = []
        self.split_regex_pattern = None
        self._initialize_split_patterns()

    @staticmethod
    def _warn_if_regex_risky(pattern: str, source: str):
        """对管理员配置的用户正则做复杂度提示（仅记录日志，不阻断）

        Args:
            pattern: 用户配置的正则表达式
            source: 来源描述（用于日志）
        """
        if not pattern:
            return
        if len(pattern) > MAX_USER_REGEX_LENGTH:
            logger.warning(
                f"心念 | ⚠️ {source} 正则长度 {len(pattern)} 超过建议上限 "
                f"{MAX_USER_REGEX_LENGTH}，复杂正则在长文本上可能导致性能问题"
            )
        for hint in REDOS_RISK_PATTERN_HINTS:
            if re.search(hint, pattern):
                logger.warning(
                    f"心念 | ⚠️ {source} 正则疑似包含嵌套量词，存在灾难性回溯（ReDoS）"
                    "风险，请确认其复杂度"
                )
                break

    def _initialize_split_patterns(self):
        """初始化分段模式（预编译正则表达式）"""
        split_config = self.config.get("message_split", {})
        split_mode = split_config.get("mode", "backslash")

        # 初始化分段词模式（words 模式 - 官方风格）
        self.split_words_pattern = None
        self.split_words = []
        if split_mode == "words":
            split_words = split_config.get("split_words", ["。", "？", "！", "~", "…"])
            if split_words:
                try:
                    # 按长度倒序排序，避免短词误匹配（官方实现）
                    escaped_words = sorted(
                        [re.escape(word) for word in split_words],
                        key=len,
                        reverse=True,
                    )
                    # 官方正则格式：(.*?(分段词1|分段词2|...)|.+$)
                    self.split_words_pattern = re.compile(
                        f"(.*?({'|'.join(escaped_words)})|.+$)", re.DOTALL
                    )
                    self.split_words = split_words
                    logger.debug(f"心念 | 初始化 words 模式，分段词: {split_words}")
                except re.error as e:
                    logger.error(f"心念 | ❌ 分段词模式初始化失败: {e}")
                    self.split_words_pattern = None

        # 初始化正则模式（regex 模式 - 官方风格）
        self.split_regex_pattern = None
        if split_mode == "regex":
            regex = split_config.get("regex", "")
            if regex:
                self._warn_if_regex_risky(regex, "regex 模式")
                try:
                    # 使用 DOTALL 和 MULTILINE 标志（官方实现）
                    self.split_regex_pattern = re.compile(
                        regex, re.DOTALL | re.MULTILINE
                    )
                    logger.debug(f"心念 | 初始化 regex 模式，正则: {regex}")
                except re.error as e:
                    logger.error(f"心念 | ❌ 正则表达式编译失败: {e}, 表达式: {regex}")
                    self.split_regex_pattern = None

        # custom 模式（legacy re.split）下也对用户正则做一次复杂度提示
        if split_mode == "custom":
            self._warn_if_regex_risky(
                split_config.get("custom_pattern", ""), "custom 模式"
            )

    def _is_text_too_long(self, text: str) -> bool:
        """文本是否超过参与正则分割的长度上限（ReDoS 长度保护）"""
        if len(text) > MAX_SPLIT_TEXT_LENGTH:
            logger.warning(
                f"心念 | ⚠️ 待分割文本长度 {len(text)} 超过上限 "
                f"{MAX_SPLIT_TEXT_LENGTH}，跳过正则分割并整条发送（ReDoS 保护）"
            )
            return True
        return False

    def split_message(self, text: str) -> tuple[list[str], str]:
        """根据配置的分割模式将文本分割为多条

        Args:
            text: 待分割的文本

        Returns:
            元组 (片段列表, 模式描述字符串)
        """
        split_config = self.config.get("message_split", {})
        split_mode = split_config.get("mode", "backslash")

        if split_mode == "words":
            # 官方风格：分段词列表模式
            message_parts = self._split_text_by_words(text)
            split_words_count = len(split_config.get("split_words", []))
            mode_display = f"分段词模式({split_words_count}个词)"
        elif split_mode == "regex":
            # 官方风格：正则表达式模式
            message_parts = self._split_text_by_regex(text)
            regex_preview = split_config.get("regex", "")[:30]
            mode_display = f"正则模式(/{regex_preview}{'...' if len(split_config.get('regex', '')) > 30 else ''}/)"
        else:
            # 向后兼容：使用旧的 re.split 逻辑
            message_parts = self._split_text_legacy(text, split_mode, split_config)
            if split_mode == "custom":
                split_pattern = split_config.get("custom_pattern", "")
                mode_display = f"自定义模式(/{split_pattern}/)"
            else:
                mode_display = f"{split_mode}模式"

        return message_parts, mode_display

    def _split_text_by_words(self, text: str) -> list[str]:
        """使用分段词列表分段文本（官方风格）

        Args:
            text: 待分割的文本

        Returns:
            分割后的文本片段列表
        """
        if not self.split_words_pattern:
            return [text]
        if self._is_text_too_long(text):
            return [text]

        segments = self.split_words_pattern.findall(text)
        result = []

        for seg in segments:
            if isinstance(seg, tuple):
                # findall 返回的是元组（捕获组）
                content = seg[0]
                if not isinstance(content, str):
                    continue

                # 去掉末尾的分段词（官方实现）
                for word in self.split_words:
                    if content.endswith(word):
                        content = content[: -len(word)]
                        break

                if content.strip():
                    result.append(content.strip())
            elif seg and seg.strip():
                result.append(seg.strip())

        return result if result else [text]

    def _split_text_by_regex(self, text: str) -> list[str]:
        """使用正则表达式分段文本（官方风格）

        Args:
            text: 待分割的文本

        Returns:
            分割后的文本片段列表
        """
        if not self.split_regex_pattern:
            return [text]
        if self._is_text_too_long(text):
            return [text]

        segments = self.split_regex_pattern.findall(text)
        result = []

        for seg in segments:
            if isinstance(seg, tuple):
                # 如果正则有多个捕获组，取第一个
                content = seg[0] if seg else ""
            else:
                content = seg

            if content and content.strip():
                result.append(content.strip())

        return result if result else [text]

    def _split_text_legacy(
        self, text: str, split_mode: str, split_config: dict
    ) -> list[str]:
        """使用旧的 re.split 方式分割（向后兼容）

        Args:
            text: 待分割的文本
            split_mode: 分割模式
            split_config: 分割配置

        Returns:
            分割后的文本片段列表
        """
        # 确定使用的正则表达式
        if split_mode == "custom":
            split_pattern = split_config.get("custom_pattern", "")
            if not split_pattern:
                logger.warning(
                    "心念 | ⚠️ custom 模式下未配置正则表达式，使用默认 backslash 模式"
                )
                split_pattern = self.SPLIT_MODE_PATTERNS["backslash"]
                split_mode = "backslash"
        else:
            split_pattern = self.SPLIT_MODE_PATTERNS.get(
                split_mode, self.SPLIT_MODE_PATTERNS["backslash"]
            )

        # 仅对用户可配置的 custom 模式做长度保护（内置模式正则简单，无回溯风险）
        if split_mode == "custom" and self._is_text_too_long(text):
            return [text]

        try:
            # 使用 re.split 分割
            message_parts = re.split(split_pattern, text)
            message_parts = [part.strip() for part in message_parts if part.strip()]
            return message_parts if message_parts else [text]
        except re.error as e:
            logger.error(
                f"心念 | ❌ 正则表达式错误: {e}, 模式: {split_mode}, 表达式: {split_pattern}"
            )
            return [text]
