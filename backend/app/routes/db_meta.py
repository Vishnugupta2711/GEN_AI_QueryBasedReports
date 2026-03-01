from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from utils.db import root_engine
import traceback
from utils.db import DB_USER, DB_PASS, DB_HOST, DB_PORT
from sqlalchemy import create_engine



router = APIRouter()

@router.get("/")
def list_databases():
    try:
        print("🚀 Using root_engine for SHOW DATABASES")
        with root_engine.connect() as conn:
            print("✅ Connected successfully")
            result = conn.execute(text("SHOW DATABASES;"))
            dbs = [row[0] for row in result.fetchall()]
            print("📂 Databases found:", dbs)
        return {"databases": dbs}
    except Exception as e:
        print("❌ Error in /databases:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{db_name}")
def list_tables(db_name: str):
    try:
        print(f"🚀 Connecting to DB: {db_name}")
        engine_db = create_engine(
            f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{db_name}"
        )
        with engine_db.connect() as conn:
            print("✅ Connected to", db_name)
            result = conn.execute(text("SHOW TABLES;"))
            tables = [row[0] for row in result.fetchall()]
            print(f"📂 Tables in {db_name}:", tables)
        return {"tables": tables}
    except Exception as e:
        print(f"❌ Error listing tables in {db_name}:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
