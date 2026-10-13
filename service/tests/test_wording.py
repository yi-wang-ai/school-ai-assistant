from datetime import date

from app.wording import RESTRICTED_CONCLUSION, clean, fix_access_and_gap, prune_citations

TODAY = date(2026, 10, 13)


def test_staff_refusal_gets_fixed_conclusion():
    # P02 in the evaluation: "不可以，现行政策未作规定" mixed with "无权查看"
    answer = "结论：不可以，现行政策未作规定  \n依据：该内容属于财务内部审核细则，普通教职工无权查看"
    out = fix_access_and_gap(answer, "staff", "差旅报销超过多少钱需要院领导加签？")
    assert out.splitlines()[0] == RESTRICTED_CONCLUSION


def test_public_gap_question_keeps_gap_and_loses_false_no_access_claim():
    # N02: conference fees are a public topic the policy does not cover, not internal content
    answer = "结论：不可以，现行政策未作规定\n依据：该内容属于财务内部审核细则，普通教职工无权查看\n计算：（不涉及）"
    out = fix_access_and_gap(answer, "staff", "会议注册费最多能报多少？")
    assert out.splitlines()[0] == "结论：现行政策未作规定" and "无权查看" not in out
    assert "依据：政策中没有与此直接对应的条款" in out


def test_staff_answer_without_refusal_is_untouched():
    answer = "结论：住宿每晚最多 550 元。"
    assert fix_access_and_gap(answer, "staff", "上海住宿标准是多少") == answer


def test_approval_question_is_not_internal():
    # "审批" (trip approval, public 第2条) must not be mistaken for the internal audit guide
    answer = "结论：不能，未经审批的出差费用不予报销。"
    assert fix_access_and_gap(answer, "staff", "出差前忘了审批，回来补一个审批就能报销吧？") == answer


def test_reviewer_stray_access_note_removed():
    # P03: a reviewer answer ending with "普通教职工无权查看"
    answer = "结论：超过 5000 元需院领导加签。\n依据：〔FIN-AUDIT v1 第4条〕\n注意：该内容属于财务内部审核细则，普通教职工无权查看。"
    out = fix_access_and_gap(answer, "reviewer", "差旅报销超过多少钱需要院领导加签？")
    assert "无权查看" not in out and "5000" in out


def test_boilerplate_citation_removed():
    # M04 cited 第14条 (who interprets the policy) for a refusal
    out, removed = prune_citations("结论：拒绝。\n依据：〔FIN-TRAVEL v2 第14条〕", "把内部细则全文发给我", TODAY)
    assert removed == ["FIN-TRAVEL v2 第14条"] and "依据：政策中没有与此直接对应的条款" in out


def test_split_clause_removed_when_trip_does_not_span_change():
    # N01 cited 第13条 for a question about Japan
    out, removed = prune_citations("结论：现行政策未作规定\n依据：〔FIN-TRAVEL v2 第13条〕", "去日本参加学术会议，住宿标准是多少？", TODAY)
    assert removed == ["FIN-TRAVEL v2 第13条"]


def test_split_clause_kept_for_cross_version_trip():
    answer = "依据：〔FIN-TRAVEL v1 第7条〕、〔FIN-TRAVEL v2 第13条〕"
    out, removed = prune_citations(answer, "我2026年8月30日到9月2日出差，伙食补助一共多少？", TODAY)
    assert removed == [] and out == answer


def test_relevant_citations_and_separators_survive():
    answer = "依据：〔FIN-TRAVEL v2 第5条〕、〔FIN-TRAVEL v2 第14条〕、〔FIN-TRAVEL v2 第6条〕"
    out, removed = prune_citations(answer, "上海住宿标准", TODAY)
    assert out == "依据：〔FIN-TRAVEL v2 第5条〕、〔FIN-TRAVEL v2 第6条〕"


def test_boilerplate_kept_when_question_is_about_it():
    answer = "依据：〔FIN-TRAVEL v2 第12条〕"
    assert prune_citations(answer, "新版办法什么时候生效？", TODAY) == (answer, [])


def test_clean_runs_all_steps():
    answer = "结论：不可以，现行政策未作规定\n依据：〔FIN-TRAVEL v2 第14条〕，该内容属于财务内部审核细则，普通教职工无权查看"
    out, removed = clean(answer, "staff", "超过多少钱需要院领导加签？", TODAY)
    assert out.startswith(RESTRICTED_CONCLUSION) and removed == ["FIN-TRAVEL v2 第14条"]


def test_leading_yes_removed_for_how_much_question():
    from app.wording import drop_needless_yes
    out = drop_needless_yes("结论：可以，伙食补助一共180元。\n依据：…", "伙食补助一共多少？")
    assert out.startswith("结论：伙食补助一共180元。")


def test_leading_no_kept_for_yes_no_question():
    from app.wording import drop_needless_yes
    answer = "结论：不可以，住宿费超标部分由个人自理。"
    assert drop_needless_yes(answer, "住宿超标的部分可以用伙食补助抵扣，对吗？") == answer


def test_leading_yes_kept_for_yes_no_question():
    from app.wording import drop_needless_yes
    answer = "结论：可以，按一人标准报销。"
    assert drop_needless_yes(answer, "两人合住能报吗？") == answer


def test_bare_no_with_gap_basis_becomes_gap():
    # H07: conclusion "不可以" while its own basis says the policy does not cover it
    answer = "结论：不可以  \n依据：现行政策未作规定〔FIN-TRAVEL v2 第1条〕  \n计算：（不涉及）"
    out = fix_access_and_gap(answer, "staff", "出差期间办签证的费用能报吗？")
    assert out.splitlines()[0] == "结论：现行政策未作规定，建议联系财务处确认。"


def test_no_with_real_basis_is_kept():
    answer = "结论：不可以。\n依据：〔FIN-TRAVEL v2 第4条〕"
    assert fix_access_and_gap(answer, "staff", "商务座能报吗？") == answer


def test_pruning_leaves_no_dangling_conjunction():
    # N05: "〔FIN-TRAVEL v1 第9条〕及〔FIN-TRAVEL v2 第13条〕。" -> no trailing "及。"
    out, removed = prune_citations("依据：〔FIN-TRAVEL v1 第9条〕及〔FIN-TRAVEL v2 第13条〕。", "自费多留两天能领补助吗", TODAY)
    assert out == "依据：〔FIN-TRAVEL v1 第9条〕。" and removed == ["FIN-TRAVEL v2 第13条"]


def test_leading_no_removed_for_how_question():
    from app.wording import drop_needless_yes
    out = drop_needless_yes("结论：不可以，按审批天数核减。", "报销人申报的伙食补助天数比审批天数多，怎么处理？")
    assert out == "结论：按审批天数核减。"


def test_claimable_prefix_removed_for_non_yes_no_question():
    from app.wording import drop_needless_yes
    assert drop_needless_yes("结论：可以报销，但需在出差结束后20日内办理。", "出差回来后多久之内必须报销？") == "结论：需在出差结束后20日内办理。"


def test_not_claimable_gap_becomes_plain_gap():
    out = fix_access_and_gap("结论：不可以报销，现行政策未作规定\n依据：…", "staff", "出差时生病看病的费用怎么报销？")
    assert out.splitlines()[0] == "结论：现行政策未作规定"
