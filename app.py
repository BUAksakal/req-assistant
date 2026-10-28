"""ReqLens web interface. Start it with: uv run streamlit run app.py"""

import html
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import pymupdf
import streamlit as st

from reqlens.ai_parser import MAX_PAGES

ROOT = Path(__file__).parent
LOGO = ROOT / "docs" / "assets" / "logo.svg"
MAX_MB = 20

GUIDE = [
    (
        "Choose your PDF",
        f"A text-based specification, up to {MAX_PAGES} pages. Any ID format works.",
    ),
    (
        "Click Analyze",
        "No settings to choose. A 10-page document takes about a minute.",
    ),
    (
        "Watch the agents",
        "A live view shows every step and what the agents search for.",
    ),
    (
        "Decide",
        (
            "Approve the real problems, reject false alarms. "
            "The agents can be wrong, so every finding waits for you."
        ),
    ),
]
STEPS = [
    (
        "Read and extract",
        "PyMuPDF reads the text, a regex looks for IDs like AEB-001.",
        "rules",
    ),
    (
        "Enough found?",
        "Looks for 'shall' sentences the regex missed and decides the next step.",
        "supervisor agent",
    ),
    ("LLM extraction", "Only if needed: Gemini reads the PDF in 8-page chunks.", "llm"),
    (
        "Vague wording",
        "Words like fast or sufficient are flagged, they cannot be tested.",
        "rules",
    ),
    (
        "Conflict search",
        "Searches related requirements for every one and compares their values.",
        "conflict agent",
    ),
    (
        "Verification",
        "A second look at every conflict. Clear false alarms are dropped.",
        "supervisor agent",
    ),
    (
        "Your review",
        "The workflow pauses until you approve or reject each finding.",
        "you",
    ),
    (
        "Report",
        "Findings and your decisions are stored, so precision can be measured.",
        "sqlite",
    ),
]

FONTS = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;'
    '500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">'
)

NODES = [
    ("classic_extract", "Classic extract", "regex"),
    ("supervise_extraction", "Supervisor", "enough found?"),
    ("ai_extract", "LLM extract", "Gemini"),
    ("check_vague", "Vague check", "word rules"),
    ("check_conflicts", "Conflict agent", "LlamaIndex"),
    ("verify_findings", "Supervisor", "verify"),
    ("review", "Engineer", "review"),
    ("report", "Report", "SQLite"),
]
ICONS = {"pending": "○", "active": "●", "done": "✓", "skipped": "–", "waiting": "❙❙"}

CSS = """
<style>
.rl-chip {display: inline-block; font-size: 10.5px; font-weight: 600;
          letter-spacing: 0.06em; text-transform: uppercase; padding: 2px 8px;
          border-radius: 4px; border: 1px solid #111111; white-space: nowrap;}
.rl-chip.solid {background: #111111; color: #FFFFFF;}
.rl-chip.line {background: #FFFFFF; color: #111111;}
.rl-id {font-family: ui-monospace, Menlo, monospace; font-weight: 600; font-size: 14px;
         white-space: nowrap; margin-bottom: 6px;}
.rl-head {color: #737373; font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
          text-transform: uppercase;}
.rl-flow {border: 1px solid #E5E5E5; border-radius: 8px; padding: 14px 16px 16px;
          background: #FAFAFA; margin: 4px 0 16px;}
.rl-title {color: #737373; font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
           text-transform: uppercase; margin-bottom: 12px;}
.rl-row {display: flex; align-items: stretch;}
.rl-node {flex: 1; min-width: 0; border: 1px solid #E5E5E5; border-radius: 6px;
          padding: 10px 6px; text-align: center; background: #FFFFFF;}
.rl-node i {display: block; font-style: normal; font-size: 14px; color: #A3A3A3;}
.rl-node b {display: block; color: #111111; font-size: 13px; font-weight: 600;
            margin-top: 2px;}
.rl-node span {display: block; color: #737373; font-size: 11px; margin-top: 2px;}
.rl-active {border-color: #111111; animation: rl-pulse 1.4s infinite;}
.rl-active i, .rl-done i, .rl-waiting i {color: #111111;}
.rl-done {border-color: #111111;}
.rl-skipped {opacity: 0.45; border-style: dashed;}
.rl-waiting {border: 1.5px dashed #111111;}
.rl-edge {flex: 0 0 18px; align-self: center; height: 1px; background: #D4D4D4;}
.rl-edge.on {height: 2px; background: repeating-linear-gradient(90deg, #111111 0 5px,
             transparent 5px 10px); background-size: 20px 2px;
             animation: rl-flowing 0.6s linear infinite;}
.rl-console {margin-top: 14px; background: #0A0A0A; border-radius: 6px;
             padding: 10px 12px; min-height: 112px; color: #A3A3A3;
             font-family: ui-monospace, Menlo, monospace; font-size: 12.5px;}
.rl-console div {white-space: pre; overflow: hidden; text-overflow: ellipsis;}
.rl-console .now {color: #FFFFFF;}
.rl-console .now::after {content: "▋"; margin-left: 4px;
                         animation: rl-blink 1s steps(1) infinite;}
@keyframes rl-pulse {0% {box-shadow: 0 0 0 0 rgba(17, 17, 17, 0.25);}
                     70% {box-shadow: 0 0 0 8px rgba(17, 17, 17, 0);}
                     100% {box-shadow: 0 0 0 0 rgba(17, 17, 17, 0);}}
@keyframes rl-flowing {to {background-position: 20px 0;}}
@keyframes rl-blink {50% {opacity: 0;}}

body, p, div, label, button, input {font-family: Inter, sans-serif;}
header[data-testid="stHeader"] {border-bottom: 1px solid #E5E5E5;}
[data-testid="stTopNav"] {justify-content: flex-end; padding-right: 1.5rem;}
[data-testid="stTopNavLink"] {background: transparent; color: #737373; font-size: 13.5px;}
[data-testid="stTopNavLink"]:hover {background: transparent; color: #111111;}
[data-testid="stTopNavLink"], [data-testid="stTopNavLink"] * {text-decoration: none !important;
    border-bottom: none !important; box-shadow: none !important;}
[data-testid="stTopNavLink"][aria-current="page"] {background: transparent; color: #111111;
    font-weight: 600;}
.block-container {max-width: min(1720px, 96vw); padding-left: 2.5rem; padding-right: 2.5rem;}
.mono {font-family: "JetBrains Mono", monospace;}
.eyebrow {font: 500 11px "JetBrains Mono", monospace; letter-spacing: .14em; color: #737373;
          text-transform: uppercase; display: flex; align-items: center; gap: 8px;}
.eyebrow i {width: 7px; height: 7px; border-radius: 50%; background: #111111;}
h1.title {font-size: 32px; font-weight: 600; letter-spacing: -.02em; margin: 6px 0 4px;
          color: #111111; padding: 0;}
p.lead {color: #737373; font-size: 16px; max-width: 720px; margin: 0 0 28px; line-height: 1.6;}
.sec {font: 600 11px "JetBrains Mono", monospace; letter-spacing: .12em;
      text-transform: uppercase; color: #737373; margin: 0 2px 10px;}
.guide {display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid #E5E5E5;
        border-radius: 10px; margin: 0 0 32px; background: #FFFFFF;}
.g {padding: 20px 22px; border-right: 1px solid #E5E5E5;}
.g:last-child {border-right: none;}
.g .c {display: inline-flex; width: 22px; height: 22px; border: 1.5px solid #111111;
       border-radius: 50%; align-items: center; justify-content: center;
       font: 600 10px "JetBrains Mono", monospace;}
.g .t {font-weight: 600; font-size: 16px; margin-top: 10px; color: #111111;}
.g .d {font-size: 13.5px; color: #737373; margin-top: 3px; line-height: 1.5;}
.card-head {display: flex; justify-content: space-between; align-items: center;
            background: #FAFAFA; border-radius: 6px; padding: 9px 12px; margin-bottom: 14px;}
.card-head b {font: 600 12px "JetBrains Mono", monospace; letter-spacing: .06em;
              text-transform: uppercase;}
.card-head span {font: 11px "JetBrains Mono", monospace; color: #737373;}
[data-testid="stFileUploaderDropzone"] {border: 1.5px dashed #A3A3A3; background: #FAFAFA;
                                        border-radius: 8px; padding: 42px 24px;}
[data-testid="stFileUploaderDropzone"]:hover {border-color: #111111;}
[data-testid="stFileUploaderDropzone"] button {background: #111111; color: #FFFFFF; border: none;}
[data-testid="stFileUploaderDropzoneInstructions"] span {display: none;}
[data-testid="stFileUploaderDropzoneInstructions"]::after {
    content: "Drop a specification PDF here"; color: #525252; font-size: 14px;}
.limits {font: 12px "JetBrains Mono", monospace; color: #737373; margin: 10px 0 16px;}
.limits b {color: #111111; font-weight: 600;}
.file {display: flex; justify-content: space-between; border: 1px solid #E5E5E5;
       border-radius: 6px; padding: 10px 12px; margin-bottom: 12px;
       font: 13px "JetBrains Mono", monospace;}
.file span + span {color: #737373;}
.err {border: 1px solid #111111; border-radius: 6px; padding: 10px 12px; margin-bottom: 12px;
      font-size: 13px;}
.rh {display: flex; justify-content: space-between; font: 600 11px "JetBrains Mono", monospace;
     letter-spacing: .1em; text-transform: uppercase; color: #737373; margin: 2px 2px 10px;}
.run {border: 1px solid #E5E5E5; border-radius: 8px; padding: 16px 18px; margin-bottom: 8px;}
.run .top {display: flex; justify-content: space-between; gap: 8px;}
.run .name {font: 500 14px "JetBrains Mono", monospace; color: #111111; overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap;}
.run .when {font: 11px "JetBrains Mono", monospace; color: #737373; white-space: nowrap;}
.run .stats {font-size: 13px; color: #737373; margin-top: 6px;}
.pill {display: inline-block; font: 500 10px "JetBrains Mono", monospace; background: #F0F0F0;
       border-radius: 4px; padding: 2px 7px; margin-top: 8px; color: #111111;}
.empty {border: 1px dashed #E5E5E5; border-radius: 8px; padding: 22px; color: #737373;
        font-size: 13px; text-align: center;}
.pipe-head {display: flex; justify-content: space-between; margin: 48px 0 14px;
            padding-top: 28px; border-top: 1px solid #E5E5E5;
            font: 600 11px "JetBrains Mono", monospace; letter-spacing: .12em;
            text-transform: uppercase; color: #737373;}
.pipe {display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; background: #FAFAFA;
       border-radius: 10px; padding: 22px;}
.step {background: #FFFFFF; border: 1px solid #E5E5E5; border-radius: 8px; padding: 18px;
       animation: rl-step 16s infinite; animation-delay: calc(var(--i) * 2s - 2s);}
@keyframes rl-step {
    0%, 12.5% {border-color: #111111; box-shadow: 0 0 0 3px rgba(17, 17, 17, 0.12);
               transform: translateY(-3px);}
    14%, 100% {border-color: #E5E5E5; box-shadow: none; transform: none;}}
.step .top {display: flex; justify-content: space-between; align-items: center;}
.step .n {display: inline-flex; width: 24px; height: 24px; border-radius: 4px;
          background: #111111; color: #FFFFFF; align-items: center; justify-content: center;
          font: 500 10px "JetBrains Mono", monospace;}
.step .t {font: 600 13.5px "JetBrains Mono", monospace; margin-top: 12px; color: #111111;}
.step .d {font-size: 13px; color: #737373; margin-top: 3px; line-height: 1.5;}
.who {font: 600 9px "JetBrains Mono", monospace; letter-spacing: .08em;
      text-transform: uppercase; border: 1px solid #E5E5E5; border-radius: 3px;
      padding: 2px 6px; color: #737373;}
.who.agent {background: #111111; border-color: #111111; color: #FFFFFF;}
.who.you {border-color: #111111; color: #111111;}
@media (max-width: 760px) {.pipe, .guide {grid-template-columns: 1fr 1fr;}}
</style>
"""


def flow_html(states: dict[str, str], console: list[str], live: bool) -> str:
    """Draw the LangGraph workflow with the state of every node and the agent log."""
    parts = []
    for i, (node, title, subtitle) in enumerate(NODES):
        state = states.get(node, "pending")
        if i:
            previous = states.get(NODES[i - 1][0], "pending")
            flowing = state in ("active", "waiting") and previous in ("done", "skipped")
            parts.append(f'<div class="rl-edge{" on" if flowing else ""}"></div>')
        parts.append(
            f'<div class="rl-node rl-{state}"><i>{ICONS[state]}</i>'
            f"<b>{title}</b><span>{subtitle}</span></div>"
        )
    lines = [html.escape(line) for line in console[-6:]]
    log = "".join(
        f'<div class="{"now" if live and i == len(lines) - 1 else ""}">{line}</div>'
        for i, line in enumerate(lines)
    )
    return (
        f'<div class="rl-flow"><div class="rl-title">LangGraph workflow</div>'
        f'<div class="rl-row">{"".join(parts)}</div>'
        f'<div class="rl-console">{log}</div></div>'
    )


def describe(finding: str) -> tuple[str, str, str]:
    """Split a finding into requirement ID, type and a readable description."""
    req_id, _, detail = finding.partition(": ")
    if detail.startswith("vague words"):
        words = detail.removeprefix("vague words").strip(" []").replace("'", "")
        return req_id, "Ambiguity", f"Vague wording: {words}"
    other, _, reason = detail.partition(": ")
    return req_id, "Conflict", f"Conflicts with {other}. {reason}"


def run_analysis(pdf_path: Path) -> None:
    from reqlens.llm import LLMUnavailableError
    from reqlens.workflow import build_workflow

    workflow = build_workflow()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    states = {"classic_extract": "active"}
    console = [f"$ reqlens analyze {pdf_path.name}"]
    view = st.empty()

    def show(line: str | None = None) -> None:
        if line:
            console.append(line)
        view.markdown(flow_html(states, console, live=True), unsafe_allow_html=True)

    show()
    try:
        for mode, chunk in workflow.stream(
            {"pdf": str(pdf_path)}, config, stream_mode=["updates", "custom"]
        ):
            if mode == "custom":
                if "checking" in chunk:
                    show(f"▶ agent checks {chunk['checking']}")
                elif "cached" in chunk:
                    show(f"✓ {chunk['cached']} answered from cache, no LLM call")
                elif "supervisor" in chunk:
                    show(f"◆ supervisor: {chunk['supervisor']}")
                elif "note" in chunk:
                    show(f"· {chunk['note']}")
                else:
                    hits = ", ".join(chunk["hits"][:3])
                    show(f'   find_related("{chunk["search"]}") → {hits}')
                continue
            for node, update in chunk.items():
                if node == "classic_extract":
                    states.update(classic_extract="done", supervise_extraction="active")
                    show(f"✓ classic extractor found {len(update['requirements'])}")
                elif node == "supervise_extraction":
                    use_llm = update["extraction"] == "use_llm"
                    states.update(
                        supervise_extraction="done",
                        ai_extract="active" if use_llm else "skipped",
                    )
                    if not use_llm:
                        states["check_vague"] = "active"
                elif node == "ai_extract":
                    states.update(ai_extract="done", check_vague="active")
                    show(f"✓ LLM extracted {len(update['requirements'])} requirements")
                elif node == "check_vague":
                    states.update(check_vague="done", check_conflicts="active")
                    show(f"✓ {len(update['vague'])} requirement(s) with vague wording")
                elif node == "check_conflicts":
                    states.update(check_conflicts="done", verify_findings="active")
                    show(f"✓ agent reported {len(update['conflicts'])} conflict(s)")
                elif node == "verify_findings":
                    states.update(verify_findings="done", review="waiting")
                    show(
                        f"✓ {len(update['conflicts'])} conflict(s) passed verification"
                    )
    except LLMUnavailableError as error:
        st.error(str(error), icon=":material/error:")
        return

    console.append("❙❙ waiting for the engineer's review")
    snapshot = workflow.get_state(config)
    st.session_state.update(
        stage="review",
        workflow=workflow,
        config=config,
        states=states,
        console=console,
        pdf_name=pdf_path.name,
        requirements=snapshot.values["requirements"],
        findings=snapshot.interrupts[0].value,
    )
    st.rerun()


def show_summary() -> None:
    state = st.session_state
    findings = [describe(f) for f in state.findings]
    conflicts = sum(kind == "Conflict" for _, kind, _ in findings)
    st.caption(f"Document · **{state.pdf_name}**")
    cols = st.columns(3)
    cols[0].metric("Requirements", len(state.requirements))
    cols[1].metric("Conflicts", conflicts)
    cols[2].metric("Ambiguities", len(findings) - conflicts)


def show_review() -> None:
    from langgraph.types import Command

    from reqlens.storage import connect, save_run

    state = st.session_state
    st.markdown(
        flow_html(state.states, state.console, live=False), unsafe_allow_html=True
    )
    show_summary()

    with st.expander("Extracted requirements", icon=":material/table_rows:"):
        st.dataframe(
            pd.DataFrame(
                [
                    {"ID": r.id, "Page": r.page, "Requirement": r.text}
                    for r in state.requirements
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    st.markdown("#### Review findings")
    st.caption(
        "Approve the findings that are real problems. "
        "The agent can be confidently wrong."
    )
    widths = [1.4, 4.6, 3]
    for col, label in zip(st.columns(widths), ["Requirement", "Finding", "Decision"]):
        col.markdown(f'<span class="rl-head">{label}</span>', unsafe_allow_html=True)

    decisions = {}
    for i, finding in enumerate(state.findings):
        req_id, kind, text = describe(finding)
        chip = "solid" if kind == "Conflict" else "line"
        with st.container(border=True):
            cols = st.columns(widths, vertical_alignment="center")
            cols[0].markdown(
                f'<div class="rl-id">{req_id}</div>'
                f'<span class="rl-chip {chip}">{kind}</span>',
                unsafe_allow_html=True,
            )
            cols[1].write(text)
            decisions[finding] = cols[2].segmented_control(
                "Decision",
                ["approve", "reject"],
                format_func=lambda option: (
                    ":material/check: Approve"
                    if option == "approve"
                    else ":material/close: Reject"
                ),
                key=f"decision_{i}",
                label_visibility="collapsed",
            )

    missing = sum(d is None for d in decisions.values())
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.caption(
        f"{missing} finding(s) still need a decision."
        if missing
        else "All findings reviewed."
    )
    if right.button(
        "Submit review", type="primary", disabled=bool(missing), width="stretch"
    ):
        approved = [f for f, d in decisions.items() if d == "approve"]
        result = state.workflow.invoke(Command(resume=approved), state.config)
        run_id = save_run(
            connect(), state.pdf_name, len(state.requirements), state.findings, approved
        )
        state.states.update(review="done", report="done")
        state.console.append(
            f"✓ {len(approved)} finding(s) approved, saved as run #{run_id}"
        )
        state.update(
            stage="done",
            report=result["report"],
            run_id=run_id,
            my_runs=[*state.get("my_runs", []), run_id],
        )
        st.rerun()


def show_done() -> None:
    state = st.session_state
    st.markdown(
        flow_html(state.states, state.console, live=False), unsafe_allow_html=True
    )
    st.success(f"Review saved as run #{state.run_id}.", icon=":material/check_circle:")
    st.code(state.report, language=None)
    if st.button("Analyze another document", type="primary"):
        for key in list(state.keys()):
            if key != "my_runs":
                del state[key]
        st.rerun()


def pdf_problem(name: str, data: bytes) -> str | None:
    """Show the chosen file and say why it cannot be analysed, before any LLM call."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = doc.page_count
            has_text = any(page.get_text().strip() for page in doc)
    except pymupdf.FileDataError:
        return "This file could not be read as a PDF."
    size = len(data) / 1024
    size = f"{size:.0f} KB" if size < 1024 else f"{size / 1024:.1f} MB"
    st.html(
        f'<div class="file"><span>▤ {html.escape(name)}</span>'
        f"<span>{pages} pages · {size}</span></div>"
    )
    if pages > MAX_PAGES:
        return (
            f"This PDF has {pages} pages. ReqLens reads at most {MAX_PAGES} pages, "
            "please split it."
        )
    if not has_text:
        return "This PDF has no text layer. Scanned documents are not supported yet."
    return None


def start_page() -> Path | None:
    """Explain how to use ReqLens and return the uploaded PDF once Analyze is clicked."""

    st.html(
        '<div class="eyebrow"><i></i>Requirements review · v1.0 demo</div>'
        '<h1 class="title">Analyze a specification</h1>'
        '<p class="lead">Upload a requirements PDF. AI agents extract the requirements, '
        "flag vague wording and look for contradictions. You make the final call.</p>"
        '<div class="sec">How to use ReqLens</div><div class="guide">'
        + "".join(
            f'<div class="g"><span class="c">{i}</span><div class="t">{title}</div>'
            f'<div class="d">{text}</div></div>'
            for i, (title, text) in enumerate(GUIDE, start=1)
        )
        + "</div>"
    )

    path = None
    left, right = st.columns([7, 5], gap="large")
    with left, st.container(border=True):
        st.html(
            '<div class="card-head"><b>Specification</b>'
            "<span>one PDF per analysis</span></div>"
        )
        uploaded = st.file_uploader(
            "Specification PDF", type="pdf", label_visibility="collapsed"
        )
        st.html(
            f'<div class="limits">PDF · max. <b>{MAX_PAGES} pages</b> · <b>{MAX_MB} MB</b>'
            " · text-based, any ID format (AEB-001, [SWS_Std_00011], 5.2.1)</div>"
        )
        problem = uploaded and pdf_problem(uploaded.name, uploaded.getvalue())
        if problem:
            st.html(f'<div class="err">⚠ {problem}</div>')
        if st.button(
            "Analyze specification",
            type="primary",
            disabled=uploaded is None or bool(problem),
            width="stretch",
        ):
            path = Path(tempfile.mkdtemp()) / uploaded.name
            path.write_bytes(uploaded.getvalue())

    with right:
        st.html(
            '<div class="rh"><span>Recent analyses</span><span>this session</span></div>'
        )
        runs = my_runs()[-3:][::-1]
        if not runs:
            st.html(
                '<div class="empty">No analyses in this session yet.<br>'
                "Only you can see your runs.</div>"
            )
        for _, created, pdf_name, reqs, total, approved in runs:
            st.html(
                f'<div class="run"><div class="top">'
                f'<span class="name">{html.escape(pdf_name)}</span>'
                f'<span class="when">{created[:16].replace("T", " ")}</span></div>'
                f'<div class="stats">{reqs} requirements · {total} findings</div>'
                f'<span class="pill">{approved}/{total} approved</span></div>'
            )
    return path


def system_steps() -> None:
    """What happens inside ReqLens, with who does each step."""
    kinds = {"supervisor agent": "agent", "conflict agent": "agent", "you": "you"}
    st.html(
        '<div class="pipe-head"><span>Inside ReqLens, after you click Analyze</span>'
        '<span>LangGraph workflow · 2 agents</span></div><div class="pipe">'
        + "".join(
            f'<div class="step {kinds.get(who, "")}" style="--i: {i}">'
            f'<div class="top"><span class="n">{i:02d}</span>'
            f'<span class="who {kinds.get(who, "")}">{who}</span></div>'
            f'<div class="t">{title}</div><div class="d">{text}</div></div>'
            for i, (title, text, who) in enumerate(STEPS, start=1)
        )
        + "</div>"
    )


def analyze_page() -> None:
    stage = st.session_state.get("stage")
    if stage == "review":
        show_review()
        return
    if stage == "done":
        show_done()
        return
    path = start_page()
    if path:
        run_analysis(path)
    system_steps()


def my_runs() -> list[tuple]:
    """Runs saved in this browser session.

    The demo is public, so a visitor must never see the documents that other
    visitors analysed. Every run is still stored for the measured precision.
    """
    from reqlens.storage import connect, list_runs

    mine = set(st.session_state.get("my_runs", []))
    return [row for row in list_runs(connect()) if row[0] in mine]


def history_page() -> None:
    st.markdown("### History")
    st.caption("Only the analyses from this browser session are shown.")
    rows = my_runs()
    if not rows:
        st.info("No analyses in this session yet. Run one on the Analyze page.")
        return

    runs = pd.DataFrame(
        rows,
        columns=["Run", "Date", "Document", "Requirements", "Findings", "Approved"],
    )
    runs["Rejected"] = runs["Findings"] - runs["Approved"]

    cols = st.columns(3)
    cols[0].metric("Analyses", len(runs))
    cols[1].metric("Findings reviewed", int(runs["Findings"].sum()))
    cols[2].metric(
        "Approval rate",
        f"{runs['Approved'].sum() / max(runs['Findings'].sum(), 1):.0%}",
        help="Share of agent findings that engineers confirmed as real problems.",
    )
    st.bar_chart(
        runs.set_index("Run")[["Approved", "Rejected"]],
        color=["#111111", "#A3A3A3"],
        x_label="Run",
        y_label="Findings",
        height=260,
    )
    st.dataframe(runs, hide_index=True, width="stretch")


st.set_page_config(page_title="ReqLens", page_icon=":material/search:", layout="wide")
st.logo(str(LOGO), size="large")
st.html(FONTS)
st.markdown(CSS, unsafe_allow_html=True)
page = st.navigation(
    [
        st.Page(analyze_page, title="Analyze", icon=":material/search:", default=True),
        st.Page(
            history_page, title="History", icon=":material/history:", url_path="history"
        ),
    ],
    position="top",
)
page.run()
