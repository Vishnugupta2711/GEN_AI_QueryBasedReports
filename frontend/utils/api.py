import requests
import streamlit as st

BASE_URL = "http://127.0.0.1:8000/api"

def list_databases():
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        try:
            return r.json()
        except Exception:
            print("Response text:", r.text)
            return {"databases": [], "error": "Invalid response"}
    except requests.exceptions.ConnectionError:
        return {"databases": [], "error": "Cannot connect to backend. Please ensure the backend server is running."}
    except Exception as e:
        return {"databases": [], "error": str(e)}


def list_tables(db_name):
    r = requests.get(f"{BASE_URL}/{db_name}")
    return r.json()

def upload_file(file_path, table_name=None, db_name=None, if_exists="replace"):
    with open(file_path, "rb") as f:
        files = {"file": (file_path, f)}
        data = {"table_name": table_name, "if_exists": if_exists, "db_name": db_name}
        r = requests.post(f"{BASE_URL}/upload/", files=files, data=data)
    return r.json()

# def nl_to_sql(question, db_name):
#     r = requests.post(f"{BASE_URL}/nl2sql/", json={"question": question, "db_name": db_name})
#     return r.json()

def nl_to_sql(question,db_name, table_name):
    """
    Calls /nl2sql endpoint with the selected table.
    """
    payload = {
        "question": question,
        "db_name": db_name,
        "table_name": table_name
    }
    r = requests.post(f"{BASE_URL}/nl2sql/", json=payload)
    try:
        return r.json()
    except Exception:
        st.error(f"Failed to parse response from backend: {r.text}")
        return {"status": "error", "error": "Invalid response"}


def execute_sql(sql_query, db_name):
    r = requests.post(f"{BASE_URL}/execute/", json={"sql_query": sql_query, "db_name": db_name})
    return r.json()

def ingest_data_file(file_path, filename, db_name):
    """
    Calls the intelligent ingestion endpoint with file upload.
    """
    with open(file_path, "rb") as f:
        files = {"file": (filename, f)}
        data = {"db_name": db_name}
        r = requests.post(f"{BASE_URL}/ingest/", files=files, data=data)
    return r.json()
