# FFL Knowledge Base

A local literature knowledge base for querying academic PDFs and grant proposals. Each project has its own isolated search index. Powered by Claude (Anthropic API) for synthesis; embeddings run locally.

---

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd ffl-knowledge-base
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

```bash
cp .env.example .env
# Edit .env and paste your Anthropic API key
```

---

## Adding a project

Create a folder for your project and drop PDFs into it:

```
projects/
└── fire/
    └── pdfs/
        ├── paper1.pdf
        └── grant_proposal.pdf
```

Then ingest the documents:

```bash
python ingest.py --project fire
```

Output example:
```
[info] Found 3 PDF(s) in projects/fire/pdfs
[info] Loading embedding model: all-MiniLM-L6-v2
[info] Processing: paper1.pdf
  -> Added 142 new chunk(s)
...
[done] Ingestion complete. Added 387 new chunk(s). Collection 'fire' now has 387 total chunk(s).
```

Re-running `ingest.py` on the same project is safe — existing chunks are skipped, and only new PDFs are added.

---

## Querying from the command line

```bash
python query.py --project fire "What are the main drivers of fire spread in California chaparral?"
```

Output:
```
============================================================
ANSWER
============================================================
The main drivers of fire spread in California chaparral include...
[paper1.pdf, p. 4]

============================================================
SOURCE CHUNKS RETRIEVED
============================================================
  - paper1.pdf, p. 4
  - paper1.pdf, p. 7
  - grant_proposal.pdf, p. 2
```

---

## Web UI (Streamlit)

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

- **Sidebar**: select a project from the dropdown (auto-populated from `projects/` directories)
- **Chat interface**: ask questions; responses include expandable source citations
- **Clear chat**: button in the sidebar resets the session history

---

## Project structure

```
ffl-knowledge-base/
├── ingest.py            # PDF → chunk → embed → ChromaDB
├── query.py             # CLI: retrieve → Claude API → answer + citations
├── app.py               # Streamlit web UI
├── USER_GUIDE.md        # End-user guide for lab members
├── projects/
│   └── fire/
│       └── pdfs/        # Drop PDFs here
├── chroma_db/           # Auto-created on first ingest (gitignored)
├── .env                 # Your API key (gitignored)
├── .env.example         # Template
├── requirements.txt
└── README.md
```

---

## How it works

1. **Ingestion** — `ingest.py` extracts text page-by-page from each PDF using PyMuPDF, splits pages into 512-word chunks with 50-word overlap, embeds each chunk with `sentence-transformers/all-MiniLM-L6-v2` (runs locally, no API cost), and stores chunks in a ChromaDB collection namespaced by project name.

2. **Retrieval** — `query.py` embeds the user's question with the same model, queries ChromaDB for the top-5 most similar chunks by cosine similarity, and formats them as numbered excerpts with filename and page metadata.

3. **Generation** — The excerpts and question are sent to Claude (`claude-sonnet-4-6`) with a system prompt that enforces citation and instructs the model to answer only from the provided context.

---

## Multiple projects

Each project gets its own ChromaDB collection — they are fully isolated. Switch between projects in the Streamlit sidebar or via the `--project` flag.

```bash
python ingest.py --project fire
python ingest.py --project hydrology
python query.py --project hydrology "What methods are used for streamflow prediction?"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No collection found for project` | Run `python ingest.py --project <name>` first |
| `ANTHROPIC_API_KEY not set` | Check your `.env` file |
| No PDFs found | Confirm files are in `projects/<name>/pdfs/` and end in `.pdf` |
| Empty or garbled text extraction | The PDF may be scanned (image-only); OCR support is not yet included |
| Slow first run | The embedding model (~80 MB) downloads once on first use |

---

## Adding more projects

Just repeat the steps above with a new project name. No configuration changes needed.
