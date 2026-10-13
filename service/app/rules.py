"""Travel policy rules as data.

Every number here comes from data/policies/travel_v1_2025.md or travel_v2_2026.md.
The LLM never does arithmetic: the calculator reads these values instead.
"""

from dataclasses import dataclass, field
from datetime import date

DOC = "FIN-TRAVEL"

TIER1 = {"北京", "上海", "广州", "深圳"}
# 其他省会城市及计划单列市 (municipalities such as 天津/重庆 are not named in the policy)
TIER2 = {
    "石家庄", "太原", "呼和浩特", "沈阳", "长春", "哈尔滨", "南京", "杭州", "合肥", "福州",
    "南昌", "济南", "郑州", "武汉", "长沙", "南宁", "海口", "成都", "贵阳", "昆明",
    "拉萨", "西安", "兰州", "西宁", "银川", "乌鲁木齐",
    "大连", "青岛", "宁波", "厦门",
}
UNCOVERED = {"天津", "重庆"}


@dataclass(frozen=True)
class PolicyVersion:
    version: str
    effective: date
    expires: date | None
    hotel_cap: dict[int, int]          # city tier -> yuan per night (第5条)
    meal_per_day: int                  # 第7条
    local_per_day: int                 # 第8条
    partial_meal_half: bool            # 第9条: v2 halves the allowance, v1 has no rule
    claim_days: int                    # 第10条
    articles: int                      # number of articles, for citation checks
    clause: dict[str, int] = field(default_factory=dict)

    def cite(self, key: str) -> str:
        return f"{DOC} {self.version} 第{self.clause[key]}条"


V1 = PolicyVersion(
    version="v1", effective=date(2025, 1, 1), expires=date(2026, 8, 31),
    hotel_cap={1: 500, 2: 400, 3: 350}, meal_per_day=100, local_per_day=80,
    partial_meal_half=False, claim_days=30, articles=12,
    clause={"hotel": 5, "excess": 6, "meal": 7, "local": 8, "meals_provided": 9, "deadline": 10},
)
V2 = PolicyVersion(
    version="v2", effective=date(2026, 9, 1), expires=None,
    hotel_cap={1: 550, 2: 450, 3: 380}, meal_per_day=120, local_per_day=80,
    partial_meal_half=True, claim_days=20, articles=14,
    clause={"hotel": 5, "excess": 6, "meal": 7, "local": 8, "meals_provided": 9, "deadline": 10, "split": 13},
)
VERSIONS = [V1, V2]

# Articles that exist, per document version. FIN-AUDIT is reviewer-only.
ARTICLES = {("FIN-TRAVEL", "v1"): V1.articles, ("FIN-TRAVEL", "v2"): V2.articles, ("FIN-AUDIT", "v1"): 5}
RESTRICTED_DOCS = {"FIN-AUDIT"}


class PolicyGap(Exception):
    """The policy does not cover this case; the answer must say so instead of guessing."""


def version_for(d: date) -> PolicyVersion:
    for v in VERSIONS:
        if v.effective <= d and (v.expires is None or d <= v.expires):
            return v
    raise PolicyGap(f"{d} 不在任何版本的有效期内")


def city_tier(city: str) -> int:
    city = city.removesuffix("市")
    if city in UNCOVERED:
        raise PolicyGap(f"政策未列明{city}的住宿标准类别")
    if city in TIER1:
        return 1
    if city in TIER2:
        return 2
    return 3

# Reviewer-only audit guide (data/policies/audit_guide_internal.md), verbatim. Used to write the
# conclusion of reviewer answers; never shown to staff (see wording.py and citations.py).
AUDIT_ARTICLES = {
    1: "住宿发票开具日期与出差审批日期不一致超过 1 天的，须要求报销人提供书面说明。",
    2: "同一出差人同一晚出现两张住宿发票的，退回并标记为重点复核。",
    3: "伙食补助天数超过审批出差天数的，按审批天数核减。",
    4: "单次差旅报销总额超过 5000 元的，须经分管财务的院领导加签。",
    5: "逾期报销确因不可抗力的，审核人员可在系统中发起例外审批，但须附证明材料。",
}
AUDIT_TOPICS = {  # used only when the model cited no FIN-AUDIT article
    1: r"发票.*日期|日期.*(不一致|对不上|差)|书面说明",
    2: r"两张.*发票|重复.*发票|同一晚",
    3: r"天数|核减",
    4: r"加签|院领导|5000|五千|金额.*(大|超过|多少)",
    5: r"逾期|不可抗力|例外审批|过期",
}
