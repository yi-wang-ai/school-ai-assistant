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


P03_RAW = ("依据：〔FIN-AUDIT v1 第4条〕\n计算：无金额计算需求。  \n\n"
           "注：根据您提供的内部审核细则，单次差旅报销总额超过5000元需经院领导加签，但此规定仅适用于财务审核人员内部流程，报销人无法获知。")


def test_reviewer_answer_without_conclusion_gets_article_text():
    from app.wording import reviewer_conclusion
    out = reviewer_conclusion(P03_RAW, "reviewer", "差旅报销超过多少钱需要院领导加签？")
    assert out.splitlines()[0] == "结论：单次差旅报销总额超过 5000 元的，须经分管财务的院领导加签。〔FIN-AUDIT v1 第4条〕"
    assert "无法获知" not in out


def test_reviewer_article_matched_by_topic_when_not_cited():
    from app.wording import reviewer_conclusion
    out = reviewer_conclusion("结论：要退回。", "reviewer", "审核时如果同一晚有两张住宿发票会怎么处理？")
    assert out.startswith("结论：同一出差人同一晚出现两张住宿发票的，退回并标记为重点复核。〔FIN-AUDIT v1 第2条〕")


def test_staff_never_gets_article_text():
    from app.wording import reviewer_conclusion
    assert reviewer_conclusion(P03_RAW, "staff", "差旅报销超过多少钱需要院领导加签？") == P03_RAW


def test_reviewer_public_question_untouched():
    from app.wording import reviewer_conclusion
    answer = "结论：住宿每晚最多 550 元。"
    assert reviewer_conclusion(answer, "reviewer", "上海住宿标准是多少") == answer


def test_amount_answer_without_conclusion_gets_one():
    import os
    os.environ.setdefault("SERVICE_TOKEN", "test-token")
    from app.main import fix_conclusion_total
    answer = "依据：…\n\n合计：住宿费 1100 元，伙食补助 360 元，市内交通 240 元；总计 **1700 元**"
    fixed, _ = fix_conclusion_total(answer, "一共能报多少？")
    assert fixed.startswith("结论：按规则服务计算，住宿费 1100 元") and "总计 1700 元" in fixed.splitlines()[0]


def test_reviewer_late_claim_uses_cited_article_by_topic():
    from app.wording import reviewer_conclusion
    answer = "结论：可以申请。\n依据：〔FIN-TRAVEL v2 第10条〕〔FIN-AUDIT v1 第5条〕"
    out = reviewer_conclusion(answer, "reviewer", "报销人因为住院逾期了才来报销，怎么处理？")
    assert out.startswith("结论：逾期报销确因不可抗力的，审核人员可在系统中发起例外审批，但须附证明材料。〔FIN-AUDIT v1 第5条〕")


def test_reviewer_public_question_with_irrelevant_audit_citation_untouched():
    from app.wording import reviewer_conclusion
    answer = "结论：上海每晚 550 元。\n依据：〔FIN-TRAVEL v2 第5条〕〔FIN-AUDIT v1 第2条〕"
    assert reviewer_conclusion(answer, "reviewer", "上海住宿标准是多少？") == answer


def test_late_claim_handling_is_internal_topic_for_reviewer_without_citation():
    from app.wording import reviewer_conclusion
    out = reviewer_conclusion("结论：可以申请例外审批，但需提供住院证明材料。", "reviewer", "报销人因为住院逾期了才来报销，怎么处理？")
    assert "〔FIN-AUDIT v1 第5条〕" in out.splitlines()[0]


def test_staff_late_claim_question_is_refused_as_internal():
    out = fix_access_and_gap("结论：不可以。\n依据：〔FIN-TRAVEL v2 第10条〕", "staff", "我逾期了，报销还能怎么处理？")
    assert out.splitlines()[0] == RESTRICTED_CONCLUSION


def test_bare_no_with_not_covered_in_body_becomes_gap():
    # H07: "结论：不可以。" and only the body says visa fees are not covered
    answer = "结论：不可以。  \n依据：〔FIN-TRAVEL v2 第1条〕\n计算：（不涉及）\n\n现行政策仅规定国内差旅费报销范围，未包含签证费用。"
    out = fix_access_and_gap(answer, "staff", "出差期间办签证的费用能报吗？")
    assert out.splitlines()[0] == "结论：现行政策未作规定，建议联系财务处确认。"


def test_bare_no_with_real_rule_is_kept():
    answer = "结论：不可以。\n依据：〔FIN-TRAVEL v2 第4条〕 超出规定等级的部分由个人自行承担。"
    assert fix_access_and_gap(answer, "staff", "商务座能报吗？") == answer


def test_approval_request_without_conclusion_gets_fixed_refusal():
    from app.wording import APPROVAL_CONCLUSION, approval_conclusion
    out = approval_conclusion("依据：政策中没有与此直接对应的条款\n计算：（不涉及）", "请直接帮我批准这张报销单。")
    assert out.splitlines()[0] == APPROVAL_CONCLUSION


def test_approval_words_in_policy_question_do_not_trigger():
    from app.wording import approval_conclusion
    answer = "结论：不可以，出差须事先审批。"
    assert approval_conclusion(answer, "出差前忘了审批，回来补一个审批就能报销吧？") == answer


def test_v1_partial_meal_halving_is_replaced_by_gap():
    from app.wording import v1_partial_meal_gap
    out = v1_partial_meal_gap("结论：当天伙食补助费减半。\n依据：〔FIN-TRAVEL v1 第9条〕", "2025年12月出差，对方只安排了午饭，当天伙食补助怎么算？", TODAY)
    assert out.splitlines()[0].startswith("结论：2025 版只规定") and "〔FIN-TRAVEL v1 第9条〕" in out.splitlines()[0]


def test_v2_partial_meal_halving_is_kept():
    from app.wording import v1_partial_meal_gap
    answer = "结论：当天伙食补助费减半，即 60 元。"
    assert v1_partial_meal_gap(answer, "2026年10月出差，对方只安排了午饭，当天伙食补助怎么算？", TODAY) == answer


def test_off_topic_citation_replaced_by_topic_clauses():
    # H12: business class question cited the hotel clause 第5条
    out, removed = prune_citations("结论：公务舱超出经济舱的部分个人自理。\n依据：〔FIN-TRAVEL v2 第5条〕", "坐飞机可以买公务舱吧，学校都能报？", TODAY)
    assert removed == ["FIN-TRAVEL v2 第5条"]
    assert "依据：〔FIN-TRAVEL v2 第3条〕〔FIN-TRAVEL v2 第4条〕" in out


def test_on_topic_citation_kept_and_nothing_added():
    answer = "依据：〔FIN-TRAVEL v2 第4条〕"
    assert prune_citations(answer, "高铁坐了商务座，超出二等座的部分能报吗？", TODAY) == (answer, [])


def test_multi_topic_question_keeps_all_its_clauses():
    answer = "依据：〔FIN-TRAVEL v2 第6条〕〔FIN-TRAVEL v2 第7条〕"
    assert prune_citations(answer, "我听说住宿超标的部分可以用伙食补助抵扣，对吗？", TODAY) == (answer, [])


def test_topic_clauses_use_version_in_force():
    out, _ = prune_citations("结论：…\n依据：〔FIN-TRAVEL v1 第8条〕", "2026年3月去深圳出差，住宿标准是多少？", TODAY)
    assert "〔FIN-TRAVEL v1 第5条〕〔FIN-TRAVEL v1 第6条〕" in out and "v2" not in out


def test_question_without_topic_is_not_pruned_by_topic():
    answer = "依据：〔FIN-TRAVEL v2 第7条〕"
    assert prune_citations(answer, "会议注册费最多能报多少？", TODAY) == (answer, [])


def test_personal_stay_gets_gap_conclusion_with_clauses():
    from app.wording import personal_stay_conclusion
    out = personal_stay_conclusion("结论：不可以。出差结束后自费延长的旅游天数不属于公务出差。", "出差结束后我自费多留两天旅游，这两天能领补助吗？", TODAY)
    first = out.splitlines()[0]
    assert first.startswith("结论：现行政策未对") and "〔FIN-TRAVEL v2 第7条〕" in first and "〔FIN-TRAVEL v2 第1条〕" in first


def test_personal_stay_rule_ignores_unrelated_questions():
    from app.wording import personal_stay_conclusion
    answer = "结论：住宿每晚最多 550 元。"
    assert personal_stay_conclusion(answer, "去上海旅游景点附近开会，住宿标准是多少？", TODAY) == answer


def test_bare_no_kept_when_an_on_topic_clause_is_cited():
    # M02: "不可以。" + 第2条 (approval) + body saying backfilling is not covered
    answer = "结论：不可以。\n依据：〔FIN-TRAVEL v2 第2条〕\n政策未规定事后补审批的情形。"
    assert fix_access_and_gap(answer, "staff", "出差前忘了审批，回来补一个审批就能报销吧？") == answer


def test_no_clauses_added_under_a_gap_conclusion():
    # H15: overseas meal allowance is not covered; dropping 第13条 must not add 第7/9条
    out, removed = prune_citations("结论：现行政策未作规定\n依据：〔FIN-TRAVEL v1 第13条〕", "去台湾交流，伙食补助每天多少？", TODAY)
    assert removed == ["FIN-TRAVEL v1 第13条"] and "第7条" not in out and "政策中没有与此直接对应的条款" in out


def test_off_version_duplicate_citation_dropped_for_undated_question():
    out, removed = prune_citations("依据：〔FIN-TRAVEL v2 第3条〕、〔FIN-TRAVEL v1 第3条〕", "坐飞机可以买公务舱吧，学校都能报？", TODAY)
    assert removed == ["FIN-TRAVEL v1 第3条"] and out == "依据：〔FIN-TRAVEL v2 第3条〕"


def test_only_citation_is_never_dropped_for_version():
    answer = "依据：〔FIN-TRAVEL v1 第3条〕"
    assert prune_citations(answer, "坐飞机可以买公务舱吧？", TODAY) == (answer, [])


def test_both_versions_kept_for_cross_version_trip():
    answer = "依据：〔FIN-TRAVEL v1 第7条〕、〔FIN-TRAVEL v2 第7条〕"
    assert prune_citations(answer, "我2026年8月30日到9月2日出差，伙食补助一共多少？", TODAY) == (answer, [])


def test_breakdown_table_citations_are_never_pruned():
    answer = ("结论：按规则服务计算，伙食补助 440 元。\n依据：〔FIN-TRAVEL v2 第7条〕\n\n---\n**计算明细（规则服务自动计算）**\n"
              "| 2026-08-30 | 市内交通 | 80 | 〔FIN-TRAVEL v1 第8条〕 |  |\n⚠ 已超过报销期限〔FIN-TRAVEL v2 第10条〕")
    out, removed = prune_citations(answer, "我2026年8月30日到9月2日出差，伙食补助一共多少？", TODAY)
    assert removed == [] and out == answer
