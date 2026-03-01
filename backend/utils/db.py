# backend/utils/db.py
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


load_dotenv()  # make sure .env exists in backend/

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


DB_PASS_QUOTED = quote_plus(DB_PASS)
# DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS_QUOTED}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS_QUOTED}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
db_engine = create_engine(DB_URL)

# Engine for root connection (no DB selected, used for listing databases)
ROOT_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS_QUOTED}@{DB_HOST}:{DB_PORT}/"
root_engine = create_engine(ROOT_URL)


# Ensure database exists (connect to server, create DB if absent)
tmp_engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASS_QUOTED}@{DB_HOST}:{DB_PORT}/")
with tmp_engine.connect() as conn:
    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
tmp_engine.dispose()

print("ROOT_URL =", ROOT_URL)
print("DB_URL =", DB_URL)
print("DEBUG ENV:", DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME)



# main engine
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ✅ New function for dynamic DB selection
_engine_cache = {}

def get_engine_for_db(db_name: str):
    """
    Returns a SQLAlchemy engine for the given database.
    Uses caching to avoid recreating engines each time.
    """
    if not db_name:
        return engine  # fallback to default
    
    if db_name not in _engine_cache:
        url = f"mysql+pymysql://{DB_USER}:{DB_PASS_QUOTED}@{DB_HOST}:{DB_PORT}/{db_name}"
        _engine_cache[db_name] = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    return _engine_cache[db_name]
