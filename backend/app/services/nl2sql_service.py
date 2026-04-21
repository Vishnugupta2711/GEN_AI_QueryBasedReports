import os
import traceback
from dotenv import load_dotenv
from sqlalchemy import inspect
from utils.db import get_engine_for_db
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from utils.chroma_utils import sync_chroma_schema_embeddings
from utils.fewshot_utils import build_fewshot_example_store

load_dotenv()

# --- LLM + embedding initialization (singleton-style) ---
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# --- Static default examples (will be indexed into chroma_examples if empty) ---
STATIC_EXAMPLES = [
    {
        "input": "Which staff member generated the highest total sales revenue?",
        "sql": """SELECT s.name, SUM(sa.total_amount) AS total_revenue
                  FROM sales sa
                  JOIN staff s ON sa.staff_id = s.staff_id
                  GROUP BY s.name
                  ORDER BY total_revenue DESC
                  LIMIT 1;"""
    },
    {
        "input": "List all customers from Mumbai who purchased more than one mobile.",
        "sql": """SELECT c.name, c.city, SUM(sa.quantity) AS total_mobiles_bought
                  FROM sales sa
                  JOIN customers c ON sa.customer_id = c.customer_id
                  WHERE c.city = 'Mumbai'
                  GROUP BY c.customer_id, c.name, c.city
                  HAVING total_mobiles_bought > 1;"""
    },
    {
        "input": "For each product category, show total number of orders and total revenue.",
        "sql": """SELECT p.category, COUNT(o.order_id) AS total_orders, SUM(o.total_amount) AS total_revenue
                  FROM orders o
                  JOIN products p ON o.product_id = p.product_id
                  GROUP BY p.category;"""
    }
    
]




def _get_relevant_examples(example_store: Chroma, question: str, k: int = 3):
    """
    Retrieve top-k semantically similar few-shot examples to the given question.
    Returns a formatted string block ready to inject into the LLM prompt.
    """
    try:
        # Perform similarity search
        hits = example_store.similarity_search(question, k=k)
        examples = []

        for h in hits:
            # h.page_content should look like "Q: ...\nSQL: ..."
            content = getattr(h, "page_content", "").strip()

            if "SQL:" in content:
                q_text, sql_text = content.split("SQL:", 1)
                q_text = q_text.replace("Q:", "").strip()
                sql_text = sql_text.strip()
            else:
                q_text, sql_text = content, ""

            examples.append(f"Q: {q_text}\nSQL: {sql_text}")

        print(f"[FewShotSelector] ✅ Retrieved {len(examples)} relevant few-shot examples for question '{question}'")
        return "\n\n".join(examples) if examples else "No relevant examples found."

    except Exception as e:
        print(f"[FewShotSelector] ⚠️ Error retrieving few-shot examples: {e}")
        # Fallback: use static examples if search fails
        try:
            from utils.fewshot_utils import FEWSHOT_EXAMPLES  # or wherever you stored them
            return "\n\n".join([f"Q: {ex['input']}\nSQL: {ex['sql']}" for ex in FEWSHOT_EXAMPLES])
        except Exception:
            return "No few-shot examples available."

def generate_sql_from_nl(question: str, db_name: str, table_name: str = None) -> dict:
    """
    Few-shot + Chroma-enhanced NL → SQL generator.
    Dynamically retrieves few-shot examples & schema embeddings using Chroma.
    Returns: {status, db_name, tables_used, question, sql_query} or error dict.
    """
    try:
        engine = get_engine_for_db(db_name)
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()

        if not all_tables:
            raise Exception(f"No tables found in database '{db_name}'.")

        # --- Ensure dynamic stores are ready ---
        example_store = build_fewshot_example_store()        # Few-shot examples Chroma
        schema_store = sync_chroma_schema_embeddings(db_name)  # Schema Chroma

        # --- Retrieve relevant tables from schema_store ---
        top_k = min(3, max(1, len(all_tables)))
        schema_hits = schema_store.similarity_search(question, k=top_k)

        relevant_tables = []
        for h in schema_hits:
            md = getattr(h, "metadata", None) or {}
            table = md.get("table")
            if table and table not in relevant_tables:
                relevant_tables.append(table)

        # fallback: include selected table if not already present
        if table_name and table_name in all_tables and table_name not in relevant_tables:
            relevant_tables.insert(0, table_name)

        if not relevant_tables:
            relevant_tables = [all_tables[0]]

        # --- Build schema context string ---
        schema_str = ""
        for t in relevant_tables:
            cols = inspector.get_columns(t)
            col_parts = [f"{c.get('name')} ({c.get('type')})" for c in cols]
            schema_str += f"TABLE: {t}\nCOLUMNS: {', '.join(col_parts)}\n\n"

        # --- Retrieve few-shot examples dynamically ---
        fewshot_str = _get_relevant_examples(example_store, question, k=3)
        if "No few-shot examples available" in fewshot_str or not fewshot_str.strip():
            print("[FewShot] ⚠️ No dynamic examples found, rebuilding few-shot store...")
            example_store = build_fewshot_example_store()
            fewshot_str = _get_relevant_examples(example_store, question, k=3)

        # --- Debug info (optional, safe to keep) ---
        try:
            print("\n[DEBUG] --- Chroma schema collection snapshot ---")
            docs_schema = schema_store._collection.get(include=["documents", "metadatas"])
            for i, doc in enumerate(docs_schema.get("documents", [])):
                print(f"  - SCHEMA DOC {i+1}: {doc[:150]} ...  METADATA: {docs_schema['metadatas'][i]}")
            print("[DEBUG] --- Chroma few-shot collection snapshot ---")
            docs_examples = example_store._collection.get(include=["documents", "metadatas"])
            for i, doc in enumerate(docs_examples.get("documents", [])):
                print(f"  - EXAMPLE DOC {i+1}: {doc[:150]} ... METADATA: {docs_examples['metadatas'][i]}")
        except Exception as e:
            print("[DEBUG] (info) Could not dump Chroma internals for debug:", e)

        # --- Prompt building (LLM input) ---
        prompt = f"""
You are a MySQL expert. The user is asking about the database '{db_name}'.

Relevant tables & enriched columns:
{schema_str}

Use JOINs if multiple tables are relevant.

Few-shot examples (use these as stylistic guides):
{fewshot_str}

User question:
{question}

Instructions:
- Only use the listed tables and columns.
- Do NOT invent columns or tables.
- Generate a syntactically correct MySQL query.
- Return only the SQL, no markdown or commentary.
"""

        # --- Query LLM ---
        response = llm.invoke(prompt)
        sql_query = response.content.strip().replace("```sql", "").replace("```", "").strip()

        # Escape % for pandas/pymysql
        if "%" in sql_query:
            sql_query = sql_query.replace("%", "%%")

        print("\n=======================")
        print(f"[NL2SQL] Database: {db_name}")
        print(f"[NL2SQL] Relevant Tables: {relevant_tables}")
        print(f"================ Schema sent :\n {schema_str}")
        print(f"================ Few-shot examples sent :\n {fewshot_str}")
        print(f"[NL2SQL] Question: {question}")
        print(f"[NL2SQL] SQL (escaped): {sql_query}")
        print("=======================\n")

        return {
            "status": "success",
            "db_name": db_name,
            "tables_used": relevant_tables,
            "question": question,
            "schema_str": schema_str,
            "fewshot_str": fewshot_str,
            "sql_query": sql_query
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "error": str(e), "question": question}
