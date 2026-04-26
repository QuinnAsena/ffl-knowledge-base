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
- [x] **OCR support** — `extract_pages()` falls back to Tesseract via PyMuPDF on image-only pages; graceful skip with install hint if Tesseract not present
- [x] **Per-project config** — `projects/{name}/config.json` overrides `chunk_size` and `chunk_overlap` at ingest time
- [x] **Cross-session memory** — conversations auto-summarised on "New Chat" (≥2 exchanges); last 3 summaries injected as prior context in all queries; sidebar expander with clear option
- [x] **Surface un-ingested Zotero papers** — Documents tab fetches Zotero collection, compares by DOI/title, shows missing papers with ingest command
- [x] **Model selector** — Haiku 4.5 / Sonnet 4.6 / Opus 4.7 chooser in Advanced settings; applies to all query and draft calls
- [x] **Temperature control** — sidebar slider 0.0–1.0; defaults 0.3 (Q&A) and 0.4 (drafting) vs API default of 1.0
- [x] **Max draft tokens** — select slider (1 024–8 192) in Advanced settings; allows long grant sections without truncation
- [x] **Retrieval confidence scores** — cosine similarity shown per source chunk when "Show retrieval scores" is toggled on
- [x] **Guide tab** — renders USER_GUIDE.md inline; covers all tabs, advanced settings, privacy, and FAQs
- [x] **Weighted theme graph** — `extract_themes()` returns `dict[str, float]`; edge width and theme node size proportional to relevance scores; backwards-compatible shim for old list-format files
- [x] **Write tab (Assisted Draft)** — split-pane markdown editor + live preview; AI assistance modes (Find citations, Refine, Challenge, Expand, Custom); session-state persistence across tab switches; markdown download; cross-project support
- [x] **Write tab — full persistence layer** — per-project auto-save (`write_draft.md`); writing context brief (`write_context.md`) injected into every AI call; version snapshots before each AI call (last 20 kept in `write_snapshots/`); append-only notes history (`write_notes.md`) with "Save to notes" + "Download notes" + "Clear notes"; "Append to draft" button inserts AI suggestion directly into editor
- [x] **Write tab — template library** — 8 built-in templates (Grant: Background & Significance, Objectives & Aims; Academic: Introduction, Methods, Discussion; Outreach: Press release, Blog post; Response to reviewers); template picker with Apply button
- [x] **Write tab — DOCX export** — "Export as DOCX" via pandoc; graceful "install pandoc" hint if not present
- [x] **Write tab — external file sync** — read/write draft from any mounted network drive path; "Save suggestion to file" appends AI notes alongside draft as `{stem}.notes.md`; path persisted to `write_config.json` per project

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

## Backlog (completed)

- [x] **Cross-project synthesis** — `query_multi` / `draft_multi` merge results across ChromaDB collections; multi-select project picker in Chat and Draft tabs.
- [x] **Multi-iterative drafting** — "Refine this draft" input in Draft tab; `refine_draft()` revises without new retrieval; flags uncited new claims.
- [x] **Theme / node visualisation** — Graph tab; Claude tags each paper with 3–4 themes; pyvis bipartite network (papers blue, themes amber); theme nodes sized by cumulative weight; edge width proportional to relevance; persisted to `themes.json`.
- [x] **OCR support** — `extract_pages()` tries Tesseract via PyMuPDF on image-only pages; graceful skip with install hint if Tesseract not present. Requires [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) on PATH.
- [x] **Per-project config file** — `projects/{name}/config.json` overrides `chunk_size` and `chunk_overlap` at ingest time; missing keys fall back to defaults.
- [x] **Cross-session conversation memory** — conversations auto-summarised on "New Chat" (≥2 exchanges); last 3 summaries injected as prior context in all queries; sidebar expander with clear option; stored in `projects/{name}/memory.json`.
- [x] **Surface un-ingested Zotero papers** — Documents tab fetches the Zotero collection (cached per session), compares by DOI then title, lists missing papers with the ingest command.

## Backlog (pending)

- [x] **Pandoc export** — Write tab "Export as DOCX" via pandoc; graceful "install pandoc" hint if not found. PDF excluded (requires LaTeX).
- [ ] **Figure caption writer** — describe a figure, get a publication-quality caption in the style of the current manuscript section.
- [ ] **Email and letter drafts** — outreach mode extended to professional correspondence: grant inquiry letters, collaboration proposals, cover letters.
- [ ] **Literature review outline** — given a research question, generate a thematic outline with suggested section headings and papers mapped to each.
- [ ] **Systematic review assistant** — guided workflow: define inclusion/exclusion criteria → Claude screens abstracts → extracts data → drafts synthesis section.