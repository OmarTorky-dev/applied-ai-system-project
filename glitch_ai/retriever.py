"""Retrieval over the bug-pattern knowledge base (the "R" in RAG).

A small TF-IDF retriever written in plain Python. The knowledge base is nine short
Markdown documents, so a vector database would be overkill. TF-IDF is transparent,
deterministic and easy to test.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

KB_DIR = Path(__file__).parent / "knowledge_base"

# Below this cosine score a document is treated as "not relevant". It was tuned on the
# sample failures in samples/: real matches score around 0.15-0.45, noise is under 0.05.
MIN_RELEVANCE = 0.06

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "for", "on", "with",
    "be", "as", "by", "at", "this", "that", "are", "was", "if", "not", "no", "but",
    "from", "so", "than", "then", "def", "return", "assert", "py", "e", "i",
}


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. snake_case and camelCase identifiers are also split
    into their parts so `check_guess` matches both "check" and "guess"."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    tokens: list[str] = []
    for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+", text):
        word = word.lower()
        parts = [p for p in word.split("_") if p]
        candidates = [word] + (parts if len(parts) > 1 else [])
        tokens.extend(t for t in candidates if t not in _STOPWORDS and len(t) > 1)
    return tokens


@dataclass
class KBDocument:
    doc_id: str
    title: str
    tags: list[str]
    body: str
    path: Path

    @property
    def text(self) -> str:
        return f"{self.title}\n{' '.join(self.tags)}\n{self.body}"


@dataclass
class RetrievedDoc:
    doc: KBDocument
    score: float


@dataclass
class Retriever:
    docs: list[KBDocument]
    _idf: dict[str, float] = field(default_factory=dict, init=False)
    _vectors: list[dict[str, float]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not self.docs:
            raise ValueError("Knowledge base is empty; nothing to retrieve from.")
        doc_tokens = [tokenize(d.text) for d in self.docs]
        n = len(self.docs)
        df = Counter(t for toks in doc_tokens for t in set(toks))
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        # Tags are curated keywords, so they count double.
        for d, toks in zip(self.docs, doc_tokens):
            toks.extend(tokenize(" ".join(d.tags)))
        self._vectors = [self._vectorize(toks) for toks in doc_tokens]

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, k: int = 3) -> list[RetrievedDoc]:
        """Return up to k documents scoring at least MIN_RELEVANCE, best first."""
        qvec = self._vectorize(tokenize(query))
        scored = []
        for doc, dvec in zip(self.docs, self._vectors):
            score = sum(w * dvec.get(t, 0.0) for t, w in qvec.items())
            scored.append(RetrievedDoc(doc, round(score, 4)))
        scored.sort(key=lambda r: r.score, reverse=True)
        return [r for r in scored[:k] if r.score >= MIN_RELEVANCE]


def load_knowledge_base(kb_dir: Path = KB_DIR) -> list[KBDocument]:
    """Parse every KB*.md file: a front-matter block (id, title, tags) followed by the body."""
    docs = []
    for path in sorted(kb_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if not match:
            continue
        meta = dict(
            line.split(":", 1) for line in match.group(1).splitlines() if ":" in line
        )
        docs.append(
            KBDocument(
                doc_id=meta.get("id", path.stem).strip(),
                title=meta.get("title", path.stem).strip(),
                tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                body=match.group(2).strip(),
                path=path,
            )
        )
    return docs
