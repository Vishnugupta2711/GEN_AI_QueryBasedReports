# backend/routes/upload_excel.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from app.services.upload_service import ingest_file_to_db
import traceback
from utils.db_utils import refresh_schema_cache
from utils.chroma_utils import sync_chroma_schema_embeddings

router = APIRouter()

@router.post("/")
async def upload_excel(
    file: UploadFile = File(...),
    table_name: Optional[str] = Form(None),
    db_name: str = Form(...),
    if_exists: str = Form("replace")  # allowed: replace, append, fail
):
    if if_exists not in ("replace", "append", "fail"):
        raise HTTPException(status_code=400, detail="if_exists must be one of 'replace','append','fail'")

    try:
        result = await ingest_file_to_db(file,db_name=db_name, table_name=table_name, if_exists=if_exists)

         # Step 2: Refresh SQLAlchemy cache
        refresh_schema_cache(db_name)

        # Step 3: Rebuild Chroma schema embeddings
        sync_chroma_schema_embeddings(db_name)

        return {"status": "success", **result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
