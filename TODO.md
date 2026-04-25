# Lab AI — TODO

## Setup (complete)

- [x] Install Python 3.12.10, Microsoft C++ Build Tools, create venv
- [x] Install dependencies
- [x] Fix chromadb 0.6 API, model ID, torch/Streamlit file watcher noise

## Functionality (complete)

- [x] **Zotero integration** — `--zotero` flag; pulls PDFs + metadata; caches locally; citations as `Author et al. (YEAR), p. N`
- [x] **Zotero web links** — `--zotero` also scrapes web links from collection via trafilatura; cites as `Author (YEAR) [online]`
- [x] **Chat history persistence** — auto-saves to `projects/{project}/history/`; sidebar panel; reload past sessions
- [x] **Browsable document index** — "Documents" tab; title, authors, year, DOI, chunk count per item
- [x] **Annotated bibliography** — per-paper annotation button in Documents tab; persisted to `annotations.json`; bulk markdown download
- [x] **5 writing modes** — Grant Proposal, Academic Paper, Outreach & Communication, Response to Reviewers, Research Gap Map; each with its own system prompt and section presets
- [x] **Iterative draft refinement** — "Refine this draft" input in Draft tab; revises without new retrieval
- [x] **Structured extraction** — Extract tab; user-defined fields → table + CSV; persisted to `last_extraction.json`
- [x] **Cross-project synthesis** — `query_multi` / `draft_multi`; multi-select in Chat and Draft tabs
- [x] **Theme graph** — Graph tab; Claude tags papers; pyvis bipartite network; theme nodes sized by degree; persisted to `themes.json`
- [x] **Retrieval depth slider** — sidebar slider controls top-k for Draft and Extract (5–25)
- [x] **File-based persistence** — annotations, extractions, and themes survive Streamlit restart

---

## Next: Hosting

- [x] Decide final hosting approach — **lab server + Cloudflare Tunnel + Cloudflare Access** (see NOTES.md)
- [x] Consider Cloudflare Tunnel — adopted as primary external access method
- [x] Add a second project to confirm multi-project isolation in production
- [ ] Deploy repo to lab server and install dependencies (Python 3.12, C++ Build Tools, venv)
- [ ] Set up Streamlit as a persistent service on lab server (NSSM on Windows, systemd on Linux)
- [ ] Configure Cloudflare Tunnel (named tunnel for stable URL) + Cloudflare Access (@caryinstitute.org policy)
- [ ] Create lab Anthropic account + shared API key; add to server `.env`
- [ ] Build out group Zotero library; switch `.env` to `ZOTERO_LIBRARY_TYPE=group` + group ID

---

## Backlog

- [ ] OCR support for scanned PDFs (currently skipped with a warning)
- [ ] Per-project ingestion config file (chunk size, overlap, top-k overrides)
- [ ] Cross-session conversation memory (summaries carried across chats)
- [ ] Surface papers in Zotero but not yet ingested in Documents tab

---
