# FFL Knowledge Base — User Guide

A literature search and synthesis tool for the lab. Ask a question in plain English and get an answer drawn directly from ingested papers, with citations you can verify.

---

## Why not just use Claude.ai?

It is a fair question. Claude.ai and ChatGPT are extraordinary tools, and for many tasks they are the right choice. But for day-to-day research work — reading your own literature, drafting grants, building evidence tables — they have a structural problem: you cannot trust what they cite.

When you ask Claude.ai to write a grant background on fire return intervals, it draws on its training data: patterns distilled from billions of documents of unknown provenance, with a fixed knowledge cutoff, and no awareness of which papers your lab actually relies on. The citations it produces may be real papers, may be plausible-sounding fabrications, or may be real papers that say something subtly different from what Claude claims. Verifying them is slow and unreliable.

This app is built on a different architecture. Instead of answering from training knowledge, it first searches your ingested paper collection for the most relevant passages, then passes only those passages to Claude and instructs it to answer *from them alone*. If the answer is not in your literature, it says so. Every claim links to a specific page in a specific paper you own. The citation is not a guess — it is the exact chunk of text that generated the answer, and you can read it in one click.

That architectural difference — **retrieval from your curated library rather than synthesis from training data** — is what makes the tool useful for research rather than just impressive.

### How they compare

| | Claude.ai / ChatGPT | This app |
|---|---|---|
| **Knowledge source** | Training data — billions of documents, unknown provenance | Your Zotero library only — papers you chose |
| **Citations** | Approximate; sometimes hallucinated | Exact — author, year, page number; verifiable in one click |
| **Answers outside your literature** | Yes — draws on all training knowledge | No — refuses rather than guesses |
| **Retrieval method** | None — answers from memory | Semantic vector search — finds meaning, not just keywords |
| **Knows your specific papers** | Only if you paste them in each time | Yes — all ingested papers always searchable |
| **Writing assistance** | General purpose | Research-mode: Challenge, Gap Map, Response to Reviewers |
| **Session memory** | Resets each conversation | Summarised and re-injected across sessions |
| **Privacy** | All content processed in the cloud | Papers and embeddings stay on your server |

### Five things this app does that Claude.ai cannot

**1. Find the paper you half-remember.** You know a study showed permafrost carbon release timescales were shorter than models predicted, but you cannot remember the author. Type that paraphrase as a question. Semantic search finds the relevant passage from a paper you ingested a year ago — even if you used completely different words. Claude.ai does not know which papers are in your library.

**2. Challenge your own grant draft against your own evidence.** Paste your Background section into the Write tab and click *Challenge*. The app retrieves passages from your collection and asks Claude to identify every claim that is not supported by your specific literature — not by the internet, not by training data, but by the papers you are actually citing. This is the pre-submission check that takes hours to do manually.

**3. Synthesise across collections at midnight.** You are writing Broader Impacts for your Arctic-NSF proposal and want to know what your JFSP fire literature says about permafrost. Select both collections, ask your question, and get a synthesised answer with citations from both — in seconds. Claude.ai does not know either collection exists.

**4. Build a methods table for 40 papers in ten minutes.** Open the Extract tab, type the fields you want — *study region, sample size, statistical approach, main finding, key limitation* — and click Extract. Every ingested paper is processed in sequence and the results download as a CSV. With Claude.ai you would need to copy-paste each paper individually and prompt for consistent formatting every time.

**5. Draft a background section you can actually submit.** Claude.ai drafts from its training knowledge, which may include retracted work, papers your reviewers will not recognise as relevant, or citations that do not exist. This app drafts exclusively from your collection. Every inline citation is a real chunk you can inspect. Where your literature is thin, it tells you explicitly — *[GAP: insufficient literature on X]* — rather than filling the gap with plausible-sounding speculation.

### What you give up

The constraint is real: this tool cannot answer questions that your ingested papers do not address. It does not know about work published since your last Zotero sync. And when you query the app, the text of the retrieved passages is sent to Anthropic's servers to generate the answer — the same data flow as using Claude.ai directly, though files, embeddings, and chat history stay on your server.

The constraint is also the point. A tool that only answers from sources you have chosen, and tells you when those sources are insufficient, is one you can build research arguments on. The inability to hallucinate is not a bug.

---

## What this tool is (and isn't)

**It is:** a searchable index of papers and documents that have been deliberately added to the system. Every answer comes from those documents, with citations pointing to the exact source.

**It is not:** a general-purpose AI assistant. It cannot draw on knowledge outside the ingested literature. If the answer isn't in the documents, it will say so rather than guess.

---

## How retrieval works

When you submit a question or draft request, the system does not send all your documents to Claude — that would be too slow and expensive. Instead:

1. Your question is converted into a numeric vector (an "embedding" capturing its meaning)
2. ChromaDB finds the K passages whose vectors are most similar to your question
3. Only those K passages are sent to Claude to generate the answer

**Chat tab:** retrieves 5 passages — enough for a focused factual answer.
**Draft and Extract tabs:** retrieves 12 by default (adjustable in Advanced settings) — broader coverage for synthesis and extraction tasks.

---

## Chat tab

Type your question in the chat box and press Enter.

- Answers include inline citations — e.g. `[Smith et al. (2023), p. 4]`
- Expand **"Source chunks retrieved"** below any answer to read the exact passages that were used
- With **"Show retrieval scores"** enabled (Advanced settings), each source shows a match score (0–1). Scores above ~0.6 indicate strong relevance; below ~0.4 the match may be weak
- Conversations are auto-saved and accessible in the sidebar for future reference
- Use **"Also search in"** to pool literature from multiple projects in one query

### Getting good answers

- Be specific. *"What methods are used to measure soil carbon flux in boreal forests?"* retrieves better passages than *"tell me about soil carbon."*
- If an answer seems thin, check the Documents tab — the relevant papers may not yet be ingested.
- Open the source chunks and read the raw passages. The answer is only as good as what was retrieved.

### What it will not do

- Answer from memory or prior training if the information isn't in the provided passages
- Speculate beyond what the documents state
- Where the passages only partly cover your question, it answers with what they do support and
  says plainly what is missing
- Where nothing relevant was retrieved: *"I don't have enough information in the provided documents to answer this question."* If you see this on a question your papers should cover, raise **Passages retrieved** in Advanced settings or rephrase using the terminology of the literature

---

## Documents tab

A browsable index of every ingested paper, showing title, authors, year, DOI, and chunk count.

- **Generate annotation** — produces a structured three-part annotation (*What it does / Key findings / Methods*) for that paper. Saved automatically; persists across sessions.
- **Download all annotations** — exports every generated annotation as a single `.md` file, suitable for a literature review appendix.
- **Zotero sync check** — if Zotero credentials are configured, shows any papers present in your Zotero collection but not yet ingested. Click **Refresh** to re-check after adding papers.

---

## Draft tab

Retrieves a broader set of passages and instructs Claude to write formal prose rather than answer a question.

### Writing modes

| Mode | Best for |
|---|---|
| **Grant Proposal** | NSF/NIH background, significance, objectives, approach sections |
| **Academic Paper** | IMRaD manuscript sections — introduction through discussion |
| **Outreach & Communication** | Press releases, blog posts, plain-language summaries, social media |
| **Response to Reviewers** | Point-by-point responses to peer review comments |
| **Research Gap Map** | Structured synthesis of what is known, contested, and missing |

Every factual claim is cited. Where the literature is thin, the draft flags the gap explicitly:

> **[GAP: insufficient literature on X — consider adding sources]**

### Iterative refinement

After a draft is generated, use the **"Refine this draft"** input to revise it:

- *"Make the third paragraph more concise"*
- *"Add more on remote sensing methods"*
- *"Rewrite the opening sentence to emphasise fire frequency rather than severity"*

Refinement does not retrieve new passages — it revises the existing text. All existing citations are preserved; any new claims Claude introduces are flagged `[UNVERIFIED]`.

### Tips for good drafts

- Be specific about the section and angle — the more precise the prompt, the better the synthesis
- More ingested literature = better coverage; add papers to Zotero before drafting
- Use **"Also draw from"** to include literature from additional projects
- Raise the **Max draft length** slider for long sections (4 096+ tokens for a full background)
- Treat the output as a first draft — it saves synthesis time but requires your editorial judgement

---

## Extract tab

Extract specific fields from every ingested paper into a structured table.

1. Enter the fields you want, comma-separated (e.g. *study region, sample size, key method, main finding, limitations*)
2. Click **Extract from all papers**
3. Results appear as a table — download as CSV

Useful for systematic reviews, meta-analyses, and rapid evidence mapping. The tool processes one paper at a time and pauses briefly between papers to stay within API rate limits. Results are saved automatically and restored on the next session.

---

## Graph tab

An interactive network showing which papers share which themes.

- **Blue nodes** = papers
- **Amber nodes** = themes (larger = shared by more papers)
- Drag nodes to explore; hover for details
- Click **Tag unprocessed papers** to run Claude's theme tagging on new papers
- Click **Re-tag all** to regenerate all tags (useful after ingesting many new papers)

Themes are 2–4 word tags generated by Claude from each paper's text. Papers connected to the same theme node share that subject area. Tags are saved automatically.

---

## Write tab

The Write tab is a markdown editor with a research collaborator that reads your draft and suggests improvements grounded in your ingested literature.

### Editor and preview

The tab shows two panels side-by-side: a markdown editor on the left and a live preview on the right. Write in the left panel; the right panel renders your markdown in real time. Standard markdown formatting is supported — headings, bold, lists, tables, blockquotes.

### Assistance modes

| Mode | What it does |
|---|---|
| **Find citations** | Scans your draft and retrieves passages from the literature you could cite to support your claims |
| **Refine** | Suggests improvements to flow, clarity, and structure while preserving your argument |
| **Challenge** | Points out claims that are too strong, speculative, or unsupported given the available evidence |
| **Expand** | Identifies where the draft could go deeper and retrieves relevant passages to support expansion |
| **Custom** | Enter any instruction — translate a concept, adjust tone, identify jargon, etc. |

Click a mode button and then **Ask**. Claude reads your entire draft plus retrieved literature passages. The result appears below the editor. Click **Append to draft** to insert the suggestion at the end of your draft.

### Writing context

Open **Writing context (optional)** to describe the document's purpose, audience, and constraints. This is included with every suggestion request:

> *NSF proposal for the Division of Environmental Biology. Audience: program officers with ecology background. Main argument: fire return intervals have shortened 40% since 1980. Data is correlational — avoid causal language.*

Click **Save context** to persist it — it reloads automatically each session.

### Templates

Choose a template from the **Start from template** dropdown and click **Apply** to populate the editor with a structured outline. Available templates cover grant proposals, academic IMRaD sections, outreach formats, and response to reviewers.

**Note:** applying a template replaces the current editor contents. Save your draft first if it matters.

### Saving your work

- **Save draft** — saves the current editor contents to `write_draft.md` in your project folder. The draft reloads automatically at the start of the next session.
- **Save to notes** — appends the current suggestion to `write_notes.md` with a timestamp and mode header. This builds an append-only history of suggestions for the piece.
- **Download draft (.md)** — downloads the draft as a markdown file.
- **Export as DOCX** — converts to Word format via pandoc (requires pandoc to be installed on the server).

### Notes history

Once you have saved suggestions to notes, they appear in the **Notes history** expander below the suggestion pane. Download or clear the full history from there.

### Version snapshots

Each time you ask for a suggestion, the current draft is automatically saved as a timestamped snapshot in `write_snapshots/` before the request is sent. The last 20 snapshots are kept. These are silent backups — no action required.

### External file sync

Open **External file sync (network drive)** to connect the editor to a file on a mounted network drive or any path the server can reach:

- **Load from file** — fills the editor with the file's contents
- **Save to file** — writes the current draft to the file
- **Save suggestion to file** — appends the current suggestion to a companion file named `{filename}.notes.md` in the same directory

The file path is saved per-project in `write_config.json` and restored automatically.

---

## Usage tab

The Usage tab charts everything recorded in `usage_log.jsonl`, so the lab can see what the
shared API account is spending:

- **Total calls, tokens in, tokens out, estimated cost** across the whole log
- **Cumulative cost over time** — a running total by day
- **By model** and **by call type** — where the spend is going (chat, drafting, extraction, …)
- **Raw log data** — the full table, downloadable as CSV

Costs are estimates calculated from published per-token rates; the authoritative figure is
always your Anthropic Console. For the sidebar counter and the log format, see
**Session usage tracker** below.

---

## Advanced settings

Open the **Advanced settings** expander in the sidebar to fine-tune every call.

| Setting | Effect |
|---|---|
| **Claude model** | Haiku 4.5: fast, lower cost. Sonnet 5: recommended default. Opus 5: highest quality, higher cost. |
| **Temperature** (Haiku only — Sonnet 5 and Opus 5 do not accept the setting) | 0.0–0.3 for precise factual Q&A. 0.4–0.6 for grant drafting. 0.7–1.0 for creative outreach writing. |
| **Reasoning depth** (Sonnet 5 / Opus 5) | How much the model reasons before answering. Low for factual questions; Medium (default) for most work; High for grant drafting and gap maps. Reasoning is billed as output. |
| **Passages retrieved** | Controls how many passages are sent for Draft and Extract. More = broader coverage, higher cost. |
| **Max draft length** | Maximum tokens in generated drafts. Raise to 4 096+ for long grant sections. |
| **Show retrieval scores** | Displays cosine similarity (0–1) next to each source chunk in Chat answers. |

### Session usage tracker

The usage tracker measures **Anthropic API credit consumption** — the pay-per-use charges billed to the lab's API account. This is entirely separate from any Claude.ai or Pro subscription; the app uses the API directly and is billed by the token regardless of what subscription plan exists.

After your first API call, an expander appears at the bottom of the sidebar. It shows two sections:

**This session** (resets when the app server restarts):
- **Tokens in / Tokens out** — cumulative counts for all calls in the current session
- **Est. cost** — estimated USD cost at published Anthropic pricing
- **Reset session counter** — clears the in-memory session tally only; does not affect the log file

**All time** (persistent across restarts):
- Cumulative totals and cost since the log file was created
- Total call count

Pricing shown: Haiku 4.5 $1.00/$5.00 · Sonnet 5 $3.00/$15.00 · Opus 5 $5.00/$25.00 per million input/output tokens. Verify current rates at [console.anthropic.com](https://console.anthropic.com).

#### The log file

Every API call is appended to `usage_log.jsonl` in the project root. Each line is a JSON record:

```json
{"ts": "2026-05-07T14:23:01", "fn": "query", "model": "claude-sonnet-5", "input": 3241, "output": 287}
```

Fields: `ts` (ISO timestamp), `fn` (call type: `query`, `draft`, `extract_themes`, `annotate`, `extract_fields`, `refine`, `write_assist`, `summarise`), `model`, `input` and `output` token counts.

This file is never overwritten — only appended to. You can download it and analyse it in any tool that reads JSON Lines (Python, R, Excel via Power Query). For example, to chart cumulative cost over time in Python:

```python
import json, pandas as pd
df = pd.read_json("usage_log.jsonl", lines=True)
df["cost"] = df["input"] / 1e6 * 3.0 + df["output"] / 1e6 * 15.0  # Sonnet rates
df["ts"] = pd.to_datetime(df["ts"])
df.set_index("ts")["cost"].cumsum().plot(title="Cumulative API cost")
```

#### Setting details

- **Claude model** — All three models read the same retrieved passages and follow the same instructions; the difference is reasoning quality and cost. Haiku 4.5 is roughly 5× cheaper than Opus 5 and responds in seconds — well suited to quick factual queries, annotation runs, and field extraction where the task is reading comprehension rather than synthesis. Sonnet 5 is the recommended default: it handles nuanced academic writing, complex gap maps, and multi-source synthesis well at a reasonable cost. Opus 5 is meaningfully better at weighing ambiguous or conflicting evidence, constructing rigorous arguments, and producing polished prose — worth using for final grant sections or a Response to Reviewers letter where quality justifies the cost.

- **Reasoning depth** — Sonnet 5 and Opus 5 reason before they answer, and that reasoning is billed as output tokens, so the setting is a direct cost and speed dial. **Low** is genuinely strong on these models and is a good default for factual questions over the literature. **Medium** (the app default) suits most drafting. **High** is worth it where the task is weighing conflicting evidence — gap maps, Response to Reviewers, final grant sections. Haiku 4.5 does not reason and ignores the setting, which is why the control disappears when you select it.

- **Temperature** — Controls how deterministically the model samples from its next-token probability distribution. At 0, the model always picks the highest-probability token, producing consistent and reproducible output. As temperature rises, lower-probability tokens are sampled more often, introducing variation. For research Q&A, 0.0–0.3 is best: the model should draw the same logical deductions from the same evidence every time. For grant drafting, 0.3–0.5 adds enough variation to avoid stilted phrasing without risking factual drift. Above 0.7 the model may subtly rephrase findings in ways that shift their meaning — useful for creative outreach writing, but a liability for any text that will be cited or submitted.

- **Passages retrieved (K)** — Your question is encoded as a vector and ChromaDB returns the K closest passages by cosine distance. More passages = broader literature coverage, but also more noise: irrelevant chunks dilute the answer and consume token budget. The default of 12 for drafting balances coverage against focus. Raise to 20–25 for gap maps spanning the whole literature, or when the answer to a broad question draws on many papers. Lower to 5–8 for highly specific factual questions where you want the tightest possible match.

- **Max draft length** — Sets the maximum token budget Claude is allowed to spend on the output. Approximately 1 token = 0.75 words, so: 2 048 tokens ≈ 1 500 words (a developed section), 4 096 ≈ 3 000 words (a full grant background), 8 192 ≈ 6 000 words (very long sections or multi-part gap maps). If a draft ends abruptly mid-sentence, the output hit this limit — raise the slider and regenerate. Note that higher limits increase API cost proportionally, since you pay for output tokens.

- **Show retrieval scores** — Displays the cosine similarity between your query embedding and each retrieved passage (0.00–1.00, where 1.00 = identical direction in embedding space). In practice: scores above 0.65 indicate strong topical overlap; 0.45–0.65 is a reasonable match; below 0.45 the passage may be only peripherally relevant. If all retrieved scores are low and the answer is thin, the relevant papers likely have not been ingested yet — or rephrase the question using terminology closer to the language of the literature (e.g., "eddy covariance" rather than "carbon flux measurement").

### Choosing a model

- **Day-to-day Q&A and exploration:** Haiku 4.5 — fast and inexpensive
- **Standard drafting:** Sonnet 5 — the recommended default
- **Final grant sections or complex gap maps:** Opus 5 at High reasoning depth — maximum reasoning quality

### Research memory

The system automatically summarises each conversation when you start a new chat (if the session contains at least 2 exchanges). These summaries are stored locally and silently injected as prior context in future queries — so Claude knows what research threads you've been pursuing. View and clear summaries in the **Research memory** expander in the sidebar.

---

## Privacy and data

### What stays on the lab server
- All PDF files
- The search index (ChromaDB vector database)
- Chat history, annotations, extractions, and theme data
- Zotero metadata

### What is sent to Anthropic
When you submit a question or draft request:
- Your question or prompt
- The text of the most relevant passages retrieved (~5–12 excerpts of ~500 words each)

**No files, no embeddings, no chat history, and no metadata are sent.** Only the text needed to generate your answer leaves the server.

### Sensitive documents
For papers under embargo or grant proposals in preparation, consider whether sending passage text to Anthropic's API servers is acceptable before adding them to the Zotero collection. Published open-access papers carry no such concern.

---

## What makes answers reliable

- **Grounded responses:** Claude is instructed to answer only from the retrieved passages, not from general training knowledge
- **Mandatory citations:** Every factual claim is cited to a specific passage and page. Uncited claims are a sign something has gone wrong
- **No hallucinated references:** The citations shown are the actual passages retrieved — open "Source chunks retrieved" to read the raw text
- **Gap flagging:** If the literature is insufficient, drafts say so explicitly rather than fabricating content
- **Verification path:** Citation → source chunk → original PDF. Every claim is traceable

---

## Common questions

**Why didn't it find a paper I know exists?**
Check the Documents tab. If it's missing, it hasn't been ingested yet — ask the lab administrator to add it to Zotero and run a sync.

**The answer seems wrong or oversimplified.**
Open the source chunks and read the raw passages. The answer is only as good as what was retrieved. Relevant papers may not yet be ingested, or the question may need to be rephrased more specifically.

**Can I search across multiple projects?**
Yes — use the "Also search in" multiselect in the Chat tab, or "Also draw from" in the Draft tab.

**How do I get a longer draft?**
Raise the **Max draft length** slider in Advanced settings to 4 096 or higher before generating.

**The extraction returned errors for some papers.**
This usually means the field wasn't mentioned in that paper's text, or the paper hit the API rate limit. Wait a minute and re-run. The "—" result means the field was not found; "parse error" means Claude's response couldn't be parsed (rare).

**Is my conversation saved?**
Yes. Conversations are automatically saved after each response and accessible in the sidebar. The system also saves a summary to research memory when you start a new chat.

**Does the Write tab save my draft if I close the browser?**
Not automatically — click **Save draft** to write it to disk. After that, it reloads automatically. Version snapshots are saved before each suggestion request, so you always have a recent backup even without clicking Save draft.

**The Write tab shows a cached result and I want a fresh response.**
Click **↺ Refresh** to clear the cache and trigger a new API call.

**How is the Write tab different from the Draft tab?**
Draft tab synthesises from the literature to generate a new section from scratch. Write tab reads *your existing text* and suggests ways to improve, extend, or cite it. Use Draft tab to get a first draft; use Write tab to refine and strengthen it.
