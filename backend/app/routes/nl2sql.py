from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.nl2sql_service import generate_sql_from_nl
import traceback

router = APIRouter()

class NLQueryRequest(BaseModel):
    question: str
    db_name: str
    table_name: str


@router.post("/")
def nl2sql_route(request: NLQueryRequest):
    """
    Converts a natural language question into an SQL query for a specific database and table.
    """
    try:
        response = generate_sql_from_nl(
            question=request.question,
            db_name=request.db_name,
            table_name=request.table_name
        )
        return {"status": "success", **response}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
