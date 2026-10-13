"""Read trip details from the user's question with plain rules.

The LLM extractor sometimes misreads dates (it once turned 8月30日到9月2日 into a trip
ending on 8月31日). Anything this parser finds overrides the LLM's value; anything it
cannot find is left to the LLM.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from .rules import TIER1, TIER2, UNCOVERED

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
DATE = r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"
RANGE = re.compile(DATE + r"\s*(?:到|至|-|~|—|－)\s*(?:" + DATE + r"|(\d{1,2})\s*[日号])")
SINGLE = re.compile(DATE)
NIGHTS = re.compile(r"(?:住了?|住宿)?\s*(\d+|[一二两三四五六七八九十]+)\s*(?:个)?晚")
PRICE = re.compile(r"(?:每晚|一晚|房价|住宿费)\s*(?:是|为)?\s*(\d+(?:\.\d+)?)\s*元|(\d+(?:\.\d+)?)\s*元\s*(?:/|每|一)\s*晚")
CITIES = sorted(TIER1 | TIER2 | UNCOVERED, key=len, reverse=True)
CITY = re.compile(r"去(?P<c>[一-龥]{2,4}?)(?:市)?(?:出差|参加|开会|培训|学习|办事|调研)")
FULL_MEALS = re.compile(r"(统一安排|安排了?全天|全天.*?用餐|包吃|全部.*?用餐)")
PART_MEALS = re.compile(r"(只安排|仅安排|安排了?(?:一顿|午饭|午餐|晚饭|晚餐|早饭|早餐)|只管(?:午饭|晚饭|早饭))")


def _num(text: str) -> int:
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + CN_NUM[text[1]]
    if text.endswith("十"):
        return CN_NUM[text[0]] * 10
    return CN_NUM.get(text, 0)


@dataclass
class ParsedTrip:
    city: str = ""
    start: date | None = None
    end: date | None = None
    nights: int | None = None
    price: float | None = None
    meals: dict[date, str] = field(default_factory=dict)


def parse_trip(question: str, today: date) -> ParsedTrip:
    p = ParsedTrip()
    year = today.year

    m = RANGE.search(question)
    if m:
        y1, m1, d1, y2, m2, d2, d_only = m.groups()
        y1 = int(y1) if y1 else year
        p.start = date(y1, int(m1), int(d1))
        if d_only:
            p.end = date(y1, int(m1), int(d_only))
        else:
            p.end = date(int(y2) if y2 else y1, int(m2), int(d2))
    else:
        single = SINGLE.findall(question)
        if len(single) == 1:  # a one-day trip
            y, mo, d = single[0]
            p.start = p.end = date(int(y) if y else year, int(mo), int(d))

    m = NIGHTS.search(question)
    if m:
        p.nights = _num(m.group(1))
    m = PRICE.search(question)
    if m:
        p.price = float(m.group(1) or m.group(2))

    m = CITY.search(question)
    if m:
        p.city = m.group("c")
    else:
        p.city = next((c for c in CITIES if c in question), "")

    # Meals provided on a named day, e.g. "21日对方统一安排了全天用餐" or "11日对方只安排了午饭".
    if p.start:
        for m in re.finditer(r"(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*[日号][^，。,；;]*", question):
            clause = m.group(0)
            kind = "partial" if PART_MEALS.search(clause) else "full" if FULL_MEALS.search(clause) else None
            if not kind:
                continue
            month = int(m.group(1)) if m.group(1) else p.start.month
            try:
                p.meals[date(p.start.year, month, int(m.group(2)))] = kind
            except ValueError:
                pass
    return p
