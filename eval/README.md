# Evaluation

`testset.jsonl` holds 39 questions with expected answers, citations and (for calculations) amounts.
`run_eval.py` sends each question to the Dify app through its API and applies automatic checks.

```bash
python eval/run_eval.py --label baseline            # call Dify, save eval/results/baseline.jsonl
python eval/run_eval.py --label baseline --rescore  # re-score saved answers only
```

Automatic checks: expected citations present (version + article), expected amount present,
refusal or no refusal judged on the "结论" line. Items flagged by the checks are then reviewed
by hand; verdicts are stored in the `manual` field of the results file.

## Baseline (2026-10-13): Dify only, no custom service

App: `dify/reimbursement_assistant.yml` (chatflow, `deepseek-v4-flash`, temperature 0.1;
hybrid retrieval with `bge-m3` + `bge-reranker-v2-m3`, Top K 3; role chosen at start).

| Category | Auto checks | After manual review |
|---|---|---|
| Answerable | 8/10 | 10/10 |
| Version traps | 6/6 | 6/6 |
| Calculations | 6/7 | 6/7 |
| No evidence (must refuse) | 5/6 | 5/6 + 1 debatable |
| Access control | 3/4 | 4/4 |
| Misleading | 5/6 | 6/6 |
| **Total** | **33/39** | **37/39 pass, 1 fail, 1 debatable** |

Manual review covered every item the checks flagged, plus a sample of passing items
(C03, V04, V05, P02, M04). The other passing items were not read in full.

### Findings

1. **Retrieval miss (C05, real failure).** For the trip spanning 2026-09-01, only the 2026
   document reached the model, so it said the 2025 standards were unavailable and could not
   give a total. Both documents need to be in context for cross-version questions.
2. **Grader false negatives (A09, A10, P03, M03).** Correct answers that mention a gap in
   passing ("现行政策未作规定") or refuse with different wording ("我不能批准") fail
   keyword checks. Keyword grading is only a filter; flagged items need human review.
3. **Inference on silent policy (N05, debatable).** The policy does not cover a private
   extension after the trip. The model answered "no" by reasoning from 第1/7/8条 while
   flagging the gap. Whether that counts as a refusal is a policy decision.
4. **Test-set gap (C05).** The trip ended 2026-09-02; under the 20-day rule the claim
   window closed on 2026-09-22. The model pointed this out; the expected answer did not.
   The test set should state the claim date for every calculation question.
5. **Access control is prompt-level only.** The role is picked by the user at the start of
   the chat, so anyone can choose "reviewer". Real enforcement belongs in the custom service.

## With the rules service (2026-10-13)

Questions go through the service's `/ask` endpoint: the role comes from the user's token,
citations are checked, every answer is written to the PostgreSQL audit log. Inside Dify, a
parameter extractor pulls trip details from the question and an HTTP node calls the
service's `/tool/calculate`; the LLM must copy the service's amounts instead of computing.
Public-policy retrieval Top K raised from 3 to 6.

| Category | Baseline auto | Baseline manual | With service auto | With service manual |
|---|---|---|---|---|
| Answerable | 8/10 | 10/10 | 10/10 | 10/10 |
| Version traps | 6/6 | 6/6 | 6/6 | 6/6 |
| Calculations | 6/7 | 6/7 | 7/7 | 7/7 |
| No evidence | 5/6 | 5/6 + 1 debatable | 5/6 | 6/6 |
| Access control | 3/4 | 4/4 | 4/4 | 4/4 |
| Misleading | 5/6 | 6/6 | 5/6 | 6/6 |
| **Total** | **33/39** | **37/39** | **37/39** | **39/39** |

Both runs were re-scored with the same (final) grader. Manual review again covered every
flagged item; N04 and M02 were correct answers that the keyword grader missed.

What changed:

- **C05 fixed.** All amounts now come from the calculator (¥2300 with v1/v2 split per day),
  and the overdue warning (deadline 2026-09-22) comes from code, not from the model.
- **N05 improved.** The answer now leads with the policy gap and refers to the finance office.
- **Role can no longer be chosen by the user.** A staff token asking for the sign-off
  threshold gets a refusal; a reviewer token gets "超过 5000 元" citing FIN-AUDIT v1 第4条.
- **Every cited article is checked** against the policy registry; none were unknown or
  restricted in this run.
- **Cost:** median latency rose to 19 s (max 27 s) because of the extra extraction call.

Limits of this evaluation: 39 questions written by the same person who built the system;
keyword grading needs manual review; one run per configuration (LLM output varies between
runs).
