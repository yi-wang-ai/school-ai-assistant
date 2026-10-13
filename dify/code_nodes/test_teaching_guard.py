"""Tests for the course app's code guard (the same source is pasted into the Dify code node).

    cd dify/code_nodes && python -m pytest -q
"""

from teaching_guard import main


def block(code):
    return f"思路：……\n```python\n{code}\n```\n写完后把你的代码贴给我。"


def test_complete_solution_is_hidden():
    r = main(block("balance = 0\nyear = 0\nwhile balance <= 10000:\n    balance = balance * 1.03 + 1000\n    year += 1\nprint(year)"))
    assert r["removed"] == 1 and "year += 1" not in r["text"]


def test_skeleton_with_enough_blanks_is_kept():
    code = "balance = ____\nyear = 0\nwhile ____:\n    balance = ____\n    year += 1\nprint(year)"
    r = main(block(code))
    assert r["removed"] == 0 and "while ____" in r["text"]


def test_nearly_complete_skeleton_is_hidden():
    code = "\n".join(["scores = []", "for ____ in range(10):", "    scores.append(int(input()))",
                      "total = 0", "best = ____", "for s in scores:", "    total += s",
                      "    if s > best:", "        best = s", "avg = total / 10", "print(best, avg)", "print(____)"])
    assert main(block(code))["removed"] == 1  # 12 lines, 3 blanks


def test_reference_answer_section_is_cut():
    r = main("思路：先……\n\n**参考答案**：\nprint(1)")
    assert "参考答案" not in r["text"] and r["text"].startswith("思路")


def test_short_example_without_loop_is_kept():
    assert main(block("squares = [x * x for x in range(1, 6)]"))["removed"] == 0


def test_unfenced_near_complete_code_is_hidden():
    text = ("思路：……\n关键语句：\nprincipal = 0  \nyear = 0  \nwhile ____:  \n"
            "    principal = principal * 1.03 + 1000  \n    year = year + 1  \nprint(\"____年\")  \n\n自查：……")
    r = main(text)
    assert r["removed"] == 1 and "1.03" not in r["text"] and r["text"].startswith("思路")


def test_unfenced_skeleton_with_enough_blanks_is_kept():
    text = "关键语句：\nyear = ____\nwhile ____:\n    balance = ____\nprint(____)\n自查：……"
    assert main(text)["removed"] == 0


def test_prose_is_not_mistaken_for_code():
    text = "思路：\n1. 初始化本金为 0。\n2. 使用 while 循环判断本金。\n3. 每年存入 1000 元。\n写完后把代码贴给我。"
    assert main(text)["removed"] == 0
