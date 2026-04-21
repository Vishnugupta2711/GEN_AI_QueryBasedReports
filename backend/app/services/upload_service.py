import tempfile
import os
import pandas as pd
from fastapi import UploadFile
from sqlalchemy import text
from utils.db import get_engine_for_db, root_engine
from utils.db_utils import sanitize_name, clean_dataframe, infer_sql_type


async def ingest_file_to_db(file: UploadFile, db_name: str, table_name: str = None, if_exists: str = "replace"):
    """
    Ingests an uploaded CSV/XLSX into the selected database and creates/overwrites a table.
    - Auto-creates the database if missing
    - Cleans data and column names
    - Returns clean JSON always (never HTML)
    """
    suffix = ".csv" if file.filename.lower().endswith(".csv") else ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

    try:
        # --- Step 1: Save the uploaded file temporarily
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        tmp_path = tmp.name

        # --- Step 2: Read CSV/XLSX into DataFrame
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(tmp_path)
        else:
            df = pd.read_excel(tmp_path, engine="openpyxl")

        # --- Step 3: Basic cleaning
        df = clean_dataframe(df)
        df = df.where(pd.notnull(df), None)  # replace NaN with None
        df.columns = [sanitize_name(c) for c in df.columns]

        # --- Step 4: Determine table name
        if table_name:
            table_name = sanitize_name(table_name)
        else:
            base = os.path.splitext(file.filename)[0]
            table_name = sanitize_name(base)

        # --- Step 5: Make sure database exists
        with root_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))

        # --- Step 6: Get engine for that DB
        engine = get_engine_for_db(db_name)

        # --- Step 7: Infer SQL column types
        dtype_map = {col: infer_sql_type(dtype) for col, dtype in df.dtypes.items()}

        # --- Step 8: Write to SQL with error handling
        try:
            df.to_sql(table_name, con=engine, if_exists=if_exists, index=False, dtype=dtype_map)
        except Exception as e:
            raise Exception(f"Failed to write table '{table_name}' to database '{db_name}': {e}")

        # --- Step 9: Verify row count
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) AS cnt FROM `{table_name}`;"))
            cnt = result.scalar() or 0

        return {
            "status": "success",
            "db_name": db_name,
            "table_name": table_name,
            "rows_written": len(df),
            "rows_in_db": int(cnt),
            "columns": list(df.columns)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
