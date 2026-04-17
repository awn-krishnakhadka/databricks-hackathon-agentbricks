import re
import streamlit as st
import pandas as pd
from utils.db import sqlQueryWithHttpPath

# Warehouse that originally ran the queries we want to replay
SOURCE_WAREHOUSE_ID = "20b9f65d4a8c7b8e"

# New warehouse to use for replaying
REPLAY_HTTP_PATH = "/sql/1.0/warehouses/ed74c81ceff22252"

# Tables to replay against
ORIGINAL_TABLE = "prod_observations_catalog.silver.axes_observations"
REPLAY_TABLE = "prod_staging_catalog.experiments.silver_axes_observations"


@st.cache_data(ttl=120)
def load_history() -> pd.DataFrame:
    """Fetch historical queries for the source warehouse from querybroker_history."""
    # SOURCE_WAREHOUSE_ID is a hardcoded constant (not user input), so interpolation
    # here does not introduce a SQL injection risk.
    query = (
        "SELECT"
        "  query_id,"
        "  query_text,"
        "  query_start_time_ms,"
        "  query_end_time_ms,"
        "  status,"
        "  user_name,"
        "  executed_as_user_name,"
        "  compute.warehouse_id AS warehouse_id"
        " FROM system_archive.query.querybroker_history"
        f" WHERE compute.warehouse_id = '{SOURCE_WAREHOUSE_ID}'"
        " ORDER BY query_start_time_ms DESC"
        " LIMIT 200"
    )
    return sqlQueryWithHttpPath(query, REPLAY_HTTP_PATH)


def swap_table(query_text: str, original: str, replacement: str) -> str:
    """Replace all occurrences of *original* table reference with *replacement* in a query.

    Uses negative look-around assertions to avoid replacing the name when it appears
    as a substring of a longer identifier (e.g. a table with a similar prefix/suffix).
    """
    # Escape dots (catalog.schema.table) and add word-boundary-like anchors so we
    # don't accidentally match partial identifiers.
    escaped = re.escape(original)
    pattern = r"(?<![.\w])" + escaped + r"(?![.\w])"
    return re.sub(pattern, replacement, query_text, flags=re.IGNORECASE)


def show_page():
    st.title("🔁 Query Replay")
    st.markdown(
        f"""
        Replay historical queries that ran on warehouse **`{SOURCE_WAREHOUSE_ID}`** using the
        new warehouse **`{REPLAY_HTTP_PATH.split('/')[-1]}`**.

        Each query is executed **twice** — once against the **original** table and once against
        the **replay (staging)** table — so you can compare results side-by-side.

        | | Table |
        |---|---|
        | **Original** | `{ORIGINAL_TABLE}` |
        | **Replay** | `{REPLAY_TABLE}` |
        """
    )

    st.divider()

    # ------------------------------------------------------------------ #
    # Load query history
    # ------------------------------------------------------------------ #
    with st.spinner("Loading query history…"):
        try:
            history_df = load_history()
        except Exception as exc:
            st.error(f"❌ Failed to load query history: {exc}")
            return

    if history_df.empty:
        st.warning("No queries found for the specified warehouse.")
        return

    st.markdown(f"**{len(history_df)} queries** found in history (most recent first).")

    # Allow user to browse and filter history
    search = st.text_input("🔍 Filter queries (keyword search in SQL text)", "")
    if search.strip():
        mask = history_df["query_text"].str.contains(search, case=False, na=False)
        display_df = history_df[mask].reset_index(drop=True)
    else:
        display_df = history_df.reset_index(drop=True)

    st.dataframe(
        display_df[["query_id", "user_name", "status", "query_start_time_ms", "query_text"]],
        use_container_width=True,
        height=300,
    )

    st.divider()

    # ------------------------------------------------------------------ #
    # Query selection & replay
    # ------------------------------------------------------------------ #
    st.subheader("Run Replay")

    query_ids = display_df["query_id"].tolist()
    if not query_ids:
        st.info("No queries match the current filter.")
        return

    selected_id = st.selectbox("Select a query to replay", options=query_ids)
    row = display_df[display_df["query_id"] == selected_id].iloc[0]
    original_sql = row["query_text"]

    st.markdown("**Original SQL:**")
    st.code(original_sql, language="sql")

    replay_sql = swap_table(original_sql, ORIGINAL_TABLE, REPLAY_TABLE)
    if replay_sql != original_sql:
        st.markdown("**Replay SQL** *(table reference replaced)*:")
        st.code(replay_sql, language="sql")
    else:
        st.info(
            f"ℹ️ The selected query does not reference `{ORIGINAL_TABLE}` directly. "
            "Both runs will execute the same SQL."
        )

    col_run1, col_run2, _ = st.columns([1, 1, 4])
    run_both = col_run1.button("▶ Run Both", type="primary")
    clear = col_run2.button("🗑 Clear Results")

    if clear:
        for key in ("result_original", "result_replay", "error_original", "error_replay"):
            st.session_state.pop(key, None)

    if run_both:
        # Run against original table
        with st.spinner(f"Running against original table `{ORIGINAL_TABLE}`…"):
            try:
                st.session_state["result_original"] = sqlQueryWithHttpPath(
                    original_sql, REPLAY_HTTP_PATH
                )
                st.session_state.pop("error_original", None)
            except Exception as exc:
                st.session_state["error_original"] = str(exc)
                st.session_state.pop("result_original", None)

        # Run against replay/staging table
        with st.spinner(f"Running against replay table `{REPLAY_TABLE}`…"):
            try:
                st.session_state["result_replay"] = sqlQueryWithHttpPath(
                    replay_sql, REPLAY_HTTP_PATH
                )
                st.session_state.pop("error_replay", None)
            except Exception as exc:
                st.session_state["error_replay"] = str(exc)
                st.session_state.pop("result_replay", None)

    # ------------------------------------------------------------------ #
    # Display results
    # ------------------------------------------------------------------ #
    if any(k in st.session_state for k in ("result_original", "error_original",
                                            "result_replay", "error_replay")):
        st.divider()
        st.subheader("Results Comparison")

        left, right = st.columns(2)

        with left:
            st.markdown(f"#### Original\n`{ORIGINAL_TABLE}`")
            if "error_original" in st.session_state:
                st.error(f"Query failed: {st.session_state['error_original']}")
            elif "result_original" in st.session_state:
                df_orig = st.session_state["result_original"]
                st.success(f"{len(df_orig):,} rows returned")
                st.dataframe(df_orig, use_container_width=True)

        with right:
            st.markdown(f"#### Replay\n`{REPLAY_TABLE}`")
            if "error_replay" in st.session_state:
                st.error(f"Query failed: {st.session_state['error_replay']}")
            elif "result_replay" in st.session_state:
                df_replay = st.session_state["result_replay"]
                st.success(f"{len(df_replay):,} rows returned")
                st.dataframe(df_replay, use_container_width=True)

        # Row-count diff summary
        if "result_original" in st.session_state and "result_replay" in st.session_state:
            orig_rows = len(st.session_state["result_original"])
            replay_rows = len(st.session_state["result_replay"])
            diff = replay_rows - orig_rows
            if diff == 0:
                st.success("✅ Both tables returned the same number of rows.")
            else:
                sign = "+" if diff > 0 else ""
                st.warning(
                    f"⚠️ Row count difference: replay has **{sign}{diff}** rows "
                    f"({orig_rows:,} original vs {replay_rows:,} replay)."
                )
