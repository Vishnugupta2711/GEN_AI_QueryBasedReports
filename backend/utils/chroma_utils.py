# utils/chroma_utils.py
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from sqlalchemy import inspect
from utils.db import get_engine_for_db
import os, traceback

def sync_chroma_schema_embeddings(db_name: str):
    """
    Incrementally synchronize Chroma embeddings with the DB schema:
    - Adds new tables if missing
    - Removes deleted ones
    - Updates modified tables
    ✅ Returns the active Chroma store instance for immediate querying.
    """

    persist_dir = f"./chroma_schemas/{db_name}"
    os.makedirs(persist_dir, exist_ok=True)

    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    store = Chroma(
        collection_name=f"schema_{db_name}",   # unified consistent name
        embedding_function=embedding_model,
        persist_directory=persist_dir
    )

    try:
        # 1️⃣ Fetch live DB schema
        engine = get_engine_for_db(db_name)
        inspector = inspect(engine)
        live_tables = inspector.get_table_names()

        # 2️⃣ Fetch existing Chroma docs
        existing = store.get()
        existing_docs = existing.get("documents", [])
        existing_ids = existing.get("ids", [])
        existing_tables = set()

        for doc in existing_docs:
            if "Table:" in doc:
                tbl = doc.split("Table:")[1].split("\n")[0].strip()
                existing_tables.add(tbl)

        # 3️⃣ Add or update tables
        added, updated, removed = 0, 0, 0
        for table in live_tables:
            cols = inspector.get_columns(table)
            col_names = [col["name"] for col in cols]
            col_types = [str(col["type"]) for col in cols]
            doc = f"Table: {table}\nColumns: {', '.join(col_names)}\nTypes: {', '.join(col_types)}"

            if table not in existing_tables:
                store.add_texts([doc], metadatas=[{"table": table}])
                added += 1
            else:
                for i, old_doc in enumerate(existing_docs):
                    if f"Table: {table}" in old_doc and old_doc != doc:
                        store.delete(ids=[existing_ids[i]])
                        store.add_texts([doc], metadatas=[{"table": table}])
                        updated += 1

        # 4️⃣ Remove deleted tables
        for i, old_doc in enumerate(existing_docs):
            if not any(tbl in old_doc for tbl in live_tables):
                store.delete(ids=[existing_ids[i]])
                removed += 1

        print(f"[Chroma Sync] ✅ schema_{db_name} → added={added}, updated={updated}, removed={removed}")

    except Exception as e:
        print(f"[Chroma Sync] ❌ Error while syncing schema for '{db_name}': {e}")
        traceback.print_exc()

    # ✅ Return the store so it can be used immediately for similarity search
    return store
