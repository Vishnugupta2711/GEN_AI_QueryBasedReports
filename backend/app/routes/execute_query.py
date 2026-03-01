from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from utils.db import get_engine_for_db
from utils.sql_readonly_validator import is_read_only_query
import pandas as pd
import numpy as np
import logging
import traceback, json

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    sql_query: str
    db_name: str


@router.post("/")
def execute_query(request: QueryRequest):
    try:
        if not is_read_only_query(request.sql_query):
            logger.warning("Rejected non-read-only query in execute API: %s", request.sql_query)
            raise HTTPException(status_code=400, detail="Only read-only queries are allowed")

        engine = get_engine_for_db(request.db_name)
        with engine.connect() as conn:
            df = pd.read_sql(request.sql_query, conn)

        # --- Step 1: Clean numeric edge cases ---
        df = df.replace([np.inf, -np.inf], None)
        df = df.where(pd.notnull(df), None)

        # --- Step 2: Convert all timestamps/dates to strings ---
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype(str)

        # --- Step 3: Convert to plain Python objects ---
        df = df.astype(object)

        response = {
            "status": "success",
            "rows": df.to_dict(orient="records"),
            "columns": list(df.columns),
            "row_count": len(df)
        }

        # --- Step 4: Validate JSON safety ---
        try:
            json.dumps(response, allow_nan=False)
        except (TypeError, ValueError):
            def clean_for_json(obj):
                if isinstance(obj, float):
                    if np.isnan(obj) or np.isinf(obj):
                        return None
                elif isinstance(obj, dict):
                    return {k: clean_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [clean_for_json(x) for x in obj]
                elif hasattr(obj, "isoformat"):  # Handle datetime objects
                    return obj.isoformat()
                return obj

            response = clean_for_json(response)

        return response

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}
