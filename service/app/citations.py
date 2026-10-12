"""Check the citations in an LLM answer.

An answer may cite 〔FIN-TRAVEL v2 第5条〕 or 〔FIN-TRAVEL v2 第5条、第6条〕.
Every cited article must exist, and staff answers must not cite restricted documents.
"""

import re

from pydantic import BaseModel

from .rules import ARTICLES, RESTRICTED_DOCS

BRACKET = re.compile(r"〔([^〕]*)〕")
REF = re.compile(r"(FIN-[A-Z]+)\s*(v\d+)")
ARTICLE = re.compile(r"第\s*(\d+)\s*条")


class CitationCheck(BaseModel):
    cited: list[str]
    unknown: list[str]        # article does not exist in that document version
    restricted: list[str]     # reviewer-only document cited for a staff user
    ok: bool


def extract(answer: str) -> list[tuple[str, str, int]]:
    found = []
    for inner in BRACKET.findall(answer):
        ref = REF.search(inner)
        if not ref:
            continue
        doc, ver = ref.groups()
        for art in ARTICLE.findall(inner):
            found.append((doc, ver, int(art)))
    return sorted(set(found))


def check(answer: str, role: str) -> CitationCheck:
    cited, unknown, restricted = [], [], []
    for doc, ver, art in extract(answer):
        label = f"{doc} {ver} 第{art}条"
        cited.append(label)
        if not 1 <= art <= ARTICLES.get((doc, ver), 0):
            unknown.append(label)
        if doc in RESTRICTED_DOCS and role != "reviewer":
            restricted.append(label)
    return CitationCheck(cited=cited, unknown=unknown, restricted=restricted, ok=not unknown and not restricted)
