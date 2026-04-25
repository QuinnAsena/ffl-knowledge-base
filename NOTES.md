# Lab AI — Notes

## Hosting

### Privacy caveat (applies to all options)
Document text chunks are always sent to Anthropic's API servers at query time regardless of
where Streamlit is hosted. Files, ChromaDB, embeddings, and chat history stay local.
Factor this in for embargoed papers or sensitive grant proposals.

### Recommended: Lab server + Cloudflare Tunnel + Cloudflare Access

**Why this combination:**
- All files, embeddings, ChromaDB, and chat history remain on your server (privacy)
- Lab members access a stable HTTPS URL from anywhere — no VPN, no logging into the server desktop
- Cloudflare Access restricts the URL to specific email addresses or domains (e.g. `@caryinstitute.org`)
- No port forwarding or firewall changes needed on the server
- Cost: $0 (Cloudflare Free tier covers Tunnel and Access at this scale)

**Step 1 — Run Streamlit as a persistent service**

Linux (systemd):
```ini
# /etc/systemd/system/ffl-knowledge-base.service
[Unit]
Description=FFL Knowledge Base Streamlit App
After=network.target

[Service]
User=<your-user>
WorkingDirectory=/path/to/ffl-knowledge-base
ExecStart=/path/to/ffl-knowledge-base/.venv/bin/streamlit run app.py \
  --server.address 127.0.0.1 --server.port 8501
Restart=always
EnvironmentFile=/path/to/ffl-knowledge-base/.env

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable ffl-knowledge-base
sudo systemctl start ffl-knowledge-base
```

Windows (NSSM — https://nssm.cc):
```powershell
nssm install FFLKnowledgeBase "C:\path\to\ffl-knowledge-base\.venv\Scripts\streamlit.exe" `
  "run app.py --server.address 127.0.0.1 --server.port 8501"
nssm set FFLKnowledgeBase AppDirectory "C:\path\to\ffl-knowledge-base"
nssm set FFLKnowledgeBase AppEnvironmentExtra "ANTHROPIC_API_KEY=<key>"
nssm start FFLKnowledgeBase
```
> Note: bind to `127.0.0.1` (loopback only) — Cloudflare Tunnel is the only entry point.

**Step 2 — Install and start Cloudflare Tunnel**
```bash
# Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
# Quick tunnel (no account needed, URL changes on restart):
cloudflared tunnel --url http://localhost:8501

# Named tunnel (stable URL, requires free Cloudflare account):
cloudflared login
cloudflared tunnel create lab-ai
cloudflared tunnel route dns lab-ai lab-ai.<your-domain>.com
cloudflared tunnel run lab-ai
# Add to systemd/NSSM alongside the Streamlit service for persistence
```

**Step 3 — Enable Cloudflare Access (email-based auth)**
1. Go to Cloudflare Zero Trust dashboard → Access → Applications → Add an application
2. Choose "Self-hosted", enter the tunnel URL
3. Under "Policies", add a rule: `Emails ending in` → `@caryinstitute.org`
   (or list individual emails if you prefer)
4. Lab members visit the URL, enter their institutional email, receive a one-time code, and are in

No passwords to manage; Cloudflare handles the auth flow.

### Option comparison (for reference)

| Option                                    | Privacy   | Accessibility        | Setup effort | Cost       |
|-------------------------------------------|-----------|----------------------|--------------|------------|
| **Lab server + Cloudflare Tunnel + Access** | **High** | **Anyone with link** | **Moderate** | **$0**   |
| Shared lab server (LAN only)              | High      | Lab network only     | Low          | $0         |
| Streamlit Community Cloud                 | Low       | Public internet      | Low          | $0         |
| Cloud VM (AWS/GCP/Azure)                  | Config.   | Public internet      | High         | ~$10–30/mo |
| Hugging Face Spaces                       | Low       | Public internet      | Low          | $0–50/mo   |

---

## Anthropic API key — lab setup

**Use a single shared lab API key stored in `.env` on the server.**

Anthropic's API is pay-per-use — there is no per-seat model. The lab needs one account:

1. Go to `console.anthropic.com` → create a lab account (use a shared email like `labai@caryinstitute.org` so it doesn't depend on one person)
2. Add a credit card or purchase API credits
3. Generate an API key under API Keys
4. On the server, add it to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`
5. All lab members share it transparently through the Streamlit UI — no per-user setup

**Cost:** claude-sonnet-4-6 is ~$3 per million input tokens and ~$15 per million output tokens.
A typical query retrieves ~5 chunks of ~500 words each (~3 500 tokens) plus the answer (~300 tokens).
For light academic use (a few dozen queries per day), expect well under $5/month.
Usage is visible in the Anthropic console dashboard at any time.

---

## Setup guide — Windows (primary)

> **Python version:** Use 3.12.x — Python 3.14 has no pre-built wheels for `chroma-hnswlib`.
> **C++ Build Tools:** Required to compile `chroma-hnswlib`. Install from
> https://visualstudio.microsoft.com/visual-cpp-build-tools/ (select "Desktop development with C++").

```powershell
# 1. Verify Python 3.12
py -0                        # should list Python 3.12
py -3.12 --version

# 2. Clone repo and enter directory
cd C:\path\to\lab-ai

# 3. Create and activate virtual environment with Python 3.12
py -3.12 -m venv .venv
.venv\Scripts\activate

# 4. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5. Configure secrets
copy .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY, ZOTERO_API_KEY, ZOTERO_USER_ID

# 6. Sync from Zotero (recommended) or drop PDFs manually
python ingest.py --project fire --zotero
# or: python ingest.py --project fire   (manual PDFs in projects\fire\pdfs\)

# 7. Test CLI
python query.py --project fire "What are the main findings?"

# 8. Launch UI
.venv\Scripts\streamlit run app.py
# Opens at http://localhost:8501
```

---

## Setup guide — Mac/Linux (reference framework)

```bash
# 1. Verify Python version (3.12 recommended)
python3 --version

# 2. Clone repo and enter directory
cd /path/to/lab-ai

# 3. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 5. Configure secrets
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY, ZOTERO_API_KEY, ZOTERO_USER_ID

# 6. Sync from Zotero or drop PDFs manually
python ingest.py --project fire --zotero

# 7. Test CLI
python query.py --project fire "What are the main findings?"

# 8. Launch UI
streamlit run app.py
# Opens at http://localhost:8501
```

**Mac-specific notes:**
- Install Python 3.12 via `brew install python@3.12`
- PyMuPDF may need Xcode command-line tools: `xcode-select --install`

**Linux-specific notes:**
- `sudo apt install python3.12 python3.12-venv build-essential` (Ubuntu/Debian)

---

## Grant proposal drafting tool

The "Draft" tab in the Streamlit UI is a separate mode from chat. It retrieves more chunks
(12 vs 5) and uses a different system prompt that instructs Claude to write academic prose
rather than answer questions.

**How to use:**
1. Open the "Draft" tab
2. Select a section type (Background, Significance, Objectives, etc.) or leave as "Custom"
3. Describe what you want written (e.g., "Write a background paragraph on deep learning methods for wildfire risk prediction, focusing on CNN and LSTM approaches")
4. Click "Generate draft"
5. Download the result as a `.md` file

**Design principles:**
- Every factual claim is cited inline `[Author et al. (YEAR), p. N]`
- If the literature is insufficient, Claude flags what's missing rather than fabricating
- Output is markdown — paste directly into a document or export to Word via Pandoc

**Tips for good drafts:**
- Be specific about the section and angle
- More ingested literature = better coverage; add papers to Zotero before drafting
- Treat the output as a first draft — it needs editing, but saves hours of synthesis work

---

## Zotero integration

**How it works:**
- `ingest.py --zotero` finds a Zotero collection matching the project name (case-insensitive)
- Downloads PDFs to `projects/{name}/pdfs/` as a local cache
- Stores metadata per chunk: title, authors, year, DOI
- Citations upgrade from `[filename.pdf, p. N]` to `[Author et al. (YEAR), p. N]`
- Re-running is safe — cached PDFs and existing chunks are skipped

**Switching from personal to group library:**
Change one line in `.env`:
```
ZOTERO_LIBRARY_TYPE=group
ZOTERO_USER_ID=<group-id>   # find at zotero.org/groups/<name>/settings
```
No code changes needed.

**Required `.env` keys:**
```
ZOTERO_API_KEY=...          # zotero.org/settings/keys — needs library read access
ZOTERO_USER_ID=...          # numeric ID shown at top of zotero.org/settings/keys
ZOTERO_LIBRARY_TYPE=user    # or "group"
```

---

## Dependency notes

| Package               | Purpose                          | Notes                                      |
|-----------------------|----------------------------------|--------------------------------------------|
| `anthropic`           | Claude API client                | Pinned to 0.49.0                           |
| `sentence-transformers` | Local embeddings               | Downloads all-MiniLM-L6-v2 (~80 MB) on first run |
| `chromadb`            | Vector database                  | Persists to `chroma_db/` on disk           |
| `PyMuPDF`             | PDF text extraction              | Handles multi-column layouts well          |
| `pyzotero`            | Zotero API client                | Pinned to 1.5.18                           |
| `streamlit`           | Web UI                           | Runs on port 8501 by default               |
| `python-dotenv`       | Load `.env` secrets              |                                            |

---

## Future features

### Backlog (not yet scoped)
- **Figure caption writer** — describe a figure, get a publication-quality caption in the style of the current manuscript section.
- **Email and letter drafts** — same outreach mode but for professional correspondence: grant inquiry letters, collaboration proposals, cover letters.
- **Literature review outline** — given a research question, generate a thematic outline for a review paper with suggested section headings and papers mapped to each.
- **Systematic review assistant** — guided workflow: define inclusion/exclusion criteria → Claude screens abstracts → extracts data → drafts synthesis section. Essentially a mini-SR pipeline.
- **OCR support** — scanned PDFs are currently skipped with a warning. Add OCR via `pytesseract` or `pymupdf` with OCR backend so image-only PDFs can be ingested.
- **Per-project config file** — `projects/{name}/config.json` to override chunk size, overlap, and top-k defaults per project without touching code.
- **Cross-session conversation memory** — summarise past chat sessions and carry a compressed context forward so Claude "remembers" earlier discussions within a project.
- **Surface un-ingested Zotero papers** — in the Documents tab, show papers present in Zotero but not yet in ChromaDB, with a one-click ingest button.

---

## Architecture decisions record

**Why not LlamaIndex?**
The project brief listed it, but chunking/embedding/retrieval is simple enough to do directly
with PyMuPDF + sentence-transformers + chromadb. Fewer moving parts, easier to debug.

**Why sentence-transformers instead of OpenAI embeddings?**
Runs locally — no API cost, no data leaving the machine at embed time, no rate limits.

**Why ChromaDB instead of Pinecone?**
Zero setup, runs on disk, easy to migrate to Pinecone later by swapping the storage backend.
Multi-project isolation is handled via collection namespacing.

**Why `ValueError` instead of `sys.exit` in `query.py`?**
`query.py` is imported by `app.py`. `sys.exit` would kill the Streamlit process.
Raising `ValueError` lets the caller (CLI or Streamlit) handle errors appropriately.

**Why Python 3.12 on Windows instead of 3.14?**
`chroma-hnswlib` has no pre-built Windows wheels for Python 3.14 and must compile from C++ source.
Python 3.12 has full wheel coverage for all ML dependencies.
