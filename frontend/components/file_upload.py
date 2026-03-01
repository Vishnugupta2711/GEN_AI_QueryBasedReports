import streamlit as st
from utils.api import upload_file

def upload_ui(db_selected):
    st.subheader("Upload Table")
    uploaded_file = st.file_uploader("Upload Excel/CSV", type=["xlsx","xls","csv"])
    table_name = st.text_input("Optional table name")
    if uploaded_file and st.button("Ingest Table"):
        with open("temp_upload.xlsx","wb") as f:
            f.write(uploaded_file.getbuffer())
            result = upload_file("temp_upload.xlsx", table_name, db_selected["db_name"])
        st.success(f"Table created: {result.get('table_name')}")
        st.write(result)


