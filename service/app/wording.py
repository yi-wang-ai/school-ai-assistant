"""Deterministic clean-up of answer wording that the small model gets wrong despite the prompt.

Applied in /ask after citation normalization and before the citation check:
- answers to questions that are not yes/no lose a leading "可以，" / "不可以，";
- staff questions about the internal audit guide get one fixed conclusion; anywhere else a
  "普通教职工无权查看" claim is removed (reviewers have access; public topics are not internal);
- "不可以，现行政策未作规定" becomes "现行政策未作规定" (a gap is not a no);
- citations of clauses that cannot support the conclusion are removed.
"""

import re
from datetime import date

from .rules import AUDIT_ARTICLES, AUDIT_TOPICS, V1, V2, VERSIONS, version_for
from .trip_parser import PART_MEALS, parse_trip

RESTRICTED_CONCLUSION = "结论：该内容属于财务内部审核细则，普通教职工无权查看。如有疑问请联系财务处。"
NO_ACCESS = "无权查看"
CONCLUSION = re.compile(r"^结论[:：].*$", re.M)
BASIS = re.compile(r"^依据[:：](.*)$", re.M)
CITE = re.compile(r"〔(FIN-[A-Z]+)\s*(v\d+)\s*第\s*(\d+)\s*条〕")

# Clauses that never decide a question by themselves: who interprets the policy and when it
# takes effect. Cited only when the question is about exactly that.
BOILERPLATE = {("FIN-TRAVEL", "v1", 12), ("FIN-TRAVEL", "v2", 12), ("FIN-TRAVEL", "v2", 14)}
BOILERPLATE_TOPIC = re.compile(r"解释|生效|施行|废止|哪个版本|新版|旧版")
SPLIT = ("FIN-TRAVEL", "v2", 13)  # the cross-version rule: relevant only if the trip spans 2026-09-01
SPLIT_TOPIC = re.compile(r"跨|分段|新旧|两个版本")
CHANGE_DATE = date(2026, 9, 1)


YES_NO_QUESTION = re.compile(r"吗|吧[？?]?$|能不能|可不可以|是不是|对不对|行不行|是否|有没有")
LEADING_YES = re.compile(r"^(结论[:：]\s*)(?:不可以|不能|不是|不对|可以|是的|是|对|否)(?:报销|报)?[，,、]\s*(?:但)?")


def drop_needless_yes(answer: str, question: str) -> str:
    """The yes/no rule makes the model open "how much / how" answers with "可以，" or
    "不可以，". Remove it unless the question actually asks yes or no."""
    if YES_NO_QUESTION.search(question.strip()):
        return answer
    concl = CONCLUSION.search(answer)
    if not concl:
        return answer
    fixed = LEADING_YES.sub(r"\1", concl.group())
    return answer[:concl.start()] + fixed + answer[concl.end():]


# Questions about the reviewer-only audit guide (FIN-AUDIT). Decided from the question, not the
# answer: the small model also writes "无权查看" for public topics it cannot answer.
INTERNAL_TOPIC = re.compile(r"审核(?!通过)|加签|复核|核减|例外审批|审批日期|院领导|两张.*发票|内部细则|审核细则|不可抗力|逾期.*(处理|怎么办|还能|能不能|可以)")
GAP = "现行政策未作规定"
NOT_COVERED = re.compile(r"未(?:作)?规定|未包含|未涉及|没有规定|未明确规定|不在.*范围")


# Which FIN-TRAVEL clauses can support an answer on each topic (same numbering in v1 and v2).
TOPIC_CLAUSES = [
    (re.compile(r"飞机|机票|舱|高铁|动车|火车|座|轮船|交通工具|等级"), {3, 4}),
    (re.compile(r"住宿|住了|房|酒店|宾馆|合住|晚"), {5, 6}),
    (re.compile(r"伙食|餐|饭|用餐"), {7, 9}),
    (re.compile(r"市内交通"), {8}),
    (re.compile(r"审批|批准|审批单"), {2}),
    (re.compile(r"期限|多久|几天内|多少天|来得及|逾期|过期"), {10}),
    (re.compile(r"材料|票据|发票|清单|通知|行程单|需要准备|需要什么"), {11}),
    (re.compile(r"适用|哪些人|学生|合同制|在编|范围"), {1}),
]


def question_topics(question: str) -> set[int]:
    clauses: set[int] = set()
    for pattern, arts in TOPIC_CLAUSES:
        if pattern.search(question):
            clauses |= arts
    return clauses



def fix_access_and_gap(answer: str, role: str, question: str) -> str:
    concl = CONCLUSION.search(answer)
    if role == "staff" and INTERNAL_TOPIC.search(question):
        if concl:
            answer = answer[:concl.start()] + RESTRICTED_CONCLUSION + answer[concl.end():]
        return answer
    # Not an internal topic (or a reviewer): a "no access" claim is wrong, remove it.
    out = []
    for line in answer.split("\n"):
        if NO_ACCESS in line and "普通教职工" in line:
            if line.startswith("依据"):
                out.append("依据：政策中没有与此直接对应的条款")
            continue
        out.append(line)
    answer = "\n".join(out)
    # A bare "不可以" while the answer itself says the policy does not cover it: the answer is the gap.
    concl = CONCLUSION.search(answer)
    says_gap = GAP in answer or (NOT_COVERED.search(answer) and "总计 **" not in answer)
    cites_rule = any(int(m.group(3)) in question_topics(question) for m in CITE.finditer(answer) if m.group(1) == "FIN-TRAVEL")
    if concl and says_gap and not cites_rule and re.fullmatch(r"结论[:：]\s*(不可以|不能|不行|否)[。.]?\s*", concl.group()):
        answer = answer[:concl.start()] + "结论：" + GAP + "，建议联系财务处确认。" + answer[concl.end():]
    # "不可以，现行政策未作规定" -> "现行政策未作规定": a gap is not a no.
    concl = CONCLUSION.search(answer)
    if concl and GAP in concl.group():
        fixed = re.sub(r"^(结论[:：]\s*)(?:不可以|可以|不能|是|不是)(?:报销|报)?[，,、]\s*(?=现行政策未作规定)", r"\1", concl.group())
        answer = answer[:concl.start()] + fixed + answer[concl.end():]
    return answer


def _spans_change(question: str, today: date) -> bool:
    p = parse_trip(question, today)
    return bool(p.start and p.end and p.start < CHANGE_DATE <= p.end)


def question_versions(question: str, today: date) -> list:
    """Policy versions in force for the dates in the question (both when the trip spans the
    change), falling back to a bare 年/月, then to today."""
    p = parse_trip(question, today)
    dates = [d for d in (p.start, p.end) if d]
    if not dates:
        m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", question)
        dates = [date(int(m.group(1)), int(m.group(2)), 15)] if m else [today]
    found = []
    for d in dates:
        try:
            v = version_for(d)
        except Exception:
            continue
        if v not in found:
            found.append(v)
    return found or [version_for(today)]


def prune_citations(answer: str, question: str, today: date) -> tuple[str, list[str]]:
    """Remove citations that cannot support the conclusion; if that leaves the public policy
    uncited on a question with a known topic, cite the topic's clauses for the version in
    force. Returns (answer, removed)."""
    keep_boiler = bool(BOILERPLATE_TOPIC.search(question))
    keep_split = _spans_change(question, today) or bool(SPLIT_TOPIC.search(question))
    topics = question_topics(question)
    removed = []

    def drop(m):
        key = (m.group(1), m.group(2), int(m.group(3)))
        off_topic = key[0] == "FIN-TRAVEL" and topics and key[2] not in topics and key not in BOILERPLATE and key != SPLIT
        if (key in BOILERPLATE and not keep_boiler) or (key == SPLIT and not keep_split) or off_topic:
            removed.append(f"{key[0]} {key[1]} 第{key[2]}条")
            return ""
        return m.group(0)

    answer = CITE.sub(drop, answer)
    concl = CONCLUSION.search(answer)
    is_gap = bool(concl and (GAP in concl.group() or NOT_COVERED.search(concl.group())))
    if topics and removed and not is_gap and not re.search(r"〔FIN-TRAVEL\s*v\d\s*第", answer):
        # Every public citation was off-topic: cite the topic's clauses instead of leaving none.
        added = "".join(f"〔FIN-TRAVEL {v.version} 第{a}条〕" for v in question_versions(question, today) for a in sorted(topics))
        basis = BASIS.search(answer)
        answer = (answer[:basis.start()] + "依据：" + added + basis.group(1) + answer[basis.end():]) if basis else answer + "\n依据：" + added
    # Tidy the basis line if removals left it with only separators.
    basis = BASIS.search(answer)
    if basis:  # tidy even when nothing was removed now (e.g. a dangling "及" from the model)
        rest = re.sub(r"^[\s、，,和及]+|[\s、，,和及]+(?=[。.]?\s*$)", "", basis.group(1)).rstrip()
        rest = re.sub(r"^[。.]$", "", rest)
        rest = re.sub(r"[、，,]\s*[、，,]", "、", rest)
        if not rest and removed:
            rest = "政策中没有与此直接对应的条款"
        answer = answer[:basis.start()] + "依据：" + rest + answer[basis.end():]
    return answer, removed


AUDIT_CITE = re.compile(r"〔FIN-AUDIT\s*v1\s*([^〕]*)〕")
REVIEWER_NOISE = re.compile(r"无法获知|不得向报销人公开|报销人无权|普通教职工")


def reviewer_conclusion(answer: str, role: str, question: str) -> str:
    """Reviewer questions about the audit guide: the conclusion is the article text itself.
    A cited FIN-AUDIT article is used if the question is clearly about internal auditing or
    the article's topic matches the question; otherwise the article is matched by topic."""
    if role != "reviewer":
        return answer
    internal = bool(INTERNAL_TOPIC.search(question))
    cited = sorted({int(a) for inner in AUDIT_CITE.findall(answer) for a in re.findall(r"第\s*(\d+)\s*条", inner)
                    if int(a) in AUDIT_ARTICLES})
    arts = [n for n in cited if internal or re.search(AUDIT_TOPICS[n], question)]
    if not arts and internal:
        arts = [n for n, pattern in AUDIT_TOPICS.items() if re.search(pattern, question)]
    if not arts:
        return answer
    text = "结论：" + "".join(f"{AUDIT_ARTICLES[n]}〔FIN-AUDIT v1 第{n}条〕" for n in arts)
    lines = [l for l in answer.split("\n") if not REVIEWER_NOISE.search(l)]
    body = "\n".join(lines)
    concl = CONCLUSION.search(body)
    if concl:
        return body[:concl.start()] + text + body[concl.end():]
    return text + "\n" + body.lstrip()


APPROVAL_REQUEST = re.compile(r"(帮我|直接|请)?(批准|审批通过|批一下|通过审批|审批一下|给我批)|批准这张|审批这张")
APPROVAL_CONCLUSION = "结论：本助手只提供报销政策咨询，不能审批、批准或驳回报销单，请通过 OA 系统按正常流程提交审批。"


def approval_conclusion(answer: str, question: str) -> str:
    """A request to approve a claim gets a fixed refusal conclusion (prompt rule 6), whether or
    not the model wrote a conclusion line."""
    if not APPROVAL_REQUEST.search(question):
        return answer
    concl = CONCLUSION.search(answer)
    if concl:
        return answer[:concl.start()] + APPROVAL_CONCLUSION + answer[concl.end():]
    return APPROVAL_CONCLUSION + "\n" + answer.lstrip()


V1_PARTIAL_MEAL = f"结论：2025 版只规定接待单位统一安排用餐的当天不发伙食补助，没有规定只安排部分餐次如何处理，建议联系财务处确认。〔{V1.cite('meals_provided')}〕"


def v1_partial_meal_gap(answer: str, question: str, today: date) -> str:
    """The halving rule for partial meals exists only in v2 (rules.V2.partial_meal_half). If the
    trip falls entirely under v1 and the model applied halving, state the gap instead."""
    if V1.partial_meal_half or not PART_MEALS.search(question) or not re.search(r"减半|一半|50%|60 ?元", answer):
        return answer
    p = parse_trip(question, today)
    dates = [d for d in (p.start, p.end) if d]
    if not dates:  # try a bare year/month such as "2025年12月"
        m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", question)
        if not m:
            return answer
        dates = [date(int(m.group(1)), int(m.group(2)), 1)]
    if max(dates) > V1.expires:
        return answer
    concl = CONCLUSION.search(answer)
    return (answer[:concl.start()] + V1_PARTIAL_MEAL + answer[concl.end():]) if concl else V1_PARTIAL_MEAL + "\n" + answer


PERSONAL_STAY = re.compile(r"自费|私人|旅游|顺便|多留|多待|延长.*(停留|几天)|个人原因|提前.*(到|去)")
PERSONAL_STAY_CONCLUSION = ("结论：现行政策未对出差结束后（或开始前）个人自费停留的期间作出规定。"
                            "伙食补助和市内交通费按出差自然天数计算〔{v} 第7条〕〔{v} 第8条〕，办法只适用于因公出差〔{v} 第1条〕，"
                            "个人停留期间通常不计入，具体请联系财务处确认。")


def personal_stay_conclusion(answer: str, question: str, today: date) -> str:
    """Private days around a business trip are not covered by the policy; say so, with the
    clauses that define the counted days, instead of letting the model infer a bare answer."""
    if not (PERSONAL_STAY.search(question) and re.search(r"补助|交通费|报|领", question)):
        return answer
    v = f"FIN-TRAVEL {question_versions(question, today)[0].version}"
    text = PERSONAL_STAY_CONCLUSION.format(v=v)
    concl = CONCLUSION.search(answer)
    return (answer[:concl.start()] + text + answer[concl.end():]) if concl else text + "\n" + answer.lstrip()


def clean(answer: str, role: str, question: str, today: date) -> tuple[str, list[str]]:
    answer = drop_needless_yes(answer, question)
    answer = fix_access_and_gap(answer, role, question)
    answer = reviewer_conclusion(answer, role, question)
    answer = approval_conclusion(answer, question)
    answer = v1_partial_meal_gap(answer, question, today)
    answer = personal_stay_conclusion(answer, question, today)
    return prune_citations(answer, question, today)
