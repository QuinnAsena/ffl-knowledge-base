"""
ingest.py — Load PDFs, chunk, embed, and store in ChromaDB.

Local mode (default):
    python ingest.py --project fire

Zotero mode (pulls from a Zotero collection matching the project name):
    python ingest.py --project fire --zotero
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import chromadb
import fitz  # PyMuPDF
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
EMBED_MODEL = "all-MiniLM-L6-v2"
CHROMA_DIR = "chroma_db"

# ── Section detection ─────────────────────────────────────────────────────────

_SECTION_PATTERNS: list[tuple[str, str]] = [
    ("abstract",     r"^\s*abstract\s*$"),
    ("introduction", r"^\s*(?:\d+[\.\s]+)?introduction\s*$"),
    ("methods",      r"^\s*(?:\d+[\.\s]+)?(?:materials?\s+and\s+)?methods?(?:\s+and\s+materials?)?\s*$"),
    ("methods",      r"^\s*(?:\d+[\.\s]+)?(?:study\s+)?(?:area|site|design|system|approach)\s*$"),
    ("methods",      r"^\s*(?:\d+[\.\s]+)?(?:experimental\s+(?:design|setup)|data\s+(?:collection|analysis)|statistical\s+(?:analysis|methods?))\s*$"),
    ("results",      r"^\s*(?:\d+[\.\s]+)?results?\s*$"),
    ("results",      r"^\s*(?:\d+[\.\s]+)?results?\s+and\s+discussion\s*$"),
    ("results",      r"^\s*(?:\d+[\.\s]+)?findings?\s*$"),
    ("discussion",   r"^\s*(?:\d+[\.\s]+)?discussion\s*$"),
    ("conclusion",   r"^\s*(?:\d+[\.\s]+)?conclusions?\s*$"),
    ("references",   r"^\s*(?:\d+[\.\s]+)?(?:references?|literature\s+cited|bibliography)\s*$"),
]
_SECTION_RE = [(label, re.compile(pat, re.IGNORECASE)) for label, pat in _SECTION_PATTERNS]


def detect_section(text: str, current: str) -> str:
    """Scan text lines for a section header; return the matched label or current unchanged."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            continue
        for label, pattern in _SECTION_RE:
            if pattern.match(stripped):
                return label
    return current


# ── PDF helpers ───────────────────────────────────────────────────────────────


def extract_pages(pdf_path: Path) -> list[dict]:
    """Return [{text, page, filename}] for every non-empty page.

    For image-only pages (no extractable text), falls back to Tesseract OCR via
    PyMuPDF's built-in bridge. If Tesseract is not installed the page is skipped
    with a one-time warning.
    """
    doc = fitz.open(str(pdf_path))
    pages = []
    ocr_warned = False
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if not text:
            try:
                tp = page.get_textpage_ocr(flags=3, language="eng", dpi=300)
                text = page.get_text("text", textpage=tp).strip()
                if text:
                    print(f"  [ocr] Page {page_num} (Tesseract)")
            except Exception:
                if not ocr_warned:
                    print(
                        f"  [warn] {pdf_path.name}: image-only page(s) detected. "
                        "Install Tesseract to OCR them: "
                        "https://github.com/UB-Mannheim/tesseract/wiki"
                    )
                    ocr_warned = True
        if text:
            pages.append({"text": text, "page": page_num, "filename": pdf_path.name})
    doc.close()
    return pages


def load_project_config(project: str) -> dict:
    """Load per-project ingestion settings from projects/{project}/config.json.

    Supported keys (all optional — omitted keys use the module defaults):
        chunk_size    (int)  words per chunk
        chunk_overlap (int)  overlapping words between consecutive chunks
    """
    path = Path("projects") / project / "config.json"
    defaults = {"chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP}
    if not path.exists():
        return defaults
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        merged = {**defaults, **{k: int(v) for k, v in cfg.items() if k in defaults}}
        print(
            f"[info] Project config: chunk_size={merged['chunk_size']}, "
            f"chunk_overlap={merged['chunk_overlap']}"
        )
        return merged
    except Exception as e:
        print(f"[warn] Could not read config.json: {e} — using defaults")
        return defaults


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start : start + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        if start + chunk_size >= len(words):
            break
        start += chunk_size - overlap
    return chunks


def make_chunk_id(filename: str, page: int, chunk_index: int) -> str:
    """Stable SHA-256 ID (32 hex chars) from '{filename}::p{page}::c{chunk_index}'."""
    raw = f"{filename}::p{page}::c{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Source: local PDFs ────────────────────────────────────────────────────────


def collect_local_items(project: str) -> list[dict]:
    """Return item dicts for every PDF in projects/{project}/pdfs/."""
    pdf_dir = Path("projects") / project / "pdfs"
    if not pdf_dir.exists():
        print(f"[error] Directory not found: {pdf_dir}")
        sys.exit(1)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[warn] No PDFs found in {pdf_dir}")
        sys.exit(0)

    print(f"[info] Found {len(pdf_files)} local PDF(s) in {pdf_dir}")
    return [
        {
            "content_type": "pdf",
            "pdf_path": p,
            "filename": p.name,
            "title": "", "author_str": "", "year": "", "doi": "", "url": "",
        }
        for p in pdf_files
    ]


# ── Web scraping ─────────────────────────────────────────────────────────────


def scrape_web_item(url: str, title: str) -> str | None:
    """Fetch and extract clean text from a URL using trafilatura."""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
        return text
    except Exception as e:
        print(f"  [warn] Scraping failed for {url}: {e}")
        return None


# ── Source: Zotero ────────────────────────────────────────────────────────────


def collect_zotero_items(project: str) -> list[dict]:
    """
    Pull items from the Zotero collection whose name matches `project` (case-insensitive).
    Downloads PDFs to projects/{project}/pdfs/ as a local cache.
    Returns item dicts with enriched metadata.
    """
    try:
        from pyzotero import zotero as pyzotero_lib
    except ImportError:
        print("[error] pyzotero not installed. Run: pip install pyzotero")
        sys.exit(1)

    api_key = os.getenv("ZOTERO_API_KEY")
    user_id = os.getenv("ZOTERO_USER_ID")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user")

    if not api_key or not user_id:
        print("[error] ZOTERO_API_KEY and ZOTERO_USER_ID must be set in .env")
        sys.exit(1)

    zot = pyzotero_lib.Zotero(user_id, library_type, api_key)

    # Find collection by name (case-insensitive)
    all_collections = zot.collections()
    matches = [c for c in all_collections if c["data"]["name"].lower() == project.lower()]

    if not matches:
        names = [c["data"]["name"] for c in all_collections]
        print(f"[error] No Zotero collection named '{project}' found.")
        print(f"  Available collections: {names}")
        sys.exit(1)

    if len(matches) > 1:
        print(f"[warn] Multiple collections named '{project}'; using the first match.")

    col = matches[0]
    print(f"[info] Zotero collection: '{col['data']['name']}' (key: {col['key']})")

    # Top-level items only — exclude attachments via API, filter notes in code
    items = [
        i for i in zot.collection_items(col["key"], itemType="-attachment")
        if i["data"].get("itemType") != "note"
    ]
    print(f"[info] Found {len(items)} item(s) in collection")

    pdf_dir = Path("projects") / project / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    result = []
    for item in items:
        data = item["data"]
        title = data.get("title", item["key"])

        # Format author string: "Smith et al." or "Smith"
        authors = [c for c in data.get("creators", []) if c.get("creatorType") == "author"]
        if not authors:
            author_str = ""
        elif len(authors) == 1:
            author_str = authors[0].get("lastName") or authors[0].get("name", "")
        else:
            first = authors[0].get("lastName") or authors[0].get("name", "Unknown")
            author_str = f"{first} et al."

        year = (data.get("date") or "")[:4]
        doi = data.get("DOI", "")

        # Find PDF among children
        children = zot.children(item["key"])
        pdf_child = next(
            (c for c in children if c["data"].get("contentType") == "application/pdf"),
            None,
        )

        if pdf_child is None:
            # Fall back to web link if one exists (linked_url or imported_url)
            web_child = next(
                (
                    c for c in children
                    if c["data"].get("linkMode") in ("linked_url", "imported_url")
                    or c["data"].get("contentType") == "text/html"
                ),
                None,
            )
            if web_child is None:
                print(f"  [skip] No PDF or web link for: {title[:70]}")
                continue

            url = web_child["data"].get("url", "")
            if not url:
                print(f"  [skip] Web link has no URL for: {title[:70]}")
                continue

            print(f"  [scrape] {title[:60]} — {url}")
            scraped_text = scrape_web_item(url, title)
            if not scraped_text or len(scraped_text.split()) < 50:
                print(f"  [warn] Could not extract usable text from {url}")
                continue

            result.append(
                {
                    "content_type": "web",
                    "filename": f"{web_child['key']}.web",
                    "url": url,
                    "scraped_text": scraped_text,
                    "title": title,
                    "author_str": author_str,
                    "year": year,
                    "doi": doi,
                }
            )
            continue

        attachment_key = pdf_child["key"]
        filename = pdf_child["data"].get("filename") or f"{attachment_key}.pdf"
        dest = pdf_dir / filename

        if dest.exists():
            print(f"  [cached] {filename}")
        else:
            print(f"  [download] {filename}")
            try:
                zot.dump(attachment_key, filename, str(pdf_dir))
            except Exception as e:
                print(f"  [warn] Download failed for '{filename}': {e}")
                continue

        result.append(
            {
                "content_type": "pdf",
                "pdf_path": dest,
                "filename": filename,
                "url": "",
                "title": title,
                "author_str": author_str,
                "year": year,
                "doi": doi,
            }
        )

    return result


# ── Ingestion core ────────────────────────────────────────────────────────────


def ingest(project: str, use_zotero: bool = False) -> None:
    items = collect_zotero_items(project) if use_zotero else collect_local_items(project)

    if not items:
        print("[warn] No ingestible items found.")
        sys.exit(0)

    cfg = load_project_config(project)
    chunk_size = cfg["chunk_size"]
    chunk_overlap = cfg["chunk_overlap"]

    print(f"[info] Loading embedding model: {EMBED_MODEL}")
    embed_model = SentenceTransformer(EMBED_MODEL)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(
        name=project,
        metadata={"hnsw:space": "cosine"},
    )

    existing_ids: set[str] = set(collection.get(include=[])["ids"])
    print(f"[info] Collection '{project}' already has {len(existing_ids)} chunk(s)")

    total_added = 0

    for item in items:
        print(f"[info] Processing: {item['filename']}")
        if item.get("author_str") and item.get("year"):
            print(f"  Metadata: {item['author_str']} ({item['year']}){' — DOI: ' + item['doi'] if item['doi'] else ''}")

        if item.get("content_type") == "web":
            text = item.get("scraped_text", "")
            if not text:
                print(f"  [warn] No scraped text, skipping")
                continue
            pages = [{"text": text, "page": 1, "filename": item["filename"]}]
        else:
            pages = extract_pages(item["pdf_path"])
            if not pages:
                print(f"  [warn] No extractable text, skipping")
                continue

        item_added = 0
        current_section = "other"

        for page_data in pages:
            current_section = detect_section(page_data["text"], current_section)
            raw_chunks = chunk_text(page_data["text"], chunk_size, chunk_overlap)
            ids, documents, embeddings, metadatas = [], [], [], []

            for idx, chunk_val in enumerate(raw_chunks):
                chunk_id = make_chunk_id(page_data["filename"], page_data["page"], idx)
                if chunk_id in existing_ids:
                    continue

                ids.append(chunk_id)
                documents.append(chunk_val)
                embeddings.append(embed_model.encode(chunk_val, normalize_embeddings=True).tolist())
                metadatas.append(
                    {
                        "filename": page_data["filename"],
                        "page": page_data["page"],
                        "project": project,
                        "title": item.get("title", ""),
                        "author_str": item.get("author_str", ""),
                        "year": item.get("year", ""),
                        "doi": item.get("doi", ""),
                        "source_type": item.get("content_type", "pdf"),
                        "url": item.get("url", ""),
                        "section": current_section,
                    }
                )
                existing_ids.add(chunk_id)

            if ids:
                collection.add(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                item_added += len(ids)

        print(f"  -> Added {item_added} new chunk(s)")
        total_added += item_added

    print(
        f"\n[done] Ingestion complete. "
        f"Added {total_added} new chunk(s). "
        f"Collection '{project}' now has {collection.count()} total chunk(s)."
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest PDFs into a project knowledge base.")
    parser.add_argument("--project", required=True, help="Project name (e.g. fire)")
    parser.add_argument(
        "--zotero",
        action="store_true",
        help="Pull PDFs and metadata from the matching Zotero collection",
    )
    args = parser.parse_args()
    ingest(args.project, use_zotero=args.zotero)
