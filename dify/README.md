# Dify apps

Exported DSL files (import in Dify: Studio → Import DSL file). Secrets are exported empty.
All three apps run on the same Dify instance, one per scenario named in the job description.

| File | Scenario | Type | What it does |
|---|---|---|---|
| `reimbursement_assistant.yml` | Administration | Chatflow | Travel-policy Q&A with citations; trip details go to the rules service for calculation; reviewer-only knowledge for reviewers |
| `course_qa_assistant.yml` | Teaching | Chatflow | Answers questions from a lecture's notes, cites sections, writes practice questions, gives hints (not full code) for lab tasks |
| `literature_summary_workflow.yml` | Research | Workflow | Turns a pasted paper or abstract into a fixed-format summary: question, method, data, findings, limitations, relevance |

## Knowledge bases

| Name | Source | Chunking |
|---|---|---|
| 差旅政策-公开 | `data/policies/travel_v1_2025.md`, `travel_v2_2026.md` | Parent-child, parent = full document (keeps version header with every clause) |
| 差旅审核细则-内部 | `data/policies/audit_guide_internal.md` | Same; only the reviewer branch retrieves it |
| 课程讲义-Python基础 | `data/teaching/python_lecture04_lists_loops.md` | General, split on `\n## ` (one chunk per section), whitespace kept so code survives |

All use `bge-m3` embeddings, hybrid search and `bge-reranker-v2-m3`.

## Spot checks (course and research apps)

Not evaluated with a test set; checked by hand on 2026-10-13.

Course app:
- "实验任务2怎么做？" → step hints and a code skeleton, no complete solution. Pass.
- "Python 的字典怎么用？" → "本讲讲义未涉及". Pass. Minor error: its list of what the lecture
  covers left out `while` and `break`/`continue`.
- "while 循环什么时候会变成死循环？" → correct, cites 4.4. Pass.
- First version failed: default chunking split on every newline, so the model received
  fragments such as `python` and said the notes looked empty (it did not invent content).
  Fixed by splitting on section headings.

Research workflow (input: `data/research/sample_abstract.md`, a fictional abstract):
- All numbers (n=42/40, 78.6 vs 71.2, p<0.05, 91%/76%, 83%, 15%, 40%) copied exactly.
- Unstated items (randomisation, sampling) marked "文中未说明".
- Author-stated and model-observed limitations kept separate, as instructed.
