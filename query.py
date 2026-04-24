"""
query.py — Retrieve relevant chunks from ChromaDB and synthesise an answer via Claude.

Usage:
    python query.py --project fire "What are the main drivers of fire spread?"
"""

import argparse
import os
import sys

import anthropic
import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

EMBED_MODEL = "all-MiniLM-L6-v2"
CHROMA_DIR = "chroma_db"
TOP_K = 5
TOP_K_DRAFT = 12
CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a research assistant for an academic lab. Your job is to answer \
questions using only the document excerpts provided to you.

Rules:
1. Answer solely from the provided context. Do not use prior knowledge.
2. Cite every claim using the reference label shown in the excerpt header \
(e.g., [Smith et al. (2023), p. 4] or [Smith et al. (2023) [online]]). \
Place the citation immediately after the relevant sentence.
3. If multiple excerpts support the same point, cite all of them.
4. If the answer is not contained in the provided excerpts, say exactly:
   "I don't have enough information in the provided documents to answer this question."
5. Be concise but complete. Prefer bullet points for multi-part answers.
6. Do not speculate or extrapolate beyond what the documents state."""

DRAFT_SYSTEM_PROMPT = """You are an expert academic writer assisting with grant proposal drafting. \
You will be given excerpts from a project's literature base and a description of the section to write.

Rules:
1. Write formal academic prose suitable for a grant proposal or scientific manuscript.
2. Ground every factual claim in the provided excerpts. Cite inline immediately after the \
relevant sentence using the reference label in the excerpt header \
(e.g., [Smith et al. (2023), p. 4] or [Smith et al. (2023) [online]]).
3. If multiple excerpts support the same point, cite all of them.
4. If the provided literature is insufficient to fully support a point, explicitly flag the gap \
with a note such as: **[GAP: insufficient literature on X — consider adding sources]**
5. Do not fabricate facts, statistics, or citations. Do not use prior knowledge not grounded in \
the excerpts.
6. Output clean markdown. Use paragraph breaks, not bullet points, unless the section type \
specifically calls for a list (e.g., Objectives or Aims).
7. Aim for the length and depth appropriate to the section type requested."""

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_ref(meta: dict) -> str:
    """Format a short citation reference from chunk metadata.
    - Zotero PDF:  'Author et al. (YEAR), p. N'
    - Zotero web:  'Author et al. (YEAR) [online]'
    - Local PDF:   'filename.pdf, p. N'
    """
    author = meta.get("author_str", "")
    year = meta.get("year", "")
    page = meta.get("page", "?")
    is_web = meta.get("source_type") == "web"

    if is_web:
        if author and year:
            return f"{author} ({year}) [online]"
        return f"{meta.get('title', 'web source')} [online]"
    if author and year:
        return f"{author} ({year}), p. {page}"
    return f"{meta.get('filename', 'unknown')}, p. {page}"


def format_context(results: dict) -> str:
    """Convert Chroma query results into a numbered context block for Claude."""
    lines = []
    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0]), start=1
    ):
        lines.append(f"[Excerpt {i} — {make_ref(meta)}]\n{doc}")
    return "\n\n---\n\n".join(lines)


def build_user_message(question: str, context: str) -> str:
    return f"Document excerpts:\n\n{context}\n\n---\n\nQuestion: {question}"


def format_citations(results: dict) -> list[str]:
    """Return a deduplicated ordered list of citation reference strings."""
    seen: set[str] = set()
    citations = []
    for meta in results["metadatas"][0]:
        ref = make_ref(meta)
        if ref not in seen:
            seen.add(ref)
            citations.append(ref)
    return citations


# ── Main ──────────────────────────────────────────────────────────────────────


def query(project: str, question: str) -> tuple[str, list[str]]:
    """
    Run a RAG query against a project collection.

    Returns:
        (answer_text, list_of_citation_strings)

    Raises:
        ValueError: collection missing/empty, or API key not set.
    """
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    existing = client.list_collections()
    if project not in existing:
        raise ValueError(
            f"No collection found for project '{project}'. "
            f"Run `python ingest.py --project {project}` first."
        )

    collection = client.get_collection(name=project)
    if collection.count() == 0:
        raise ValueError(
            f"Collection '{project}' is empty. "
            f"Run `python ingest.py --project {project}` first."
        )

    model = SentenceTransformer(EMBED_MODEL)
    q_embedding = model.encode(question, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(TOP_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    context = format_context(results)
    citations = format_citations(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(question, context)}],
    )

    return message.content[0].text, citations


def draft(project: str, prompt: str) -> tuple[str, list[str]]:
    """
    Generate a grant proposal section draft grounded in the project literature.

    Retrieves TOP_K_DRAFT chunks (more than query()) for broader coverage.

    Returns:
        (draft_text, list_of_citation_strings)

    Raises:
        ValueError: collection missing/empty, or API key not set.
    """
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    existing = client.list_collections()
    if project not in existing:
        raise ValueError(
            f"No collection found for project '{project}'. "
            f"Run `python ingest.py --project {project}` first."
        )

    collection = client.get_collection(name=project)
    if collection.count() == 0:
        raise ValueError(
            f"Collection '{project}' is empty. "
            f"Run `python ingest.py --project {project}` first."
        )

    model = SentenceTransformer(EMBED_MODEL)
    q_embedding = model.encode(prompt, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(TOP_K_DRAFT, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    context = format_context(results)
    citations = format_citations(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=DRAFT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(prompt, context)}],
    )

    return message.content[0].text, citations


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query a project knowledge base via Claude.")
    parser.add_argument("--project", required=True, help="Project name (e.g. fire)")
    parser.add_argument("question", help="Question to ask")
    args = parser.parse_args()

    try:
        answer, citations = query(args.project, args.question)
    except ValueError as e:
        print(f"[error] {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(answer)

    print("\n" + "=" * 60)
    print("SOURCE CHUNKS RETRIEVED")
    print("=" * 60)
    for ref in citations:
        print(f"  - {ref}")
    print()
