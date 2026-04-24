"""
app.py — Streamlit web UI for the Lab AI RAG system.

Run:
    streamlit run app.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import chromadb
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from query import draft, query

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="FFL Knowledge Base",
    page_icon="🔬",
    layout="wide",
)

# ── History helpers ───────────────────────────────────────────────────────────


def history_dir(project: str) -> Path:
    return Path("projects") / project / "history"


def save_conversation(project: str, messages: list, file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "project": project,
        "saved_at": datetime.now().isoformat(),
        "messages": messages,
    }
    file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_conversation(file_path: Path) -> list:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    return data.get("messages", [])


def list_conversations(project: str) -> list[Path]:
    d = history_dir(project)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"), reverse=True)


def format_history_label(file_path: Path, messages: list) -> str:
    try:
        ts = datetime.strptime(file_path.stem, "%Y-%m-%d_%H-%M-%S")
        date_str = ts.strftime("%b %d, %H:%M")
    except ValueError:
        date_str = file_path.stem
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    preview = (first_user[:55] + "…") if len(first_user) > 55 else first_user
    return f"{date_str} — {preview}" if preview else date_str


# ── Document index helpers ────────────────────────────────────────────────────


def get_document_index(project: str) -> list[dict]:
    """
    Read ChromaDB metadata to build a per-document summary for the project.
    Returns a list of dicts sorted by author/year.
    """
    try:
        client = chromadb.PersistentClient(path="chroma_db")
        if project not in client.list_collections():
            return []
        collection = client.get_collection(project)
        if collection.count() == 0:
            return []

        # Pull all metadata (no documents/embeddings — fast)
        result = collection.get(include=["metadatas"])
        metadatas = result["metadatas"]

    except Exception:
        return []

    # Aggregate chunks by filename
    docs: dict[str, dict] = {}
    for meta in metadatas:
        fname = meta.get("filename", "unknown")
        if fname not in docs:
            docs[fname] = {
                "filename": fname,
                "title": meta.get("title", ""),
                "author_str": meta.get("author_str", ""),
                "year": meta.get("year", ""),
                "doi": meta.get("doi", ""),
                "chunks": 0,
                "pages": set(),
            }
        docs[fname]["chunks"] += 1
        docs[fname]["pages"].add(meta.get("page", 0))

    rows = []
    for d in docs.values():
        rows.append({**d, "page_count": len(d["pages"])})

    # Sort: Zotero items (have author) first by year desc, then plain filenames
    rows.sort(key=lambda r: (0 if r["author_str"] else 1, -(int(r["year"]) if r["year"].isdigit() else 0)))
    return rows


# ── Project discovery ─────────────────────────────────────────────────────────


def get_projects() -> list[str]:
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []
    return sorted(
        p.name for p in projects_dir.iterdir() if p.is_dir() and (p / "pdfs").exists()
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("FFL Knowledge Base")
    st.caption("Literature search and synthesis")

    projects = get_projects()
    if not projects:
        st.warning(
            "No projects found. Create a folder under `projects/` with a `pdfs/` "
            "subfolder, add PDFs, then run `python ingest.py --project <name>`."
        )
        st.stop()

    selected_project = st.selectbox("Project", projects)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("New chat", use_container_width=True):
            st.session_state[f"messages_{selected_project}"] = []
            st.session_state.pop(f"history_file_{selected_project}", None)
            st.rerun()
    with col2:
        msg_count = len(st.session_state.get(f"messages_{selected_project}", []))
        st.button("Saved", disabled=True, use_container_width=True,
                  help="Conversations are auto-saved after each response.")

    past = list_conversations(selected_project)
    if past:
        st.markdown("**Past conversations**")
        for hist_path in past[:15]:
            try:
                hist_messages = load_conversation(hist_path)
            except Exception:
                continue
            label = format_history_label(hist_path, hist_messages)
            if st.button(label, key=str(hist_path), use_container_width=True):
                st.session_state[f"messages_{selected_project}"] = hist_messages
                st.session_state[f"history_file_{selected_project}"] = hist_path
                st.rerun()

    st.markdown("---")
    st.markdown(
        "**Sync documents**\n"
        "```\npython ingest.py \\\n  --project {name} --zotero\n```"
    )

# ── Session state ─────────────────────────────────────────────────────────────

messages_key = f"messages_{selected_project}"
file_key = f"history_file_{selected_project}"

if messages_key not in st.session_state:
    st.session_state[messages_key] = []

messages = st.session_state[messages_key]

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_chat, tab_docs, tab_draft = st.tabs(["Chat", "Documents", "Draft"])

# ── Chat tab ──────────────────────────────────────────────────────────────────

with tab_chat:
    st.header(f"Project: {selected_project}")

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("citations"):
                with st.expander("Source chunks retrieved", expanded=False):
                    for ref in msg["citations"]:
                        st.markdown(f"- {ref}")

    if prompt := st.chat_input("Ask a question about the literature…"):
        messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY is not set. Add it to your `.env` file and restart.")
            st.stop()

        with st.chat_message("assistant"):
            with st.spinner("Searching documents and generating answer…"):
                try:
                    answer, citations = query(selected_project, prompt)
                except ValueError as e:
                    st.error(str(e))
                    st.stop()
                except Exception as exc:
                    st.error(f"An error occurred: {exc}")
                    st.stop()

            st.markdown(answer)
            if citations:
                with st.expander("Source chunks retrieved", expanded=False):
                    for ref in citations:
                        st.markdown(f"- {ref}")

        messages.append({"role": "assistant", "content": answer, "citations": citations})

        if file_key not in st.session_state:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            st.session_state[file_key] = history_dir(selected_project) / f"{timestamp}.json"

        save_conversation(selected_project, messages, st.session_state[file_key])

# ── Documents tab ─────────────────────────────────────────────────────────────

with tab_docs:
    st.header(f"Ingested documents — {selected_project}")

    docs = get_document_index(selected_project)

    if not docs:
        st.info(
            f"No documents ingested yet for project **{selected_project}**. "
            f"Run `python ingest.py --project {selected_project} --zotero` to sync from Zotero."
        )
    else:
        st.caption(f"{len(docs)} document(s) · {sum(d['chunks'] for d in docs)} total chunks")
        st.markdown("---")

        for doc in docs:
            has_meta = bool(doc["author_str"] and doc["year"])

            if has_meta:
                title = doc["title"] or doc["filename"]
                label = f"**{doc['author_str']} ({doc['year']})** — {title}"
            else:
                label = f"**{doc['filename']}**"

            with st.expander(label, expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Chunks", doc["chunks"])
                col2.metric("Pages", doc["page_count"])
                col3.metric("Year", doc["year"] or "—")

                if doc["title"]:
                    st.markdown(f"**Title:** {doc['title']}")
                if doc["author_str"]:
                    st.markdown(f"**Authors:** {doc['author_str']}")
                if doc["doi"]:
                    st.markdown(f"**DOI:** [{doc['doi']}](https://doi.org/{doc['doi']})")
                st.markdown(f"**File:** `{doc['filename']}`")

        st.markdown("---")
        st.markdown(
            "To add more papers: add them to your Zotero collection, then run "
            f"`python ingest.py --project {selected_project} --zotero`"
        )

# ── Draft tab ─────────────────────────────────────────────────────────────────

SECTION_TYPES = [
    "Background",
    "Significance & Innovation",
    "Specific Aims / Objectives",
    "Approach / Methods",
    "Preliminary Data",
    "Custom",
]

with tab_draft:
    st.header(f"Draft a grant proposal section — {selected_project}")
    st.caption(
        "Retrieves up to 12 literature chunks and writes academic prose with inline citations. "
        "Every claim is grounded in your ingested documents."
    )

    section_type = st.selectbox("Section type", SECTION_TYPES)

    placeholder = (
        f"Describe what to write for the {section_type} section…\n\n"
        "Example: 'Write a background paragraph on deep learning approaches for wildfire risk "
        "prediction, focusing on CNN and LSTM methods and their limitations.'"
    )
    draft_prompt = st.text_area(
        "What should this section cover?",
        height=140,
        placeholder=placeholder,
    )

    if section_type != "Custom":
        full_prompt = f"Write the {section_type} section. {draft_prompt}".strip()
    else:
        full_prompt = draft_prompt.strip()

    generate_clicked = st.button(
        "Generate draft", type="primary", disabled=not full_prompt
    )

    if generate_clicked and full_prompt:
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY is not set. Add it to your `.env` file and restart.")
        else:
            with st.spinner("Retrieving literature and drafting section…"):
                try:
                    draft_text, draft_citations = draft(selected_project, full_prompt)
                except ValueError as e:
                    st.error(str(e))
                    draft_text, draft_citations = None, []
                except Exception as exc:
                    st.error(f"An error occurred: {exc}")
                    draft_text, draft_citations = None, []

            if draft_text:
                st.markdown("---")
                st.markdown(draft_text)

                if draft_citations:
                    with st.expander("Source chunks retrieved", expanded=False):
                        for ref in draft_citations:
                            st.markdown(f"- {ref}")

                download_content = (
                    f"# {section_type}\n\n{draft_text}\n\n---\n\n"
                    "## Sources\n\n"
                    + "\n".join(f"- {r}" for r in draft_citations)
                )
                st.download_button(
                    label="Download as .md",
                    data=download_content,
                    file_name=f"{selected_project}_{section_type.replace(' ', '_').replace('/', '-')}.md",
                    mime="text/markdown",
                )
