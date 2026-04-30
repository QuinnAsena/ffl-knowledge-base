# FFL Knowledge Base

A local literature knowledge base for querying academic PDFs and grant proposals. Each project maps to an isolated Zotero collection and search index. Powered by Claude (Anthropic API) for synthesis; embeddings run locally with no API cost.

See [USER_GUIDE.md](USER_GUIDE.md) for the full end-user guide, including tab-by-tab documentation and advanced settings.

---

## Prerequisites

- **Python 3.12.x** — Python 3.13+ has no pre-built wheels for `chroma-hnswlib`
- **Microsoft C++ Build Tools** (Windows only) — required to compile `chroma-hnswlib`; install from [visualstudio.microsoft.com/visual-cpp-build-tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/), select "Desktop development with C++"
- An [Anthropic API key](https://console.anthropic.com/)
- A [Zotero API key](https://www.zotero.org/settings/keys) (optional — needed for Zotero sync; manual PDF drop works without it)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd lab-ai

# Windows — explicitly use Python 3.12
py -3.12 -m venv .venv
.venv\Scripts\activate          # PowerShell
source .venv/Scripts/activate   # Git Bash

# Mac / Linux
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

The embedding model (`all-MiniLM-L6-v2`, ~80 MB) downloads automatically on first run.

### 3. Configure secrets

```bash
cp .env.example .env
# Edit .env and fill in the keys below
```

Required `.env` keys:

```
ANTHROPIC_API_KEY=sk-ant-...

# Zotero (optional — skip if using manual PDF drop)
ZOTERO_API_KEY=...
ZOTERO_USER_ID=...              # numeric ID at zotero.org/settings/keys
ZOTERO_LIBRARY_TYPE=user        # or "group" for a shared group library
```

---

## Adding a project

Projects are subfolders of `projects/`. Each project must have a `pdfs/` directory to be recognised by the app.

### Option A — Zotero sync (recommended)

Create a Zotero collection whose name matches your project name (case-insensitive), then run:

```bash
python ingest.py --project Arctic-NSF --zotero
```

This downloads PDFs from Zotero into `projects/Arctic-NSF/pdfs/`, enriches metadata (title, authors, year, DOI), and builds the search index. Re-running is safe — cached PDFs and existing chunks are skipped.

### Option B — Manual PDF drop

```bash
mkdir -p projects/JFSP/pdfs
# Copy PDFs into projects/JFSP/pdfs/
python ingest.py --project JFSP
```

Citations in this mode use filenames (`[paper.pdf, p. 4]`) rather than author/year.

### Ingest output

```
[info] Found 24 PDF(s) in projects/Arctic-NSF/pdfs
[info] Loading embedding model: all-MiniLM-L6-v2
[info] Processing: smith2023_permafrost.pdf
  -> Added 187 new chunk(s)
...
[done] Ingestion complete. Added 2 841 new chunk(s).
       Collection 'Arctic-NSF' now has 2 841 total chunk(s).
```

---

## Querying from the command line

```bash
python query.py --project Arctic-NSF "What are the main controls on permafrost carbon release?"
```

Output:
```
============================================================
ANSWER
============================================================
The primary controls on permafrost carbon release include... [Smith et al. (2023), p. 4]

============================================================
SOURCE CHUNKS RETRIEVED
============================================================
  - Smith et al. (2023), p. 4
  - Jones & Lee (2021), p. 12
  - ...
```

---

## Web UI

```bash
# Windows (PowerShell)
.venv\Scripts\streamlit run app.py

# Windows (Git Bash) or Mac/Linux
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

The UI has seven tabs:

| Tab | Purpose |
|---|---|
| **Chat** | Ask questions; answers cite exact pages from your literature |
| **Documents** | Browse the full index; generate annotated bibliography entries |
| **Extract** | Pull structured fields from every paper into a CSV table |
| **Draft** | Generate grant sections, IMRaD sections, gap maps, outreach copy |
| **Write** | Assisted markdown editor — AI helps refine, challenge, or expand your draft |
| **Graph** | Interactive theme network — papers connected by shared subject tags |
| **Guide** | Full user guide rendered inline |

The sidebar lets you switch projects, access past conversations, adjust model (Haiku / Sonnet / Opus), temperature, retrieval depth, and other advanced settings.

---

## Project structure

```
lab-ai/
├── ingest.py                 # PDF/Zotero → chunk → embed → ChromaDB
├── query.py                  # CLI + all query/draft/write functions
├── app.py                    # Streamlit web UI (7 tabs)
├── USER_GUIDE.md             # End-user guide for lab members
├── NOTES.md                  # Hosting, setup, and architecture notes
├── RUNBOOK.md                # Quick-reference for common operations
├── projects/
│   ├── Arctic-NSF/
│   │   ├── pdfs/             # PDFs cached here
│   │   ├── history/          # Auto-saved chat sessions (gitignored)
│   │   ├── annotations.json  # Generated annotated bibliography entries
│   │   ├── last_extraction.json
│   │   ├── themes.json       # Theme tags for the graph
│   │   ├── memory.json       # Cross-session conversation summaries
│   │   ├── write_draft.md    # Auto-saved Write tab draft
│   │   ├── write_context.md  # Writing brief for AI calls
│   │   ├── write_notes.md    # Append-only AI suggestion history
│   │   ├── write_config.json # Write tab config (external file path)
│   │   └── write_snapshots/  # Timestamped draft backups (last 20)
│   ├── JFSP/
│   └── Uncurated/
├── chroma_db/                # Auto-created; one collection per project (gitignored)
├── .env                      # API keys (gitignored)
├── .env.example              # Template
└── requirements.txt
```

---

## How it works

1. **Ingestion** — `ingest.py` extracts text from PDFs using PyMuPDF (with Tesseract OCR fallback for scanned pages), splits into 512-word chunks with 50-word overlap, and embeds each chunk with `all-MiniLM-L6-v2` (local, no API cost). Chunks are stored in a ChromaDB collection namespaced by project name. Chunk IDs are SHA-256 hashes, so re-ingestion is idempotent.

2. **Retrieval** — At query time, the question is embedded with the same model and ChromaDB returns the top-K most similar chunks by cosine similarity. K is configurable: 5 for Chat, 12 for Draft/Extract/Write (adjustable via the sidebar slider, 5–25).

3. **Generation** — Retrieved chunks and the question are sent to Claude with a system prompt that enforces citation and instructs the model to answer only from the provided context. Temperature defaults: 0.3 for Q&A, 0.4 for drafting.

4. **Zotero enrichment** — When using `--zotero`, metadata (title, authors, year, DOI) is attached to every chunk. Citations upgrade from `[filename.pdf, p. N]` to `[Author et al. (YEAR), p. N]`. Web links in Zotero collections are also scraped via trafilatura and ingested as text chunks.

---

## Multiple projects and cross-project synthesis

Each project has its own ChromaDB collection — fully isolated by default. Switch between projects in the Streamlit sidebar. For cross-project queries, use the **"Also search in"** multiselect in Chat, Draft, or Write tabs to pool literature from multiple collections in a single call.

```bash
python ingest.py --project Arctic-NSF --zotero
python ingest.py --project JFSP --zotero
python query.py --project Arctic-NSF "What methods are used to measure soil carbon flux?"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No collection found for project` | Run `python ingest.py --project <name>` first |
| `ANTHROPIC_API_KEY not set` | Check your `.env` file |
| No PDFs found | Confirm files are in `projects/<name>/pdfs/` and end in `.pdf` |
| Scanned / image-only PDF | Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and add it to PATH; the app will use it automatically |
| `chroma-hnswlib` build fails | You need Python 3.12 and Microsoft C++ Build Tools (Windows) |
| Rate limit (429) error | The app retries automatically after 65 s; for bulk Extract/Graph runs, inter-paper sleep is built in |
| Slow first run | Embedding model (~80 MB) downloads once on first use |
| Zotero collection not found | Collection name in Zotero must match `--project` name (case-insensitive) |
| Graph shows no connections | Re-tag papers with a broader theme set; tags that are too specific don't connect papers |
