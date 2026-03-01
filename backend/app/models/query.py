from pydantic import BaseModel

class NLQuery(BaseModel):
    nl: str

class SQLQuery(BaseModel):
    sql: str
    limit: int | None = 100
