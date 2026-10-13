"""Check the course Q&A app for full-solution leaks.

Usage:
    python eval/run_teaching_eval.py --label before --runs 2

A "lab" answer fails if it contains code a student could hand in: any block, fenced or not,
with fewer blanks (____ / TODO / ...) than one per 2 lines. Detection is shared with the
guard in dify/code_nodes/teaching_guard.py. A "check" answer must point out that `year`
is never incremented. "concept" answers must not be empty; "out_of_scope" answers must say
the lecture does not cover the topic.
"""

import argparse
import json
import re
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dify/code_nodes"))
from teaching_guard import code_blocks, too_complete  # noqa: E402


def env():
    return dict(l.split("=", 1) for l in (ROOT / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))


def ask(e, question):
    req = urllib.request.Request(
        e["DIFY_BASE_URL"] + "/chat-messages",
        data=json.dumps({"inputs": {}, "query": question, "response_mode": "blocking", "user": "teach-eval"}).encode(),
        headers={"Authorization": "Bearer " + e["DIFY_TEACH_KEY"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        answer = json.load(r)["answer"]
    return re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()


def full_solution_blocks(answer):
    return [b for b in code_blocks(answer) if too_complete(b)]


def judge(item, answer):
    kind = item["kind"]
    if kind == "lab":
        leaks = full_solution_blocks(answer)
        return not leaks, f"{len(leaks)} complete code block(s)" if leaks else "hints only"
    if kind == "check":
        ok = "year" in answer and re.search(r"year\s*\+=\s*1|没有.*(增加|加 ?1|自增)|未.*(增加|更新)|年份.*(不变|没有)", answer)
        return bool(ok), "found the missing year += 1" if ok else "missed the bug"
    if kind == "out_of_scope":
        ok = "未涉及" in answer
        return ok, "says not covered" if ok else "answered beyond the notes"
    return bool(answer.strip()), "answered"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()
    e = env()
    items = [json.loads(l) for l in (ROOT / "eval/teaching_testset.jsonl").read_text().splitlines() if l.strip()]
    rows = []
    for item in items:
        for run in range(args.runs):
            answer = ask(e, item["question"])
            ok, why = judge(item, answer)
            rows.append({**item, "run": run + 1, "answer": answer, "pass": ok, "reason": why})
            print(f"{item['id']} run{run + 1}: {'PASS' if ok else 'FAIL'} ({why})")
    out = ROOT / "eval/results" / f"teaching-{args.label}.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    lab = [r for r in rows if r["kind"] == "lab"]
    print(f"\n{args.label}: {sum(r['pass'] for r in rows)}/{len(rows)} passed; "
          f"lab answers without a full solution: {sum(r['pass'] for r in lab)}/{len(lab)}")


if __name__ == "__main__":
    main()
