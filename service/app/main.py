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


def _nights(req: ToolCalcRequest, start: date, end: date, parsed) -> tuple[list[dict], str]:
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


ASKS_AMOUNT = re.compile(r"多少|能报|可报|报销|一共|合计|总共|算一下|计算")


TOTAL_IN_TABLE = re.compile(r"总计 \*\*(\d+(?:\.\d+)?) 元\*\*")
CONCLUSION = re.compile(r"^结论[:：].*$", re.M)


def fix_conclusion_total(answer: str) -> tuple[str, bool]:
    """If the LLM's conclusion states a total that differs from the code-computed one,
    replace the conclusion. Returns (answer, corrected)."""
    table = TOTAL_IN_TABLE.search(answer)
    concl = CONCLUSION.search(answer)
    if not table or not concl:
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
    wants_amount = parsed.start and parsed.end and ASKS_AMOUNT.search(req.question)
    if req.is_calculation != "yes" and not wants_amount:
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
    answer, corrected = fix_conclusion_total(answer)

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
    return AskResponse(answer=answer, audit_id=audit_id, citation_check=result, blocked=blocked, total_corrected=corrected)


@app.post("/feedback")
def feedback(req: FeedbackRequest, user=Depends(current_user)):
    if not db.add_feedback(req.audit_id, user["id"], req.helpful, req.comment):
        raise HTTPException(404, "answer not found")
    return {"status": "saved"}
