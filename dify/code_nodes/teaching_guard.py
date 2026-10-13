"""Guard for the course app's hint branch (pasted into the Dify code node "拦截完整代码").

Hides code a student could hand in as is. Code counts whether or not the model put it
in ``` fences: three or more consecutive Python-looking lines are treated as a block.
"""

import re

FENCED = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
BLANK = re.compile(r"_{3,}|TODO|\.\.\.|…")
PY_LINE = re.compile(
    r"^\s*(?:[A-Za-z_][\w\[\]\.]*\s*(?:=|\+=|-=|\*=|/=)(?!=)|while\b|for\b|if\b|elif\b|else\s*:|print\(|def\b|return\b|import\b|[A-Za-z_]\w*\.\w+\()"
)
NOTE = "（这里本来是一段完整或接近完整的代码，已省略。请按上面的思路自己写，写完把代码贴给我，我帮你检查。）"


def too_complete(code: str) -> bool:
    lines = [l for l in code.strip().splitlines() if l.strip() and not l.strip().startswith("#")]
    runnable = re.search(r"\b(while|for)\b|print\(", code) and len(lines) >= 3
    # Hand-in-able: fewer blanks than the hint prompt requires (one per 2 lines).
    return bool(runnable) and len(BLANK.findall(code)) < max(1, len(lines) // 2)


def unfenced_runs(text: str) -> list[tuple[int, int]]:
    """Line ranges [start, end) of 3+ consecutive Python-looking lines outside fences."""
    lines, runs, start = text.split("\n"), [], None
    in_fence = False
    for i, line in enumerate(lines + [""]):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        is_code = not in_fence and bool(PY_LINE.match(line.replace("　", " ")))
        if is_code and start is None:
            start = i
        elif not is_code and start is not None:
            if i - start >= 3:
                runs.append((start, i))
            start = None
    return runs


def code_blocks(text: str) -> list[str]:
    lines = text.split("\n")
    return FENCED.findall(text) + ["\n".join(lines[a:b]) for a, b in unfenced_runs(text)]


def main(text: str) -> dict:
    removed = 0

    def hide_fenced(m):
        nonlocal removed
        if too_complete(m.group(1)):
            removed += 1
            return "```\n" + NOTE + "\n```"
        return m.group(0)

    text = FENCED.sub(hide_fenced, text)
    lines = text.split("\n")
    for a, b in reversed(unfenced_runs(text)):
        if too_complete("\n".join(lines[a:b])):
            removed += 1
            lines[a:b] = [NOTE]
    text = "\n".join(lines)
    text = re.split(r"\n\**\s*(参考答案|完整代码|标准答案)\s*\**[:：]?", text)[0].rstrip()
    return {"text": text, "removed": removed}
