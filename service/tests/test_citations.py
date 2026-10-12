from app.citations import check, extract


def test_extracts_multiple_articles_in_one_bracket():
    assert extract("依据〔FIN-TRAVEL v2 第5条、第6条〕") == [("FIN-TRAVEL", "v2", 5), ("FIN-TRAVEL", "v2", 6)]


def test_valid_citations_pass():
    r = check("〔FIN-TRAVEL v1 第7条〕〔FIN-TRAVEL v2 第13条〕", role="staff")
    assert r.ok and len(r.cited) == 2


def test_nonexistent_article_flagged():
    r = check("〔FIN-TRAVEL v1 第13条〕", role="staff")  # v1 has only 12 articles
    assert not r.ok and r.unknown == ["FIN-TRAVEL v1 第13条"]


def test_staff_citing_internal_guide_flagged():
    r = check("〔FIN-AUDIT v1 第4条〕", role="staff")
    assert not r.ok and r.restricted


def test_reviewer_may_cite_internal_guide():
    assert check("〔FIN-AUDIT v1 第4条〕", role="reviewer").ok
