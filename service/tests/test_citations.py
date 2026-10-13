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


def test_single_version_document_is_normalized():
    from app.citations import normalize
    assert normalize("依据〔FIN-AUDIT 内部细则 第2条〕") == "依据〔FIN-AUDIT v1 第2条〕"


def test_ambiguous_citation_is_malformed():
    r = check("依据〔FIN-TRAVEL 第5条〕和〔第7条〕", role="staff")
    assert not r.ok and len(r.malformed) == 2


def test_unversioned_internal_citation_is_restricted_for_staff():
    r = check("〔FIN-AUDIT 内部细则 第2条〕", role="staff")
    assert r.restricted and not r.ok


def test_brackets_without_articles_are_ignored():
    assert check("〔角色权限设定〕〔FIN-TRAVEL v2 第5条〕", role="staff").ok
