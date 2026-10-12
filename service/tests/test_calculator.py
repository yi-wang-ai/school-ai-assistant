from datetime import date

import pytest

from app.calculator import TripRequest, calculate
from app.rules import PolicyGap


def trip(**kw):
    return calculate(TripRequest(**kw))


def test_c01_beijing_over_cap():
    r = trip(city="北京", start="2026-10-12", end="2026-10-14",
             nights=[{"date": "2026-10-12", "price": 600}, {"date": "2026-10-13", "price": 600}])
    assert r.totals == {"hotel": 1100, "meal": 360, "local": 240}
    assert r.total == 1700
    assert r.personal_excess == 100


def test_c02_hangzhou_under_cap():
    r = trip(city="杭州", start="2026-11-03", end="2026-11-04", nights=[{"date": "2026-11-03", "price": 400}])
    assert r.total == 800


def test_c03_full_meals_provided():
    r = trip(city="绍兴", start="2026-10-20", end="2026-10-22", meals_provided={"2026-10-21": "full"})
    assert r.totals["meal"] == 240 and r.totals["local"] == 240


def test_c04_shenzhen():
    r = trip(city="深圳", start="2026-10-05", end="2026-10-09",
             nights=[{"date": f"2026-10-0{d}", "price": 520} for d in range(5, 9)])
    assert r.total == 3080


def test_c05_spans_version_change():
    r = trip(city="广州", start="2026-08-30", end="2026-09-02",
             nights=[{"date": d, "price": 540} for d in ("2026-08-30", "2026-08-31", "2026-09-01")])
    assert r.totals == {"hotel": 1540, "meal": 440, "local": 320}
    assert r.total == 2300
    assert "FIN-TRAVEL v2 第13条" in r.citations
    assert "FIN-TRAVEL v1 第5条" in r.citations and "FIN-TRAVEL v2 第5条" in r.citations


def test_c05_deadline_passed():
    r = trip(city="广州", start="2026-08-30", end="2026-09-02", claim_date="2026-10-13")
    assert any("2026-09-22" in w for w in r.warnings)


def test_c07_partial_meal_v2_halved():
    r = trip(city="成都", start="2026-10-10", end="2026-10-12", meals_provided={"2026-10-11": "partial"})
    assert r.totals["meal"] == 300


def test_c08_overdue():
    r = trip(city="绍兴", start="2026-09-28", end="2026-10-01", claim_date="2026-10-25")
    assert r.warnings and "第10条" in r.warnings[0]


def test_v04_meals_across_versions():
    r = trip(city="绍兴", start="2026-08-30", end="2026-09-02")
    assert r.totals["meal"] == 440


def test_v05_partial_meal_v1_is_a_gap():
    r = trip(city="绍兴", start="2025-12-10", end="2025-12-11", meals_provided={"2025-12-10": "partial"})
    assert not r.complete
    assert "v1" in r.gaps[0]


def test_uncovered_city_raises():
    with pytest.raises(PolicyGap):
        trip(city="重庆", start="2026-10-10", end="2026-10-11")


def test_date_before_any_policy_raises():
    with pytest.raises(PolicyGap):
        trip(city="北京", start="2024-12-30", end="2024-12-31")


def test_night_outside_trip_rejected():
    with pytest.raises(ValueError):
        TripRequest(city="北京", start=date(2026, 10, 1), end=date(2026, 10, 2), nights=[{"date": "2026-10-02", "price": 300}])
