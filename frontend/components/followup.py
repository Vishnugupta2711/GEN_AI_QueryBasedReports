import streamlit as st
import pandas as pd
from utils.api import nl_to_sql, execute_sql  # ✅ use your unified API helpers

def followup_ui(db_selected):
    """
    Handle follow-up questions for contextual query generation.
    db_selected: dict -> {"db_name": "unox", "table_name": "movies"}
    """

    st.subheader("🔁 Follow-up Question")

    # --- Initialize session state safely ---
    if "last_result_df" not in st.session_state:
        st.session_state.last_result_df = pd.DataFrame()

    if "last_sql" not in st.session_state:
        st.session_state.last_sql = ""

    if "last_followup_sql" not in st.session_state:
        st.session_state.last_followup_sql = ""

    # --- Display previous result if available ---
    if not st.session_state.last_result_df.empty:
        st.markdown("**Previous Result:**")
        st.dataframe(st.session_state.last_result_df)
    else:
        st.info("No previous result found. Please run a main query first.")

    # --- User input for follow-up ---
    followup = st.text_input("Ask a follow-up question related to the previous result")

    # --- Generate follow-up SQL ---
    if st.button("Generate Follow-up SQL") and followup:
        if not st.session_state.last_sql:
            st.warning("Please run a main query first before asking a follow-up.")
            return

        with st.spinner("Generating follow-up SQL using Gemini..."):
            try:
                # ✅ Call the same /nl2sql API but give extra context (previous query)
                context_question = f"""
                Previous SQL Query: {st.session_state.last_sql}
                Follow-up Question: {followup}
                """

                # --- Use your existing API helper ---
                sql_result = nl_to_sql(
                    context_question,
                    db_selected["db_name"],
                    db_selected["table_name"]
                )

                followup_sql = sql_result.get("sql_query")
                st.session_state.last_followup_sql = followup_sql

                if not followup_sql:
                    st.error("No SQL query generated for follow-up.")
                    return

                st.success("✅ Generated SQL for follow-up:")
                st.code(followup_sql, language="sql")

                # --- (Optional) Run the follow-up query immediately ---
                with st.spinner("Running follow-up query..."):
                    result = execute_sql(followup_sql, db_selected["db_name"])

                if result.get("status") == "success":
                    df = pd.DataFrame(result["rows"])
                    st.session_state.last_result_df = df
                    st.dataframe(df)
                else:
                    st.error(result.get("detail", result.get("error", "Query failed.")))

            except Exception as e:
                st.error(f"Error while generating follow-up: {e}")
