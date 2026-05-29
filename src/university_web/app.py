"""Streamlit demo + validation app for the University QA agent (multi-page).

Two deliberately separate PAGES over one SQLite file (switch via the sidebar nav):
- Data view (admin/validation): a DIRECT, read-only DB read of every table, shown in an
  Ag-Grid with per-column sort + filter. Bypasses the agent and per-user scoping; use it to
  check the agent's answers against ground truth.
- Query tool (scoped agent path): the real agent (role -> user -> question), with identity
  enforced server-side by the MCP server. A student sees only their own data; an admin all.

Run: `uv run streamlit run src/university_web/app.py` (or `uv run university-agent-web`).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from st_aggrid import AgGrid, GridOptionsBuilder

from university_db.directory import list_users_by_role
from university_db.engine import make_engine
from university_db.roles import Role
from university_db.seed import SeedConfig
from university_web import data
from university_web.agent_runner import run_question

load_dotenv()
os.environ.setdefault("LANGSMITH_PROJECT", "university-agent")

# One working DB file for the whole session, shared by both pages.
DB_PATH = Path(tempfile.gettempdir()) / "university_web_demo.db"
DB_URL = f"sqlite:///{DB_PATH}"


def _sidebar_data_control() -> None:
    """Shared sidebar (both pages): choose a data source and (re)build the working DB."""
    st.sidebar.header("Data control")
    source_label = st.sidebar.radio(
        "Working database",
        ("Fixed fixture (evals/fixture.sql)", "Fresh random seed"),
        help="The fixture is the deterministic eval dataset; the seed is freshly generated.",
    )
    config: SeedConfig | None = None
    if source_label.startswith("Fresh"):
        config = SeedConfig(
            students=st.sidebar.number_input("students", 5, 300, 50),
            teachers=st.sidebar.number_input("teachers", 2, 60, 10),
            courses=st.sidebar.number_input("courses", 5, 80, 20),
            semesters=st.sidebar.number_input("semesters", 2, 12, 6),
        )

    if st.sidebar.button("Load / rebuild database", type="primary"):
        source = "fixture" if source_label.startswith("Fixed") else "seed"
        with st.spinner("Building database…"):
            st.session_state["counts"] = data.build_db(DB_PATH, source=source, config=config)
        st.session_state["loaded"] = True
        st.session_state["source"] = source_label

    if st.session_state.get("loaded"):
        st.sidebar.success(f"Loaded: {st.session_state['source']}")
        st.sidebar.caption(f"`{DB_URL}`")
        st.sidebar.table(
            pd.DataFrame(
                sorted(st.session_state["counts"].items()), columns=["table", "rows"]
            ).set_index("table")
        )


def _require_db() -> None:
    """Stop the page early (with guidance) until a database has been loaded."""
    if not st.session_state.get("loaded"):
        st.info("⬅️ Load a database from the sidebar to begin.")
        st.stop()


def _grid(df: pd.DataFrame, *, key: str) -> None:
    """Render a dataframe in Ag-Grid with sort + per-column filtering at the header.

    Each column header gets a sort toggle, a filter menu, and a floating filter input row
    right under the header — so filtering is implicit and per-column, not a separate widget.
    """
    builder = GridOptionsBuilder.from_dataframe(df)
    builder.configure_default_column(
        sortable=True, filter=True, floatingFilter=True, resizable=True
    )
    AgGrid(
        df,
        gridOptions=builder.build(),
        theme="streamlit",
        height=520,
        fit_columns_on_grid_load=True,
        key=key,
    )


def data_view() -> None:
    """Data view page — read-only direct DB browser for validating the agent's answers."""
    _require_db()
    st.title("🛠️ Data view — admin / validation")
    st.caption(
        "Direct, **read-only** read of the raw tables. This **bypasses the agent and per-user "
        "scoping** — it exists so you can verify the agent's answers against ground truth. "
        "It is NOT the scoped agent path."
    )
    table = st.selectbox("Table", data.TABLES)
    df = data.read_table(DB_URL, table)
    st.caption(f"{len(df)} row(s) — sort and filter from each column header.")
    _grid(df, key=f"grid_{table}")


def query_tool() -> None:
    """Query tool page — the scoped agent path: role -> user -> question -> answer/SQL/rows."""
    _require_db()
    st.title("🤖 Query tool — scoped agent")
    st.caption(
        "The agent translates your question to SQL and runs it through the MCP server, which "
        "enforces identity **server-side**: a student sees only their own enrollments/grades, "
        "a teacher their courses and students, an admin everything."
    )

    engine = make_engine(DB_URL, read_only=True)
    role = st.selectbox("Role", [r.value for r in Role])
    users = list_users_by_role(engine, Role(role))
    if not users:
        st.warning(f"No users with role '{role}' in this database.")
        return
    user = st.selectbox("Identify as", users)
    question = st.text_input("Question", placeholder="e.g. what is my average grade?")

    if st.button("Ask the agent", type="primary", disabled=not question.strip()):
        with st.spinner("Running agent…"):
            result = run_question(question.strip(), user, DB_URL, role=role)
        final = result.final

        st.markdown("#### Answer")
        st.write(final.get("answer") or "_(no answer)_")

        if final.get("sql"):
            st.markdown("#### Generated SQL")
            st.code(final["sql"], language="sql")

        res = final.get("result") or {}
        if res.get("status") == "ok" and res.get("rows"):
            st.markdown("#### Result rows")
            _grid(pd.DataFrame(res["rows"]), key="agent_result_grid")
        elif res:
            st.markdown("#### Result")
            st.json(res)

        with st.expander("Reasoning & scope decision"):
            st.json({k: final.get(k) for k in ("reasoning", "in_scope", "is_compound")})

        if result.trace_url:
            st.markdown(f"🔍 [View LangSmith trace]({result.trace_url})")


def main() -> None:
    """Wire the shared sidebar and the two pages into a multi-page app."""
    st.set_page_config(page_title="University QA Agent — demo & validation", layout="wide")
    _sidebar_data_control()
    navigation = st.navigation(
        [
            st.Page(data_view, title="Data view", icon="🛠️", url_path="data", default=True),
            st.Page(query_tool, title="Query tool", icon="🤖", url_path="query"),
        ]
    )
    navigation.run()


if __name__ == "__main__":
    main()
