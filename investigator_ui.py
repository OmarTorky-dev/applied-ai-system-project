"""Streamlit UI for the Glitch Investigator agent (the "🕵️ AI Investigator" tab in app.py)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from glitch_ai import setup_logging
from glitch_ai.agent import GlitchInvestigator
from glitch_ai.llm import LLMError, make_client

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
STATUS_STYLE = {"FIXED": st.success, "NO_BUGS": st.success, "PARTIAL": st.warning,
                "FAILED": st.error, "REFUSED": st.error, "ERROR": st.error}


def render_investigator() -> None:
    load_dotenv()
    setup_logging()

    st.markdown(
        "Give the agent a version of `logic_utils.py`. It runs the test suite, retrieves "
        "matching bug patterns from its knowledge base, asks an LLM for a grounded fix, "
        "and re-runs the tests until they pass. **You** decide whether to apply the result."
    )

    samples = sorted(p.stem for p in SAMPLES.glob("*.py"))
    source_choice = st.radio("Code to investigate", ["Bundled sample", "Paste my own"],
                             horizontal=True)
    if source_choice == "Bundled sample":
        name = st.selectbox("Sample", samples, index=samples.index("lying_hints"))
        code = (SAMPLES / f"{name}.py").read_text(encoding="utf-8")
        with st.expander("View sample code"):
            st.code(code, language="python")
    else:
        code = st.text_area("Paste logic_utils.py", height=300)

    col1, col2, col3 = st.columns(3)
    mode = col1.selectbox("Model mode", ["auto", "live", "replay"],
                          help="live calls the model API (needs a key in .env). replay uses "
                               "recorded model responses for the bundled samples.")
    provider = col2.selectbox("Provider", ["auto", "gemini", "claude"])
    max_iters = col3.slider("Max fix attempts", 1, 5, 3)

    if st.button("Investigate 🔍", type="primary"):
        try:
            client = make_client(mode, provider)
        except LLMError as exc:
            st.error(str(exc))
            return
        with st.spinner("Investigating: testing, retrieving, proposing, verifying..."):
            st.session_state.ai_report = GlitchInvestigator(
                client, max_iterations=max_iters).investigate(code)

    report = st.session_state.get("ai_report")
    if report is None:
        return

    STATUS_STYLE.get(report.status, st.info)(f"**{report.status}**: {report.summary}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Confidence", f"{report.confidence:.2f}")
    m2.metric("Tests before", report.tests_before or "n/a")
    m3.metric("Tests after", report.tests_after or "n/a")

    with st.expander("Agent trace (every step it took)", expanded=True):
        for step in report.steps:
            st.markdown(f"**{step.name}**: {step.detail}")

    if report.diagnosis:
        st.subheader("Diagnosis")
        st.write(report.diagnosis)
        if report.cited_patterns:
            st.caption("Grounded in knowledge-base docs: " + ", ".join(report.cited_patterns))
        st.markdown("\n".join(f"- {c}" for c in report.changes))

    if report.fixed_code:
        st.subheader("Proposed fix (human review required)")
        st.code(report.diff(), language="diff")
        st.download_button("Download fixed logic_utils.py", report.fixed_code,
                           file_name="logic_utils_fixed.py")
        st.caption("Nothing is applied automatically. Review the diff, then replace "
                   "logic_utils.py yourself if you agree with it.")
