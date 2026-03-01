import streamlit as st
from utils.api import execute_sql
import pandas as pd

def sql_editor_ui(db_selected):
    st.subheader("🧠 Edit & Execute SQL")

    if "last_sql" in st.session_state:
        edited_sql = st.text_area("Edit SQL if needed", value=st.session_state["last_sql"])

        if st.button("Run SQL"):
            with st.spinner("Running query..."):
                result = execute_sql(edited_sql, db_selected["db_name"])

            # --- Handle backend errors gracefully ---
            if result.get("status") != "success":
                st.error(result.get("detail", result.get("error", "Query failed.")))
                return

            rows = result.get("rows") or []
            if not rows:
                st.warning("No data returned from the query.")
                return

            # ✅ Convert result into DataFrame
            df = pd.DataFrame(rows)
            st.dataframe(df)

            # ✅ Store result + query for follow-up usage
            st.session_state.last_result_df = df
            st.session_state.last_sql = edited_sql

            # Optional: visualize numeric columns
            numeric_cols = df.select_dtypes(include="number").columns
            if len(numeric_cols):
                st.line_chart(df[numeric_cols])
