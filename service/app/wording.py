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

from .trip_parser import parse_trip

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
LEADING_YES = re.compile(r"^(结论[:：]\s*)(?:不可以|不能|不是|不对|可以|是的|是|对|否)[，,、]\s*")


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
INTERNAL_TOPIC = re.compile(r"审核(?!通过)|加签|复核|核减|例外审批|审批日期|院领导|两张.*发票|内部细则|审核细则")
GAP = "现行政策未作规定"


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
    # A bare "不可以" whose own basis says the policy does not cover it: the answer is the gap.
    concl, basis = CONCLUSION.search(answer), BASIS.search(answer)
    if concl and basis and GAP in basis.group() and re.fullmatch(r"结论[:：]\s*(不可以|不能|不行|否)[。.]?\s*", concl.group()):
        answer = answer[:concl.start()] + "结论：" + GAP + "，建议联系财务处确认。" + answer[concl.end():]
    # "不可以，现行政策未作规定" -> "现行政策未作规定": a gap is not a no.
    concl = CONCLUSION.search(answer)
    if concl and GAP in concl.group():
        fixed = re.sub(r"^(结论[:：]\s*)(?:不可以|可以|不能|是|不是)[，,、]\s*(?=现行政策未作规定)", r"\1", concl.group())
        answer = answer[:concl.start()] + fixed + answer[concl.end():]
    return answer


def _spans_change(question: str, today: date) -> bool:
    p = parse_trip(question, today)
    return bool(p.start and p.end and p.start < CHANGE_DATE <= p.end)


def prune_citations(answer: str, question: str, today: date) -> tuple[str, list[str]]:
    """Remove citations that cannot support the conclusion. Returns (answer, removed)."""
    keep_boiler = bool(BOILERPLATE_TOPIC.search(question))
    keep_split = _spans_change(question, today) or bool(SPLIT_TOPIC.search(question))
    removed = []

    def drop(m):
        key = (m.group(1), m.group(2), int(m.group(3)))
        if (key in BOILERPLATE and not keep_boiler) or (key == SPLIT and not keep_split):
            removed.append(f"{key[0]} {key[1]} 第{key[2]}条")
            return ""
        return m.group(0)

    answer = CITE.sub(drop, answer)
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


def clean(answer: str, role: str, question: str, today: date) -> tuple[str, list[str]]:
    answer = drop_needless_yes(answer, question)
    answer = fix_access_and_gap(answer, role, question)
    return prune_citations(answer, question, today)
