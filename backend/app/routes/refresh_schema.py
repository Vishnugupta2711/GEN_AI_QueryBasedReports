# backend/app/routes/refresh_schema.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import traceback
from utils.db_utils import refresh_schema_cache
from utils.chroma_utils import sync_chroma_schema_embeddings

router = APIRouter()

class DBRefreshRequest(BaseModel):
    db_name: str

@router.post("/")
def refresh_schema_and_embeddings(request: DBRefreshRequest):
    """
    Refresh both SQLAlchemy schema cache and Chroma embeddings for the selected DB.
    """
    try:
        db_name = request.db_name
        refresh_schema_cache(db_name)
        sync_chroma_schema_embeddings(db_name)
        
        return {
            "status": "success",
            "message": f"Schema cache + embeddings refreshed for '{db_name}' ✅"
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh schema for '{request.db_name}': {e}"
        )
