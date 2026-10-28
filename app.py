"""ReqLens web interface. Start it with: uv run streamlit run app.py"""

import html
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
LOGO = ROOT / "docs" / "assets" / "logo.svg"
WORKFLOW = ROOT / "docs" / "assets" / "reqlens-workflow.svg"

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
        state.update(stage="done", report=result["report"], run_id=run_id)
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
            del state[key]
        st.rerun()


def analyze_page() -> None:
    st.markdown("### Analyze specification")
    stage = st.session_state.get("stage")
    if stage == "review":
        show_review()
        return
    if stage == "done":
        show_done()
        return

    from reqlens.storage import connect, list_runs

    st.caption(
        "Upload a specification PDF. ReqLens extracts the requirements, flags vague "
        "wording and lets an AI agent look for contradicting requirements. "
        "You make the final call."
    )
    path = None
    upload, recent = st.columns([3, 2], gap="large")
    with upload, st.container(border=True):
        st.markdown("**Upload specification**")
        uploaded = st.file_uploader(
            "Specification PDF", type="pdf", label_visibility="collapsed"
        )
        st.caption(
            "Text-based PDF. Requirement IDs in any format, "
            "for example AEB-001 or [SWS_Std_00011]."
        )
        if st.button("Analyze", type="primary", disabled=uploaded is None):
            path = Path(tempfile.mkdtemp()) / uploaded.name
            path.write_bytes(uploaded.getvalue())
    with recent, st.container(border=True):
        st.markdown("**Recent analyses**")
        runs = list_runs(connect())[-4:][::-1]
        if not runs:
            st.caption("No analyses yet. Your reviewed runs will appear here.")
        for run_id, created, pdf_name, reqs, total, approved in runs:
            st.markdown(f"`#{run_id}` **{pdf_name}**")
            st.caption(
                f"{created[:10]} · {reqs} requirements · "
                f"{approved}/{total} findings approved"
            )

    if path:
        run_analysis(path)

    st.markdown("#### What ReqLens checks")
    checks = [
        (
            ":material/description: Extraction",
            (
                "Finds every requirement with its ID, text and page. Rules first, "
                "the LLM only when the ID format is unknown."
            ),
        ),
        (
            ":material/help: Ambiguity",
            (
                "Flags vague wording such as *fast*, *about* or *sufficient* "
                "that cannot be tested."
            ),
        ),
        (
            ":material/compare_arrows: Conflicts",
            (
                "A LlamaIndex agent searches related requirements and reports "
                "contradicting values, with a reason."
            ),
        ),
    ]
    for col, (title, text) in zip(st.columns(3), checks):
        with col, st.container(border=True, height="stretch"):
            st.markdown(f"**{title}**")
            st.caption(text)

    st.markdown("#### How it works")
    st.image(str(WORKFLOW), width="stretch")


def history_page() -> None:
    from reqlens.storage import approval_rate, connect, list_runs

    st.markdown("### History")
    conn = connect()
    rows = list_runs(conn)
    if not rows:
        st.info("No analyses yet. Run one on the Analyze page.")
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
        f"{approval_rate(conn):.0%}",
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
st.markdown(CSS, unsafe_allow_html=True)
page = st.navigation(
    [
        st.Page(analyze_page, title="Analyze", icon=":material/search:", default=True),
        st.Page(
            history_page, title="History", icon=":material/history:", url_path="history"
        ),
    ]
)
with st.sidebar:
    st.caption("Requirements analysis for the automotive industry")
    st.markdown("[GitHub](https://github.com/BUAksakal/reqlens)")
page.run()
