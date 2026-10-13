"""Check the citations in an LLM answer.

An answer may cite 〔FIN-TRAVEL v2 第5条〕 or 〔FIN-TRAVEL v2 第5条、第6条〕.
Every cited article must exist, and staff answers must not cite restricted documents.

A bracket that cites an article without a usable document and version (e.g.
〔FIN-AUDIT 内部细则 第2条〕 or 〔第5条〕) used to be skipped silently. Now:
- if the document has only one version, the version is filled in (normalize());
- otherwise the citation is reported as malformed and the check fails.
"""

import re

from pydantic import BaseModel

from .rules import ARTICLES, RESTRICTED_DOCS

BRACKET = re.compile(r"〔([^〕]*)〕")
REF = re.compile(r"(FIN-[A-Z]+)\s*(v\d+)")
DOC = re.compile(r"FIN-[A-Z]+")
ARTICLE = re.compile(r"第\s*(\d+)\s*条")
VERSIONS = {}
for _doc, _ver in ARTICLES:
    VERSIONS.setdefault(_doc, []).append(_ver)


class CitationCheck(BaseModel):
    cited: list[str]
    unknown: list[str]        # article does not exist in that document version
    restricted: list[str]     # reviewer-only document cited for a staff user
    malformed: list[str] = []  # article cited without a document version we can resolve
    ok: bool


def normalize(answer: str) -> str:
    """Fill in the version when the cited document has exactly one version."""
    def fix(m):
        inner = m.group(1)
        if REF.search(inner) or not ARTICLE.search(inner):
            return m.group(0)
        doc = DOC.search(inner)
        if doc and len(VERSIONS.get(doc.group(), [])) == 1:
            arts = "、".join(f"第{a}条" for a in ARTICLE.findall(inner))
            return f"〔{doc.group()} {VERSIONS[doc.group()][0]} {arts}〕"
        return m.group(0)
    return BRACKET.sub(fix, answer)


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


def malformed(answer: str) -> list[str]:
    return [f"〔{inner}〕" for inner in BRACKET.findall(answer) if ARTICLE.search(inner) and not REF.search(inner)]


def check(answer: str, role: str) -> CitationCheck:
    cited, unknown, restricted = [], [], []
    for doc, ver, art in extract(answer):
        label = f"{doc} {ver} 第{art}条"
        cited.append(label)
        if not 1 <= art <= ARTICLES.get((doc, ver), 0):
            unknown.append(label)
        if doc in RESTRICTED_DOCS and role != "reviewer":
            restricted.append(label)
    bad = malformed(answer)
    for inner in bad:  # a restricted document cited without a version is still restricted
        if role != "reviewer" and any(d in inner for d in RESTRICTED_DOCS):
            restricted.append(inner)
    return CitationCheck(cited=cited, unknown=unknown, restricted=restricted, malformed=bad,
                         ok=not unknown and not restricted and not bad)
