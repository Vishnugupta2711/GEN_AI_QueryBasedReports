from fastapi import APIRouter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import os

router = APIRouter()

@router.get("/chroma/{db_name}")
def debug_chroma(db_name: str):
    """
    Returns documents and metadata from Chroma schema and few-shot stores.
    """
    try:
        embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

        # Schema collection
        schema_dir = f"./chroma_schemas/{db_name}"
        schema_coll_name = f"schema_{db_name}"
        schema_store = Chroma(collection_name=schema_coll_name, embedding_function=embedding_model, persist_directory=schema_dir)
        schema_docs = schema_store._collection.get(include=["documents", "metadatas"])

        # Few-shot collection
        ex_store = Chroma(collection_name="fewshot_examples", embedding_function=embedding_model, persist_directory="./chroma_examples")
        ex_docs = ex_store._collection.get(include=["documents", "metadatas"])

        return {
            "schema_docs": schema_docs,
            "example_docs": ex_docs,
            "status": "success"
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
