"""Knowledge base for RAG: runbooks (Markdown), policies (TXT) and a known-error database (CSV).

Three file types are loaded with three loaders, chunked per section with the document title prefixed to every
chunk, embedded with all-MiniLM-L6-v2 and indexed in FAISS (exact search, squared L2 distance).
"""
from __future__ import annotations

import csv
import glob
import hashlib
import logging
import math
import os
import re
import time
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import Settings

logger = logging.getLogger("oncall.knowledge")


class HashEmbeddings(Embeddings):
    """Offline bag-of-words embedder (384-d, unit length) for tests and CI. Not used in production."""

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * 384
        for word in re.findall(r"[a-z0-9_]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % 384] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


def create_embeddings(model_name: str) -> Embeddings:
    if model_name == "hash":
        return HashEmbeddings()
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=model_name)


@dataclass
class Passage:
    text: str
    source: str
    section: str
    incident_type: str
    distance: float


# ----------------------------------------------------------------------------- loaders
def load_markdown_runbooks(folder: str) -> list[Document]:
    docs = []
    for path in sorted(glob.glob(os.path.join(folder, "*.md"))):
        text = open(path, encoding="utf-8").read()
        title_m = re.search(r"^#\s+(.+)$", text, re.M)
        title = title_m.group(1).strip() if title_m else os.path.basename(path)
        incident_type = os.path.splitext(os.path.basename(path))[0]
        # split into "## Section" blocks
        parts = re.split(r"^##\s+", text, flags=re.M)
        for part in parts[1:]:
            heading, _, body = part.partition("\n")
            docs.append(Document(page_content=body.strip(),
                                 metadata={"source": os.path.basename(path), "type": "runbook", "title": title,
                                           "section": heading.strip(), "incident_type": incident_type}))
    return docs


def load_text_policies(folder: str) -> list[Document]:
    docs = []
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        text = open(path, encoding="utf-8").read()
        title = text.strip().splitlines()[0].strip()
        for i, para in enumerate(p for p in re.split(r"\n\s*\n", text) if p.strip()):
            docs.append(Document(page_content=para.strip(),
                                 metadata={"source": os.path.basename(path), "type": "policy", "title": title,
                                           "section": f"paragraph {i + 1}", "incident_type": "general"}))
    return docs


def load_known_errors(folder: str) -> list[Document]:
    docs = []
    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                content = (f"Known error {row['id']}: {row['title']}. Root cause: {row['root_cause']}. "
                           f"Resolution: {row['resolution']}. Date: {row['date']}.")
                docs.append(Document(page_content=content,
                                     metadata={"source": os.path.basename(path), "type": "known_error",
                                               "title": "Known error database", "section": row["id"],
                                               "incident_type": row["incident_type"]}))
    return docs


def build_chunks(docs: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    chunks: list[Document] = []
    for d in docs:
        prefix = f"{d.metadata['title']} - {d.metadata['section']}\n"
        budget = max(150, chunk_size - len(prefix))
        splitter = RecursiveCharacterTextSplitter(chunk_size=budget, chunk_overlap=min(chunk_overlap, budget // 3))
        for piece in splitter.split_text(d.page_content):
            chunks.append(Document(page_content=prefix + piece, metadata={**d.metadata, "chunk_id": len(chunks)}))
    return chunks


class KnowledgeBase:
    def __init__(self, settings: Settings):
        from langchain_community.vectorstores import FAISS
        t0 = time.perf_counter()
        kb = settings.knowledge_dir
        self.documents = (load_markdown_runbooks(os.path.join(kb, "runbooks"))
                          + load_text_policies(os.path.join(kb, "policies"))
                          + load_known_errors(os.path.join(kb, "policies")))
        if not self.documents:
            raise ValueError(f"No knowledge-base documents found under {kb}")
        self.chunks = build_chunks(self.documents, settings.chunk_size, settings.chunk_overlap)
        self.embeddings = create_embeddings(settings.embedding_model)
        self.store = FAISS.from_documents(self.chunks, self.embeddings)
        self.settings = settings
        self.build_ms = (time.perf_counter() - t0) * 1000
        self.file_types = sorted({os.path.splitext(d.metadata["source"])[1] for d in self.documents})
        logger.info("knowledge_ready documents=%d chunks=%d file_types=%s build_ms=%.0f",
                    len(self.documents), len(self.chunks), self.file_types, self.build_ms)

    @property
    def size(self) -> int:
        return int(self.store.index.ntotal)

    def search(self, query: str, k: int | None = None, incident_type: str | None = None) -> list[Passage]:
        """Top-k passages. When the incident type is known, runbook chunks of that type are boosted by
        searching with a larger k and preferring matching chunks (hybrid of semantic search + metadata)."""
        k = k or self.settings.top_k
        hits = self.store.similarity_search_with_score(query, k=k * 3 if incident_type else k)
        passages = [Passage(doc.page_content, doc.metadata["source"], doc.metadata["section"],
                            doc.metadata["incident_type"], float(dist)) for doc, dist in hits]
        if incident_type:
            matching = [p for p in passages if p.incident_type == incident_type]
            general = [p for p in passages if p.incident_type != incident_type]
            passages = (matching + general)[:k]
        return passages[:k]
