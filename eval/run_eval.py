"""Run the evaluation set against the Dify chat app and score the answers.

Usage:
    python eval/run_eval.py --label baseline                      # Dify only
    python eval/run_eval.py --label with-service --target service # through /ask

Reads DIFY_BASE_URL and DIFY_API_KEY from .env in the repo root.
Writes eval/results/<label>.jsonl (raw answers + automatic checks) and
prints a summary by category.

Automatic checks (no LLM judge):
  - citation: every expected citation (e.g. "FIN-TRAVEL v2 第5条") appears
    in the answer, matched on version + article number.
  - amount:   for calculation items, the expected total appears in the answer.
  - refusal:  for "refuse" items, the answer contains a refusal marker;
              for "answer" items, it must not refuse.
key_facts are left for manual review (column "manual" in the output).
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSAL_MARKERS = ["未作规定", "未规定", "没有规定", "未作明确规定", "未作出规定", "作出明确规定", "无权查看", "无权审批", "拒绝", "无法提供", "不能提供", "无法给出"]


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def ask(env, role, question, target="dify", retries=2):
    if target == "dify":
        # straight to Dify: the role is whatever the caller claims
        url = env["DIFY_BASE_URL"] + "/chat-messages"
        token = env["DIFY_API_KEY"]
        body = {"inputs": {"role": role}, "query": question, "response_mode": "blocking", "user": "eval"}
    else:
        # through the rules service: the role comes from the user's token
        url = env.get("SERVICE_URL", "http://localhost:8000") + "/ask"
        token = env["REVIEWER_TOKEN" if role == "reviewer" else "STAFF_TOKEN"]
        body = {"question": question}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    for attempt in range(retries + 1):
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            return data["answer"], round(time.time() - t0, 1)
        except Exception as e:  # network or server error: retry, then record
            if attempt == retries:
                return f"[ERROR] {e}", None
            time.sleep(3)


def strip_reasoning(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def citation_found(answer, citation):
    # "FIN-TRAVEL v2 第5条" -> require "v2" and "第5条" close together
    m = re.match(r"(FIN-\w+) (v\d) 第(\d+)条", citation)
    doc, ver, art = m.groups()
    pattern = rf"{doc}\s*{ver}[^〕\]\n]{{0,30}}第\s*{art}\s*条|{ver}[^〕\]\n]{{0,30}}第\s*{art}\s*条"
    if re.search(pattern, answer):
        return True
    # "第5条、第6条" style lists after a version tag
    for block in re.findall(rf"{ver}([^〕\]\n]*)", answer):
        if re.search(rf"第\s*{art}\s*条|、\s*{art}\s*条|、第\s*{art}\s*条", block):
            return True
    return False


def conclusion(answer):
    # The prompt asks for "结论：..." first. Judge refusal on that line only, because
    # most answers end with boilerplate such as "不能审批" that is not a refusal.
    m = re.search(r"结论[:：](.*)", answer)
    return m.group(1) if m else answer.split("\n", 1)[0]


def score(item, answer):
    exp = item["expect"]
    refused = any(m in conclusion(answer) for m in REFUSAL_MARKERS)
    checks = {}
    if exp["type"] == "refuse":
        checks["refusal"] = refused
    elif exp["type"] == "answer":
        checks["no_false_refusal"] = not refused
    elif exp["type"] == "ambiguous":
        checks["flags_gap"] = refused
    if exp.get("citations") and exp["type"] != "refuse":
        found = [c for c in exp["citations"] if citation_found(answer, c)]
        checks["citation"] = len(found) == len(exp["citations"])
        checks["citation_recall"] = round(len(found) / len(exp["citations"]), 2)
    if "amount" in exp:
        checks["amount"] = bool(re.search(rf"(?<![\d.]){exp['amount']}(\.0+)?\s*元", answer))
    passed = all(v for k, v in checks.items() if isinstance(v, bool))
    return checks, passed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--target", choices=["dify", "service"], default="dify")
    ap.add_argument("--testset", default="testset.jsonl", help="file in eval/, e.g. holdout.jsonl")
    ap.add_argument("--rescore", action="store_true", help="re-score saved answers without calling Dify")
    args = ap.parse_args()

    items = [json.loads(l) for l in (ROOT / "eval" / args.testset).read_text().splitlines() if l.strip()]
    out = ROOT / "eval/results" / f"{args.label}.jsonl"

    if args.rescore:
        saved = {r["id"]: r for r in map(json.loads, out.read_text().splitlines())}
        results = []
        for item in items:
            r = saved[item["id"]]
            checks, passed = score(item, r["answer"])
            results.append({**r, **item, "checks": checks, "auto_pass": passed})
        report(args.label, results, out)
        return

    env = load_env()

    def run(item):
        raw, secs = ask(env, item["role"], item["question"], args.target)
        answer = strip_reasoning(raw)
        checks, passed = score(item, answer)
        return {**item, "answer": answer, "latency_s": secs, "checks": checks, "auto_pass": passed, "manual": None}

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(run, items))
    out.parent.mkdir(exist_ok=True)
    report(args.label, results, out)


def report(label, results, out):
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results))

    cats = {}
    for r in results:
        c = cats.setdefault(r["category"], [0, 0])
        c[0] += r["auto_pass"]
        c[1] += 1
    total = sum(r["auto_pass"] for r in results)
    print(f"{label}: {total}/{len(results)} passed automatic checks")
    for k, (p, n) in cats.items():
        print(f"  {k:12s} {p}/{n}")
    print("failed:", ", ".join(r["id"] for r in results if not r["auto_pass"]) or "none")
    errors = [r["id"] for r in results if r["answer"].startswith("[ERROR]")]
    if errors:
        print("errors:", ", ".join(errors))
        sys.exit(1)


if __name__ == "__main__":
    main()
