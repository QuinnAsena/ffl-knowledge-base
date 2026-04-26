"""
query.py — Retrieve relevant chunks from ChromaDB and synthesise an answer via Claude.

Usage:
    python query.py --project fire "What are the main drivers of fire spread?"
"""

import argparse
import json
import os
import re
import sys
import time
from functools import lru_cache

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

PAPER_SYSTEM_PROMPT = """You are an expert scientific writer assisting with academic manuscript drafting. \
You will be given excerpts from a project's literature base and a description of the section to write.

Rules:
1. Write formal academic prose appropriate for a peer-reviewed journal manuscript. Use third person, \
past tense for methods and results, present tense for established facts and interpretation.
2. Ground every factual claim in the provided excerpts. Cite inline immediately after the \
relevant sentence using the reference label in the excerpt header \
(e.g., [Smith et al. (2023), p. 4] or [Smith et al. (2023) [online]]).
3. Use appropriately hedged language for interpretation (e.g., "suggest", "indicate", "appear to", \
"may", "is consistent with"). Reserve strong claims for what the data directly shows.
4. If the provided literature is insufficient to fully support a point, flag the gap explicitly: \
**[GAP: insufficient literature on X — consider adding sources]**
5. Do not fabricate facts, statistics, or citations. Do not use prior knowledge not grounded in \
the excerpts.
6. Output clean markdown. Structure the section according to its type (e.g., Introduction builds \
from broad context to specific gap and hypothesis; Discussion moves from summary of findings to \
comparison with literature to limitations to implications).
7. Aim for the length and depth appropriate to the section type and a typical journal manuscript."""

REVIEWER_SYSTEM_PROMPT = """You are an expert academic writing assistant helping researchers respond to peer review. \
You will be given excerpts from the project's literature base and reviewer comments to respond to.

Rules:
1. Address each reviewer comment individually. Quote or paraphrase the comment, then write the response.
2. Acknowledge valid criticisms directly and describe concretely how they will be addressed.
3. For comments that misrepresent the work, politely and precisely clarify without being dismissive.
4. Where the literature supports a response, cite relevant excerpts inline \
(e.g., [Smith et al. (2023), p. 4]). Do not fabricate citations.
5. If no supporting literature is available for a point, flag it: \
**[GAP: no supporting literature found — may need additional sources or new data]**
6. Maintain a professional, collegial tone throughout.
7. Output clean markdown. Use a clear heading for each reviewer comment."""

GAP_MAP_SYSTEM_PROMPT = """You are an expert research analyst. You will be given excerpts from a \
project's literature base and a description of the research area to analyse.

Your task is to produce a structured research gap map: a synthesis of what is known, what is \
contested, and what is missing or understudied.

Rules:
1. Organise the map under exactly three headings: \
**Well established**, **Contested or inconsistent**, **Understudied or absent**.
2. Under each heading, list specific topics or findings as bullet points, citing relevant excerpts \
inline [Author et al. (YEAR), p. N].
3. Be specific about gaps — not just "more research is needed" but what type, where, at what \
scale, or using what methods.
4. Do not fabricate findings or citations. Do not use prior knowledge not grounded in the excerpts.
5. If the literature is too limited to map gaps confidently, flag it: \
**[NOTE: gap map is based on limited literature — add more sources for a fuller picture]**
6. Output clean markdown with the three headings and bulleted evidence under each."""

ANNOTATION_SYSTEM_PROMPT = """You are a research librarian generating structured annotations for \
academic papers. You will be given text excerpts from a single paper.

Write a concise structured annotation using exactly these three bold headings:

**What it does:** One to two sentences on the research question, study system, and approach.
**Key findings:** Two to three sentences on the main results or conclusions.
**Methods:** One sentence on the primary methodology or data type.

Be precise and objective. Base the annotation only on the provided text. Do not speculate.
Output only the annotation — no preamble, no closing remarks."""

EXTRACT_SYSTEM_PROMPT = """You are a precise data extraction assistant. Given text excerpts from \
an academic paper, extract specific fields and return them as a JSON object. \
Use null for any field not clearly stated in the text. \
Return ONLY a valid JSON object — no explanation, no markdown fences, no other text."""

THEMES_SYSTEM_PROMPT = """You are a research librarian tagging academic papers with subject themes. \
Given text excerpts from a paper, identify 3 to 4 themes that characterise its subject matter \
and rate how central each theme is to the paper.

Return a JSON object where:
- Keys are theme tags (2–4 words, all lowercase)
- Values are relevance scores from 0.1 (minor mention) to 1.0 (core focus of the paper)

Example: {"fire ecology": 0.9, "remote sensing methods": 0.7, "land use change": 0.4}

Guidelines for good tags:
- Use broad disciplinary terms, not paper-specific details.
  Good: "fire ecology", "remote sensing methods", "soil carbon cycling"
  Bad:  "sub-arctic fire regime 1980–2010", "CNN wildfire detection", "permafrost thaw rate study"
- Imagine the tag will be shared by 3–5 papers in the same research collection.
  If a tag could only describe this one paper, it is too specific — broaden it one level.
- Cover both the domain topic and the primary method where relevant.
- Return exactly 3–4 themes (not 5).

Return ONLY the JSON object. No other text."""

REFINE_SYSTEM_PROMPT = """You are an expert academic editor. You will receive a draft section and \
a revision instruction from the author. Revise the draft according to the instruction.

Rules:
1. Preserve all inline citations from the original draft unless the instruction specifically \
asks you to remove or replace them.
2. If the revision introduces new factual claims, flag them: \
**[UNVERIFIED: this claim needs a citation — check your literature]**
3. Maintain the writing style and register (grant, manuscript, or outreach) of the original.
4. Return only the revised draft text — no preamble, no commentary, no explanation of changes.
5. Output clean markdown."""

ASSIST_SYSTEM_PROMPT = """You are a research collaborator reviewing a draft in progress. \
The author has requested specific help. Suggest, highlight gaps, or add citations — \
do not rewrite the entire document unless the instruction explicitly says so.

Rules:
1. Base all suggestions on the provided document excerpts. Do not use prior knowledge.
2. Respond according to the requested mode:
   - Find citations: Identify claims in the draft that can be supported by the literature. \
For each, quote the claim and provide the citation [Author et al. (YEAR), p. N].
   - Refine: Suggest specific wording improvements for clarity or precision. \
Quote the original phrase, then offer a revised version.
   - Challenge: Identify claims that appear unsupported or that overstep the evidence \
in the provided excerpts. Quote each problematic claim and explain the concern.
   - Expand: Identify points that could be developed further using the available literature \
and draft 1–2 additional sentences for each, with citations.
3. Format your response as a numbered list of specific, actionable suggestions.
4. If the literature is insufficient to assist, say so explicitly rather than guessing."""

MEMORY_SYSTEM_PROMPT = """You are a research assistant summarising a past conversation. \
Given an exchange between a researcher and an assistant, write a 2–3 sentence summary \
capturing the research questions explored and the key conclusions or findings discussed. \
Be specific — name methods, species, regions, or findings mentioned. \
Output only the summary, no preamble or closing remarks."""

OUTREACH_SYSTEM_PROMPT = """You are a science communication writer helping translate research findings \
for non-specialist audiences. You will be given excerpts from a project's literature base and a \
description of the piece to write.

Rules:
1. Write in plain, engaging language accessible to a general or non-specialist audience. \
Avoid jargon; if a technical term is unavoidable, define it in plain words immediately.
2. Use active voice and short sentences. Write as if explaining to an interested, intelligent \
non-scientist — not a child, but not a specialist either.
3. Ground every factual claim in the provided excerpts. Do not fabricate findings or statistics. \
Do not use prior knowledge not found in the excerpts.
4. Citations should be light and integrated naturally into the prose \
(e.g., "Research by Smith and colleagues found that…" or "A 2023 study showed…") rather than \
using formal inline citation brackets. Include the author and year so claims remain traceable.
5. If the provided excerpts don't contain enough material to write a complete, accurate piece, \
flag what's missing: **[GAP: insufficient material on X — consider adding sources]**
6. Match the tone and length to the format requested (e.g., a social media post should be punchy \
and concise; a blog post can be conversational and longer; a press release follows an \
inverted-pyramid structure with a strong opening sentence).
7. Output clean markdown."""

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


def format_citations_and_scores(results: dict) -> tuple[list[str], list[float]]:
    """Return deduplicated citations paired with their best cosine similarity score.

    Score = 1 - cosine_distance, range 0–1 (higher = more similar to the query).
    Only the first (best-ranked) occurrence of each reference is kept.
    """
    seen: dict[str, float] = {}
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        ref = make_ref(meta)
        if ref not in seen:
            seen[ref] = round(1 - float(dist), 2)
    return list(seen.keys()), list(seen.values())


# ── Embedding model (cached — loaded once per process) ───────────────────────


@lru_cache(maxsize=1)
def _get_embed_model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


# ── Main ──────────────────────────────────────────────────────────────────────


def summarise_conversation(messages: list) -> str:
    """Generate a 2–3 sentence summary of a conversation for cross-session memory.

    Raises:
        ValueError: API key not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    convo_text = "\n".join(
        f"{'Researcher' if m['role'] == 'user' else 'Assistant'}: {m['content'][:600]}"
        for m in messages
        if m.get("role") in ("user", "assistant")
    )

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        temperature=0.3,
        system=MEMORY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": convo_text}],
    )
    return message.content[0].text.strip()


def query(
    project: str,
    question: str,
    prior_context: str = "",
    model: str = CLAUDE_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> tuple[str, list[str], list[float]]:
    """
    Run a RAG query against a project collection.

    Returns:
        (answer_text, citation_strings, similarity_scores)
        similarity_scores align with citation_strings; range 0–1 (higher = better match).

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

    embed_model = _get_embed_model()
    q_embedding = embed_model.encode(question, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(TOP_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    context = format_context(results)
    citations, scores = format_citations_and_scores(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    system = (
        f"Prior context from earlier research sessions:\n{prior_context}\n\n---\n\n{SYSTEM_PROMPT}"
        if prior_context
        else SYSTEM_PROMPT
    )

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": build_user_message(question, context)}],
    )

    return message.content[0].text, citations, scores


def draft(
    project: str,
    prompt: str,
    system_prompt: str = DRAFT_SYSTEM_PROMPT,
    top_k: int = TOP_K_DRAFT,
    model: str = CLAUDE_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> tuple[str, list[str]]:
    """
    Generate a written section grounded in the project literature.

    system_prompt selects the writing mode (grant, paper, outreach).
    top_k controls how many chunks are retrieved (default TOP_K_DRAFT).

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

    embed_model = _get_embed_model()
    q_embedding = embed_model.encode(prompt, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    context = format_context(results)
    citations = format_citations(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": build_user_message(prompt, context)}],
    )

    return message.content[0].text, citations


def _merge_results(
    projects: list[str], q_embedding: list[float], n_results: int
) -> dict:
    """Query multiple collections and return the top n_results chunks by similarity."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    available = client.list_collections()
    all_docs, all_metas, all_dists = [], [], []

    for project in projects:
        if project not in available:
            continue
        collection = client.get_collection(name=project)
        if collection.count() == 0:
            continue
        k = min(n_results, collection.count())
        r = collection.query(
            query_embeddings=[q_embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        all_docs.extend(r["documents"][0])
        all_metas.extend(r["metadatas"][0])
        all_dists.extend(r["distances"][0])

    if not all_docs:
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    combined = sorted(zip(all_dists, all_docs, all_metas))[:n_results]
    return {
        "documents": [[d for _, d, _ in combined]],
        "metadatas": [[m for _, _, m in combined]],
        "distances": [[dist for dist, _, _ in combined]],
    }


def query_multi(
    projects: list[str],
    question: str,
    prior_context: str = "",
    model: str = CLAUDE_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> tuple[str, list[str], list[float]]:
    """
    Query across multiple project collections and synthesise a single answer.

    Merges and re-ranks results from all listed projects before sending to Claude.
    """
    if not projects:
        raise ValueError("At least one project must be specified.")

    embed_model = _get_embed_model()
    q_embedding = embed_model.encode(question, normalize_embeddings=True).tolist()
    results = _merge_results(projects, q_embedding, TOP_K)

    if not results["documents"][0]:
        raise ValueError(
            f"No documents found across projects: {', '.join(projects)}. "
            "Run ingest.py for each project first."
        )

    context = format_context(results)
    citations, scores = format_citations_and_scores(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    system = (
        f"Prior context from earlier research sessions:\n{prior_context}\n\n---\n\n{SYSTEM_PROMPT}"
        if prior_context
        else SYSTEM_PROMPT
    )

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": build_user_message(question, context)}],
    )
    return message.content[0].text, citations, scores


def draft_multi(
    projects: list[str],
    prompt: str,
    system_prompt: str = DRAFT_SYSTEM_PROMPT,
    top_k: int = TOP_K_DRAFT,
    model: str = CLAUDE_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> tuple[str, list[str]]:
    """
    Draft a section drawing from multiple project collections.

    Merges and re-ranks results before sending to Claude.
    """
    if not projects:
        raise ValueError("At least one project must be specified.")

    embed_model = _get_embed_model()
    q_embedding = embed_model.encode(prompt, normalize_embeddings=True).tolist()
    results = _merge_results(projects, q_embedding, top_k)

    if not results["documents"][0]:
        raise ValueError(
            f"No documents found across projects: {', '.join(projects)}. "
            "Run ingest.py for each project first."
        )

    context = format_context(results)
    citations = format_citations(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": build_user_message(prompt, context)}],
    )
    return message.content[0].text, citations


def refine_draft(current_draft: str, instruction: str) -> str:
    """
    Revise an existing draft according to a plain-language instruction.

    Does not retrieve new chunks — operates on the draft text already in hand.
    Flags any new claims introduced without a citation.

    Returns:
        Revised draft text.

    Raises:
        ValueError: API key not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    user_msg = f"Current draft:\n\n{current_draft}\n\n---\n\nRevision instruction: {instruction}"

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        temperature=0.3,
        system=REFINE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text


def extract_themes(project: str, filename: str, model: str = CLAUDE_MODEL) -> dict[str, float]:
    """
    Extract 3–5 subject-matter themes with relevance scores for one paper.

    Returns a dict mapping lowercase theme tag → relevance score (0.1–1.0),
    where 1.0 means the theme is a core focus of the paper.
    Uses 5 chunks (enough for thematic content; conserves token budget).
    Retries once after 65 s on a rate-limit error.

    Returns:
        {theme: score} dict, or {} if extraction fails.

    Raises:
        ValueError: API key not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(name=project)
    all_result = collection.get(include=["documents", "metadatas"])
    indices = [
        i for i, m in enumerate(all_result["metadatas"])
        if m.get("filename") == filename
    ]

    if not indices:
        return {}

    context = "\n\n---\n\n".join(all_result["documents"][i] for i in indices[:5])

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = None
    for attempt in range(2):
        try:
            message = client_ai.messages.create(
                model=model,
                max_tokens=100,
                temperature=0.3,
                system=THEMES_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": context}],
            )
            break
        except anthropic.RateLimitError:
            if attempt == 0:
                time.sleep(65)
            else:
                raise

    if message is None:
        return {}
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            result = {}
            for k, v in list(parsed.items())[:5]:
                try:
                    result[str(k).lower().strip()] = max(0.1, min(1.0, float(v)))
                except (TypeError, ValueError):
                    result[str(k).lower().strip()] = 0.5
            return result
        if isinstance(parsed, list):
            # Fallback: old-format list response — treat all weights as 0.5
            return {str(t).lower().strip(): 0.5 for t in parsed[:5] if t}
    except json.JSONDecodeError:
        pass
    return {}


def annotate_paper(project: str, filename: str) -> str:
    """
    Generate a structured annotation (what/findings/methods) for one paper.

    Retrieves up to 15 chunks for the given filename from the project collection.

    Returns:
        Markdown annotation string.

    Raises:
        ValueError: collection missing, no chunks for filename, or API key not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    if project not in client.list_collections():
        raise ValueError(f"No collection found for project '{project}'.")

    collection = client.get_collection(name=project)
    all_result = collection.get(include=["documents", "metadatas"])
    indices = [
        i for i, m in enumerate(all_result["metadatas"])
        if m.get("filename") == filename
    ]

    if not indices:
        raise ValueError(f"No chunks found for '{filename}' in project '{project}'.")

    docs = [all_result["documents"][i] for i in indices[:15]]
    ref = make_ref(all_result["metadatas"][indices[0]])
    context = f"Paper: {ref}\n\n" + "\n\n---\n\n".join(docs)

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = client_ai.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        system=ANNOTATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    return message.content[0].text


def extract_fields_from_paper(
    project: str, filename: str, fields: list[str], top_k: int = 5
) -> dict[str, str]:
    """
    Extract specified fields from one paper using Claude and return as a dict.

    Uses up to top_k chunks (default 5 to stay within per-minute token limits).
    Retries once after 65 s on a rate-limit error.
    Returns "—" for fields not found in the text.

    Raises:
        ValueError: API key not set.
        anthropic.RateLimitError: if rate limit persists after retry.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(name=project)
    all_result = collection.get(include=["documents", "metadatas"])
    indices = [
        i for i, m in enumerate(all_result["metadatas"])
        if m.get("filename") == filename
    ]

    if not indices:
        return {f: "—" for f in fields}

    context = "\n\n---\n\n".join(all_result["documents"][i] for i in indices[:top_k])
    prompt = (
        f"Extract these fields from the academic paper text below.\n"
        f"Use these exact key names: {json.dumps(fields)}\n\n"
        f"Return a JSON object with exactly those keys (preserve case and spacing). "
        f"Use null for any field not clearly stated in the text.\n\n"
        f"Paper text:\n{context}"
    )

    client_ai = anthropic.Anthropic(api_key=api_key)
    message = None
    for attempt in range(2):
        try:
            message = client_ai.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                temperature=0.0,
                system=EXTRACT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.RateLimitError:
            if attempt == 0:
                time.sleep(65)
            else:
                raise

    if message is None:
        return {f: "—" for f in fields}
    raw = message.content[0].text.strip()

    # Strip markdown code fences Claude sometimes adds despite instructions
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        # Last resort: find first {...} block in the response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {f: "parse error" for f in fields}
        try:
            extracted = json.loads(match.group())
        except json.JSONDecodeError:
            return {f: "parse error" for f in fields}

    # Case-insensitive key lookup so capitalisation differences don't break results
    extracted_ci = {k.lower(): v for k, v in extracted.items()}
    return {
        f: str(extracted_ci[f.lower()]) if extracted_ci.get(f.lower()) is not None else "—"
        for f in fields
    }


def assist_writing(
    project: str,
    document_text: str,
    mode: str,
    custom_instruction: str = "",
    writing_context: str = "",
    top_k: int = TOP_K_DRAFT,
    model: str = CLAUDE_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> tuple[str, list[str], list[float]]:
    """
    Provide AI assistance on a draft in progress.

    Retrieves relevant chunks using the first 500 characters of the draft as a query,
    then asks Claude to assist according to the specified mode.

    mode: "Find citations" | "Refine" | "Challenge" | "Expand" | "Custom"
    custom_instruction: used when mode is "Custom"

    Returns:
        (response_text, citations, scores) — same shape as query().

    Raises:
        ValueError: collection missing/empty or API key not set.
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

    embed_model = _get_embed_model()
    query_text = document_text[:500] if document_text.strip() else mode
    q_embedding = embed_model.encode(query_text, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    context = format_context(results)
    citations, scores = format_citations_and_scores(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    instruction = custom_instruction.strip() if mode == "Custom" and custom_instruction.strip() else mode
    context_block = (
        f"Writing brief (author-supplied context about this document):\n{writing_context}\n\n---\n\n"
        if writing_context.strip() else ""
    )
    user_msg = (
        f"{context_block}"
        f"Assistance mode: {instruction}\n\n"
        f"Author's current draft:\n\n{document_text}\n\n"
        f"---\n\nDocument excerpts from the literature:\n\n{context}"
    )

    client_ai = anthropic.Anthropic(api_key=api_key)
    for attempt in range(2):
        try:
            message = client_ai.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=ASSIST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except anthropic.RateLimitError:
            if attempt == 0:
                time.sleep(65)
            else:
                raise
    return message.content[0].text, citations, scores


def assist_writing_multi(
    projects: list[str],
    document_text: str,
    mode: str,
    custom_instruction: str = "",
    writing_context: str = "",
    top_k: int = TOP_K_DRAFT,
    model: str = CLAUDE_MODEL,
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> tuple[str, list[str], list[float]]:
    """
    Provide AI writing assistance drawing from multiple project collections.

    Returns:
        (response_text, citations, scores)
    """
    if not projects:
        raise ValueError("At least one project must be specified.")

    embed_model = _get_embed_model()
    query_text = document_text[:500] if document_text.strip() else mode
    q_embedding = embed_model.encode(query_text, normalize_embeddings=True).tolist()
    results = _merge_results(projects, q_embedding, top_k)

    if not results["documents"][0]:
        raise ValueError(
            f"No documents found across projects: {', '.join(projects)}. "
            "Run ingest.py for each project first."
        )

    context = format_context(results)
    citations, scores = format_citations_and_scores(results)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    instruction = custom_instruction.strip() if mode == "Custom" and custom_instruction.strip() else mode
    context_block = (
        f"Writing brief (author-supplied context about this document):\n{writing_context}\n\n---\n\n"
        if writing_context.strip() else ""
    )
    user_msg = (
        f"{context_block}"
        f"Assistance mode: {instruction}\n\n"
        f"Author's current draft:\n\n{document_text}\n\n"
        f"---\n\nDocument excerpts from the literature:\n\n{context}"
    )

    client_ai = anthropic.Anthropic(api_key=api_key)
    for attempt in range(2):
        try:
            message = client_ai.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=ASSIST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except anthropic.RateLimitError:
            if attempt == 0:
                time.sleep(65)
            else:
                raise
    return message.content[0].text, citations, scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query a project knowledge base via Claude.")
    parser.add_argument("--project", required=True, help="Project name (e.g. fire)")
    parser.add_argument("question", help="Question to ask")
    args = parser.parse_args()

    try:
        answer, citations, _ = query(args.project, args.question)
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
