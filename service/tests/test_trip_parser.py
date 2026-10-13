from datetime import date

import pytest

from app.trip_parser import parse_trip

TODAY = date(2026, 10, 13)


def d(s):
    return date.fromisoformat(s)


@pytest.mark.parametrize("q,start,end", [
    ("2026年10月12日到14日去北京出差", "2026-10-12", "2026-10-14"),
    ("我2026年8月30日到9月2日出差，伙食补助一共多少？", "2026-08-30", "2026-09-02"),  # V04: LLM once read end as 8-31
    ("10月20日至22日去绍兴出差", "2026-10-20", "2026-10-22"),
    ("2025年12月30日到2026年1月2日去杭州", "2025-12-30", "2026-01-02"),
    ("11月3号-4号去杭州出差", "2026-11-03", "2026-11-04"),
    ("10月5日去宁波开会，当天往返", "2026-10-05", "2026-10-05"),
])
def test_dates(q, start, end):
    p = parse_trip(q, TODAY)
    assert (p.start, p.end) == (d(start), d(end))


@pytest.mark.parametrize("q,nights,price", [
    ("住了2晚，每晚600元", 2, 600),
    ("住了8月30日、31日和9月1日三晚，每晚540元", 3, 540),
    ("住1晚400元/晚", 1, 400),
    ("住宿两晚，房价是480元", 2, 480),
    ("伙食补助一共多少", None, None),
])
def test_nights_and_price(q, nights, price):
    p = parse_trip(q, TODAY)
    assert (p.nights, p.price) == (nights, price)


@pytest.mark.parametrize("q,city", [
    ("去北京出差", "北京"), ("去绍兴出差", "绍兴"), ("去广州参加会议", "广州"),
    ("2026年10月在杭州开会", "杭州"), ("去重庆调研", "重庆"),
])
def test_city(q, city):
    assert parse_trip(q, TODAY).city == city


def test_full_and_partial_meals():
    p = parse_trip("2026年10月20日到22日去绍兴出差，21日对方统一安排了全天用餐。", TODAY)
    assert p.meals == {d("2026-10-21"): "full"}
    p = parse_trip("2026年10月10日到12日去成都出差，11日对方只安排了午饭。", TODAY)
    assert p.meals == {d("2026-10-11"): "partial"}


def test_no_trip_in_policy_question():
    p = parse_trip("现在出差伙食补助每天多少钱？", TODAY)
    assert (p.start, p.end, p.nights, p.price) == (None, None, None, None)
