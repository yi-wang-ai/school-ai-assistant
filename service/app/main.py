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

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import db
from .calculator import CalcResult, PolicyGap, TripRequest, calculate, to_markdown
from .citations import CitationCheck, check

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
    """
    is_calculation: str = "no"
    city: str = ""
    start: str = ""
    end: str = ""
    nights: str = ""
    meals_provided: str = ""
    claim_date: str | None = None


def _pairs(text: str) -> list[tuple[str, str]]:
    return [tuple(p.split(":", 1)) for p in re.split(r"[;；,，\s]+", text.strip()) if ":" in p]


@app.post("/tool/calculate", dependencies=[Depends(service_caller)])
def tool_calculate(req: ToolCalcRequest):
    """Always answers 200 so the Dify workflow keeps running; errors go in the body."""
    if req.is_calculation != "yes":
        return {"ok": False, "skipped": True}
    try:
        trip = TripRequest(
            city=req.city, start=req.start, end=req.end,
            nights=[{"date": d, "price": float(p)} for d, p in _pairs(req.nights)],
            meals_provided={d: kind for d, kind in _pairs(req.meals_provided)},
            claim_date=req.claim_date or None,
        )
        result = calculate(trip)
        return {"ok": True, "result": result.model_dump(mode="json"), "breakdown_md": to_markdown(result)}
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

    result = check(answer, user["role"])
    blocked = bool(result.restricted)
    if blocked:
        answer = BLOCKED_ANSWER
    elif result.unknown:
        answer += "\n\n⚠ 系统提示：回答中引用的 " + "、".join(result.unknown) + " 在政策中不存在，请以政策原文为准。"

    latency = int((time.monotonic() - t0) * 1000)
    audit_id = db.log_answer(user, req.question, answer, result, blocked, latency, data.get("message_id"))
    return AskResponse(answer=answer, audit_id=audit_id, citation_check=result, blocked=blocked)


@app.post("/feedback")
def feedback(req: FeedbackRequest, user=Depends(current_user)):
    if not db.add_feedback(req.audit_id, user["id"], req.helpful, req.comment):
        raise HTTPException(404, "answer not found")
    return {"status": "saved"}
