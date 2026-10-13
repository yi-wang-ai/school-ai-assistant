"""Teacher-written hints for the lecture's lab tasks (pasted into the Dify code node "教师提示").

For a recognised lab task the app answers from this sheet directly, so the hint cannot be
wrong in the way a small model's hint can. test_lab_hints.py fills each skeleton's
blanks with the reference answer and runs it, so a wrong skeleton fails the tests.
"""

import re

HINTS = {
    "1": {
        "title": "实验任务 1：最高分、最低分、平均分",
        "section": "4.3、4.7",
        "steps": [
            "用 for 循环和 range(10) 读入 10 个成绩，逐个 append 到列表里。",
            "先假设第一个成绩既是最高分也是最低分。",
            "再遍历列表：遇到更大的就更新最高分，遇到更小的就更新最低分，同时累加总分。",
            "平均分 = 总分 ÷ 成绩个数。题目要求不用 max/min。",
        ],
        "skeleton": [
            "scores = []",
            "for i in range(10):",
            "    scores.append(____)",
            "highest = scores[0]",
            "lowest = ____",
            "total = 0",
            "for s in scores:",
            "    if s > highest:",
            "        highest = ____",
            "    if ____:",
            "        lowest = s",
            "    total += ____",
            "print(highest, lowest, ____)",
        ],
        "checks": [
            "input() 得到的是字符串，记得转换成数字。",
            "最高分、最低分的初始值不能设成 0：如果全班都是负分或都很高，结果会错。",
        ],
    },
    "2": {
        "title": "实验任务 2：存款多少年后超过 10000 元",
        "section": "4.4",
        "steps": [
            "本题约定：每年年初存入 1000 元，年末按 3% 计息。",
            "余额从 0 开始，年数从 0 开始。",
            "只要余额还没有超过 10000 元，就再过一年：先存入 1000 元，再乘以 1.03，年数加 1。",
            "循环结束时的年数就是答案。",
        ],
        "skeleton": [
            "balance = 0",
            "years = 0",
            "while ____:",
            "    balance = (____) * ____",
            "    years += 1",
            "print(years)",
        ],
        "checks": [
            "题目是“超过” 10000 元：想清楚循环条件用 < 还是 <=。",
            "循环体里一定要改变余额和年数，否则会死循环（见 4.4）。",
        ],
    },
    "3": {
        "title": "实验任务 3：用列表推导式筛选 90 分及以上",
        "section": "4.6",
        "steps": [
            "列表推导式的格式是 [表达式 for 变量 in 列表 if 条件]。",
            "这里表达式就是成绩本身，条件是成绩不低于 90。",
        ],
        "skeleton": [
            "excellent = [____ for s in scores if ____]",
        ],
        "checks": [
            "“90 分及以上”包含 90 分本身，注意比较符号。",
        ],
    },
}

TASK_NUMBER = re.compile(r"实验(?:任务)?\s*([123一二三])")
CN = {"一": "1", "二": "2", "三": "3"}


def match(query: str) -> str | None:
    m = TASK_NUMBER.search(query)
    if m:
        return CN.get(m.group(1), m.group(1))
    if re.search(r"最高分|最低分", query) and re.search(r"平均", query):
        return "1"
    if re.search(r"利率|本息|存入|存款|存钱", query):
        return "2"
    if re.search(r"90|九十", query) and re.search(r"筛选|推导式|及以上", query):
        return "3"
    return None


def render(task_id: str) -> str:
    h = HINTS[task_id]
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(h["steps"], 1))
    checks = "\n".join(f"- {c}" for c in h["checks"])
    code = "\n".join(h["skeleton"])
    return (
        f"**{h['title']}**（任课教师编写的提示）\n\n"
        f"思路：\n{steps}\n\n"
        f"关键语句（把 ____ 换成你自己的代码）：\n```python\n{code}\n```\n\n"
        f"自查：\n{checks}\n\n"
        f"出处：〔CS101 第4讲 {h['section']}〕\n\n"
        "写完后把你的代码贴给我，我帮你检查。"
    )


def main(query: str) -> dict:
    task = match(query)
    if task is None:
        return {"matched": "no", "text": ""}
    return {"matched": "yes", "text": render(task)}
