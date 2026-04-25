# FFL Knowledge Base — User Guide

A tool for searching the lab's literature and drafting grant proposal sections. Ask a question in plain English and get an answer drawn directly from ingested papers, with citations you can verify.

---

## What this tool is (and isn't)

**It is:** a searchable index of papers and documents that have been deliberately added to the system. Every answer comes from those documents, with citations pointing to the exact source.

**It is not:** a general-purpose AI chatbot. It cannot draw on knowledge outside the ingested literature. If the answer isn't in the documents, it will say so rather than guess.

---

## What's in the knowledge base

The knowledge base contains papers that a lab administrator has synced from a curated Zotero library. Each paper is broken into passages and indexed for search — the tool retrieves the most relevant passages when you ask a question.

**Only documents deliberately added to the Zotero collection are included.** The system does not browse the internet or access any external database during a query.

Sources currently indexed are visible in the **Documents** tab.

---

## Asking questions (Chat tab)

Type your question in the chat box and press Enter. The system will:

1. Find the passages from the literature most relevant to your question
2. Send those passages (and only those passages) to Claude to generate an answer
3. Return the answer with inline citations — e.g. `[Smith et al. (2023), p. 4]`

**Expand "Source chunks retrieved"** below any answer to see exactly which passages were used.

### Getting good answers

- Be specific. "What methods are used for measuring soil carbon flux in boreal forests?" will retrieve better passages than "tell me about soil carbon."
- If an answer seems thin, check the Documents tab — the relevant papers may not yet be ingested.
- Citations are your verification tool. If a claim looks surprising, look up the cited page in the original paper.

### What the tool will not do

- It will not answer from memory or prior training if the information isn't in the provided passages.
- If evidence is insufficient, it responds: *"I don't have enough information in the provided documents to answer this question."*
- It will not speculate or extrapolate beyond what the documents state.

- What TOP_K_DRAFT = 12 means

When you submit a question or draft request, the system doesn't send all your documents to Claude — it would be too slow and expensive. Instead:

Your question is converted into a numeric vector (an "embedding" that captures its meaning)
ChromaDB finds the K chunks whose vectors are most similar to your question's vector
Only those K chunks are sent to Claude to generate the answer
TOP_K = 5 for chat queries — 5 most relevant passages is enough to answer a focused question concisely.
TOP_K_DRAFT = 12 for drafting — when writing a grant section you want broader coverage so Claude can synthesize across more sources, at the cost of a slightly longer, more expensive call.

---

## Drafting grant proposal sections (Draft tab)

The Draft tab retrieves a broader set of passages (up to 12) and instructs Claude to write formal academic prose rather than answer a question.

1. Select a section type (Background, Significance, Objectives, etc.)
2. Describe what the section should cover
3. Click **Generate draft**
4. Download the result as a `.md` file (paste into Word or convert via Pandoc)

Every factual claim in the draft is cited. Where the literature is thin, the draft flags the gap explicitly rather than filling it with fabricated content:

> **[GAP: insufficient literature on X — consider adding sources]**

Treat the output as a first draft — it saves synthesis time but requires editing and your own judgement before submission.

---

## Privacy and data

### What stays on the lab server
- All PDF files
- The search index (ChromaDB vector database)
- Chat history
- Zotero metadata

### What is sent to Anthropic
When you submit a question or request a draft, the system sends:
- Your question or prompt
- The text of the most relevant passages retrieved from the documents (~5–12 excerpts of ~500 words each)

**No files, no embeddings, no chat history, and no metadata are sent.** Only the text needed to generate your answer leaves the server.

### Implication for sensitive documents
Text from ingested documents is sent to Anthropic's API servers at query time. For papers under embargo or grant proposals in preparation, consider whether this is acceptable before adding them to the Zotero collection. Published open-access papers carry no such concern.

---

## What makes answers reliable

- **Grounded responses:** Claude is instructed to answer only from the retrieved passages, not from general training knowledge.
- **Mandatory citations:** Every factual claim must be cited to a specific passage and page. Uncited claims are a sign something has gone wrong.
- **Curated inputs:** The knowledge base reflects the quality of what's been added. Papers with complete Zotero metadata (authors, year, DOI) produce the best citations. Scanned PDFs with no text layer cannot be read and are skipped with a warning.
- **No hallucinated references:** The citations shown are the actual passages retrieved, not invented sources. You can open the "Source chunks retrieved" expander to read the raw text that was used.

---

## Adding papers to the knowledge base

Contact the lab administrator to add papers to the Zotero collection. Once added and synced, they will appear in the Documents tab and be available for querying. You do not need to do anything on your end — just wait for the next sync.

---

## Common questions

**Why didn't it find a paper I know exists?**
It may not have been ingested yet. Check the Documents tab. If it's missing, ask the lab administrator to add it to Zotero.

**The answer seems wrong or oversimplified.**
Open the source chunks and read the raw passages. The answer is only as good as what was retrieved. Sometimes relevant information is in a paper that hasn't been added yet.

**Can I use this for my own project?**
Projects are isolated — each has its own literature index. Ask the lab administrator to set up a new project and Zotero collection.

**Is my conversation saved?**
Yes. Conversations are automatically saved and accessible in the sidebar for future reference.

## notes to self

`streamlit run app.py`