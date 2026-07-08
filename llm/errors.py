"""主动消息链路中的可分类异常。"""


class ProactiveMessageError(RuntimeError):
    """可被调度层识别的主动消息异常。

    retryable 用于区分瞬时错误与配置、会话等永久错误，避免无意义地重试。
    """

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class MessageGenerationError(ProactiveMessageError):
    """主动消息生成失败。"""


class DuplicateMessageError(MessageGenerationError):
    """生成结果与上次主动消息重复。"""

    def __init__(
        self, generated_message: str, proactive_prompt_used: str | None = None
    ):
        super().__init__("生成结果与上次主动消息重复", retryable=True)
        self.generated_message = generated_message
        self.proactive_prompt_used = proactive_prompt_used


class MessageDeliveryError(ProactiveMessageError):
    """主动消息投递失败。"""
