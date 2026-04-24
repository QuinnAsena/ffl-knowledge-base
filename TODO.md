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
- [x] **Grant proposal drafting** — "Draft" tab; section type selector; retrieves 12 chunks; academic prose with inline citations; flags literature gaps; markdown download

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
