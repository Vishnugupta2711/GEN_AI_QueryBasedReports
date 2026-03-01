from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.summarize_service import summarize_sql_result
from utils.sql_readonly_validator import is_read_only_query
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class SummarizeRequest(BaseModel):
    db_name: str
    sql_query: str

@router.post("/")
def summarize_query(request: SummarizeRequest):
    try:
        if not is_read_only_query(request.sql_query):
            logger.warning("Rejected non-read-only query in summarize API: %s", request.sql_query)
            raise HTTPException(status_code=400, detail="Only read-only queries are allowed")

        result = summarize_sql_result(request.sql_query, request.db_name)
        if "error" in result:
            # Handle quota exceeded errors with appropriate status code
            if result.get("quota_exceeded"):
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": result.get("error", "API quota exceeded"),
                        "details": result.get("details", ""),
                        "quota_exceeded": True
                    }
                )
            # Other errors return 500
            raise HTTPException(status_code=500, detail=result["error"])
        return {"status": "success", **result}
    except HTTPException:
        # Re-raise HTTP exceptions (like 429) as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")