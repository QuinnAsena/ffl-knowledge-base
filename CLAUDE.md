# FFL Knowledge Base — Claude Code Context

## What this project is
A local RAG (Retrieval-Augmented Generation) system for querying academic PDFs and grant proposals using Claude (Anthropic API). Branded as "FFL Knowledge Base" for lab users — avoid "AI" branding in user-facing text. Lab members sync papers from a Zotero library, run ingestion once, then query via CLI or browser UI. The repo folder will be renamed from `lab-ai` to `ffl-knowledge-base` before the first GitHub push.

## Tech stack
- **LLM:** Claude (`claude-sonnet-4-6`) via Anthropic API
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` — runs locally, no API cost
- **Vector DB:** ChromaDB — persisted to `chroma_db/` on disk
- **PDF parsing:** PyMuPDF (`fitz`)
- **Zotero sync:** `pyzotero` — pulls PDFs + metadata (title, authors, year, DOI) from a named collection; also scrapes Zotero web-link attachments via `trafilatura`
- **UI:** Streamlit (three tabs: Chat, Documents, Draft)
- **Secrets:** `python-dotenv` loading from `.env`

## File map
```
ingest.py           PDF → chunk (512 words, 50 overlap) → embed → ChromaDB
                    --zotero flag: pulls from Zotero collection, downloads PDFs, enriches metadata
                    Falls back to trafilatura web scraping for Zotero web-link attachments
query.py            query(): embed question → retrieve top-5 chunks → Claude → answer + citations
                    draft(): embed prompt → retrieve top-12 chunks → Claude (prose mode) → draft + citations
                    DRAFT_SYSTEM_PROMPT instructs Claude to write academic prose and flag literature gaps
app.py              Streamlit UI
                    Tab 1 — Chat: per-project chat, auto-saves history to projects/{name}/history/
                    Tab 2 — Documents: browsable index from ChromaDB metadata (author, year, DOI, chunks)
                    Tab 3 — Draft: section type selector, generate button, markdown download
USER_GUIDE.md       Plain-language guide for lab members (privacy, how citations work, how to get good answers)
projects/
  {name}/
    pdfs/           PDFs cached here (by Zotero download or manual drop)
    history/        Auto-saved conversations as JSON (gitignored)
chroma_db/          Auto-created on first ingest; gitignored; one collection per project
.env                ANTHROPIC_API_KEY, ZOTERO_API_KEY, ZOTERO_USER_ID, ZOTERO_LIBRARY_TYPE
```

## Key conventions
- Projects are isolated by ChromaDB collection name (same as folder name under `projects/`)
- Zotero collection name must match project name (case-insensitive) — e.g., "Fire" → `--project fire`
- Chunk IDs are SHA-256 of `filename::page::chunk_index` — re-ingestion is safe/idempotent
- `query.py` raises `ValueError` (not `sys.exit`) so it can be imported by `app.py` safely
- Citation format: `[Author et al. (YEAR), p. N]` when Zotero metadata present; falls back to `[filename, p. N]`
- Web sources cite as `[Author et al. (YEAR) [online]]`
- Claude is instructed to refuse to answer if the answer isn't in the provided document excerpts
- Draft mode flags missing literature as `**[GAP: insufficient literature on X — consider adding sources]**`
- chromadb 0.6 API: `client.list_collections()` returns plain strings (not objects); use directly
- Zotero itemType filter: use `itemType="-attachment"` only, then filter notes in Python code (compound filter causes 400)

## How to run
```bash
# Activate venv first (Git Bash on Windows)
source .venv/Scripts/activate

# Ingest from Zotero (recommended)
python ingest.py --project fire --zotero

# Ingest local PDFs (fallback)
python ingest.py --project fire

# CLI query
python query.py --project fire "What are the main drivers of fire spread?"

# Web UI
.venv\Scripts\streamlit run app.py     # Windows (PowerShell)
source .venv/Scripts/activate && streamlit run app.py  # Windows (Git Bash)
streamlit run app.py                   # Mac/Linux
```

## Hard constraints
- No OpenAI — Anthropic API only
- Local-first — embeddings, vector DB, and chat history never leave the machine
- Citations on every answer — lab members must be able to verify claims
- Multi-project support — do not break collection namespacing when adding features
- Avoid "AI" in user-facing text — the tool is branded as a "knowledge base"

## Windows-specific notes
- Python 3.12.x required (3.14 has no pre-built wheels for `chroma-hnswlib`)
- Microsoft C++ Build Tools required to compile `chroma-hnswlib` from source
- Use `py -3.12 -m venv .venv` to create the virtualenv with the correct Python
- Streamlit command: `.venv\Scripts\streamlit run app.py` (PowerShell) or activate venv first in Git Bash
- `.streamlit/config.toml` sets `fileWatcherType = "none"` to suppress torch/Streamlit noise

## Privacy note
Document chunks (text) are sent to Anthropic's API servers at query time.
Files, embeddings, and chat history stay local. Factor this in for embargoed papers or sensitive grants.

## Completed features
- Zotero integration with PDF download and metadata enrichment
- Zotero web-link scraping via trafilatura (curated sources only, not general URL ingestion)
- Chat history auto-save/reload (JSON per session in projects/{name}/history/)
- Browsable document index (Documents tab — title, authors, year, DOI, chunk count)
- Grant proposal drafting mode (Draft tab — 12 chunks, prose system prompt, gap flagging, markdown download)
- Multi-project isolation confirmed with Fire and Alaska projects

## Hosting plan
- Deploy to lab server + Cloudflare Tunnel + Cloudflare Access
- Streamlit binds to 127.0.0.1:8501; Cloudflare Tunnel is the only entry point
- Cloudflare Access restricts to @caryinstitute.org emails
- Persistent service via NSSM (Windows) or systemd (Linux) — service name: FFLKnowledgeBase / ffl-knowledge-base
- Single shared lab Anthropic API key in .env on server
- Switch ZOTERO_LIBRARY_TYPE=group once group library is ready
