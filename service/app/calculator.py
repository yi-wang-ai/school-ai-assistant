"""Deterministic travel reimbursement calculation.

Conventions (stated so they can be checked against the policy):
- Allowance days are natural days, first and last day included (第7、8条).
- Each day and each hotel night uses the version in force on that date (v2 第13条).
- The claim deadline uses the version in force on the trip's last day (第10条).
"""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .rules import PolicyGap, city_tier, version_for, V2


class Night(BaseModel):
    date: date
    price: float = Field(gt=0)


class TripRequest(BaseModel):
    city: str
    start: date
    end: date
    nights: list[Night] = []
    meals_provided: dict[date, Literal["full", "partial"]] = {}
    claim_date: date | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end < self.start:
            raise ValueError("end must not be before start")
        for n in self.nights:
            if not (self.start <= n.date < self.end):
                raise ValueError(f"night {n.date} is outside the trip")
        return self


class Line(BaseModel):
    item: Literal["hotel", "meal", "local"]
    date: date
    amount: float
    citation: str
    note: str = ""


class CalcResult(BaseModel):
    lines: list[Line]
    totals: dict[str, float]
    total: float
    personal_excess: float
    citations: list[str]
    warnings: list[str]
    gaps: list[str]          # cases the policy does not cover; total excludes them
    complete: bool


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def calculate(req: TripRequest) -> CalcResult:
    lines: list[Line] = []
    warnings: list[str] = []
    gaps: list[str] = []
    excess = 0.0

    tier = city_tier(req.city)  # raises PolicyGap for cities the policy does not classify

    for n in req.nights:
        v = version_for(n.date)
        cap = v.hotel_cap[tier]
        paid = min(n.price, cap)
        note = ""
        if n.price > cap:
            excess += n.price - cap
            note = f"超标 {n.price - cap:g} 元个人自理〔{v.cite('excess')}〕"
        lines.append(Line(item="hotel", date=n.date, amount=paid, citation=v.cite("hotel"), note=note))

    for d in days(req.start, req.end):
        v = version_for(d)
        meal = v.meal_per_day
        provided = req.meals_provided.get(d)
        if provided == "full":
            lines.append(Line(item="meal", date=d, amount=0, citation=v.cite("meals_provided"), note="接待单位统一安排用餐"))
        elif provided == "partial":
            if v.partial_meal_half:
                lines.append(Line(item="meal", date=d, amount=meal / 2, citation=v.cite("meals_provided"), note="部分餐次，减半"))
            else:
                gaps.append(f"{d} 只安排部分餐次：{v.version} 未规定如何处理〔{v.cite('meals_provided')}〕，需财务处确认")
        else:
            lines.append(Line(item="meal", date=d, amount=meal, citation=v.cite("meal")))
        lines.append(Line(item="local", date=d, amount=v.local_per_day, citation=v.cite("local")))

    versions_used = {version_for(d).version for d in days(req.start, req.end)}
    citations = sorted({l.citation for l in lines})
    if len(versions_used) > 1:
        citations.append(V2.cite("split"))

    if req.claim_date:
        v_end = version_for(req.end)
        deadline = req.end + timedelta(days=v_end.claim_days)
        if req.claim_date > deadline:
            warnings.append(f"已超过报销期限：应在 {deadline} 前办理（出差结束后 {v_end.claim_days} 日内），逾期不予受理〔{v_end.cite('deadline')}〕")
            citations.append(v_end.cite("deadline"))

    totals = {k: sum(l.amount for l in lines if l.item == k) for k in ("hotel", "meal", "local")}
    return CalcResult(
        lines=lines,
        totals=totals,
        total=sum(totals.values()),
        personal_excess=excess,
        citations=citations,
        warnings=warnings,
        gaps=gaps,
        complete=not gaps,
    )


__all__ = ["TripRequest", "CalcResult", "calculate", "PolicyGap"]
