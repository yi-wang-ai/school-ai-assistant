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

## Free model: Qwen3-8B (2026-10-13)

Goal: remove the paid DeepSeek API. All three apps now use SiliconFlow `Qwen/Qwen3-8B`
(listed at ¥0 on SiliconFlow's pricing page). Same 39 questions, through `/ask`.

| Run | Change | Auto checks | After manual review | Median latency |
|---|---|---|---|---|
| `free-qwen3-8b` | swap model, thinking off | 21/39 | not reviewed | 24 s |
| `free-qwen3-8b-thinking` | thinking on for answers | 29/39 | not reviewed | 36 s (max 125 s) |
| `free-qwen3-8b-thinking-codecalc` | calculation table rendered by code and appended | 32/39 | 36/39, 3 fail | 36 s |
| `free-final` | + hotel price × nights extraction, conclusion-total check, domestic-only rule | 34/39 | 36/39, 2 debatable, 1 fail | 36 s (max 71 s) |

What the small model got wrong, and what was changed:

- **Numbers.** It ignored or miscopied the service's amounts (e.g. ¥1000 conclusion vs ¥3200
  in its own sum vs ¥3080 correct) and invented explanations (Hangzhou as "other region").
  Fix: the service returns `breakdown_md`; a Dify code node appends it to the answer, and the
  model may state only the total. `/ask` replaces the conclusion if its total differs.
- **Extraction.** It sometimes failed to write per-night `date:price` pairs. Fix: also accept
  `hotel_price` + `hotel_nights`, expanded into consecutive nights in code.
- **Overseas trips.** It applied the domestic "other regions" rate (¥380) to Japan. Fix: an
  explicit rule that the policy covers domestic travel only; 6/6 overseas questions then refused.
- **Still open (free-final):** M01 concludes "政策未作规定" although 第6条 covers it (fail);
  V05 and N05 infer an answer instead of leading with the policy gap (debatable). In an earlier
  free run the extractor misread an end date (V04), so code computed the wrong trip correctly:
  extraction errors remain possible and are not caught by any check.

Trade-off: the free model costs nothing per question but is slower (36 s vs 19 s) and less
reliable in wording; the paid model reached 39/39. Model output varies between runs, so a
single run per configuration is weak evidence.

## Second round of fixes and a held-out set (2026-10-13)

Before changing anything, 15 new questions were written (`holdout.jsonl`), phrased differently
from the main set, with expected answers fixed in advance. They were not used to tune.

| | Main 39 (manual) | Held-out 15 (manual) | Median latency |
|---|---|---|---|
| Before this round (`free-final`, `holdout-before`) | 36/39, 2 debatable, 1 fail | 13/15 | 36 s |
| After (`fix2`, `holdout-after`) | **38/39, 1 debatable** | **15/15** | 35 s |

Changes:
- **Trip parser** (`service/app/trip_parser.py`, 18 tests): reads dates, nights, prices, city
  and provided meals from the question with rules; whatever it finds overrides the LLM's
  extraction. Fixes V04 (end date misread) and H04 (wrong day marked as partial meals). A
  Dify code node now builds the request with `json.dumps`, so quotes or line breaks in a
  question cannot break it.
- **Conclusion rules** in the prompt: answer yes/no whenever a clause decides it; say
  "未作规定" only when no clause covers the matter; a fixed sentence for internal content.
  Fixes M01 and held-out H11 (both had said "not covered").
- **Citation normalization:** a citation without a version (e.g. 〔FIN-AUDIT 内部细则 第2条〕)
  used to be skipped by the checker. Now it is completed when the document has one version
  and flagged as malformed otherwise.

A bug found while reviewing: the conclusion-total check compared the conclusion with the
grand total only, so for "伙食补助一共多少" it replaced the correct meal subtotal with
meals + transport (all 7 corrections in the audit log were of this kind). It now accepts
subtotals and sums of two subtotals; C07, V04 and H04 were re-run after the fix (noted in
their `manual` field).

## Third round: wording (2026-10-13)

`service/app/wording.py` (17 tests) plus changes in `main.py`, all deterministic. Every rule
was first replayed on the 54 recorded answers before deploying; the replay caught two bad
rules (a "no access" rewrite that would have hit public "not covered" questions, and
deadline questions being turned into calculations), both fixed before the live run.

| | Main 39 (manual) | Held-out 15 (manual) |
|---|---|---|
| Before (`fix2`, `holdout-after`) | 38/39, 1 debatable | 15/15 |
| After (`fix4`, `holdout-fix4`) | **39/39** | **15/15** |

- Amount questions: the conclusion is written by code from the breakdown (items asked about
  first, total, overdue / not-covered warnings).
- Internal-audit questions are recognised from the question; staff get one fixed sentence.
  Elsewhere a "普通教职工无权查看" claim is removed (the model also wrote it for public topics).
- "不可以，现行政策未作规定" becomes "现行政策未作规定"; a leading "可以/不可以（报销），" is removed
  when the question is not a yes/no question.
- Citations of interpretation/effective-date clauses, and of the cross-version clause when
  the trip does not span 2026-09-01, are removed.
- Hotel nights from the LLM are ignored when the question mentions no lodging (V04 had two
  invented nights, total ¥1460 instead of ¥760).
- Six answers (A01, A03, V03, V04, H06, H08) were re-run live after the last two changes;
  marked with a `rerun` field.

Still open: P03 (reviewer) came back without a 结论 line and with an odd note; code cannot
write a reliable conclusion from that text, so it is documented rather than patched.

Still wrong after the second round (now fixed above), all wording rather than numbers or access: P02 concludes
"不可以，现行政策未作规定" where the rule asks for "无权查看" only; P03 (reviewer) ends with a
stray "staff cannot view this" note; N01 and M04 cite clauses unrelated to the question. The
keyword grader passes all four, so the totals above count them as passes.

Limits of this evaluation: 39 questions written by the same person who built the system;
keyword grading needs manual review; one run per configuration (LLM output varies between
runs).
