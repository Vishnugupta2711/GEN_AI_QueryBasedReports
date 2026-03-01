import streamlit as st
from components.sidebar import sidebar_ui
from components.nl_query import nl_query_ui
from components.sql_editor import sql_editor_ui
from components.followup import followup_ui
from components.result_viewer import show_result_summary


st.set_page_config(
    page_title="NL2SQL Intelligence",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_css():
    with open("frontend/assets/styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
load_css()

# Initialize session state for page navigation
if "current_page" not in st.session_state:
    st.session_state.current_page = "main"

# Sidebar navigation
st.sidebar.title("🧠 NL2SQL Intelligence")
page = st.sidebar.radio(
    "Navigate",
    ["Main Dashboard", "Ingest Data"],
    index=0 if st.session_state.current_page == "main" else 1
)

if page == "Ingest Data":
    st.session_state.current_page = "ingest"
    # Import and show ingestion page
    from components.data_ingestion import data_ingestion_page
    data_ingestion_page()
else:
    st.session_state.current_page = "main"
    st.title("NL2SQL Dashboard")
    
    # Sidebar for database selection
    db_selected = sidebar_ui()
    
    if db_selected:
        # Two columns for query & results
        col1, col2 = st.columns([1,1])
        
        with col1:
            nl_query_ui(db_selected)
            followup_ui(db_selected)
        
        with col2:
            sql_editor_ui(db_selected)
            if "last_sql" in st.session_state and st.session_state["last_sql"]:
              sql_query = st.session_state["last_sql"]
              show_result_summary(sql_query, db_selected)
    else:
        st.info("Please select a database from the sidebar to get started.")
