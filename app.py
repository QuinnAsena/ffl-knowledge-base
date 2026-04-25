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

from query import (
    DRAFT_SYSTEM_PROMPT,
    GAP_MAP_SYSTEM_PROMPT,
    OUTREACH_SYSTEM_PROMPT,
    PAPER_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    annotate_paper,
    draft,
    draft_multi,
    extract_fields_from_paper,
    extract_themes,
    query,
    query_multi,
    refine_draft,
)

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


# ── Theme graph helpers ───────────────────────────────────────────────────────


def _themes_path(project: str) -> Path:
    return Path("projects") / project / "themes.json"


def _load_themes(project: str) -> dict:
    p = _themes_path(project)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_themes(project: str, themes: dict) -> None:
    p = _themes_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(themes, indent=2), encoding="utf-8")


# ── Annotation persistence helpers ────────────────────────────────────────────


def _annotations_path(project: str) -> Path:
    return Path("projects") / project / "annotations.json"


def _load_annotations(project: str) -> dict:
    p = _annotations_path(project)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_annotations(project: str, annotations: dict) -> None:
    p = _annotations_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(annotations, indent=2), encoding="utf-8")


# ── Extraction persistence helpers ────────────────────────────────────────────


def _extraction_path(project: str) -> Path:
    return Path("projects") / project / "last_extraction.json"


def _load_extraction(project: str) -> dict | None:
    p = _extraction_path(project)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _save_extraction(project: str, fields: list, results: list) -> None:
    p = _extraction_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"fields": fields, "results": results}, indent=2), encoding="utf-8")


def _build_theme_graph(docs: list[dict], themes_map: dict) -> str:
    from pyvis.network import Network

    net = Network(height="640px", width="100%", bgcolor="#0f172a", font_color="#e2e8f0")
    net.set_options("""{
        "physics": {
            "barnesHut": {
                "gravitationalConstant": -9000,
                "centralGravity": 0.12,
                "springLength": 300,
                "springConstant": 0.025,
                "damping": 0.88,
                "avoidOverlap": 0.7
            },
            "maxVelocity": 60,
            "minVelocity": 0.5,
            "timestep": 0.4
        },
        "nodes": {
            "borderWidth": 1,
            "borderWidthSelected": 3,
            "shadow": {"enabled": true, "color": "rgba(0,0,0,0.6)", "size": 10, "x": 2, "y": 3}
        },
        "edges": {
            "smooth": {"enabled": true, "type": "continuous", "roundness": 0.45},
            "hoverWidth": 2.5
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "navigationButtons": true,
            "zoomView": true
        }
    }""")

    # Count how many papers share each theme (for node sizing)
    theme_degree: dict[str, int] = {}
    for themes in themes_map.values():
        for t in themes:
            theme_degree[t] = theme_degree.get(t, 0) + 1

    doc_map = {d["filename"]: d for d in docs}

    for fname, themes in themes_map.items():
        if not themes:
            continue
        doc = doc_map.get(fname, {})
        label = (
            f"{doc['author_str']} ({doc['year']})"
            if doc.get("author_str") and doc.get("year")
            else fname[:28]
        )
        title_text = doc.get("title") or fname
        net.add_node(
            fname,
            label=label,
            color={
                "background": "#1d4ed8",
                "border": "#93c5fd",
                "highlight": {"background": "#3b82f6", "border": "#bfdbfe"},
                "hover": {"background": "#2563eb", "border": "#bfdbfe"},
            },
            size=26,
            shape="dot",
            font={"size": 12, "color": "#e2e8f0"},
            title=f"<div style='font-family:sans-serif;max-width:240px'><b>{title_text}</b><br><i style='color:#94a3b8'>{label}</i></div>",
        )

    for theme, degree in theme_degree.items():
        node_size = 13 + min(degree * 5, 22)
        net.add_node(
            f"__t__{theme}",
            label=theme,
            color={
                "background": "#b45309",
                "border": "#fcd34d",
                "highlight": {"background": "#f59e0b", "border": "#fde68a"},
                "hover": {"background": "#d97706", "border": "#fde68a"},
            },
            size=node_size,
            shape="ellipse",
            font={"size": 11, "color": "#fef3c7"},
            title=f"<div style='font-family:sans-serif'><b style='color:#fcd34d'>{theme}</b><br><span style='color:#94a3b8'>Shared by {degree} paper{'s' if degree != 1 else ''}</span></div>",
        )

    for fname, themes in themes_map.items():
        if not themes or fname not in doc_map:
            continue
        for theme in themes:
            net.add_edge(
                fname,
                f"__t__{theme}",
                color={"color": "#334155", "highlight": "#64748b", "hover": "#94a3b8"},
                width=1.5,
            )

    return net.generate_html()


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

    st.markdown("---")
    with st.expander("Advanced settings"):
        retrieval_k = st.slider(
            "Passages retrieved (Draft & Extract)",
            min_value=5,
            max_value=25,
            value=12,
            step=1,
            help=(
                "How many passages from the literature are sent to Claude when drafting or "
                "extracting. More passages = broader coverage but slower and higher API cost. "
                "Chat queries always use 5."
            ),
        )

# ── Session state ─────────────────────────────────────────────────────────────

messages_key = f"messages_{selected_project}"
file_key = f"history_file_{selected_project}"

if messages_key not in st.session_state:
    st.session_state[messages_key] = []

messages = st.session_state[messages_key]

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_chat, tab_docs, tab_draft, tab_extract, tab_graph = st.tabs(
    ["Chat", "Documents", "Draft", "Extract", "Graph"]
)

# ── Chat tab ──────────────────────────────────────────────────────────────────

with tab_chat:
    other_projects_chat = [p for p in projects if p != selected_project]
    if other_projects_chat:
        extra_chat = st.multiselect(
            "Also search in",
            other_projects_chat,
            default=[],
            help="Pool literature from additional projects for this conversation.",
            key="extra_chat",
        )
    else:
        extra_chat = []
    active_projects_chat = [selected_project] + extra_chat

    if len(active_projects_chat) > 1:
        st.caption(f"Searching across: {', '.join(active_projects_chat)}")

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
                    if len(active_projects_chat) > 1:
                        answer, citations = query_multi(active_projects_chat, prompt)
                    else:
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

    # Load persisted annotations into session state once per project
    _ann_loaded_key = f"_ann_loaded_{selected_project}"
    if _ann_loaded_key not in st.session_state:
        for fname, ann_text in _load_annotations(selected_project).items():
            k = f"ann_{selected_project}_{fname}"
            if k not in st.session_state:
                st.session_state[k] = ann_text
        st.session_state[_ann_loaded_key] = True

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

                # ── Annotation ────────────────────────────────────────────
                ann_key = f"ann_{selected_project}_{doc['filename']}"
                if ann_key in st.session_state:
                    st.markdown("---")
                    st.markdown(st.session_state[ann_key])
                if st.button("Generate annotation", key=f"annbtn_{doc['filename']}"):
                    with st.spinner("Generating annotation…"):
                        try:
                            annotation = annotate_paper(selected_project, doc["filename"])
                            st.session_state[ann_key] = annotation
                            saved = _load_annotations(selected_project)
                            saved[doc["filename"]] = annotation
                            _save_annotations(selected_project, saved)
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

        st.markdown("---")

        # Download all annotations that have been generated this session
        ann_prefix = f"ann_{selected_project}_"
        existing_anns = {
            k[len(ann_prefix):]: v
            for k, v in st.session_state.items()
            if k.startswith(ann_prefix)
        }
        if existing_anns:
            ann_md = "\n\n---\n\n".join(
                f"## {fname}\n\n{ann}" for fname, ann in existing_anns.items()
            )
            st.download_button(
                "Download all annotations as .md",
                data=ann_md,
                file_name=f"{selected_project}_annotations.md",
                mime="text/markdown",
            )

        st.markdown(
            "To add more papers: add them to your Zotero collection, then run "
            f"`python ingest.py --project {selected_project} --zotero`"
        )

# ── Draft tab ─────────────────────────────────────────────────────────────────

WRITING_MODES = {
    "Grant Proposal": {
        "system_prompt": DRAFT_SYSTEM_PROMPT,
        "caption": (
            "Formal academic prose for grant applications. "
            "Every claim is cited; literature gaps are flagged explicitly."
        ),
        "sections": [
            "Background",
            "Significance & Innovation",
            "Specific Aims / Objectives",
            "Approach / Methods",
            "Preliminary Data",
            "Custom",
        ],
    },
    "Academic Paper": {
        "system_prompt": PAPER_SYSTEM_PROMPT,
        "caption": (
            "Peer-reviewed manuscript style. "
            "Hedged language, IMRaD structure, past tense for methods and results."
        ),
        "sections": [
            "Introduction",
            "Methods",
            "Results",
            "Discussion",
            "Abstract",
            "Conclusion",
            "Custom",
        ],
    },
    "Outreach & Communication": {
        "system_prompt": OUTREACH_SYSTEM_PROMPT,
        "caption": (
            "Plain language for non-specialist audiences. "
            "No jargon, active voice — still grounded in the literature."
        ),
        "sections": [
            "Plain-language summary",
            "Press release",
            "Blog post",
            "Social media post",
            "Newsletter",
            "FAQ",
            "Custom",
        ],
    },
    "Response to Reviewers": {
        "system_prompt": REVIEWER_SYSTEM_PROMPT,
        "caption": (
            "Draft point-by-point responses to peer reviewer comments, "
            "grounded in your literature."
        ),
        "sections": [
            "Full response letter",
            "Response to a single comment",
            "Cover letter to editor",
            "Custom",
        ],
    },
    "Research Gap Map": {
        "system_prompt": GAP_MAP_SYSTEM_PROMPT,
        "caption": (
            "Synthesise what is well established, contested, and missing "
            "across the ingested literature."
        ),
        "sections": [
            "Full gap analysis",
            "Methodological gaps",
            "Geographic / spatial gaps",
            "Temporal gaps",
            "Conceptual / theoretical gaps",
            "Custom",
        ],
    },
}

with tab_draft:
    st.header(f"Draft — {selected_project}")

    other_projects_draft = [p for p in projects if p != selected_project]
    if other_projects_draft:
        extra_draft = st.multiselect(
            "Also draw from",
            other_projects_draft,
            default=[],
            help="Include literature from additional projects when generating this draft.",
            key="extra_draft",
        )
    else:
        extra_draft = []
    active_projects_draft = [selected_project] + extra_draft

    mode_name = st.radio(
        "Writing mode",
        list(WRITING_MODES.keys()),
        horizontal=True,
    )
    mode = WRITING_MODES[mode_name]
    st.caption(mode["caption"])
    st.markdown("---")

    section_type = st.selectbox("Section type", mode["sections"])

    if mode_name == "Response to Reviewers":
        text_label = "Paste reviewer comments here"
        text_placeholder = "Paste the reviewer comments you want to respond to…"
    else:
        text_label = "What should this section cover?"
        text_placeholder = f"Describe what to write for the {section_type} section…"

    draft_prompt = st.text_area(
        text_label,
        height=140,
        placeholder=text_placeholder,
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
                    if len(active_projects_draft) > 1:
                        draft_text, draft_citations = draft_multi(
                            active_projects_draft, full_prompt, mode["system_prompt"], retrieval_k
                        )
                    else:
                        draft_text, draft_citations = draft(
                            selected_project, full_prompt, mode["system_prompt"], retrieval_k
                        )
                except ValueError as e:
                    st.error(str(e))
                    draft_text, draft_citations = None, []
                except Exception as exc:
                    st.error(f"An error occurred: {exc}")
                    draft_text, draft_citations = None, []

            if draft_text:
                st.session_state[f"draft_text_{selected_project}"] = draft_text
                st.session_state[f"draft_citations_{selected_project}"] = draft_citations
                st.session_state[f"draft_section_{selected_project}"] = section_type

    # ── Display current draft (persists across refine cycles) ─────────────────
    draft_key = f"draft_text_{selected_project}"
    if draft_key in st.session_state:
        current_draft = st.session_state[draft_key]
        current_citations = st.session_state.get(f"draft_citations_{selected_project}", [])
        current_section = st.session_state.get(f"draft_section_{selected_project}", section_type)

        st.markdown("---")
        st.markdown(current_draft)

        if current_citations:
            with st.expander("Source chunks retrieved", expanded=False):
                for ref in current_citations:
                    st.markdown(f"- {ref}")

        download_content = (
            f"# {current_section}\n\n{current_draft}\n\n---\n\n"
            "## Sources\n\n"
            + "\n".join(f"- {r}" for r in current_citations)
        )
        st.download_button(
            label="Download as .md",
            data=download_content,
            file_name=f"{selected_project}_{current_section.replace(' ', '_').replace('/', '-')}.md",
            mime="text/markdown",
            key="draft_download",
        )

        # ── Iterative refinement ──────────────────────────────────────────────
        st.markdown("---")
        st.markdown("**Refine this draft**")
        refine_instruction = st.text_input(
            "Revision instruction",
            placeholder="e.g. Make the third paragraph more concise. Add more on remote sensing methods.",
            key="refine_input",
        )
        refine_clicked = st.button("Revise", disabled=not refine_instruction)

        if refine_clicked and refine_instruction:
            with st.spinner("Revising draft…"):
                try:
                    revised = refine_draft(current_draft, refine_instruction)
                    st.session_state[f"draft_text_{selected_project}"] = revised
                    st.rerun()
                except Exception as exc:
                    st.error(f"Revision failed: {exc}")

# ── Extract tab ───────────────────────────────────────────────────────────────

with tab_extract:
    st.header(f"Structured extraction — {selected_project}")

    # Load persisted extraction into session state once per project
    _ext_loaded_key = f"_ext_loaded_{selected_project}"
    if _ext_loaded_key not in st.session_state:
        saved_ext = _load_extraction(selected_project)
        if saved_ext and f"extract_{selected_project}" not in st.session_state:
            st.session_state[f"extract_{selected_project}"] = saved_ext["results"]
        st.session_state[_ext_loaded_key] = True

    st.caption(
        "Extract specific fields from every ingested paper into a table. "
        "Useful for systematic reviews and meta-analyses."
    )

    fields_input = st.text_input(
        "Fields to extract (comma-separated)",
        placeholder="e.g. study region, sample size, key method, main finding, limitations",
    )
    fields = [f.strip() for f in fields_input.split(",") if f.strip()] if fields_input else []

    extract_clicked = st.button(
        "Extract from all papers", type="primary", disabled=not fields
    )

    if extract_clicked and fields:
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY is not set. Add it to your `.env` file and restart.")
        else:
            extract_docs = get_document_index(selected_project)
            if not extract_docs:
                st.warning("No documents ingested yet.")
            else:
                import time as _time
                n = len(extract_docs)
                st.caption(
                    f"Processing {n} paper(s) — allow ~{n * 8} seconds "
                    f"(API rate limit: brief pause between each paper)."
                )
                results = []
                progress = st.progress(0, text="Starting extraction…")
                for i, doc in enumerate(extract_docs):
                    progress.progress(i / n, text=f"Processing {doc['filename']}…")
                    try:
                        extracted = extract_fields_from_paper(
                            selected_project, doc["filename"], fields
                        )
                    except Exception as e:
                        extracted = {f: f"ERROR: {type(e).__name__}: {e}" for f in fields}
                    if i < n - 1:
                        _time.sleep(7)
                    ref = (
                        f"{doc['author_str']} ({doc['year']})"
                        if doc["author_str"] and doc["year"]
                        else doc["filename"]
                    )
                    results.append({"Paper": ref, **extracted})
                progress.progress(1.0, text="Done.")
                st.session_state[f"extract_{selected_project}"] = results
                _save_extraction(selected_project, fields, results)

    if f"extract_{selected_project}" in st.session_state:
        results = st.session_state[f"extract_{selected_project}"]
        st.dataframe(results, use_container_width=True)

        if results:
            headers = list(results[0].keys())
            csv_rows = [",".join(f'"{h}"' for h in headers)]
            for row in results:
                csv_rows.append(",".join(f'"{str(row.get(h, ""))}"' for h in headers))
            st.download_button(
                "Download as CSV",
                data="\n".join(csv_rows),
                file_name=f"{selected_project}_extraction.csv",
                mime="text/csv",
            )

# ── Graph tab ─────────────────────────────────────────────────────────────────

with tab_graph:
    import time as _time_g

    st.header(f"Theme map — {selected_project}")
    st.caption(
        "Papers are blue nodes; shared themes are amber nodes. "
        "Drag nodes to explore, hover for details."
    )

    graph_docs = get_document_index(selected_project)
    themes_map = _load_themes(selected_project)

    tagged = [d for d in graph_docs if d["filename"] in themes_map]
    untagged = [d for d in graph_docs if d["filename"] not in themes_map]

    col_a, col_b = st.columns(2)
    col_a.metric("Papers tagged", len(tagged))
    col_b.metric("Awaiting tagging", len(untagged))

    tag_new = st.button(
        f"Tag {len(untagged)} unprocessed paper(s)" if untagged else "All papers tagged",
        disabled=not untagged,
        type="primary",
    )
    regen_all = st.button("Re-tag all papers (overwrites existing)", type="secondary")

    papers_to_tag = graph_docs if regen_all else (untagged if tag_new else [])

    if papers_to_tag:
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY is not set. Add it to your `.env` file and restart.")
        else:
            n = len(papers_to_tag)
            st.caption(f"Tagging {n} paper(s) — allow ~{n * 8} seconds.")
            prog = st.progress(0, text="Starting…")
            for i, doc in enumerate(papers_to_tag):
                prog.progress(i / n, text=f"Tagging {doc['filename']}…")
                try:
                    themes = extract_themes(selected_project, doc["filename"])
                    themes_map[doc["filename"]] = themes
                except Exception as e:
                    themes_map[doc["filename"]] = []
                    st.warning(f"Could not tag {doc['filename']}: {e}")
                if i < n - 1:
                    _time_g.sleep(7)
            prog.progress(1.0, text="Done.")
            _save_themes(selected_project, themes_map)
            st.rerun()

    if themes_map and any(themes_map.values()):
        try:
            html = _build_theme_graph(graph_docs, themes_map)
            st.components.v1.html(html, height=660, scrolling=False)
        except ImportError:
            st.error(
                "pyvis is not installed. Run `pip install pyvis==0.3.2` "
                "inside your virtual environment and restart Streamlit."
            )
    elif graph_docs:
        st.info("Click **Tag unprocessed papers** above to generate the theme map.")
