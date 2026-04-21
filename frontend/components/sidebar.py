import streamlit as st
from utils.api import list_databases, list_tables, execute_sql
from utils.api import BASE_URL
import requests

def sidebar_ui():
    st.sidebar.header("⚙️ Database Settings")

    

    # --- Step 1: Select Database ---
    db_response = list_databases()
    
    # Check for connection errors
    if "error" in db_response:
        st.sidebar.error(db_response["error"])
        st.sidebar.info("💡 Make sure the backend server is running: `uvicorn main:app --reload`")
        return None
    
    databases = db_response.get("databases", [])
    if not databases:
        st.sidebar.warning("No databases found. Please upload a file first.")
        return None

    db_selected = st.sidebar.selectbox("Select Database", databases)

     # --- 🔄 Refresh schema button ---
    if st.sidebar.button("🔄 Refresh Schema & Embeddings"):
        try:
            r = requests.post(f"{BASE_URL}/refresh/", json={"db_name": db_selected})
            if r.status_code == 200:
                st.sidebar.success(r.json().get("message", "Schema refreshed ✅"))
            else:
                st.sidebar.error(r.text)
        except Exception as e:
            st.sidebar.error(f"Error refreshing schema: {e}")

    # --- Step 2: Select Table ---
    table_response = list_tables(db_selected)
    tables = table_response.get("tables", [])
    if not tables:
        st.sidebar.warning(f"No tables found in database '{db_selected}'.")
        return {"db_name": db_selected, "table_name": None}

    table_selected = st.sidebar.selectbox("Select Table", tables)

    # --- Step 3: Optional Table Preview ---
    st.sidebar.markdown("### 🔍 Preview Selected Table")
    if table_selected:
        try:
            preview_sql = f"SELECT * FROM `{table_selected}` LIMIT 5;"
            result = execute_sql(preview_sql, db_selected)

            if result.get("status") == "success":
                st.sidebar.dataframe(result.get("rows"))
            else:
                st.sidebar.error(result.get("detail", "Failed to load preview."))

        except Exception as e:
            st.sidebar.error(f"Error previewing table: {e}")

    # --- Step 4: Return both DB and Table ---
    return {"db_name": db_selected, "table_name": table_selected}
