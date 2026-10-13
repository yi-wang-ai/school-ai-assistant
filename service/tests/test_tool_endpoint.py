import os

os.environ.setdefault("SERVICE_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)  # no context manager: skips startup, so no database needed
H = {"X-Service-Token": "test-token"}


def post(body):
    return client.post("/tool/calculate", json=body, headers=H)


def test_requires_service_token():
    assert client.post("/tool/calculate", json={}, headers={"X-Service-Token": "wrong"}).status_code == 401


def test_not_a_calculation_is_skipped():
    assert post({"is_calculation": "no"}).json() == {"ok": False, "skipped": True}


def test_c05_flat_strings():
    r = post({"is_calculation": "yes", "city": "广州", "start": "2026-08-30", "end": "2026-09-02",
              "nights": "2026-08-30:540;2026-08-31:540;2026-09-01:540"}).json()
    assert r["ok"] and r["result"]["total"] == 2300


def test_policy_gap_reported_not_raised():
    r = post({"is_calculation": "yes", "city": "重庆", "start": "2026-10-10", "end": "2026-10-11"})
    assert r.status_code == 200 and "policy_gap" in r.json()


def test_bad_input_reported_not_raised():
    r = post({"is_calculation": "yes", "city": "北京", "start": "2026-10-12", "end": "2026-10-10"})
    assert r.status_code == 200 and "input_error" in r.json()


def test_breakdown_markdown_carries_every_amount():
    r = post({"is_calculation": "yes", "city": "广州", "start": "2026-08-30", "end": "2026-09-02",
              "nights": "2026-08-30:540;2026-08-31:540;2026-09-01:540", "claim_date": "2026-10-13"}).json()
    md = r["breakdown_md"]
    assert "总计 **2300 元**" in md and "个人自理：80 元" in md
    assert "〔FIN-TRAVEL v1 第5条〕" in md and "〔FIN-TRAVEL v2 第13条〕" in md
    assert "2026-09-22" in md


def test_price_and_count_expand_to_consecutive_nights():
    r = post({"is_calculation": "yes", "city": "北京", "start": "2026-10-12", "end": "2026-10-14",
              "hotel_price": "600元", "hotel_nights": "2"}).json()
    assert r["result"]["total"] == 1700


def test_explicit_nights_win_over_price_and_count():
    r = post({"is_calculation": "yes", "city": "杭州", "start": "2026-11-03", "end": "2026-11-04",
              "nights": "2026-11-03:400", "hotel_price": "999", "hotel_nights": "5"}).json()
    assert r["result"]["total"] == 800


def test_wrong_conclusion_total_is_replaced():
    from app.main import fix_conclusion_total
    answer = "结论：一共可报销 1700 元。\n依据：…\n\n合计：…；总计 **600 元**"
    fixed, corrected = fix_conclusion_total(answer)
    assert corrected and "总计 600 元" in fixed.splitlines()[0] and "1700" not in fixed.splitlines()[0]


def test_conclusion_written_from_breakdown_with_warning():
    from app.main import fix_conclusion_total
    answer = ("结论：不可以，超出标准部分个人自理。\n\n合计：住宿费 1540 元，伙食补助 440 元，市内交通 320 元；总计 **2300 元**\n"
              "⚠ 已超过报销期限：应在 2026-09-22 前办理")
    fixed, corrected = fix_conclusion_total(answer)
    first = fixed.splitlines()[0]
    assert "总计 2300 元" in first and "住宿费 1540 元" in first and "已超过报销期限" in first and not corrected


def test_parser_overrides_misread_end_date():
    # V04: the LLM once extracted end=2026-08-31 for "8月30日到9月2日"
    r = post({"is_calculation": "yes", "city": "绍兴", "start": "2026-08-30", "end": "2026-08-31",
              "question": "我2026年8月30日到9月2日出差，伙食补助一共多少？", "claim_date": "2026-10-13"}).json()
    assert r["result"]["totals"]["meal"] == 440 and r["sources"]["dates"] == "parser"


def test_parser_triggers_calculation_when_llm_says_no():
    r = post({"is_calculation": "no", "claim_date": "2026-10-13",
              "question": "2026年10月12日到14日去北京出差，住了2晚，每晚600元。一共能报多少？"}).json()
    assert r["ok"] and r["result"]["total"] == 1700


def test_llm_per_night_prices_kept_when_they_differ():
    r = post({"is_calculation": "yes", "city": "杭州", "start": "2026-11-03", "end": "2026-11-05",
              "nights": "2026-11-03:400;2026-11-04:500", "claim_date": "2026-10-13",
              "question": "11月3日到5日去杭州，第一晚400元，第二晚500元，能报多少"}).json()
    assert r["sources"]["nights"] == "llm" and r["result"]["totals"]["hotel"] == 850


def test_policy_question_is_skipped():
    assert post({"is_calculation": "no", "question": "现在出差伙食补助每天多少钱？"}).json() == {"ok": False, "skipped": True}


def test_item_subtotal_in_conclusion_is_kept():
    # "伙食补助一共多少？" -> the model answers the meal subtotal, not the grand total
    from app.main import fix_conclusion_total
    answer = "结论：伙食补助一共 180 元。\n\n合计：伙食补助 180 元，市内交通 160 元；总计 **340 元**"
    fixed, corrected = fix_conclusion_total(answer)
    assert not corrected and "伙食补助 180 元" in fixed.splitlines()[0]


def test_sum_of_two_subtotals_is_kept():
    from app.main import fix_conclusion_total
    answer = "结论：两项共 480 元。\n\n合计：住宿费 500 元，伙食补助 240 元，市内交通 240 元；总计 **980 元**"
    assert fix_conclusion_total(answer)[1] is False


def test_amount_matching_nothing_is_replaced():
    from app.main import fix_conclusion_total
    answer = "结论：伙食补助一共 200 元。\n\n合计：伙食补助 180 元，市内交通 160 元；总计 **340 元**"
    fixed, corrected = fix_conclusion_total(answer)
    assert corrected and "总计 340 元" in fixed.splitlines()[0]


def test_deadline_question_is_not_calculated():
    r = post({"is_calculation": "yes", "city": "", "start": "2026-07-10", "end": "2026-07-10",
              "question": "我2026年7月10日出差结束，报销期限是多久？", "claim_date": "2026-10-13"}).json()
    assert r == {"ok": False, "skipped": True}


def test_conclusion_leads_with_the_item_asked():
    from app.main import fix_conclusion_total
    answer = "结论：可以。\n\n合计：伙食补助 440 元，市内交通 320 元；总计 **760 元**"
    fixed, _ = fix_conclusion_total(answer, "我2026年8月30日到9月2日出差，伙食补助一共多少？")
    assert fixed.splitlines()[0] == "结论：按规则服务计算，伙食补助 440 元（全部费用总计 760 元），明细见下表。"


def test_deadline_question_conclusion_is_left_to_the_model():
    from app.main import fix_conclusion_total
    answer = "结论：应在出差结束后 30 日内办理。\n\n合计：伙食补助 100 元；总计 **100 元**"
    assert fix_conclusion_total(answer, "报销期限是多少天？") == (answer, False)


def test_invented_hotel_nights_ignored_when_question_has_no_lodging():
    # V04: the LLM added two hotel nights to a question about meal allowance only
    r = post({"is_calculation": "yes", "city": "某地", "start": "2026-08-30", "end": "2026-09-02",
              "nights": "2026-08-30:540;2026-08-31:500", "claim_date": "2026-10-13",
              "question": "我2026年8月30日到9月2日出差，伙食补助一共多少？"}).json()
    assert r["result"]["totals"]["hotel"] == 0 and r["result"]["total"] == 760
