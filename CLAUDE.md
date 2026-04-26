# FFL Knowledge Base — Claude Code Context

## What this project is
A local RAG (Retrieval-Augmented Generation) system for querying academic PDFs and grant proposals using Claude (Anthropic API). Branded as "FFL Knowledge Base" for lab users — avoid "AI" branding in user-facing text. Lab members sync papers from a Zotero library, run ingestion once, then query via CLI or browser UI. The repo folder will be renamed from `lab-ai` to `ffl-knowledge-base` before the first GitHub push.

## Tech stack
- **LLM:** Claude (`claude-sonnet-4-6`) via Anthropic API
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` — runs locally, no API cost
- **Vector DB:** ChromaDB — persisted to `chroma_db/` on disk
- **PDF parsing:** PyMuPDF (`fitz`)
- **Zotero sync:** `pyzotero` — pulls PDFs + metadata (title, authors, year, DOI) from a named collection; also scrapes Zotero web-link attachments via `trafilatura`
- **UI:** Streamlit (seven tabs: Chat, Documents, Draft, Extract, Graph, Guide, Write)
- **Graph:** `pyvis` — interactive HTML network, embedded via `st.components.v1.html()`
- **Secrets:** `python-dotenv` loading from `.env`

## File map
```
ingest.py           PDF → chunk (512 words, 50 overlap) → embed → ChromaDB
                    --zotero flag: pulls from Zotero collection, downloads PDFs, enriches metadata
                    Falls back to trafilatura web scraping for Zotero web-link attachments
query.py            query() / query_multi()     — retrieve top-5 chunks → Claude → answer + citations
                    draft() / draft_multi()     — retrieve top-12 chunks → Claude (prose mode)
                    refine_draft()              — revise existing draft without new retrieval
                    annotate_paper()            — annotated bibliography entry for one paper
                    extract_fields_from_paper() — structured field extraction → dict
                    extract_themes()            — 3–5 theme tags per paper for graph
                    assist_writing()            — RAG + Claude collaborator for Write tab
                    assist_writing_multi()      — multi-project variant
                    System prompts: DRAFT_, PAPER_, OUTREACH_, REVIEWER_, GAP_MAP_,
                                    ANNOTATION_, EXTRACT_, THEMES_, REFINE_, ASSIST_SYSTEM_PROMPT
app.py              Streamlit UI
                    Tab 1 — Chat: per-project + cross-project (multi-select), auto-saves history
                    Tab 2 — Documents: browsable index; per-paper annotation; persisted to annotations.json
                    Tab 3 — Draft: 5 writing modes; iterative refinement; multi-project; markdown download
                    Tab 4 — Extract: structured field extraction → table + CSV; persisted to last_extraction.json
                    Tab 5 — Graph: pyvis theme network; paper (blue) + theme (amber) nodes; persisted to themes.json
                    Tab 6 — Guide: renders USER_GUIDE.md inline
                    Tab 7 — Write: split-pane markdown editor + live preview; AI assistance (Find
                             citations, Refine, Challenge, Expand, Custom); writing context brief;
                             template library; per-project draft persistence; version snapshots;
                             append-only notes history; DOCX export (pandoc); external file sync
                    Sidebar: retrieval_k slider (5–25, default 12) for Draft, Extract & Write
USER_GUIDE.md       Plain-language guide for lab members
RUNBOOK.md          Personal quick reference — run commands, common problems, file paths
projects/
  {name}/
    pdfs/               PDFs cached here (by Zotero download or manual drop)
    history/            Auto-saved conversations as JSON (gitignored)
    annotations.json    Persisted annotated bibliography entries
    last_extraction.json  Persisted last structured extraction (fields + results)
    themes.json         Persisted theme tags per paper (used by Graph tab)
    write_draft.md      Auto-saved Write tab draft (created by "Save draft" button)
    write_context.md    Writing brief — injected into every Write tab AI call
    write_notes.md      Append-only AI suggestion history from Write tab
    write_config.json   Write tab config (external_file path)
    write_snapshots/    Timestamped draft snapshots before each AI call (last 20 kept)
chroma_db/          Auto-created on first ingest; gitignored; one collection per project
.env                ANTHROPIC_API_KEY, ZOTERO_API_KEY, ZOTERO_USER_ID, ZOTERO_LIBRARY_TYPE
.env.example        Template committed to git — copy to .env on new deployments
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
- Annotated bibliography — per-paper annotations generated on demand; persisted to annotations.json
- 5 writing modes in Draft tab: Grant Proposal, Academic Paper, Outreach & Communication, Response to Reviewers, Research Gap Map
- Iterative draft refinement — REFINE_SYSTEM_PROMPT revises existing draft without new retrieval
- Structured extraction (Extract tab) — user-defined fields → table + CSV download; persisted to last_extraction.json
- Cross-project synthesis — query_multi / draft_multi merge ChromaDB collections; UI multi-select in Chat and Draft
- Theme graph (Graph tab) — Claude tags each paper; pyvis bipartite network; theme nodes sized by degree; persisted to themes.json
- Retrieval depth slider (sidebar) — controls top-k for Draft and Extract (5–25, default 12)
- File-based persistence for annotations, extractions, and themes — survive Streamlit restart
- Multi-project isolation confirmed with Fire and Alaska projects
- Rate-limit handling — 65 s retry on 429; 7 s inter-paper sleep in Extract and Graph tabs
- Advanced settings sidebar — model selector (Haiku/Sonnet/Opus), temperature slider, max draft tokens, retrieval-k, show-scores toggle
- Retrieval confidence scores — cosine similarity returned alongside citations; optionally shown in Chat source expander
- Guide tab — renders USER_GUIDE.md inline; covers all tabs and advanced features
- Temperature defaults: 0.3 for Q&A, 0.4 for drafting (API default is 1.0 — these defaults are a meaningful quality improvement)
- Write tab (Assisted Draft) — split-pane markdown editor + AI assistance (Find citations, Refine, Challenge, Expand, Custom modes); writing context brief injected into all calls; 8-entry template library; per-project draft auto-save; version snapshots before AI calls; append-only notes history; "Append to draft" button; DOCX export via pandoc; external file sync (network drive read/write with companion .notes.md)

## Hosting plan
- Deploy to lab server + Cloudflare Tunnel + Cloudflare Access
- Streamlit binds to 127.0.0.1:8501; Cloudflare Tunnel is the only entry point
- Cloudflare Access restricts to @caryinstitute.org emails
- Persistent service via NSSM (Windows) or systemd (Linux) — service name: FFLKnowledgeBase / ffl-knowledge-base
- Single shared lab Anthropic API key in .env on server
- Switch ZOTERO_LIBRARY_TYPE=group once group library is ready
