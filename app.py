"""
app.py — Streamlit web UI for the Lab AI RAG system.

Run:
    streamlit run app.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import chromadb
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from query import (
    CHROMA_DIR,
    DRAFT_SYSTEM_PROMPT,
    USAGE_LOG,
    GAP_MAP_SYSTEM_PROMPT,
    OUTREACH_SYSTEM_PROMPT,
    PAPER_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    annotate_paper,
    assist_writing,
    assist_writing_multi,
    clear_session_usage,
    draft,
    draft_multi,
    extract_fields_from_paper,
    extract_themes,
    get_session_usage,
    query,
    query_multi,
    refine_draft,
    summarise_conversation,
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
        client = chromadb.PersistentClient(path=CHROMA_DIR)
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
        rows.append({
            "filename":   d["filename"],
            "title":      d["title"],
            "author_str": d["author_str"],
            "year":       d["year"],
            "doi":        d["doi"],
            "chunks":     d["chunks"],
            "page_count": len(d["pages"]),
        })

    # Sort: Zotero items (have author) first by year desc, then plain filenames
    rows.sort(key=lambda r: (
        0 if r["author_str"] else 1,
        -(int(r["year"]) if str(r.get("year") or "").isdigit() else 0),
    ))
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


# ── Pandoc export helper ──────────────────────────────────────────────────────


@st.cache_resource
def _pandoc_available() -> bool:
    try:
        result = subprocess.run(
            ["pandoc", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_pandoc(markdown_text: str, fmt: str) -> bytes:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "draft.md"
        out = Path(tmp) / f"draft.{fmt}"
        src.write_text(markdown_text, encoding="utf-8")
        subprocess.run(
            ["pandoc", str(src), "-o", str(out)],
            check=True, capture_output=True,
        )
        return out.read_bytes()


# ── Write tab helpers ─────────────────────────────────────────────────────────


def _write_draft_path(project: str) -> Path:
    return Path("projects") / project / "write_draft.md"


def _write_notes_path(project: str) -> Path:
    return Path("projects") / project / "write_notes.md"


def _write_context_path(project: str) -> Path:
    return Path("projects") / project / "write_context.md"


def _write_config_path(project: str) -> Path:
    return Path("projects") / project / "write_config.json"


def _load_write_config(project: str) -> dict:
    p = _write_config_path(project)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_write_config(project: str, config: dict) -> None:
    p = _write_config_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _append_to_notes(notes_path: Path, mode: str, response: str, draft_snippet: str) -> None:
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    snippet = draft_snippet.strip()[:200].replace("\n", " ")
    entry = (
        f"\n## {mode} — {ts}\n\n"
        + (f"> *Draft opening: \"{snippet}…\"*\n\n" if snippet else "")
        + f"{response}\n\n---\n"
    )
    with open(notes_path, "a", encoding="utf-8") as f:
        f.write(entry)


def _snapshot_draft(project: str, text: str) -> None:
    snap_dir = Path("projects") / project / "write_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (snap_dir / f"draft_{ts}.md").write_text(text, encoding="utf-8")
    for old in sorted(snap_dir.glob("draft_*.md"))[:-20]:
        old.unlink()


WRITE_TEMPLATES = {
    "Grant: Background & Significance": (
        "## Background\n\n\n\n## Significance\n\n"
    ),
    "Grant: Objectives & Aims": (
        "## Specific Aims\n\n1. \n2. \n3. \n\n## Objectives\n\n"
    ),
    "Academic: Introduction": (
        "## Introduction\n\n\n\n### Research gap\n\n\n\n### Hypothesis\n\n"
    ),
    "Academic: Methods": (
        "## Methods\n\n### Study design\n\n\n\n### Data collection\n\n\n\n### Analysis\n\n"
    ),
    "Academic: Discussion": (
        "## Discussion\n\n\n\n### Limitations\n\n\n\n### Implications\n\n"
    ),
    "Outreach: Press release": (
        "**FOR IMMEDIATE RELEASE**\n\n## [Headline]\n\n[Lead sentence]\n\n"
        "### Key findings\n\n\n\n### About [lab name]\n\n"
    ),
    "Outreach: Blog post": (
        "# [Title]\n\n[Hook paragraph]\n\n## Key findings\n\n\n\n## Why it matters\n\n"
    ),
    "Response to reviewers": (
        "## Response to Reviewer 1\n\n"
        "### Comment 1.1\n\n**Reviewer:** \n\n**Response:** \n\n"
        "### Comment 1.2\n\n**Reviewer:** \n\n**Response:** \n\n"
    ),
}


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


# ── Cross-session memory helpers ─────────────────────────────────────────────


def _memory_path(project: str) -> Path:
    return Path("projects") / project / "memory.json"


def _load_memory(project: str) -> list[dict]:
    p = _memory_path(project)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def _save_memory(project: str, memories: list[dict]) -> None:
    p = _memory_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(memories, indent=2), encoding="utf-8")


# ── Zotero comparison helper ──────────────────────────────────────────────────


def get_zotero_titles(project: str) -> list[dict]:
    """Fetch item metadata from the matching Zotero collection without downloading files."""
    try:
        from pyzotero import zotero as pyzotero_lib
    except ImportError:
        return []

    api_key = os.getenv("ZOTERO_API_KEY")
    user_id = os.getenv("ZOTERO_USER_ID")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user")

    if not api_key or not user_id:
        return []

    try:
        zot = pyzotero_lib.Zotero(user_id, library_type, api_key)
        all_colls = zot.collections()
        matches = [c for c in all_colls if c["data"]["name"].lower() == project.lower()]
        if not matches:
            return []

        raw = [
            i for i in zot.collection_items(matches[0]["key"], itemType="-attachment")
            if i["data"].get("itemType") != "note"
        ]

        result = []
        for item in raw:
            d = item["data"]
            authors = [c for c in d.get("creators", []) if c.get("creatorType") == "author"]
            if not authors:
                author_str = ""
            elif len(authors) == 1:
                author_str = authors[0].get("lastName") or authors[0].get("name", "")
            else:
                author_str = f"{authors[0].get('lastName', 'Unknown')} et al."
            result.append({
                "title": d.get("title", ""),
                "author_str": author_str,
                "year": (d.get("date") or "")[:4],
                "doi": d.get("DOI", ""),
            })
        return result
    except Exception:
        return []


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

    # Normalise: old list format → uniform weight dict; new dict format → use as-is
    norm: dict[str, dict[str, float]] = {}
    for fname, value in themes_map.items():
        if isinstance(value, list):
            norm[fname] = {t: 1.0 for t in value}
        elif isinstance(value, dict):
            norm[fname] = {k: float(v) for k, v in value.items()}
        else:
            norm[fname] = {}

    # Cumulative weight per theme (sum of all edge weights connecting to it)
    theme_total_weight: dict[str, float] = {}
    for tw in norm.values():
        for theme, weight in tw.items():
            theme_total_weight[theme] = theme_total_weight.get(theme, 0.0) + weight

    # Count papers per theme (for tooltip)
    theme_paper_count: dict[str, int] = {}
    for tw in norm.values():
        for theme in tw:
            theme_paper_count[theme] = theme_paper_count.get(theme, 0) + 1

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
            "hoverWidth": 1.5
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "navigationButtons": true,
            "zoomView": true
        }
    }""")

    doc_map = {d["filename"]: d for d in docs}

    for fname, themes_weights in norm.items():
        if not themes_weights:
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

    for theme, total_w in theme_total_weight.items():
        node_size = 13 + min(total_w * 4, 24)   # range ~13–37 px
        count = theme_paper_count[theme]
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
            title=(
                f"<div style='font-family:sans-serif'>"
                f"<b style='color:#fcd34d'>{theme}</b><br>"
                f"<span style='color:#94a3b8'>{count} paper{'s' if count != 1 else ''} · "
                f"total relevance: {total_w:.1f}</span></div>"
            ),
        )

    for fname, themes_weights in norm.items():
        if not themes_weights or fname not in doc_map:
            continue
        for theme, weight in themes_weights.items():
            edge_width = 0.8 + weight * 3.2   # range 0.9 (w=0.1) to 4.0 (w=1.0)
            net.add_edge(
                fname,
                f"__t__{theme}",
                color={"color": "#334155", "highlight": "#64748b", "hover": "#94a3b8"},
                width=edge_width,
                title=f"<span style='font-family:sans-serif;color:#e2e8f0'>Relevance: {weight:.2f}</span>",
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
            cur_msgs = st.session_state.get(f"messages_{selected_project}", [])
            cur_file = st.session_state.get(f"history_file_{selected_project}")
            if len([m for m in cur_msgs if m["role"] == "user"]) >= 2 and cur_file:
                st.session_state[f"_pending_summary_{selected_project}"] = {
                    "messages": cur_msgs,
                    "file": str(cur_file),
                }
            st.session_state[f"messages_{selected_project}"] = []
            st.session_state.pop(f"history_file_{selected_project}", None)
            st.rerun()
    with col2:
        st.button("Saved", disabled=True, use_container_width=True,
                  help="Conversations are auto-saved after each response.")

    # Memory display
    memories = _load_memory(selected_project)
    if memories:
        st.markdown("---")
        with st.expander(f"Research memory ({len(memories)})"):
            for mem in reversed(memories[-5:]):
                ts = mem.get("timestamp", "")[:10]
                st.caption(f"*{ts}* — {mem['summary']}")
            if st.button("Clear memory", key="clear_memory"):
                _save_memory(selected_project, [])
                st.rerun()

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
        _model_options = {
            "Sonnet 4.6 — recommended": "claude-sonnet-4-6",
            "Haiku 4.5 — fast & lower cost": "claude-haiku-4-5-20251001",
            "Opus 4.7 — highest quality": "claude-opus-4-7",
        }
        _model_label = st.selectbox(
            "Claude model",
            list(_model_options.keys()),
            help=(
                "Sonnet 4.6 is the best balance of quality and cost for most tasks. "
                "Haiku 4.5 is faster and cheaper — good for quick exploration. "
                "Opus 4.7 is the most capable — best for final grant drafts at higher cost."
            ),
        )
        claude_model = _model_options[_model_label]

        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.3,
            step=0.05,
            help=(
                "Controls output variability. "
                "0.0–0.3 = precise and consistent (best for Q&A and factual extraction). "
                "0.4–0.6 = balanced (good for grant drafting). "
                "0.7–1.0 = more creative (outreach writing, brainstorming)."
            ),
        )

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

        max_draft_tokens = st.select_slider(
            "Max draft length (tokens)",
            options=[1024, 2048, 4096, 6144, 8192],
            value=2048,
            help=(
                "Maximum length of generated drafts. "
                "2 048 suits most sections. Raise to 4 096+ for long background or methods sections. "
                "1 token ≈ ¾ of a word."
            ),
        )

        show_scores = st.toggle(
            "Show retrieval scores",
            value=True,
            help=(
                "Display cosine similarity scores (0–1) next to source chunks. "
                "Scores above ~0.6 indicate strong relevance; below ~0.4 the match may be weak."
            ),
        )

    _usage = get_session_usage()
    _PRICES = {
        "claude-haiku-4-5-20251001": (0.80, 4.00),
        "claude-sonnet-4-6":         (3.00, 15.00),
        "claude-opus-4-7":           (15.00, 75.00),
    }

    def _calc_cost(entries):
        return sum(
            u["input"]  / 1_000_000 * _PRICES.get(u["model"], (3.00, 15.00))[0]
            + u["output"] / 1_000_000 * _PRICES.get(u["model"], (3.00, 15.00))[1]
            for u in entries
        )

    _all_time = []
    try:
        with open(USAGE_LOG, encoding="utf-8") as _f:
            _all_time = [json.loads(line) for line in _f if line.strip()]
    except FileNotFoundError:
        pass

    if _usage or _all_time:
        st.markdown("---")
        with st.expander(f"Session usage ({len(_usage)} call(s))"):
            if _usage:
                _uc1, _uc2 = st.columns(2)
                _uc1.metric("Tokens in",  f"{sum(u['input']  for u in _usage):,}")
                _uc2.metric("Tokens out", f"{sum(u['output'] for u in _usage):,}")
                st.metric("Est. cost", f"${_calc_cost(_usage):.4f}")
            else:
                st.caption("No calls yet this session.")

            if _all_time:
                st.markdown("**All time**")
                _ac1, _ac2 = st.columns(2)
                _ac1.metric("Tokens in",  f"{sum(u['input']  for u in _all_time):,}")
                _ac2.metric("Tokens out", f"{sum(u['output'] for u in _all_time):,}")
                st.metric("Est. cost", f"${_calc_cost(_all_time):.4f}")
                st.caption(f"{len(_all_time)} total calls since log started.")

            st.caption("Haiku $0.80/$4 · Sonnet $3/$15 · Opus $15/$75 per M tokens. Verify at console.anthropic.com.")
            if st.button("Reset session counter", key="reset_usage"):
                clear_session_usage()
                st.rerun()

# ── Session state ─────────────────────────────────────────────────────────────

messages_key = f"messages_{selected_project}"
file_key = f"history_file_{selected_project}"

if messages_key not in st.session_state:
    st.session_state[messages_key] = []

messages = st.session_state[messages_key]

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_chat, tab_docs, tab_extract, tab_draft, tab_write, tab_graph, tab_guide = st.tabs(
    ["Chat", "Documents", "Extract", "Draft", "Write", "Graph", "Guide"]
)

# ── Chat tab ──────────────────────────────────────────────────────────────────

with tab_chat:
    # Process any pending conversation summary from the previous "New Chat" click
    _pending_key = f"_pending_summary_{selected_project}"
    if _pending_key in st.session_state and os.getenv("ANTHROPIC_API_KEY"):
        pending = st.session_state.pop(_pending_key)
        try:
            with st.spinner("Saving session to memory…"):
                summary = summarise_conversation(pending["messages"])
                mems = _load_memory(selected_project)
                existing_files = {m.get("file") for m in mems}
                if Path(pending["file"]).name not in existing_files:
                    mems.append({
                        "summary": summary,
                        "timestamp": datetime.now().isoformat(),
                        "file": Path(pending["file"]).name,
                    })
                    _save_memory(selected_project, mems[-20:])
        except Exception as _e:
            st.warning(f"Could not save session to memory: {_e}")

    # Build prior-context string from most recent memory entries
    _prior_context = ""
    _mems = _load_memory(selected_project)
    if _mems:
        _prior_context = "\n".join(f"- {m['summary']}" for m in _mems[-3:])

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
                    _sc = msg.get("scores", [])
                    for i, ref in enumerate(msg["citations"]):
                        if show_scores and i < len(_sc):
                            st.markdown(f"- {ref}  ·  match: **{_sc[i]:.2f}**")
                        else:
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
                        answer, citations, scores = query_multi(
                            active_projects_chat, prompt,
                            prior_context=_prior_context,
                            model=claude_model, temperature=temperature,
                        )
                    else:
                        answer, citations, scores = query(
                            selected_project, prompt,
                            prior_context=_prior_context,
                            model=claude_model, temperature=temperature,
                        )
                except ValueError as e:
                    st.error(str(e))
                    st.stop()
                except Exception as exc:
                    st.error(f"An error occurred: {exc}")
                    st.stop()

            st.markdown(answer)
            if citations:
                with st.expander("Source chunks retrieved", expanded=False):
                    for ref, score in zip(citations, scores):
                        line = f"- {ref}  ·  match: **{score:.2f}**" if show_scores else f"- {ref}"
                        st.markdown(line)

        messages.append({"role": "assistant", "content": answer, "citations": citations, "scores": scores})

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

        # ── Un-ingested Zotero papers ─────────────────────────────────────────
        if os.getenv("ZOTERO_API_KEY") and os.getenv("ZOTERO_USER_ID"):
            zotero_cache_key = f"_zotero_{selected_project}"
            col_z1, col_z2 = st.columns([5, 1])
            col_z1.markdown("**Zotero sync check**")
            if col_z2.button("Refresh", key="refresh_zotero"):
                st.session_state.pop(zotero_cache_key, None)
            if zotero_cache_key not in st.session_state:
                with st.spinner("Fetching Zotero collection…"):
                    st.session_state[zotero_cache_key] = get_zotero_titles(selected_project)
            zotero_items = st.session_state[zotero_cache_key]
            if zotero_items:
                ingested_dois = {d["doi"].lower() for d in docs if d.get("doi")}
                ingested_titles = {d["title"].lower().strip() for d in docs if d.get("title")}
                not_ingested = []
                for _z in zotero_items:
                    _doi = (_z.get("doi") or "").lower()
                    _title = (_z.get("title") or "").lower().strip()
                    if not ((_doi and _doi in ingested_dois) or (_title and _title in ingested_titles)):
                        not_ingested.append(_z)
                if not_ingested:
                    with st.expander(f"{len(not_ingested)} paper(s) in Zotero not yet ingested", expanded=True):
                        for z in not_ingested:
                            lbl = (f"**{z['author_str']} ({z['year']})** — {z['title']}"
                                   if z["author_str"] else z["title"])
                            st.markdown(f"- {lbl}")
                        st.caption(
                            f"Run `python ingest.py --project {selected_project} --zotero` to ingest these."
                        )
                else:
                    st.success("All Zotero papers are ingested.")
        else:
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
                            active_projects_draft, full_prompt, mode["system_prompt"], retrieval_k,
                            model=claude_model, temperature=temperature, max_tokens=max_draft_tokens,
                        )
                    else:
                        draft_text, draft_citations = draft(
                            selected_project, full_prompt, mode["system_prompt"], retrieval_k,
                            model=claude_model, temperature=temperature, max_tokens=max_draft_tokens,
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
                        time.sleep(7)
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
                    themes = extract_themes(selected_project, doc["filename"], model=claude_model)
                    themes_map[doc["filename"]] = themes
                except Exception as e:
                    themes_map[doc["filename"]] = {}
                    st.warning(f"Could not tag {doc['filename']}: {e}")
                if i < n - 1:
                    time.sleep(7)
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

# ── Guide tab ─────────────────────────────────────────────────────────────────

with tab_guide:
    guide_path = Path("USER_GUIDE.md")
    if guide_path.exists():
        st.markdown(guide_path.read_text(encoding="utf-8"))
    else:
        st.warning("USER_GUIDE.md not found.")

# ── Write tab ─────────────────────────────────────────────────────────────────

with tab_write:
    st.header(f"Write — {selected_project}")

    other_projects_write = [p for p in projects if p != selected_project]
    write_extra = []
    if other_projects_write:
        write_extra = st.multiselect(
            "Also draw from",
            other_projects_write,
            default=[],
            help="Include literature from additional projects when requesting AI assistance.",
            key="extra_write",
        )

    # ── Session state keys ────────────────────────────────────────────────────
    _wkey_resp    = f"write_ai_response_{selected_project}"
    _wkey_mode    = f"write_ai_mode_{selected_project}"
    _wkey_cites   = f"write_cites_{selected_project}"
    _wkey_ctext   = f"write_cached_text_{selected_project}"
    _wkey_cmode   = f"write_cached_mode_{selected_project}"
    _wkey_cproj   = f"write_cached_proj_{selected_project}"
    _wkey_cctx    = f"write_cached_ctx_{selected_project}"
    _wkey_ctx     = f"write_context_{selected_project}"
    _wkey_extpath = f"write_ext_path_{selected_project}"
    _wkey_widget  = f"write_textarea_{selected_project}"
    _wkey_pending = f"write_textarea_pending_{selected_project}"
    _wkey_rpane   = f"write_right_pane_{selected_project}"
    _wkey_rswitch = f"write_rpane_switch_{selected_project}"

    for _k, _v in [
        (_wkey_resp, ""), (_wkey_mode, ""), (_wkey_cites, []),
        (_wkey_ctext, ""), (_wkey_cmode, ""), (_wkey_cproj, []), (_wkey_cctx, ""),
        (_wkey_rpane, "Preview"),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # Pending editor content — must be applied before text_area renders.
    if _wkey_pending in st.session_state:
        st.session_state[_wkey_widget] = st.session_state.pop(_wkey_pending)

    # Auto-switch right pane to AI response after a successful call — must happen
    # before the radio widget renders (same Streamlit constraint as the textarea).
    if st.session_state.pop(_wkey_rswitch, False):
        st.session_state[_wkey_rpane] = "AI response"

    # Load per-project draft from file on first render
    if _wkey_widget not in st.session_state:
        _draft_file = _write_draft_path(selected_project)
        st.session_state[_wkey_widget] = (
            _draft_file.read_text(encoding="utf-8") if _draft_file.exists() else ""
        )

    # Load writing context from file on first render
    if _wkey_ctx not in st.session_state:
        _ctx_file = _write_context_path(selected_project)
        st.session_state[_wkey_ctx] = (
            _ctx_file.read_text(encoding="utf-8") if _ctx_file.exists() else ""
        )

    # Load external file path from write_config.json on first render
    if _wkey_extpath not in st.session_state:
        st.session_state[_wkey_extpath] = _load_write_config(selected_project).get(
            "external_file", ""
        )

    # Writing context drives AI calls — use the saved value so it's stable across reruns.
    writing_context = st.session_state.get(_wkey_ctx, "")

    # ── AI bar (above editor) ─────────────────────────────────────────────────
    st.caption(
        "Ask AI — retrieves relevant passages from the literature, then Claude assists "
        "with your draft. Set a writing context below to give the AI additional guidance."
    )
    _assist_cols = st.columns([1, 1, 1, 1, 3, 1])
    _mode_btn_labels = ["Find citations", "Refine", "Challenge", "Expand"]
    _selected_mode = None

    for _i, _label in enumerate(_mode_btn_labels):
        if _assist_cols[_i].button(
            _label,
            key=f"write_mode_{_label}_{selected_project}",
            use_container_width=True,
        ):
            _selected_mode = _label

    with _assist_cols[4]:
        _custom_instruction = st.text_input(
            "custom",
            placeholder="Custom instruction…",
            label_visibility="collapsed",
            key=f"write_custom_{selected_project}",
        )
    if _assist_cols[5].button(
        "Ask", key=f"write_ask_{selected_project}", use_container_width=True, type="primary"
    ):
        _selected_mode = "Custom"

    # ── Editor / right pane ───────────────────────────────────────────────────
    col_edit, col_right = st.columns(2, gap="medium")

    with col_edit:
        st.caption("Markdown editor")
        draft_text = st.text_area(
            label="editor",
            height=440,
            placeholder="Start writing here. Markdown is supported.",
            label_visibility="collapsed",
            key=_wkey_widget,
        )

    with col_right:
        # Pane header: label on left, toggle on right
        _rh_left, _rh_right = st.columns([2, 3])
        _rh_left.caption("Preview / AI response")
        _rpane_view = _rh_right.radio(
            "view",
            ["Preview", "AI response"],
            horizontal=True,
            label_visibility="collapsed",
            key=_wkey_rpane,
        )

        if _rpane_view == "Preview":
            if draft_text.strip():
                st.markdown(draft_text)
            else:
                st.markdown("*Preview appears as you write…*")
        else:
            # AI response pane
            if st.session_state[_wkey_resp]:
                _mode_label = st.session_state.get(_wkey_mode, "AI")
                _rp_hdr, _rp_ref, _rp_clr = st.columns([5, 1, 1])
                _rp_hdr.caption(f"AI — {_mode_label}")
                if _rp_ref.button("↺", key=f"write_refresh_{selected_project}",
                                  help="Clear cache and regenerate"):
                    for _k in (_wkey_ctext, _wkey_cmode, _wkey_cctx, _wkey_resp):
                        st.session_state[_k] = ""
                    st.session_state[_wkey_cproj] = []
                    st.session_state[_wkey_cites] = []
                    st.rerun()
                if _rp_clr.button("✕", key=f"write_clear_{selected_project}",
                                  help="Dismiss suggestion"):
                    st.session_state[_wkey_resp]  = ""
                    st.session_state[_wkey_cites] = []
                    st.session_state[_wkey_rpane] = "Preview"
                    st.rerun()

                st.markdown(st.session_state[_wkey_resp])

                if st.session_state[_wkey_cites]:
                    with st.expander("Sources", expanded=False):
                        for _c in st.session_state[_wkey_cites]:
                            st.caption(_c)

                _ra1, _ra2 = st.columns(2)
                if _ra1.button("Save to notes", key=f"write_save_notes_{selected_project}",
                               use_container_width=True):
                    _append_to_notes(
                        _write_notes_path(selected_project),
                        mode=_mode_label,
                        response=st.session_state[_wkey_resp],
                        draft_snippet=draft_text,
                    )
                    st.success("Saved to write_notes.md")
                if _ra2.button("Append to draft", key=f"write_append_{selected_project}",
                               use_container_width=True, type="primary"):
                    st.session_state[_wkey_pending] = (
                        draft_text.rstrip() + "\n\n" + st.session_state[_wkey_resp]
                    )
                    st.session_state[_wkey_rpane] = "Preview"
                    st.rerun()
            else:
                st.markdown(
                    "*No AI suggestion yet — choose a mode above and click **Ask**.*"
                )

    # ── API call (after columns so draft_text is available) ───────────────────
    if _selected_mode:
        if not draft_text.strip():
            st.warning("Write something in the editor first, then request AI assistance.")
        else:
            _write_projects = sorted([selected_project] + write_extra)
            _is_cached = (
                draft_text == st.session_state[_wkey_ctext]
                and _selected_mode == st.session_state[_wkey_cmode]
                and _write_projects == st.session_state[_wkey_cproj]
                and writing_context == st.session_state[_wkey_cctx]
                and st.session_state[_wkey_resp]
            )
            if _is_cached:
                st.session_state[_wkey_rpane] = "AI response"
                st.rerun()
            else:
                _snapshot_draft(selected_project, draft_text)
                st.session_state[_wkey_mode] = _selected_mode
                with st.spinner(f"Asking AI ({_selected_mode})…"):
                    try:
                        if len(_write_projects) > 1:
                            _resp, _cites, _ = assist_writing_multi(
                                projects=_write_projects,
                                document_text=draft_text,
                                mode=_selected_mode,
                                custom_instruction=_custom_instruction,
                                writing_context=writing_context,
                                top_k=retrieval_k,
                                model=claude_model,
                                temperature=temperature,
                            )
                        else:
                            _resp, _cites, _ = assist_writing(
                                project=selected_project,
                                document_text=draft_text,
                                mode=_selected_mode,
                                custom_instruction=_custom_instruction,
                                writing_context=writing_context,
                                top_k=retrieval_k,
                                model=claude_model,
                                temperature=temperature,
                            )
                        st.session_state[_wkey_resp]  = _resp
                        st.session_state[_wkey_cites] = _cites
                        st.session_state[_wkey_ctext] = draft_text
                        st.session_state[_wkey_cmode] = _selected_mode
                        st.session_state[_wkey_cproj] = _write_projects
                        st.session_state[_wkey_cctx]  = writing_context
                        # Signal the right pane to switch on next render
                        st.session_state[_wkey_rswitch] = True
                    except Exception as e:
                        st.session_state[_wkey_resp] = f"**Error:** {e}"
                        st.session_state[_wkey_rswitch] = True
                st.rerun()

    st.divider()

    # ── Footer row: template picker + export + save ───────────────────────────
    _ft1, _ft2, _ft3, _ft4, _ft5 = st.columns([3, 1, 1, 1, 1])

    with _ft1:
        _tmpl_sel = st.selectbox(
            "Template",
            ["— no template —"] + list(WRITE_TEMPLATES.keys()),
            key=f"write_tmpl_{selected_project}",
            label_visibility="visible",
        )
    with _ft2:
        st.write("")  # vertical alignment
        if st.button(
            "Apply",
            key=f"write_tmpl_apply_{selected_project}",
            disabled=(_tmpl_sel == "— no template —"),
            use_container_width=True,
            help="Replaces editor contents. Save your draft first if needed.",
        ):
            st.session_state[_wkey_pending] = WRITE_TEMPLATES[_tmpl_sel]
            st.rerun()
    with _ft3:
        st.write("")
        st.download_button(
            "Download .md",
            data=draft_text,
            file_name=f"{selected_project}_draft.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with _ft4:
        st.write("")
        if _pandoc_available():
            if st.button("Export DOCX", key=f"write_docx_{selected_project}",
                         use_container_width=True):
                if not draft_text.strip():
                    st.warning("Nothing to export — write something first.")
                else:
                    try:
                        _docx = _run_pandoc(draft_text, "docx")
                        st.download_button(
                            "Download DOCX",
                            data=_docx,
                            file_name=f"{selected_project}_draft.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"write_docx_dl_{selected_project}",
                        )
                    except subprocess.CalledProcessError as e:
                        st.error(f"Pandoc failed: {e.stderr.decode()[:200]}")
        else:
            st.caption("[pandoc](https://pandoc.org/installing.html) not installed")
    with _ft5:
        st.write("")
        if st.button("Save draft", key=f"write_save_draft_{selected_project}",
                     use_container_width=True, type="primary"):
            _write_draft_path(selected_project).parent.mkdir(parents=True, exist_ok=True)
            _write_draft_path(selected_project).write_text(draft_text, encoding="utf-8")
            st.success("Draft saved.")

    st.caption(
        f"Snapshots auto-saved before each AI call → "
        f"`projects/{selected_project}/write_snapshots/`"
    )

    # ── Writing context ───────────────────────────────────────────────────────
    with st.expander(
        "Writing context" + (" (set)" if writing_context else " (optional)"),
        expanded=False,
    ):
        st.caption(
            "Brief for the AI — audience, core argument, style constraints, things to avoid. "
            "Saved per project and injected into every AI assist call."
        )
        _ctx_area = st.text_area(
            "context",
            height=110,
            placeholder=(
                "e.g.: NSF proposal for the Division of Environmental Biology. "
                "Audience: program officers with ecology background. "
                "Main argument: fire return intervals have shortened 40% since 1980. "
                "Data is correlational — avoid causal language."
            ),
            label_visibility="collapsed",
            key=f"write_ctx_area_{selected_project}",
        )
        if st.button("Save context", key=f"write_save_ctx_{selected_project}"):
            _write_context_path(selected_project).parent.mkdir(parents=True, exist_ok=True)
            _write_context_path(selected_project).write_text(_ctx_area, encoding="utf-8")
            st.session_state[_wkey_ctx] = _ctx_area
            st.success("Writing context saved.")

    # ── Notes history ─────────────────────────────────────────────────────────
    _notes_path = _write_notes_path(selected_project)
    if _notes_path.exists() and _notes_path.stat().st_size > 0:
        with st.expander("Notes history", expanded=False):
            _notes_text = _notes_path.read_text(encoding="utf-8")
            st.markdown(_notes_text)
            _ndl_col, _nclr_col = st.columns([3, 1])
            _ndl_col.download_button(
                "Download notes (.md)",
                data=_notes_text,
                file_name=f"{selected_project}_write_notes.md",
                mime="text/markdown",
                key=f"write_dl_notes_{selected_project}",
            )
            if _nclr_col.button("Clear notes", key=f"write_clr_notes_{selected_project}"):
                _notes_path.write_text("", encoding="utf-8")
                st.rerun()

    # ── External file sync ────────────────────────────────────────────────────
    with st.expander("External file sync (network drive)", expanded=False):
        st.caption(
            "Read and write your draft directly from a file on a mounted network drive "
            "or any path the server can reach. The path is saved in write_config.json."
        )
        # Use _wkey_extpath as the widget key directly (pre-initialized at startup).
        # Do NOT pass value= — that would override session state on every rerun.
        _ext_input = st.text_input(
            "File path",
            placeholder=r"e.g. Z:\Projects\grant_background.md or /mnt/network/draft.md",
            key=_wkey_extpath,
        )
        # Persist path change to config whenever the value differs from what was last saved
        _saved_ext = _load_write_config(selected_project).get("external_file", "")
        if _ext_input != _saved_ext:
            _cfg = _load_write_config(selected_project)
            _cfg["external_file"] = _ext_input
            _save_write_config(selected_project, _cfg)

        if _ext_input.strip():
            _ext = Path(_ext_input.strip())
            # Guard against reads/writes to sensitive files (e.g. .env, SSH keys).
            # Block any path whose stem starts with a dot or whose suffix is not text-like.
            _ext_blocked = (
                _ext.stem.startswith(".")
                or _ext.suffix.lower() in {".env", ".key", ".pem", ".p12", ".pfx"}
            )
            if _ext_blocked:
                st.error("That path looks like a sensitive system file and cannot be used here.")
            else:
                _ec1, _ec2, _ec3 = st.columns(3)

                if _ec1.button("Load from file", key=f"write_ext_load_{selected_project}"):
                    try:
                        st.session_state[_wkey_pending] = _ext.read_text(encoding="utf-8")
                        st.success(f"Loaded from {_ext.name}")
                        st.rerun()
                    except OSError as e:
                        st.error(f"Could not read: {e}")

                if _ec2.button("Save to file", key=f"write_ext_save_{selected_project}"):
                    try:
                        _ext.parent.mkdir(parents=True, exist_ok=True)
                        _ext.write_text(draft_text, encoding="utf-8")
                        st.success(f"Saved to {_ext.name}")
                    except OSError as e:
                        st.error(f"Could not write: {e}")

                if _ec3.button("Save suggestion to file", key=f"write_ext_notes_{selected_project}"):
                    if not st.session_state.get(_wkey_resp):
                        st.warning("No AI suggestion to save yet.")
                    else:
                        try:
                            _notes_ext = _ext.with_name(_ext.stem + ".notes.md")
                            _append_to_notes(
                                _notes_ext,
                                mode=st.session_state.get(_wkey_mode, "AI"),
                                response=st.session_state[_wkey_resp],
                                draft_snippet=draft_text,
                            )
                            st.success(f"Appended to {_notes_ext.name}")
                        except OSError as e:
                            st.error(f"Could not write notes: {e}")
