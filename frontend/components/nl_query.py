import streamlit as st
from utils.api import nl_to_sql

def nl_query_ui(db_selected):
    """
    UI component for Natural Language to SQL conversion.
    Expects db_selected = {"db_name": "...", "table_name": "..."}
    """
    st.subheader("💬 Ask a Natural Language Question")

    # Input field for the user's question
    question = st.text_input("Enter your question here")

    # When user clicks Generate SQL
    if question and st.button("Generate SQL"):
        with st.spinner("Generating SQL from your question..."):
            # ✅ Pass both db_name and table_name to backend
            sql_result = nl_to_sql(
                question,
                db_selected["db_name"],
                db_selected["table_name"]
            )

        # ✅ Display result
        if sql_result.get("status") == "success":
            sql_query = sql_result.get("sql_query")
            st.code(sql_query, language="sql")
            st.session_state["last_sql"] = sql_query
        else:
            error_msg = sql_result.get("error", "Failed to generate SQL query.")
            st.error(error_msg)
