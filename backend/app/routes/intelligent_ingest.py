"""
Backend route for intelligent data ingestion.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.intelligent_ingestion_service import intelligent_ingest_file
import traceback

router = APIRouter()

@router.post("/")
async def intelligent_ingest(
    file: UploadFile = File(...),
    db_name: str = Form(...)
):
    """
    Intelligently ingest Excel or PDF file with Gemini AI analysis and ChromaDB matching.
    """
    try:
        result = await intelligent_ingest_file(file, db_name)
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
        return result
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

