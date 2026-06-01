"""
时间表（日历事项）内存存储

仿 ``runtime_data`` 的单例模式，仅持有「时间表事项」的内存副本与纯逻辑（匹配、
拼接），不做任何文件 IO、也不依赖 AstrBot context。

设计目标（与占位符注册表一致的单一真相源）：
- ``CalendarStore`` 是「当天事项」取值逻辑的唯一来源，``placeholder_utils`` 与
  ``CalendarManager`` 均从本单例读取，避免多处实现漂移。
- 文件读写、CRUD 与校验由 ``core/calendar_manager.py`` 负责，写入后回填本单例。

事项数据结构（单条）::

    {
        "id": "<uuid hex>",   # 稳定标识，供编辑/删除定位
        "year": 2026,          # 基准年（首次生效年份，也用于 UI 显示）
        "month": 1,            # 1-12
        "day": 1,              # 1-31（闰日 2-29 仅在闰年匹配）
        "text": "元旦",        # 事项描述
        "repeat": 0            # 重复规则，见下方常量
    }

重复规则（``repeat`` 取值语义）：
- ``REPEAT_NONE``（0）：仅在「基准年」当天生效。
- 1..4：基准年 + 之后 N 年，共 ``N + 1`` 年生效。
- ``REPEAT_FOREVER``（-1）：每年重复（永久），忽略年份，仅按月-日匹配。
"""

from astrbot.api import logger

# 重复规则常量
REPEAT_NONE = 0
REPEAT_FOREVER = -1
# 有限重复的最大年数（与 WebUI 下拉一致：1/2/3/4 年）
MAX_FINITE_REPEAT = 4

# 各月最大天数（2 月按 29 以允许闰日事项，闰日仅在闰年自然匹配）
_MONTH_MAX_DAYS = {
    1: 31,
    2: 29,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}

# 单条事项文本长度上限（防止超长文本污染提示词 / 拖慢渲染）
MAX_EVENT_TEXT_LENGTH = 200
# 事项数量上限（防滥用导致文件膨胀 / 前端卡顿）
MAX_EVENTS = 2000


def valid_month_day(month: int, day: int) -> bool:
    """校验 (month, day) 是否为合法的「年年可重复」日期"""
    if month not in _MONTH_MAX_DAYS:
        return False
    return 1 <= day <= _MONTH_MAX_DAYS[month]


def normalize_repeat(repeat) -> int:
    """将任意输入规整为合法的 repeat 取值

    非法 / 越界值回退为 ``REPEAT_NONE``。
    """
    try:
        value = int(repeat)
    except (TypeError, ValueError):
        return REPEAT_NONE
    if value == REPEAT_FOREVER:
        return REPEAT_FOREVER
    if 0 <= value <= MAX_FINITE_REPEAT:
        return value
    return REPEAT_NONE


def event_active_in_year(event: dict, year: int) -> bool:
    """判断事项在指定年份是否生效（按 repeat 规则）"""
    repeat = normalize_repeat(event.get("repeat", REPEAT_NONE))
    if repeat == REPEAT_FOREVER:
        return True
    try:
        base_year = int(event.get("year"))
    except (TypeError, ValueError):
        return False
    return base_year <= year <= base_year + repeat


class CalendarStore:
    """时间表事项内存存储（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 已校验的事项列表（保持插入顺序）
        self.events: list = []
        logger.debug("心念 | CalendarStore 初始化完成")

    def set_events(self, events: list) -> None:
        """整体替换事项列表（调用方应已完成校验/规整）"""
        self.events = list(events) if isinstance(events, list) else []

    def clear(self) -> None:
        """清空全部事项"""
        self.events = []

    def events_for_date(self, year: int, month: int, day: int) -> list:
        """返回指定日期生效的事项（保持插入顺序）"""
        result = []
        for event in self.events:
            if event.get("month") == month and event.get("day") == day:
                if event_active_in_year(event, year):
                    result.append(event)
        return result

    def today_text(self, now, separator: str = "、", empty_text: str = "") -> str:
        """拼接「今天」的所有事项文本

        Args:
            now: 当前时间（datetime，使用机器人所在时区）
            separator: 多条事项之间的分隔符
            empty_text: 当天无事项时返回的文本（默认空字符串）

        Returns:
            拼接后的事项文本；无事项时返回 ``empty_text``
        """
        events = self.events_for_date(now.year, now.month, now.day)
        texts = [str(e.get("text", "")).strip() for e in events]
        texts = [text for text in texts if text]
        if not texts:
            return empty_text
        return separator.join(texts)


# 全局单例实例
calendar_store = CalendarStore()
