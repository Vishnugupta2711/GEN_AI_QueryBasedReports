import streamlit as st
from utils.api import list_databases, ingest_data_file
import requests

def data_ingestion_page():
    """
    Data ingestion page with intelligent analysis using Gemini and ChromaDB matching.
    """
    st.title("📥 Data Ingestion & Analysis")
    st.markdown("Upload Excel or PDF files for intelligent data ingestion with automatic table/column matching.")
    
    # Database selection
    db_response = list_databases()
    
    # Check for connection errors
    if "error" in db_response:
        st.error(db_response["error"])
        st.info("💡 Make sure the backend server is running: `uvicorn main:app --reload`")
        return
    
    databases = db_response.get("databases", [])
    if not databases:
        st.warning("No databases found. Please create a database first.")
        return
    
    selected_db = st.selectbox("Select Database", databases, key="ingest_db_select")
    
    # File upload section
    st.header("📄 Upload File")
    uploaded_file = st.file_uploader(
        "Choose a file to ingest",
        type=["xlsx", "xls", "csv", "pdf"],
        key="ingest_file_upload"
    )
    
    if uploaded_file:
        st.info(f"File selected: {uploaded_file.name} ({uploaded_file.size} bytes)")
        
        # Analyze Data button
        if st.button("🔍 Analyze Data", type="primary", use_container_width=True):
            with st.spinner("Analyzing file with Gemini AI and matching with existing schema..."):
                try:
                    # Save file temporarily
                    import tempfile
                    import os
                    
                    suffix = os.path.splitext(uploaded_file.name)[1]
                    # Write file to temp location
                    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tmp_file.write(uploaded_file.getbuffer())
                    tmp_file.close()
                    tmp_path = tmp_file.name
                    
                    try:
                        # Call backend API
                        result = ingest_data_file(tmp_path, uploaded_file.name, selected_db)
                    finally:
                        # Clean up temp file
                        try:
                            os.remove(tmp_path)
                        except:
                            pass
                    
                    # Display results
                    if result.get("status") == "success":
                        st.success("✅ Data ingestion completed successfully!")
                        
                        # Show summary
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Table", result.get("table_name", "N/A"))
                        with col2:
                            st.metric("Rows Added", result.get("rows_added", 0))
                        with col3:
                            st.metric("Columns", len(result.get("columns", [])))
                        
                        # Show details
                        with st.expander("📊 Ingestion Details", expanded=True):
                            st.json(result)
                        
                        # Show matching information
                        if "matches" in result:
                            st.subheader("🔗 Schema Matches")
                            matches = result["matches"]
                            
                            if matches.get("table_match"):
                                st.success(f"✅ Matched with existing table: {matches['table_match']['table_name']} (similarity: {matches['table_match']['similarity']:.2%})")
                            
                            if matches.get("column_matches"):
                                st.info("Column Matches:")
                                for col_match in matches["column_matches"]:
                                    st.write(f"  • {col_match['source_column']} → {col_match['target_column']} (similarity: {col_match['similarity']:.2%})")
                            
                            if matches.get("new_columns"):
                                st.warning(f"New columns created: {', '.join(matches['new_columns'])}")
                        
                        # Refresh option
                        if st.button("🔄 Refresh Schema & Embeddings"):
                            try:
                                r = requests.post(
                                    f"http://127.0.0.1:8000/api/refresh/",
                                    json={"db_name": selected_db}
                                )
                                if r.status_code == 200:
                                    st.success("Schema refreshed successfully!")
                                else:
                                    st.error(f"Error: {r.text}")
                            except Exception as e:
                                st.error(f"Error refreshing schema: {e}")
                    
                    else:
                        error_msg = result.get("error", "Unknown error occurred")
                        st.error(f"❌ Ingestion failed: {error_msg}")
                        
                except Exception as e:
                    st.error(f"❌ Error during ingestion: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
    
    # Information section
    with st.expander("ℹ️ How It Works"):
        st.markdown("""
        ### Intelligent Data Ingestion
        
        This system uses **Gemini AI** and **ChromaDB** to intelligently match your data with existing database schema:
        
        1. **File Analysis**: Gemini AI analyzes the uploaded file (Excel/PDF) to understand its structure and content
        2. **Table Matching**: ChromaDB checks if the data matches any existing table using cosine similarity
        3. **Column Matching**: For each column, ChromaDB finds the best matching existing column
        4. **Smart Insertion**: 
           - If table/column matches (above threshold), data is inserted into existing structure
           - If no match found, new table/columns are created
        5. **Schema Update**: ChromaDB embeddings are updated with the new schema
        
        ### Supported Formats
        - **Excel** (.xlsx, .xls, .csv): Direct table parsing
        - **PDF** (.pdf): Text extraction and structured data parsing using Gemini AI
        
        ### Matching Threshold
        - Table similarity threshold: 0.7 (70%)
        - Column similarity threshold: 0.65 (65%)
        """)

