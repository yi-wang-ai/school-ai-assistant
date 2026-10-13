"""HTTP API.

/ask        users ask questions here. The role comes from the user's token on the server,
            never from the request, so a staff user cannot ask as a reviewer.
/calculate  called by the Dify workflow as a tool; protected by a shared service token.
/feedback   users rate an answer they received.
"""

import os
import re
import secrets
import time
from datetime import date, timedelta

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import db
from .calculator import CalcResult, PolicyGap, TripRequest, calculate, to_markdown
from .citations import CitationCheck, check, normalize
from .trip_parser import parse_trip
from .wording import clean

app = FastAPI(title="Reimbursement policy service")

BLOCKED_ANSWER = "结论：该内容属于财务内部审核细则，普通教职工无权查看。如有疑问请联系财务处。"


@app.on_event("startup")
def startup():
    db.init_schema()


def current_user(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    user = db.user_by_token(token)
    if not user:
        raise HTTPException(401, "invalid token")
    return user


def service_caller(x_service_token: str = Header(...)):
    if not secrets.compare_digest(x_service_token, os.environ["SERVICE_TOKEN"]):
        raise HTTPException(401, "invalid service token")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    audit_id: int
    citation_check: CitationCheck
    blocked: bool
    total_corrected: bool = False
    pruned_citations: list[str] = []


class FeedbackRequest(BaseModel):
    audit_id: int
    helpful: bool
    comment: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/calculate", response_model=CalcResult, dependencies=[Depends(service_caller)])
def calculate_endpoint(req: TripRequest):
    try:
        return calculate(req)
    except PolicyGap as gap:
        raise HTTPException(422, f"policy_gap: {gap}")


class ToolCalcRequest(BaseModel):
    """Flat strings, as produced by Dify's parameter extractor.

    nights:          "2026-08-30:540;2026-08-31:540"
    meals_provided:  "2026-10-21:full;2026-10-22:partial"
    hotel_price / hotel_nights: simpler form for small models, "600" and "2";
                     expanded into consecutive nights from the start date.
    """
    is_calculation: str = "no"
    city: str = ""
    start: str = ""
    end: str = ""
    nights: str = ""
    meals_provided: str = ""
    hotel_price: str = ""
    hotel_nights: str = ""
    claim_date: str | None = None
    question: str = ""          # the user's original question, read by trip_parser


def _pairs(text: str) -> list[tuple[str, str]]:
    return [tuple(p.split(":", 1)) for p in re.split(r"[;；,，\s]+", text.strip()) if ":" in p]


def _number(text: str) -> float | None:
    m = re.search(r"\d+(\.\d+)?", text or "")
    return float(m.group()) if m else None


def _consecutive(start: date, count: int, price: float) -> list[dict]:
    return [{"date": start + timedelta(days=i), "price": price} for i in range(count)]


LODGING = re.compile(r"住|晚|房|酒店|宾馆")


def _nights(req: ToolCalcRequest, start: date, end: date, parsed) -> tuple[list[dict], str]:
    if req.question and not LODGING.search(req.question):
        return [], "none"  # no hotel in the question: ignore any nights the LLM invented
    listed = [{"date": d, "price": float(p)} for d, p in _pairs(req.nights)]
    if listed and len({n["price"] for n in listed}) > 1:
        return listed, "llm"  # different price each night: only the LLM list has that detail
    if parsed.price and parsed.nights:
        return _consecutive(start, parsed.nights, parsed.price), "parser"
    if listed:
        return listed, "llm"
    price = _number(req.hotel_price) or parsed.price
    if not price:
        return [], "none"
    count = parsed.nights or int(_number(req.hotel_nights) or (end - start).days)
    return _consecutive(start, count, price), "parser" if parsed.price else "llm"


# A question asks for money only with these words; "报销期限是多少天" asks for a deadline.
ASKS_AMOUNT = re.compile(r"多少钱|报多少|一共多少|共多少|各多少|合计|总共|算一下|计算|补助.*多少|多少.*补助|费.*多少")
ASKS_DEADLINE = re.compile(r"期限|多久|几天内|多少天|来得及|逾期")


def asks_amount(question: str) -> bool:
    return bool(ASKS_AMOUNT.search(question)) and not ASKS_DEADLINE.search(question)



TOTAL_IN_TABLE = re.compile(r"总计 \*\*(\d+(?:\.\d+)?) 元\*\*")
SUBTOTAL_LINE = re.compile(r"^合计：(.*?)；总计", re.M)
CONCLUSION = re.compile(r"^结论[:：].*$", re.M)


def _valid_amounts(answer: str) -> set[float]:
    """Totals the conclusion may legitimately state: the grand total, each item's subtotal,
    and any two subtotals added (e.g. "伙食补助和市内交通一共多少")."""
    table = TOTAL_IN_TABLE.search(answer)
    if not table:
        return set()
    valid = {float(table.group(1))}
    line = SUBTOTAL_LINE.search(answer)
    subs = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?) 元", line.group(1))] if line else []
    valid.update(subs)
    valid.update(a + b for i, a in enumerate(subs) for b in subs[i + 1:])
    return valid


ITEM_WORDS = {"住宿费": r"住宿|房", "伙食补助": r"伙食|餐|饭", "市内交通": r"交通"}


def fix_conclusion_total(answer: str, question: str = "") -> tuple[str, bool]:
    """When the rules service produced a breakdown for an amount question, the conclusion is
    written from it by code: the items the user asked about, the total and the breakdown's
    warnings. The LLM's conclusion is dropped.
    Returns (answer, corrected) where corrected means the LLM's own amounts did not match."""
    valid = _valid_amounts(answer)
    concl = CONCLUSION.search(answer)
    if not valid or not concl or (question and not asks_amount(question)):
        return answer, False
    stated = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*\**\s*元", concl.group())]
    corrected = bool(stated) and not any(x in valid for x in stated)
    total = float(TOTAL_IN_TABLE.search(answer).group(1))
    line = SUBTOTAL_LINE.search(answer)
    subs = dict(re.findall(r"(住宿费|伙食补助|市内交通) (\d+(?:\.\d+)?) 元", line.group(1))) if line else {}
    asked = [k for k, w in ITEM_WORDS.items() if re.search(w, question) and k in subs]
    if asked and len(asked) < len(subs):
        lead = "，".join(f"{k} {float(subs[k]):g} 元" for k in asked)
        text = f"结论：按规则服务计算，{lead}（全部费用总计 {total:g} 元），明细见下表。"
    elif line:
        text = f"结论：按规则服务计算，{line.group(1)}；总计 {total:g} 元，明细见下表。"
    else:
        text = f"结论：按规则服务计算，总计 {total:g} 元，明细见下表。"
    parts = [text]
    if "已超过报销期限" in answer:
        parts.append("注意：已超过报销期限，见表下提示。")
    if "未计入" in answer:
        parts.append("注意：有政策未规定的情形没有计入总额，见表下提示。")
    return answer[:concl.start()] + "".join(parts) + answer[concl.end():], corrected
    stated = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*\**\s*元", concl.group())]
    if stated and not any(x in valid for x in stated):
        total = float(TOTAL_IN_TABLE.search(answer).group(1))
        fixed = f"结论：按规则服务计算，可报销总计 {total:g} 元，各项金额见下表。（系统已更正：原回答中的金额与计算结果不一致）"
        return answer[:concl.start()] + fixed + answer[concl.end():], True
    return answer, False
    total = float(table.group(1))
    stated = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*\**\s*元", concl.group())]
    if stated and total not in stated:
        fixed = f"结论：按规则服务计算，可报销总计 {total:g} 元，明细见下表。（系统已更正：原回答中的金额与计算结果不一致）"
        return answer[:concl.start()] + fixed + answer[concl.end():], True
    return answer, False


@app.post("/tool/calculate", dependencies=[Depends(service_caller)])
def tool_calculate(req: ToolCalcRequest):
    """Always answers 200 so the Dify workflow keeps running; errors go in the body."""
    today = date.fromisoformat(req.claim_date) if req.claim_date else date.today()
    parsed = parse_trip(req.question, today)
    wants_amount = bool(parsed.start and parsed.end) and asks_amount(req.question)
    deadline_only = bool(ASKS_DEADLINE.search(req.question)) and not ASKS_AMOUNT.search(req.question)
    if deadline_only or (req.is_calculation != "yes" and not wants_amount):
        return {"ok": False, "skipped": True}
    try:
        # Rule-based values win; the LLM's extraction only fills what the parser could not read.
        start = parsed.start or date.fromisoformat(req.start)
        end = parsed.end or date.fromisoformat(req.end)
        nights, nights_src = _nights(req, start, end, parsed)
        meals = parsed.meals or {date.fromisoformat(d): kind for d, kind in _pairs(req.meals_provided)}
        trip = TripRequest(city=parsed.city or req.city, start=start, end=end, nights=nights,
                           meals_provided=meals, claim_date=req.claim_date or None)
        sources = {"city": "parser" if parsed.city else "llm",
                   "dates": "parser" if parsed.start else "llm",
                   "nights": nights_src,
                   "meals": "parser" if parsed.meals else ("llm" if meals else "none")}
        result = calculate(trip)
        return {"ok": True, "result": result.model_dump(mode="json"), "breakdown_md": to_markdown(result), "sources": sources}
    except PolicyGap as gap:
        return {"ok": False, "policy_gap": str(gap)}
    except ValueError as e:
        return {"ok": False, "input_error": str(e)}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, user=Depends(current_user)):
    t0 = time.monotonic()
    try:
        r = httpx.post(
            os.environ["DIFY_BASE_URL"] + "/chat-messages",
            headers={"Authorization": "Bearer " + os.environ["DIFY_API_KEY"]},
            json={"inputs": {"role": user["role"]}, "query": req.question,
                  "response_mode": "blocking", "user": f"user-{user['id']}"},
            timeout=180,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Dify request failed: {e}")
    data = r.json()
    answer = re.sub(r"<think>.*?</think>", "", data["answer"], flags=re.S).strip()
    answer = normalize(answer)
    answer, pruned = clean(answer, user["role"], req.question, date.today())
    answer, corrected = fix_conclusion_total(answer, req.question)

    result = check(answer, user["role"])
    blocked = bool(result.restricted)
    if blocked:
        answer = BLOCKED_ANSWER
    else:
        if result.unknown:
            answer += "\n\n⚠ 系统提示：回答中引用的 " + "、".join(result.unknown) + " 在政策中不存在，请以政策原文为准。"
        if result.malformed:
            answer += "\n\n⚠ 系统提示：回答中的引用 " + "、".join(result.malformed) + " 没有注明政策版本，请以政策原文为准。"

    latency = int((time.monotonic() - t0) * 1000)
    audit_id = db.log_answer(user, req.question, answer, result, blocked, latency, data.get("message_id"), corrected)
    return AskResponse(answer=answer, audit_id=audit_id, citation_check=result, blocked=blocked, total_corrected=corrected,
                       pruned_citations=pruned)


@app.post("/feedback")
def feedback(req: FeedbackRequest, user=Depends(current_user)):
    if not db.add_feedback(req.audit_id, user["id"], req.helpful, req.comment):
        raise HTTPException(404, "answer not found")
    return {"status": "saved"}
