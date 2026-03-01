# backend/utils/db_utils.py
import re
import pandas as pd
from sqlalchemy import Integer, Float, DateTime, String
from sqlalchemy.inspection import inspect
from sqlalchemy import inspect
from utils.db import get_engine_for_db
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import shutil, os, chromadb
from utils.chroma_utils import sync_chroma_schema_embeddings


from chromadb.config import Settings



def sanitize_name(name: str) -> str:
    name = str(name).strip()
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'[^\w_]', '', name)
    name = re.sub(r'^[0-9]+', '', name)
    name = name.lower() or 'col'
    # prevent empty or reserved names
    if name == '':
        name = 'col'
    return name

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        # convert empty string to None
        df[col] = df[col].replace({'': None})
    return df

def infer_sql_type(dtype):
    # return SQLAlchemy column types
    if pd.api.types.is_integer_dtype(dtype):
        return Integer()
    elif pd.api.types.is_float_dtype(dtype):
        return Float()
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return DateTime()
    else:
        return String(255)

def refresh_schema_cache(db_name: str):
    """
    Refreshes SQLAlchemy metadata and synchronizes Chroma embeddings incrementally.
    This version no longer deletes directories — it safely updates embeddings.
    """
    # 1️⃣ Refresh SQLAlchemy cache
    engine = get_engine_for_db(db_name)
    engine.dispose()
    print(f"[Schema Refresh] ✅ Cleared SQLAlchemy cache for database '{db_name}'")

    # 2️⃣ Incremental Chroma sync
    try:
        sync_chroma_schema_embeddings(db_name)
        print(f"[Chroma Refresh] ✅ Synced embeddings incrementally for '{db_name}'")
    except Exception as e:
        print(f"[Chroma Refresh] ⚠️ Failed to sync embeddings for '{db_name}': {e}")