# FFL Knowledge Base — Personal Quick Reference

---

## Start / stop the app

```bash
# In VS Code terminal (Git Bash) — always activate the venv first
source .venv/Scripts/activate
streamlit run app.py
# Opens at http://localhost:8501

# Ctrl+C to stop
```

> The file watcher is disabled (`.streamlit/config.toml`). After any code change: **Ctrl+C → re-run**.

---

## Ingest papers from Zotero

```bash
source .venv/Scripts/activate

python ingest.py --project Arctic-NSF --zotero
python ingest.py --project JFSP --zotero
# Uncurated has no papers yet — skip it, or drop PDFs manually into projects/Uncurated/pdfs/ and run without --zotero

```

Re-running is safe — cached PDFs and already-ingested chunks are skipped automatically.

---

## Add a new project

1. Create the folder: `projects/newname/pdfs/`
2. Create a matching Zotero collection called `newname` (case-insensitive)
3. Ingest: `python ingest.py --project newname --zotero`
4. The project appears in the sidebar dropdown on next Streamlit start

---

## Install new packages

```bash
source .venv/Scripts/activate
pip install pyvis==0.3.2        # example: pin to a specific version
# or re-install everything from scratch:
pip install -r requirements.txt
```

After installing, always restart Streamlit.

---

## CLI query (no browser needed)

```bash
source .venv/Scripts/activate
python query.py --project Arctic-NSF "What are the main drivers of fire spread?"
```

---

## Where things live

| Thing | Path |
|---|---|
| Web UI | `http://localhost:8501` |
| API key | `.env` → `ANTHROPIC_API_KEY` |
| Zotero keys | `.env` → `ZOTERO_API_KEY`, `ZOTERO_USER_ID` |
| PDFs (Arctic-NSF) | `projects/Arctic-NSF/pdfs/` |
| PDFs (JFSP) | `projects/JFSP/pdfs/` |
| PDFs (Uncurated) | `projects/Uncurated/pdfs/` |
| Chat history | `projects/*/history/*.json` |
| Annotations | `projects/*/annotations.json` |
| Last extraction | `projects/*/last_extraction.json` |
| Theme graph data | `projects/*/themes.json` |
| Vector database | `chroma_db/` |

---

## Common problems

**Changes to code not taking effect**
The file watcher is off. Ctrl+C and restart Streamlit — that's it.

**Rate limit error (429)**
Hit the API quota (10 k tokens/min on a personal key). Wait ~1 minute, then retry.
On Extract or Graph tabs the UI already adds a 7 s pause between papers to avoid this.

**"pyvis is not installed" in Graph tab**
```bash
source .venv/Scripts/activate
pip install pyvis==0.3.2
```
Then restart Streamlit.

**Graph or extraction results seem stale**
Annotations, extractions, and theme data are cached in JSON files under `projects/`.
Delete the relevant file to force a re-run:
```bash
rm projects/Arctic-NSF/annotations.json
rm projects/Arctic-NSF/last_extraction.json
rm projects/Arctic-NSF/themes.json
```

**chromadb / embedding errors on first run after new ingest**
Restart Streamlit — the embedding model download sometimes causes a one-time lag.

**App dies with `Segmentation fault` on startup (Windows only)**
A native crash inside ChromaDB's hnswlib index — no Python traceback, the process
just exits. It is intermittent: the same command may work on the second try.
Known to affect this machine (see the `feature/section-filter` branch note); it does
not occur on Linux, so the lab server deployment is expected to be immune.

Mitigation already in the code: exactly one ChromaDB client is created per process
(`query.get_chroma_client()`), because building clients per call across Streamlit's
per-rerun threads is a thread-safety hazard. **Never** call
`chromadb.PersistentClient()` anywhere else.

If it recurs, capture a native traceback so the faulting library is identified
instead of guessed:
```bash
PYTHONFAULTHANDLER=1 streamlit run app.py
```
On the next crash the C-level stack is printed — it names the library at fault
(`chroma-hnswlib`, `torch`, or `onnxruntime`). Save that output.

**Console spam: `Failed to send telemetry event ... capture() takes 1 positional argument`**
Harmless. chromadb 0.6.3 calls an old posthog API and posthog 7.x is installed.
To silence it: `pip install "posthog<6"` (and pin it in `requirements.txt`).

---

## Switching to the lab group Zotero library

Edit `.env`:
```
ZOTERO_LIBRARY_TYPE=group
ZOTERO_USER_ID=<group-id>     # zotero.org/groups/<name>/settings
```
No code changes needed.

---

## Deploy to the lab server (one-time)

See `NOTES.md` → "Recommended: Lab server + Cloudflare Tunnel + Cloudflare Access"
for full step-by-step setup including NSSM persistent service.
