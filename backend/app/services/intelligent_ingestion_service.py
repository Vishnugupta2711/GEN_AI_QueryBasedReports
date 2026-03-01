"""
Intelligent Data Ingestion Service
Uses Gemini AI and ChromaDB to intelligently match and ingest data from Excel/PDF files.
"""
import os
import tempfile
import traceback
import json
import re
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import pdfplumber
from difflib import SequenceMatcher
from fastapi import UploadFile
from sqlalchemy import text, inspect, MetaData, Table, Column, String, Integer, Float, DateTime
from sqlalchemy.exc import SQLAlchemyError

from utils.db import get_engine_for_db, root_engine
from utils.db_utils import sanitize_name, clean_dataframe, infer_sql_type
from utils.chroma_utils import sync_chroma_schema_embeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# Initialize Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

# Initialize embedding model for ChromaDB
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Thresholds for matching
TABLE_SIMILARITY_THRESHOLD = 0.5  # Lowered for easier matching
COLUMN_SIMILARITY_THRESHOLD = 0.6
INTRO_SIMILARITY_THRESHOLD = 0.6

# Fallback control
# Toggle this to enable/disable name-similarity fallback when cosine similarity is below threshold.
# Set to False to turn OFF the fallback.
ENABLE_NAME_FALLBACK = True
NAME_MATCH_THRESHOLD = 0.6

TYPE_COLUMN_RECOMMENDATIONS = {
    "report": ["key_feature", "achievement", "technical_challenge", "usage", "cost_impact"],
    "log": ["user_login", "api_request", "server_error", "model_crash", "system_health_info"],
    "audit_record": ["user_updated_profile", "admin_deleted_record", "api_key_created", "permissions_changed"]
}

def normalize(s):
    return sanitize_name(s).lower().strip() if s else ''

def name_similarity(a: str, b: str) -> float:
    a_norm = normalize(a)
    b_norm = normalize(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()

def classify_file_type(text_or_table_preview: str) -> str:
    # Lightweight prompt to classify type
    classify_prompt = f"""
Given the following data or text, answer only 'report', 'log', 'audit_record', or 'other'.
What is the main FILE TYPE? Answer with a single word.
Data Preview:\n{text_or_table_preview[:1000]}
"""
    response = llm.invoke(classify_prompt)
    content = (response.content.strip() if hasattr(response, 'content') else str(response)).lower()
    if 'report' in content:
        return 'report'
    elif 'log' in content:
        return 'log'
    elif 'audit' in content:
        return 'audit_record'
    else:
        return 'other'


def get_chroma_store(db_name: str) -> Chroma:
    """Get or create ChromaDB store for schema embeddings."""
    persist_dir = f"./chroma_schemas/{db_name}"
    os.makedirs(persist_dir, exist_ok=True)
    
    store = Chroma(
        collection_name=f"schema_{db_name}",
        embedding_function=embedding_model,
        persist_directory=persist_dir
    )
    return store


def find_matching_table(table_name: str, description: str, db_name: str) -> Optional[Dict]:
    """
    Find matching table using ChromaDB cosine similarity.
    Returns: {table_name, similarity} or None
    """
    try:
        store = sync_chroma_schema_embeddings(db_name)
        engine = get_engine_for_db(db_name)
        inspector = inspect(engine)
        
        # Get all existing tables
        existing_tables = inspector.get_table_names()
        if not existing_tables:
            return None
        
        # Search for similar tables using the table name and description
        search_text = f"Table: {table_name} {description}".strip()
        results = store.similarity_search_with_score(search_text, k=min(10, len(existing_tables)))
        
        best_match = None
        best_similarity = 0.0
        top_candidate_name = None
        top_candidate_score = None
        
        for doc, distance in results:
            # Extract table name from document
            content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            
            # Parse the document format: "Table: {name}\nColumns: ..."
            if "Table:" in content:
                try:
                    table_match = content.split("Table:")[1].split("\n")[0].strip()
                    
                    # Verify table exists
                    if table_match in existing_tables:
                        # Convert distance to similarity
                        # ChromaDB uses cosine distance (0 = identical, 2 = opposite)
                        # Convert to similarity score (0-1, where 1 = identical)
                        similarity = 1.0 - (distance / 2.0)
                        similarity = max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
                        
                        # keep top candidate regardless of threshold
                        if top_candidate_score is None or similarity > top_candidate_score:
                            top_candidate_score = similarity
                            top_candidate_name = table_match

                        if similarity >= TABLE_SIMILARITY_THRESHOLD and similarity > best_similarity:
                            best_similarity = similarity
                            best_match = {
                                "table_name": table_match,
                                "similarity": similarity,
                                "metadata": metadata
                            }
                except Exception as e:
                    print(f"[Table Matching] Error parsing document: {e}")
                    continue
        
        # Name-based fallback if no match passed threshold
        if best_match is None and ENABLE_NAME_FALLBACK and top_candidate_name:
            nm = name_similarity(table_name, top_candidate_name)
            if nm >= NAME_MATCH_THRESHOLD:
                print(f"[Table Matching Fallback] Using name similarity fallback: '{table_name}' ~ '{top_candidate_name}' = {nm:.2f}")
                return {
                    "table_name": top_candidate_name,
                    "similarity": float(top_candidate_score or 0.0),
                    "name_similarity": float(nm),
                    "metadata": {}
                }

        return best_match
    except Exception as e:
        print(f"[Table Matching] Error: {e}")
        traceback.print_exc()
        return None


def find_matching_columns(column_name: str, column_description: str, table_name: str, db_name: str) -> Optional[Dict]:
    """
    Find matching column in a specific table using ChromaDB and direct embeddings.
    Returns: {column_name, similarity} or None
    """
    try:
        store = sync_chroma_schema_embeddings(db_name)
        engine = get_engine_for_db(db_name)
        inspector = inspect(engine)
        
        # Get all columns from the table
        columns = inspector.get_columns(table_name)
        if not columns:
            return None
        
        column_names = [col["name"] for col in columns]
        
        # Create embeddings for the search column
        search_text = f"{column_name} {column_description}".strip()
        search_embedding = embedding_model.embed_query(search_text)
        
        # Get the table's schema document to extract column context
        search_table_text = f"Table: {table_name}"
        table_results = store.similarity_search(search_table_text, k=1)
        
        table_context = ""
        if table_results:
            table_context = table_results[0].page_content if hasattr(table_results[0], 'page_content') else str(table_results[0])
        
        # Create embeddings for each existing column and compare
        best_match = None
        best_similarity = 0.0
        
        for col in columns:
            col_name = col["name"]
            col_type = str(col.get("type", ""))
            
            # Create column text for embedding comparison
            col_text = f"{col_name} {col_type} {table_name}"
            col_embedding = embedding_model.embed_query(col_text)
            
            # Calculate cosine similarity manually
            similarity = np.dot(search_embedding, col_embedding) / (
                np.linalg.norm(search_embedding) * np.linalg.norm(col_embedding)
            )
            
            # Boost similarity for exact or partial name matches
            if col_name.lower() == column_name.lower():
                similarity = min(1.0, similarity + 0.15)
            elif col_name.lower() in column_name.lower() or column_name.lower() in col_name.lower():
                similarity = min(1.0, similarity + 0.1)
            elif any(word in col_name.lower() for word in column_name.lower().split("_")) or \
                 any(word in column_name.lower() for word in col_name.lower().split("_")):
                similarity = min(1.0, similarity + 0.05)
            
            if similarity >= COLUMN_SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    "column_name": col_name,
                    "similarity": float(similarity)
                }
        
        # Fallback: direct string matching if no good embedding match
        if best_match is None:
            for col_name in column_names:
                # Exact match
                if col_name.lower() == column_name.lower():
                    return {
                        "column_name": col_name,
                        "similarity": 1.0
                    }
                # Partial match
                elif col_name.lower() in column_name.lower() or column_name.lower() in col_name.lower():
                    return {
                        "column_name": col_name,
                        "similarity": 0.75
                    }
        
        return best_match
    except Exception as e:
        print(f"[Column Matching] Error: {e}")
        traceback.print_exc()
        # Fallback to simple string matching
        try:
            engine = get_engine_for_db(db_name)
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name)
            column_names = [col["name"] for col in columns]
            
            for col_name in column_names:
                if col_name.lower() == column_name.lower():
                    return {
                        "column_name": col_name,
                        "similarity": 1.0
                    }
        except:
            pass
        return None


def find_table_by_subject_or_column_similarity(gemini_table_name: str, gemini_table_subject: str, column_names: list, db_name: str) -> dict:
    """
    Returns a dict with the matching table name (if EITHER the subject/title or columns are similar enough to any existing table), else None.
    """
    store = sync_chroma_schema_embeddings(db_name)
    engine = get_engine_for_db(db_name)
    inspector = inspect(engine)
    threshold = TABLE_SIMILARITY_THRESHOLD
    col_threshold = COLUMN_SIMILARITY_THRESHOLD
    best_table = None
    best_score = 0.0
    # Normalize Gemini inputs
    gemini_table_name = normalize(gemini_table_name)
    gemini_table_subject = normalize(gemini_table_subject)
    column_names_norm = [normalize(c) for c in column_names]
    print(f"[MATCH] Trying to merge: name='{gemini_table_name}', subject='{gemini_table_subject}', columns={column_names_norm}")
    for existing in inspector.get_table_names():
        existing_norm = normalize(existing)
        db_cols = [normalize(col['name']) for col in inspector.get_columns(existing)]
        print(f"  [CANDIDATE] Table={existing_norm} cols={db_cols}")
        # 1. Table subject/title similarity
        table_score = 0.0
        table_hit = store.similarity_search_with_score(f"Table: {gemini_table_name} {gemini_table_subject}", k=10)
        for doc, d in table_hit:
            content = getattr(doc, 'page_content', str(doc)).lower()
            if f"table: {existing_norm}" in content or existing_norm in content:
                s = 1.0 - (d/2.0)
                table_score = max(table_score, s)
        # 2. Best/Average column name similarity
        sim_scores = []
        for cname in column_names_norm:
            max_sim = 0.0
            col_hit = store.similarity_search_with_score(f"Column: {cname}", k=10)
            for doc, d in col_hit:
                content = getattr(doc, 'page_content', str(doc)).lower()
                if f"table: {existing_norm}" in content:
                    sim = 1.0 - (d/2.0)
                    max_sim = max(max_sim, sim)
            sim_scores.append(max_sim)
        avg_col_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0
        best_col_sim = max(sim_scores) if sim_scores else 0.0
        print(f"    > sim: TABLE={table_score:.2f}, AVG_COL={avg_col_sim:.2f}, BEST_COL={best_col_sim:.2f}")
        score = max(table_score, best_col_sim, avg_col_sim)
        if table_score >= threshold or best_col_sim >= col_threshold or avg_col_sim >= col_threshold:
            print(f"    -> MATCH: {existing_norm}")
            if score > best_score:
                best_score = score
                best_table = {'table_name': existing, 'subject_similarity': table_score, 'best_col_similarity': best_col_sim, 'avg_col_similarity': avg_col_sim}
    if best_table:
        print(f"[MATCH DECISION] SELECTED: {best_table}")
    else:
        print(f"[MATCH DECISION] No table matched. Creating new.")
    return best_table


def analyze_excel_with_gemini(file_path: str, df: pd.DataFrame) -> Dict:
    try:
        data_preview = f"File columns: {', '.join(df.columns.tolist())}\nFirst rows:\n{df.head(5).to_string()}"
        file_type = classify_file_type(data_preview)
        preferred_cols = TYPE_COLUMN_RECOMMENDATIONS.get(file_type, [])
        pc_str = ', '.join(preferred_cols) if preferred_cols else '(none)'
        prompt = f"""
You are an information extractor. The data type is: {file_type.upper()}.
Preferred columns for this file type are: [{pc_str}] — USE these columns IF the content fits, they are not required, but should be considered first when naming columns for relevant fields. Otherwise create a new abstract noun column name as needed.

1. Find a primary identifier (unique field like year, ID, etc).
2. For each record/block, extract all value-fields present; assign EACH to a column as an ABSTRACT NOUN (never 'description', 'column1', etc.).
3. Table name must be a proper noun or clear event/title best describing contents.
Only output strict JSON, no commentary.
Format:
{{{{
  "table_name": "...",
  "primary_identifier": "...",
  "columns": {{{{...}}}},
  "rows": [{{{{...}}}}, ...]
}}}}
Input Preview:\n{data_preview}
"""
        response = llm.invoke(prompt)
        content = response.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                # Simple sanity: require identifier and at least one abstract-noun column
                columns = result.get("columns", {})
                if result.get("primary_identifier") and any(col for col in columns if col not in [result['primary_identifier'], 'description', 'column1','value','field']):
                    return result
            except Exception as e:
                print("[Gemini Excel (abstract noun) RAW OUTPUT]:", content)
                print("[Gemini Excel] PARSE ERROR:", e)
        # Fallback
        cols = list(df.columns)
        return {"table_name": sanitize_name(os.path.basename(file_path).replace(".xlsx", "").replace(".xls", "")),
                "primary_identifier": cols[0] if cols else None,
                "columns": {col: f"Data column: {col}" for col in cols},
                "rows": [row._asdict() if hasattr(row, '_asdict') else dict(zip(df.columns, r)) for r in df.itertuples(index=False)]}
    except Exception as e:
        print("[Gemini Excel (abstract noun) Fallback Exception]", e)
        cols = list(df.columns)
        return {"table_name": sanitize_name(os.path.basename(file_path).replace(".xlsx", "").replace(".xls", "")),
                "primary_identifier": cols[0] if cols else None,
                "columns": {col: f"Data column: {col}" for col in cols},
                "rows": [row._asdict() if hasattr(row, '_asdict') else dict(zip(df.columns, r)) for r in df.itertuples(index=False)]}

def chunk_text_words(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    if not words:
        return chunks
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunks.append(" ".join(words[i:i + chunk_size]))
    return chunks

def analyze_pdf_with_gemini(file_path: str) -> Dict:
    try:
        text_content = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text_content += page.extract_text() or ""
        if not text_content.strip():
            raise Exception("No text content found in PDF")
            
        file_type = classify_file_type(text_content[:2000])
        preferred_cols = TYPE_COLUMN_RECOMMENDATIONS.get(file_type, [])
        pc_str = ', '.join(preferred_cols) if preferred_cols else '(none)'
        
        chunks = chunk_text_words(text_content, chunk_size=300, overlap=50)
        
        all_rows = []
        known_columns = []
        table_name = sanitize_name(os.path.basename(file_path).replace(".pdf", ""))
        primary_identifier = None
        
        print(f"\n[PDF INGESTION] Starting chunk processing. Total chunks to process: {len(chunks)}")
        
        for i, chunk in enumerate(chunks):
            print(f"  -> Processing Chunk [{i+1}/{len(chunks)}] (Length: {len(chunk.split())} words)")
            cols_context = f"Known columns established from previous sections: {known_columns}" if known_columns else "No specific columns established yet."
            
            prompt = f"""
You are an expert information extractor processing chunk {i+1} of {len(chunks)} of a {file_type.upper()} document.
Preferred semantic columns for this type are: [{pc_str}].
{cols_context}

Instructions:
1. Extract the structured data from the Input Text below.
2. If this is the first chunk, establish a primary entity identifier. If earlier chunks established it, keep it.
3. Organize the data into rows. Use the 'Known columns' if they semantically fit, otherwise invent new abstract nouns (like 'organization', 'amount', 'date', never 'column1').
4. If a row seems cut-off (due to text chunking), extract as much as possible.
5. Return JSON ONLY matching this format:
{{{{
  "table_name": "best descriptive noun for the data entity (e.g. employee_records)",
  "primary_identifier": "the main tracking column (e.g. employee_id)",
  "parsed_columns": ["col_1", "col_2"],
  "rows": [{{{{ "col_1": "val", "col_2": "val" }}}}, ...]
}}}}
NO commentary. Strict JSON ONLY.

Input Text (Chunk {i+1}):
{chunk}
"""
            try:
                response = llm.invoke(prompt)
                content = response.content.strip()
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    chunk_rows = result.get("rows", [])
                    chunk_cols = result.get("parsed_columns", [])
                    
                    if chunk_rows:
                        all_rows.extend(chunk_rows)
                        print(f"     -> Successfully extracted {len(chunk_rows)} rows from Chunk {i+1}.")
                        print(f"     -> Known schema updated to: {known_columns}")
                        
                    for c in chunk_cols:
                        if c not in known_columns and c not in ["description", "value", "column1", "field"]:
                            known_columns.append(c)
                            
                    if result.get("primary_identifier") and not primary_identifier:
                        primary_identifier = result.get("primary_identifier")
                        
                    if result.get("table_name") and table_name == sanitize_name(os.path.basename(file_path).replace(".pdf", "")):
                        table_name = sanitize_name(result.get("table_name"))
            except Exception as e:
                print(f"[Gemini PDF Chunk {i+1}] PARSE ERROR:", e)
                continue
                
        print(f"\n[PDF INGESTION] Finished scanning all chunks. Total raw rows extracted = {len(all_rows)}")
        print(f"[PDF INGESTION] Starting deduplication phase using primary identifier: '{primary_identifier}'")
        
        # Deduplication
        deduped_rows = []
        seen_ids = set()
        for row in all_rows:
            # deduplicate by primary identifier or full string representation
            pid_val = row.get(primary_identifier) if primary_identifier else None
            
            if pid_val is not None and str(pid_val).strip() != "":
                if pid_val not in seen_ids:
                    seen_ids.add(pid_val)
                    deduped_rows.append(row)
            else:
                # No primary identifier or it's empty, use dict representation
                row_str = str(sorted({str(k): str(v) for k, v in row.items()}.items()))
                if row_str not in seen_ids:
                    seen_ids.add(row_str)
                    deduped_rows.append(row)

        print(f"[PDF INGESTION] Deduplication complete! Final distinct rows: {len(deduped_rows)} (Removed {len(all_rows) - len(deduped_rows)} overlaps)")

        if not deduped_rows:
            # Fallback if no rows extracted from chunks
            tables = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables():
                        tables.append(table)
            if tables:
                first_table = tables[0]
                import pandas as pd
                df = pd.DataFrame(first_table[1:], columns=first_table[0])
                cols = list(df.columns)
                return {"table_name": table_name,
                        "primary_identifier": cols[0] if cols else None,
                        "columns": {col: f"Data column: {col}" for col in cols},
                        "rows": [row._asdict() if hasattr(row, '_asdict') else dict(zip(df.columns, r)) for r in df.itertuples(index=False)]}
            else:
                return {"table_name": table_name, "primary_identifier": primary_identifier, "rows": []}

        return {
            "table_name": table_name,
            "primary_identifier": primary_identifier,
            "rows": deduped_rows
        }

    except Exception as e:
        print(f"[Gemini PDF Analysis] Error: {e}")
        traceback.print_exc()
        return {"table_name": sanitize_name(os.path.basename(file_path).replace(".pdf", "")),
                "primary_identifier": None, "rows": []}


# Helper: Extract intro/fingerprint from any document (list of lines)
def extract_intro_fingerprint(lines, num_lines=3, char_limit=500):
    intro_lines = []
    for line in lines:
        l = line.strip()
        if l:
            intro_lines.append(l)
        if len(intro_lines) >= num_lines:
            break
    intro = ' '.join(intro_lines)
    if not intro:
        intro = ' '.join(lines)[:char_limit]
    return intro.strip()

# Helper: Register/Store intro fingerprint in Chroma (as doc type: table_intro, with metadata table=table_name)
def store_table_intro_fingerprint(db_name: str, table_name: str, intro_text: str):
    store = sync_chroma_schema_embeddings(db_name)
    store.add_texts([f"TABLE_INTRO: {intro_text}"], metadatas=[{'type':'table_intro','table':table_name}])

# Helper: Find matching table by context fingerprint
# Returns: best table (if sim >= threshold), else None
def find_table_by_intro_similarity(context_intro: str, db_name: str):
    store = sync_chroma_schema_embeddings(db_name)
    # fetch all table_intro docs from Chroma
    found = store.get()
    intros = []
    intros_meta = []
    for i, doc in enumerate(found.get('documents', [])):
        meta = found.get('metadatas', [])[i]
        if meta and meta.get('type') == 'table_intro':
            intros.append(doc)
            intros_meta.append(meta)
    # Compare
    best_table = None
    best_sim = 0.0
    for intro, meta in zip(intros, intros_meta):
        table = meta.get('table')
        docsims = store.similarity_search_with_score(f"TABLE_INTRO: {context_intro}", k=10)
        for doc, d in docsims:
            content = getattr(doc, 'page_content', str(doc)).lower()
            if intro.lower() in content:
                sim = 1.0 - (d/2.0)
                if sim > best_sim:
                    best_sim = sim
                    best_table = {'table_name': table, 'intro_similarity': sim}
    if best_table and best_sim >= INTRO_SIMILARITY_THRESHOLD:
        print(f"[FINGERPRINT MATCH] Table {best_table['table_name']} (intro sim: {best_sim:.2f})")
        return best_table
    print("[FINGERPRINT MATCH] No close table. New one will be created.")
    return None

def _fallback_match_by_name(suggested_table_name: str, db_name: str) -> Optional[Dict]:
    """When cosine similarity fails, try nearest table by name similarity only."""
    try:
        if not ENABLE_NAME_FALLBACK:
            return None
        store = sync_chroma_schema_embeddings(db_name)
        engine = get_engine_for_db(db_name)
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        if not existing_tables:
            return None
        search_text = f"Table: {suggested_table_name}"
        results = store.similarity_search_with_score(search_text, k=10)
        top_name = None
        top_distance = None
        for doc, distance in results:
            content = getattr(doc, 'page_content', str(doc))
            if "Table:" in content:
                try:
                    nm = content.split("Table:")[1].split("\n")[0].strip()
                    if nm in existing_tables:
                        top_name = nm
                        top_distance = distance
                        break
                except:
                    continue
        if top_name:
            sim_ratio = name_similarity(suggested_table_name, top_name)
            if sim_ratio >= NAME_MATCH_THRESHOLD:
                cos_sim = 1.0 - (float(top_distance) / 2.0) if top_distance is not None else 0.0
                print(f"[Name Fallback] '{suggested_table_name}' ~ '{top_name}' = {sim_ratio:.2f} (cos={cos_sim:.2f})")
                return {"table_name": top_name, "similarity": cos_sim, "name_similarity": sim_ratio}
        return None
    except Exception as e:
        print("[Name Fallback] Error:", e)
        return None


def analyze_excel_schema_with_gemini(file_name: str, df: pd.DataFrame) -> Dict:
    """
    Ask Gemini to infer a clean column schema from a small sample of Excel rows.
    Returns: { column_mapping: {original_header: clean_column_name} }
    """
    try:
        headers = df.columns.tolist()
        sample_rows = df.head(10).astype(str).fillna("").values.tolist()
        preview = {
            "file_name": file_name,
            "headers": headers,
            "rows": sample_rows
        }
        prompt = f"""
You are normalizing Excel column headers for database ingestion.
Given the JSON payload with "headers" and first "rows" (strings), produce a JSON with a mapping from ORIGINAL HEADER to a CLEAN, ABSTRACT-NOUN column name.
Rules:
- Use only lowercase snake_case for names.
- Prefer meaningful abstract nouns (e.g., 'year', 'project', 'milestone', 'owner').
- Do NOT include columns that are entirely empty or 'unnamed' unless they clearly contain data.
- Only output JSON, no commentary.
Input JSON:
{json.dumps(preview)[:12000]}
Output JSON format:
{{
  "column_mapping": {{"original_header": "clean_column_name", ...}}
}}
"""
        response = llm.invoke(prompt)
        content = response.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                mapping = result.get("column_mapping", {})
                if isinstance(mapping, dict) and mapping:
                    # sanitize mapping values
                    clean_mapping = {}
                    for k, v in mapping.items():
                        if k in headers and v:
                            clean_mapping[k] = sanitize_name(v)
                    return {"column_mapping": clean_mapping}
            except Exception as e:
                print("[Gemini Excel Schema RAW OUTPUT]:", content)
                print("[Gemini Excel Schema] PARSE ERROR:", e)
        # Fallback: identity mapping on non-empty, non-unnamed columns
        mapping = {}
        for c in headers:
            if not str(c).lower().startswith("unnamed"):
                mapping[c] = sanitize_name(c)
        return {"column_mapping": mapping}
    except Exception as e:
        print("[Gemini Excel Schema] Exception:", e)
        mapping = {c: sanitize_name(c) for c in df.columns if not str(c).lower().startswith("unnamed")}
        return {"column_mapping": mapping}


async def ingest_excel_file(file: UploadFile, db_name: str) -> Dict:
    """
    Intelligently ingest Excel file with table/column matching.
    """
    try:
        def _drop_header_like_rows(df_in: pd.DataFrame) -> pd.DataFrame:
            if df_in.empty:
                return df_in
            mask = []
            for _, row in df_in.iterrows():
                is_header = False
                for c in df_in.columns:
                    v = row.get(c)
                    if v is None:
                        continue
                    vs = str(v).strip().lower()
                    if vs == c.strip().lower():
                        is_header = True
                        break
                mask.append(not is_header)
            return df_in[pd.Series(mask, index=df_in.index)]

        def _coerce_df_to_table_schema(df_in: pd.DataFrame, engine, table_name: str) -> pd.DataFrame:
            try:
                insp = inspect(engine)
                columns = {c['name']: str(c.get('type', '')).lower() for c in insp.get_columns(table_name)}
                df_out = df_in.copy()
                # Replace common string sentinels with None
                df_out = df_out.replace({'nan': None, 'NaN': None, 'NONE': None, 'None': None}, regex=False)
                # Coerce numeric columns
                for col, t in columns.items():
                    if col in df_out.columns:
                        if 'int' in t or 'decimal' in t or 'numeric' in t or 'float' in t or 'double' in t or 'real' in t:
                            df_out[col] = pd.to_numeric(df_out[col], errors='coerce')
                # Drop header-like rows and fully empty rows
                df_out = _drop_header_like_rows(df_out)
                df_out = df_out.dropna(how='all')
                return df_out
            except Exception as e:
                print("[Schema Coerce] Warning:", e)
                return df_in

        def _clean_excel_columns(df_in: pd.DataFrame) -> pd.DataFrame:
            df_out = df_in.copy()
            # Drop 'Unnamed:' columns if they are entirely empty/null
            drop_cols = []
            for c in df_out.columns:
                if str(c).lower().startswith("unnamed"):
                    col_series = df_out[c]
                    # consider empty if all null or blank strings
                    if col_series.isna().all() or (col_series.astype(str).str.strip().replace({'nan': ''}).eq('').all()):
                        drop_cols.append(c)
            if drop_cols:
                df_out = df_out.drop(columns=drop_cols, errors='ignore')
            # Sanitize again
            df_out.columns = [sanitize_name(c) for c in df_out.columns]
            return df_out

        # Save file temporarily
        suffix = ".csv" if file.filename.lower().endswith(".csv") else ".xlsx"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        tmp_path = tmp.name
        
        try:
            # Read Excel file
            if file.filename.lower().endswith(".csv"):
                df = pd.read_csv(tmp_path)
            else:
                df = pd.read_excel(tmp_path, engine="openpyxl")
            
            # Clean data
            df = clean_dataframe(df)
            df = df.where(pd.notnull(df), None)
            df.columns = [sanitize_name(c) for c in df.columns]
            df = _clean_excel_columns(df)
            
            # Analyze with Gemini for table naming (lightweight) and schema mapping for Excel
            analysis = analyze_excel_with_gemini(file.filename, df)
            suggested_table_name = sanitize_name(analysis.get("table_name", file.filename))
            schema_info = analyze_excel_schema_with_gemini(file.filename, df)
            column_mapping_from_gemini = schema_info.get("column_mapping", {})
            # Apply column mapping to full DataFrame
            df_mapped_by_gemini = df.rename(columns=column_mapping_from_gemini)
            # Any columns not in mapping keep sanitized names (already sanitized)
            column_descriptions = {}  # descriptions not needed; using names directly for similarity
            primary_identifier = df_mapped_by_gemini.columns[0] if len(df_mapped_by_gemini.columns) else None
            primary_description = ""
            
            # Ensure database exists
            with root_engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
            
            engine = get_engine_for_db(db_name)
            inspector = inspect(engine)
            
            # Build intro text from Excel content (filename, columns, top rows)
            preview_lines = [
                f"File: {file.filename}",
                "Columns: " + ", ".join(df.columns.tolist())
            ]
            head_rows = df.head(3).astype(str).values.tolist()
            for row in head_rows:
                preview_lines.append(" | ".join(row))
            context_intro = extract_intro_fingerprint(preview_lines)
            print(f"Extracted intro for Excel: {context_intro}")

            # 2. table_match = find_table_by_intro_similarity(context_intro, db_name)
            table_match = find_table_by_intro_similarity(context_intro, db_name)

            # 3. If match, use table for upsert; else, create new table and call store_table_intro_fingerprint(db_name, new_table_name, context_intro).
            if table_match:
                matched_table_name = table_match["table_name"]
                intro_similarity = table_match["intro_similarity"]
                # Verify the matched table exists
                table_exists = matched_table_name in inspector.get_table_names()
                if table_exists:
                    target_table = matched_table_name
                    was_new_table = False
                else:
                    # Match was found but table doesn't exist (shouldn't happen, but handle it)
                    target_table = suggested_table_name
                    intro_similarity = 0.0
                    was_new_table = True
                    table_match = None  # Reset match since table doesn't exist
            else:
                # Try name-based fallback if enabled
                fb = _fallback_match_by_name(suggested_table_name, db_name)
                if fb:
                    target_table = fb["table_name"]
                    intro_similarity = fb.get("similarity", 0.0)
                    was_new_table = False
                    table_match = {"table_name": target_table, "intro_similarity": intro_similarity}
                else:
                    target_table = suggested_table_name
                    intro_similarity = 0.0
                    was_new_table = True
            
            # 4. Downstream column/row code unchanged.
            # Check if target table exists
            table_exists = target_table in inspector.get_table_names()
            
            # Match columns
            column_matches = []
            new_columns = []
            existing_columns = []
            
            if table_exists:
                existing_cols = [col["name"] for col in inspector.get_columns(target_table)]
                existing_columns = existing_cols
            else:
                existing_columns = []
            
            for col in df_mapped_by_gemini.columns:
                col_desc = f"Excel column: {col}"
                
                if table_exists:
                    # Try to match with existing column
                    col_match = find_matching_columns(col, col_desc, target_table, db_name)
                    
                    if col_match:
                        column_matches.append({
                            "source_column": col,
                            "target_column": col_match["column_name"],
                            "similarity": col_match["similarity"]
                        })
                    else:
                        # New column needed if not an empty unnamed column
                        if not str(col).lower().startswith("unnamed"):
                            series = df_mapped_by_gemini[col]
                            if not (series.isna().all() or (series.astype(str).str.strip().replace({'nan': ''}).eq('').all())):
                                new_columns.append(col)
                else:
                    # New table, all columns are new
                    new_columns.append(col)
            
            # Create or update table
            if not table_exists:
                # Create new table
                dtype_map = {col: infer_sql_type(dtype) for col, dtype in df.dtypes.items()}
                df.to_sql(target_table, con=engine, if_exists="replace", index=False, dtype=dtype_map)
                rows_added = len(df)
                # 5. Update ChromaDB embeddings
                store_table_intro_fingerprint(db_name, target_table, context_intro)
            else:
                # Update existing table
                # Create column mapping: source -> target
                column_mapping = {match["source_column"]: match["target_column"] for match in column_matches}
                
                # Add new columns to table if any
                if new_columns:
                    with engine.connect() as conn:
                        for col in new_columns:
                            if col not in existing_columns:
                                dtype = infer_sql_type(df[col].dtype)
                                sql_type = "VARCHAR(255)" if isinstance(dtype, String) else "INT" if isinstance(dtype, Integer) else "FLOAT" if isinstance(dtype, Float) else "DATETIME"
                                try:
                                    conn.execute(text(f"ALTER TABLE `{target_table}` ADD COLUMN `{sanitize_name(col)}` {sql_type};"))
                                    conn.commit()
                                    # Update existing_columns list
                                    existing_columns.append(sanitize_name(col))
                                except SQLAlchemyError as e:
                                    print(f"Error adding column {col}: {e}")
                
                # Prepare dataframe with column mapping
                df_mapped = df_mapped_by_gemini.copy()
                
                # Rename matched columns
                for src, tgt in column_mapping.items():
                    if src in df_mapped.columns:
                        df_mapped = df_mapped.rename(columns={src: tgt})
                
                # Rename new columns to sanitized names
                for col in new_columns:
                    if col in df_mapped.columns:
                        sanitized_col = sanitize_name(col)
                        if sanitized_col != col:
                            df_mapped = df_mapped.rename(columns={col: sanitized_col})
                
                # Ensure all columns in df_mapped exist in the table
                final_columns = [col["name"] for col in inspector.get_columns(target_table)]
                df_mapped = df_mapped[[col for col in df_mapped.columns if col in final_columns]]
                
                # Append data
                if not df_mapped.empty:
                    dtype_map = {col: infer_sql_type(dtype) for col, dtype in df_mapped.dtypes.items()}
                    # Align dataframe with existing table schema to avoid type errors (e.g., 'nan' into INT)
                    df_ready = _coerce_df_to_table_schema(df_mapped, engine, target_table)
                    if not df_ready.empty:
                        df_ready.to_sql(target_table, con=engine, if_exists="append", index=False, dtype=dtype_map)
                        rows_added = len(df_ready)
                    else:
                        rows_added = 0
                else:
                    rows_added = 0
            
            # Update ChromaDB embeddings
            sync_chroma_schema_embeddings(db_name)
            
            # Get final column list
            final_columns = [col["name"] for col in inspector.get_columns(target_table)]
            
            return {
                "status": "success",
                "table_name": target_table,
                "rows_added": rows_added,
                "columns": final_columns,
                "matches": {
                    "table_match": {
                        "table_name": target_table,
                        "similarity": intro_similarity,
                        "was_new": was_new_table
                    } if table_match else {
                        "table_name": target_table,
                        "similarity": 0.0,
                        "was_new": True
                    },
                    "column_matches": column_matches,
                    "new_columns": new_columns
                }
            }
            
        finally:
            try:
                os.remove(tmp_path)
            except:
                pass
                
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


async def ingest_pdf_file(file: UploadFile, db_name: str) -> Dict:
    """
    Intelligently ingest PDF file with Gemini analysis and table/column matching.
    """
    try:
        def _drop_header_like_rows(df_in: pd.DataFrame) -> pd.DataFrame:
            if df_in.empty:
                return df_in
            mask = []
            for _, row in df_in.iterrows():
                is_header = False
                for c in df_in.columns:
                    v = row.get(c)
                    if v is None:
                        continue
                    vs = str(v).strip().lower()
                    if vs == c.strip().lower():
                        is_header = True
                        break
                mask.append(not is_header)
            return df_in[pd.Series(mask, index=df_in.index)]

        def _coerce_df_to_table_schema(df_in: pd.DataFrame, engine, table_name: str) -> pd.DataFrame:
            try:
                insp = inspect(engine)
                columns = {c['name']: str(c.get('type', '')).lower() for c in insp.get_columns(table_name)}
                df_out = df_in.copy()
                df_out = df_out.replace({'nan': None, 'NaN': None, 'NONE': None, 'None': None}, regex=False)
                for col, t in columns.items():
                    if col in df_out.columns:
                        if 'int' in t or 'decimal' in t or 'numeric' in t or 'float' in t or 'double' in t or 'real' in t:
                            df_out[col] = pd.to_numeric(df_out[col], errors='coerce')
                df_out = _drop_header_like_rows(df_out)
                df_out = df_out.dropna(how='all')
                return df_out
            except Exception as e:
                print("[Schema Coerce] Warning:", e)
                return df_in

        # Save file temporarily
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        tmp_path = tmp.name
        
        try:
            # Analyze PDF with Gemini
            analysis = analyze_pdf_with_gemini(tmp_path)
            suggested_table_name = sanitize_name(analysis.get("table_name", file.filename))
            description = analysis.get("description", "")
            rows_data = analysis.get("rows", [])
            primary_identifier = analysis.get("primary_identifier") or (pd.DataFrame(rows_data).columns[0] if len(pd.DataFrame(rows_data).columns) else None)
            primary_description = description
            
            if not rows_data:
                raise Exception("No structured data found in PDF")
            
            # Convert to DataFrame
            df = pd.DataFrame(rows_data)
            df = clean_dataframe(df)
            df = df.where(pd.notnull(df), None)
            df.columns = [sanitize_name(c) for c in df.columns]
            
            # Ensure database exists
            with root_engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
            
            engine = get_engine_for_db(db_name)
            inspector = inspect(engine)
            
            # Build intro text from PDF content
            pdf_text_intro = ""
            try:
                with pdfplumber.open(tmp_path) as _pdf:
                    for page in _pdf.pages[:1]:
                        pdf_text_intro += (page.extract_text() or "")[:1000]
            except Exception as e:
                print("[PDF Intro Extraction] Error:", e)
            lines = [l for l in (pdf_text_intro.splitlines() if pdf_text_intro else []) if l.strip()][:5]
            if not lines and not df.empty:
                # fallback to table preview
                preview = ["PDF (table) preview:"] + [" | ".join([str(x) for x in r]) for r in df.head(3).values.tolist()]
                lines = preview
            context_intro = extract_intro_fingerprint(lines or ["PDF file", file.filename])
            print(f"Extracted intro for PDF: {context_intro}")

            # 2. table_match = find_table_by_intro_similarity(context_intro, db_name)
            table_match = find_table_by_intro_similarity(context_intro, db_name)

            # 3. If match, use table for upsert; else, create new table and call store_table_intro_fingerprint(db_name, new_table_name, context_intro).
            if table_match:
                matched_table_name = table_match["table_name"]
                intro_similarity = table_match["intro_similarity"]
                # Verify the matched table exists
                table_exists = matched_table_name in inspector.get_table_names()
                if table_exists:
                    target_table = matched_table_name
                    was_new_table = False
                else:
                    # Match was found but table doesn't exist (shouldn't happen, but handle it)
                    target_table = suggested_table_name
                    intro_similarity = 0.0
                    was_new_table = True
                    table_match = None  # Reset match since table doesn't exist
            else:
                # Try name-based fallback if enabled
                fb = _fallback_match_by_name(suggested_table_name, db_name)
                if fb:
                    target_table = fb["table_name"]
                    intro_similarity = fb.get("similarity", 0.0)
                    was_new_table = False
                    table_match = {"table_name": target_table, "intro_similarity": intro_similarity}
                else:
                    target_table = suggested_table_name
                    intro_similarity = 0.0
                    was_new_table = True
            
            # 4. Downstream column/row code unchanged.
            # Check if target table exists
            table_exists = target_table in inspector.get_table_names()
            
            # Match columns
            column_matches = []
            new_columns = []
            existing_columns = []
            
            if table_exists:
                existing_cols = [col["name"] for col in inspector.get_columns(target_table)]
                existing_columns = existing_cols
            else:
                existing_columns = []
            
            for col in df.columns:
                if table_exists:
                    # Try to match with existing column
                    col_match = find_matching_columns(col, f"Column from PDF: {col}", target_table, db_name)
                    
                    if col_match:
                        column_matches.append({
                            "source_column": col,
                            "target_column": col_match["column_name"],
                            "similarity": col_match["similarity"]
                        })
                    else:
                        new_columns.append(col)
                else:
                    new_columns.append(col)
            
            # Create or update table
            if not table_exists:
                # Create new table
                dtype_map = {col: infer_sql_type(dtype) for col, dtype in df.dtypes.items()}
                df.to_sql(target_table, con=engine, if_exists="replace", index=False, dtype=dtype_map)
                rows_added = len(df)
                # 5. Update ChromaDB embeddings
                store_table_intro_fingerprint(db_name, target_table, context_intro)
            else:
                # Update existing table
                # Create column mapping: source -> target
                column_mapping = {match["source_column"]: match["target_column"] for match in column_matches}
                
                # Add new columns to table if any
                if new_columns:
                    with engine.connect() as conn:
                        for col in new_columns:
                            if col not in existing_columns:
                                dtype = infer_sql_type(df[col].dtype)
                                sql_type = "VARCHAR(255)" if isinstance(dtype, String) else "INT" if isinstance(dtype, Integer) else "FLOAT" if isinstance(dtype, Float) else "DATETIME"
                                try:
                                    conn.execute(text(f"ALTER TABLE `{target_table}` ADD COLUMN `{sanitize_name(col)}` {sql_type};"))
                                    conn.commit()
                                    # Update existing_columns list
                                    existing_columns.append(sanitize_name(col))
                                except SQLAlchemyError as e:
                                    print(f"Error adding column {col}: {e}")
                
                # Prepare dataframe with column mapping
                df_mapped = df.copy()
                
                # Rename matched columns
                for src, tgt in column_mapping.items():
                    if src in df_mapped.columns:
                        df_mapped = df_mapped.rename(columns={src: tgt})
                
                # Rename new columns to sanitized names
                for col in new_columns:
                    if col in df_mapped.columns:
                        sanitized_col = sanitize_name(col)
                        if sanitized_col != col:
                            df_mapped = df_mapped.rename(columns={col: sanitized_col})
                
                # Ensure all columns in df_mapped exist in the table
                final_columns = [col["name"] for col in inspector.get_columns(target_table)]
                df_mapped = df_mapped[[col for col in df_mapped.columns if col in final_columns]]
                
                # Append data
                if not df_mapped.empty:
                    dtype_map = {col: infer_sql_type(dtype) for col, dtype in df_mapped.dtypes.items()}
                    df_ready = _coerce_df_to_table_schema(df_mapped, engine, target_table)
                    if not df_ready.empty:
                        df_ready.to_sql(target_table, con=engine, if_exists="append", index=False, dtype=dtype_map)
                        rows_added = len(df_ready)
                    else:
                        rows_added = 0
                else:
                    rows_added = 0
            
            # Update ChromaDB embeddings
            sync_chroma_schema_embeddings(db_name)
            
            # Get final column list
            final_columns = [col["name"] for col in inspector.get_columns(target_table)]
            
            return {
                "status": "success",
                "table_name": target_table,
                "rows_added": rows_added,
                "columns": final_columns,
                "matches": {
                    "table_match": {
                        "table_name": target_table,
                        "similarity": intro_similarity,
                        "was_new": was_new_table
                    } if table_match else {
                        "table_name": target_table,
                        "similarity": 0.0,
                        "was_new": True
                    },
                    "column_matches": column_matches,
                    "new_columns": new_columns
                }
            }
            
        finally:
            try:
                os.remove(tmp_path)
            except:
                pass
                
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


async def intelligent_ingest_file(file: UploadFile, db_name: str) -> Dict:
    """
    Main entry point for intelligent file ingestion.
    Routes to Excel or PDF handler based on file type.
    """
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext in [".xlsx", ".xls", ".csv"]:
        return await ingest_excel_file(file, db_name)
    elif file_ext == ".pdf":
        return await ingest_pdf_file(file, db_name)
    else:
        return {"status": "error", "error": f"Unsupported file type: {file_ext}"}





# """
# Intelligent Data Ingestion Service
# Uses Gemini AI and ChromaDB to intelligently match and ingest data from Excel/PDF files.
# """
# import os
# import tempfile
# import traceback
# import json
# import re
# from typing import Dict, List, Optional, Tuple
# import numpy as np
# import pandas as pd
# import pdfplumber
# from difflib import SequenceMatcher
# from fastapi import UploadFile
# from sqlalchemy import text, inspect, MetaData, Table, Column, String, Integer, Float, DateTime
# from sqlalchemy.exc import SQLAlchemyError

# from utils.db import get_engine_for_db, root_engine
# from utils.db_utils import sanitize_name, clean_dataframe, infer_sql_type
# from utils.chroma_utils import sync_chroma_schema_embeddings
# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_community.embeddings import HuggingFaceEmbeddings
# from langchain_community.vectorstores import Chroma

# # Initialize Gemini LLM
# llm = ChatGoogleGenerativeAI(
#     model="gemini-2.5-flash",
#     temperature=0,
#     google_api_key=os.getenv("GOOGLE_API_KEY")
# )

# # Initialize embedding model for ChromaDB
# embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# # Thresholds for matching
# TABLE_SIMILARITY_THRESHOLD = 0.5  # Lowered for easier matching
# COLUMN_SIMILARITY_THRESHOLD = 0.6
# INTRO_SIMILARITY_THRESHOLD = 0.6

# # Fallback control
# # Toggle this to enable/disable name-similarity fallback when cosine similarity is below threshold.
# # Set to False to turn OFF the fallback.
# ENABLE_NAME_FALLBACK = True
# NAME_MATCH_THRESHOLD = 0.6

# TYPE_COLUMN_RECOMMENDATIONS = {
#     "report": ["key_feature", "achievement", "technical_challenge", "usage", "cost_impact"],
#     "log": ["user_login", "api_request", "server_error", "model_crash", "system_health_info"],
#     "audit_record": ["user_updated_profile", "admin_deleted_record", "api_key_created", "permissions_changed"]
# }

# def normalize(s):
#     return sanitize_name(s).lower().strip() if s else ''

# def name_similarity(a: str, b: str) -> float:
#     a_norm = normalize(a)
#     b_norm = normalize(b)
#     if not a_norm or not b_norm:
#         return 0.0
#     return SequenceMatcher(None, a_norm, b_norm).ratio()

# def classify_file_type(text_or_table_preview: str) -> str:
#     # Lightweight prompt to classify type
#     classify_prompt = f"""
# Given the following data or text, answer only 'report', 'log', 'audit_record', or 'other'.
# What is the main FILE TYPE? Answer with a single word.
# Data Preview:\n{text_or_table_preview[:1000]}
# """
#     response = llm.invoke(classify_prompt)
#     content = (response.content.strip() if hasattr(response, 'content') else str(response)).lower()
#     if 'report' in content:
#         return 'report'
#     elif 'log' in content:
#         return 'log'
#     elif 'audit' in content:
#         return 'audit_record'
#     else:
#         return 'other'


# def get_chroma_store(db_name: str) -> Chroma:
#     """Get or create ChromaDB store for schema embeddings."""
#     persist_dir = f"./chroma_schemas/{db_name}"
#     os.makedirs(persist_dir, exist_ok=True)
    
#     store = Chroma(
#         collection_name=f"schema_{db_name}",
#         embedding_function=embedding_model,
#         persist_directory=persist_dir
#     )
#     return store


# def find_matching_table(table_name: str, description: str, db_name: str) -> Optional[Dict]:
#     """
#     Find matching table using ChromaDB cosine similarity.
#     Returns: {table_name, similarity} or None
#     """
#     try:
#         store = sync_chroma_schema_embeddings(db_name)
#         engine = get_engine_for_db(db_name)
#         inspector = inspect(engine)
        
#         # Get all existing tables
#         existing_tables = inspector.get_table_names()
#         if not existing_tables:
#             return None
        
#         # Search for similar tables using the table name and description
#         search_text = f"Table: {table_name} {description}".strip()
#         results = store.similarity_search_with_score(search_text, k=min(10, len(existing_tables)))
        
#         best_match = None
#         best_similarity = 0.0
#         top_candidate_name = None
#         top_candidate_score = None
        
#         for doc, distance in results:
#             # Extract table name from document
#             content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
#             metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            
#             # Parse the document format: "Table: {name}\nColumns: ..."
#             if "Table:" in content:
#                 try:
#                     table_match = content.split("Table:")[1].split("\n")[0].strip()
                    
#                     # Verify table exists
#                     if table_match in existing_tables:
#                         # Convert distance to similarity
#                         # ChromaDB uses cosine distance (0 = identical, 2 = opposite)
#                         # Convert to similarity score (0-1, where 1 = identical)
#                         similarity = 1.0 - (distance / 2.0)
#                         similarity = max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
                        
#                         # keep top candidate regardless of threshold
#                         if top_candidate_score is None or similarity > top_candidate_score:
#                             top_candidate_score = similarity
#                             top_candidate_name = table_match

#                         if similarity >= TABLE_SIMILARITY_THRESHOLD and similarity > best_similarity:
#                             best_similarity = similarity
#                             best_match = {
#                                 "table_name": table_match,
#                                 "similarity": similarity,
#                                 "metadata": metadata
#                             }
#                 except Exception as e:
#                     print(f"[Table Matching] Error parsing document: {e}")
#                     continue
        
#         # Name-based fallback if no match passed threshold
#         if best_match is None and ENABLE_NAME_FALLBACK and top_candidate_name:
#             nm = name_similarity(table_name, top_candidate_name)
#             if nm >= NAME_MATCH_THRESHOLD:
#                 print(f"[Table Matching Fallback] Using name similarity fallback: '{table_name}' ~ '{top_candidate_name}' = {nm:.2f}")
#                 return {
#                     "table_name": top_candidate_name,
#                     "similarity": float(top_candidate_score or 0.0),
#                     "name_similarity": float(nm),
#                     "metadata": {}
#                 }

#         return best_match
#     except Exception as e:
#         print(f"[Table Matching] Error: {e}")
#         traceback.print_exc()
#         return None


# def find_matching_columns(column_name: str, column_description: str, table_name: str, db_name: str) -> Optional[Dict]:
#     """
#     Find matching column in a specific table using ChromaDB and direct embeddings.
#     Returns: {column_name, similarity} or None
#     """
#     try:
#         store = sync_chroma_schema_embeddings(db_name)
#         engine = get_engine_for_db(db_name)
#         inspector = inspect(engine)
        
#         # Get all columns from the table
#         columns = inspector.get_columns(table_name)
#         if not columns:
#             return None
        
#         column_names = [col["name"] for col in columns]
        
#         # Create embeddings for the search column
#         search_text = f"{column_name} {column_description}".strip()
#         search_embedding = embedding_model.embed_query(search_text)
        
#         # Get the table's schema document to extract column context
#         search_table_text = f"Table: {table_name}"
#         table_results = store.similarity_search(search_table_text, k=1)
        
#         table_context = ""
#         if table_results:
#             table_context = table_results[0].page_content if hasattr(table_results[0], 'page_content') else str(table_results[0])
        
#         # Create embeddings for each existing column and compare
#         best_match = None
#         best_similarity = 0.0
        
#         for col in columns:
#             col_name = col["name"]
#             col_type = str(col.get("type", ""))
            
#             # Create column text for embedding comparison
#             col_text = f"{col_name} {col_type} {table_name}"
#             col_embedding = embedding_model.embed_query(col_text)
            
#             # Calculate cosine similarity manually
#             similarity = np.dot(search_embedding, col_embedding) / (
#                 np.linalg.norm(search_embedding) * np.linalg.norm(col_embedding)
#             )
            
#             # Boost similarity for exact or partial name matches
#             if col_name.lower() == column_name.lower():
#                 similarity = min(1.0, similarity + 0.15)
#             elif col_name.lower() in column_name.lower() or column_name.lower() in col_name.lower():
#                 similarity = min(1.0, similarity + 0.1)
#             elif any(word in col_name.lower() for word in column_name.lower().split("_")) or \
#                  any(word in column_name.lower() for word in col_name.lower().split("_")):
#                 similarity = min(1.0, similarity + 0.05)
            
#             if similarity >= COLUMN_SIMILARITY_THRESHOLD and similarity > best_similarity:
#                 best_similarity = similarity
#                 best_match = {
#                     "column_name": col_name,
#                     "similarity": float(similarity)
#                 }
        
#         # Fallback: direct string matching if no good embedding match
#         if best_match is None:
#             for col_name in column_names:
#                 # Exact match
#                 if col_name.lower() == column_name.lower():
#                     return {
#                         "column_name": col_name,
#                         "similarity": 1.0
#                     }
#                 # Partial match
#                 elif col_name.lower() in column_name.lower() or column_name.lower() in col_name.lower():
#                     return {
#                         "column_name": col_name,
#                         "similarity": 0.75
#                     }
        
#         return best_match
#     except Exception as e:
#         print(f"[Column Matching] Error: {e}")
#         traceback.print_exc()
#         # Fallback to simple string matching
#         try:
#             engine = get_engine_for_db(db_name)
#             inspector = inspect(engine)
#             columns = inspector.get_columns(table_name)
#             column_names = [col["name"] for col in columns]
            
#             for col_name in column_names:
#                 if col_name.lower() == column_name.lower():
#                     return {
#                         "column_name": col_name,
#                         "similarity": 1.0
#                     }
#         except:
#             pass
#         return None


# def find_table_by_subject_or_column_similarity(gemini_table_name: str, gemini_table_subject: str, column_names: list, db_name: str) -> dict:
#     """
#     Returns a dict with the matching table name (if EITHER the subject/title or columns are similar enough to any existing table), else None.
#     """
#     store = sync_chroma_schema_embeddings(db_name)
#     engine = get_engine_for_db(db_name)
#     inspector = inspect(engine)
#     threshold = TABLE_SIMILARITY_THRESHOLD
#     col_threshold = COLUMN_SIMILARITY_THRESHOLD
#     best_table = None
#     best_score = 0.0
#     # Normalize Gemini inputs
#     gemini_table_name = normalize(gemini_table_name)
#     gemini_table_subject = normalize(gemini_table_subject)
#     column_names_norm = [normalize(c) for c in column_names]
#     print(f"[MATCH] Trying to merge: name='{gemini_table_name}', subject='{gemini_table_subject}', columns={column_names_norm}")
#     for existing in inspector.get_table_names():
#         existing_norm = normalize(existing)
#         db_cols = [normalize(col['name']) for col in inspector.get_columns(existing)]
#         print(f"  [CANDIDATE] Table={existing_norm} cols={db_cols}")
#         # 1. Table subject/title similarity
#         table_score = 0.0
#         table_hit = store.similarity_search_with_score(f"Table: {gemini_table_name} {gemini_table_subject}", k=10)
#         for doc, d in table_hit:
#             content = getattr(doc, 'page_content', str(doc)).lower()
#             if f"table: {existing_norm}" in content or existing_norm in content:
#                 s = 1.0 - (d/2.0)
#                 table_score = max(table_score, s)
#         # 2. Best/Average column name similarity
#         sim_scores = []
#         for cname in column_names_norm:
#             max_sim = 0.0
#             col_hit = store.similarity_search_with_score(f"Column: {cname}", k=10)
#             for doc, d in col_hit:
#                 content = getattr(doc, 'page_content', str(doc)).lower()
#                 if f"table: {existing_norm}" in content:
#                     sim = 1.0 - (d/2.0)
#                     max_sim = max(max_sim, sim)
#             sim_scores.append(max_sim)
#         avg_col_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0
#         best_col_sim = max(sim_scores) if sim_scores else 0.0
#         print(f"    > sim: TABLE={table_score:.2f}, AVG_COL={avg_col_sim:.2f}, BEST_COL={best_col_sim:.2f}")
#         score = max(table_score, best_col_sim, avg_col_sim)
#         if table_score >= threshold or best_col_sim >= col_threshold or avg_col_sim >= col_threshold:
#             print(f"    -> MATCH: {existing_norm}")
#             if score > best_score:
#                 best_score = score
#                 best_table = {'table_name': existing, 'subject_similarity': table_score, 'best_col_similarity': best_col_sim, 'avg_col_similarity': avg_col_sim}
#     if best_table:
#         print(f"[MATCH DECISION] SELECTED: {best_table}")
#     else:
#         print(f"[MATCH DECISION] No table matched. Creating new.")
#     return best_table


# def analyze_excel_with_gemini(file_path: str, df: pd.DataFrame) -> Dict:
#     try:
#         data_preview = f"File columns: {', '.join(df.columns.tolist())}\nFirst rows:\n{df.head(5).to_string()}"
#         file_type = classify_file_type(data_preview)
#         preferred_cols = TYPE_COLUMN_RECOMMENDATIONS.get(file_type, [])
#         pc_str = ', '.join(preferred_cols) if preferred_cols else '(none)'
#         prompt = f"""
# You are an information extractor. The data type is: {file_type.upper()}.
# Preferred columns for this file type are: [{pc_str}] — USE these columns IF the content fits, they are not required, but should be considered first when naming columns for relevant fields. Otherwise create a new abstract noun column name as needed.

# 1. Find a primary identifier (unique field like year, ID, etc).
# 2. For each record/block, extract all value-fields present; assign EACH to a column as an ABSTRACT NOUN (never 'description', 'column1', etc.).
# 3. Table name must be a proper noun or clear event/title best describing contents.
# Only output strict JSON, no commentary.
# Format:
# {{{{
#   "table_name": "...",
#   "primary_identifier": "...",
#   "columns": {{{{...}}}},
#   "rows": [{{{{...}}}}, ...]
# }}}}
# Input Preview:\n{data_preview}
# """
#         response = llm.invoke(prompt)
#         content = response.content.strip()
#         json_match = re.search(r'\{.*\}', content, re.DOTALL)
#         if json_match:
#             try:
#                 result = json.loads(json_match.group())
#                 # Simple sanity: require identifier and at least one abstract-noun column
#                 columns = result.get("columns", {})
#                 if result.get("primary_identifier") and any(col for col in columns if col not in [result['primary_identifier'], 'description', 'column1','value','field']):
#                     return result
#             except Exception as e:
#                 print("[Gemini Excel (abstract noun) RAW OUTPUT]:", content)
#                 print("[Gemini Excel] PARSE ERROR:", e)
#         # Fallback
#         cols = list(df.columns)
#         return {"table_name": sanitize_name(os.path.basename(file_path).replace(".xlsx", "").replace(".xls", "")),
#                 "primary_identifier": cols[0] if cols else None,
#                 "columns": {col: f"Data column: {col}" for col in cols},
#                 "rows": [row._asdict() if hasattr(row, '_asdict') else dict(zip(df.columns, r)) for r in df.itertuples(index=False)]}
#     except Exception as e:
#         print("[Gemini Excel (abstract noun) Fallback Exception]", e)
#         cols = list(df.columns)
#         return {"table_name": sanitize_name(os.path.basename(file_path).replace(".xlsx", "").replace(".xls", "")),
#                 "primary_identifier": cols[0] if cols else None,
#                 "columns": {col: f"Data column: {col}" for col in cols},
#                 "rows": [row._asdict() if hasattr(row, '_asdict') else dict(zip(df.columns, r)) for r in df.itertuples(index=False)]}

# def analyze_pdf_with_gemini(file_path: str) -> Dict:
#     try:
#         text_content = ""
#         with pdfplumber.open(file_path) as pdf:
#             for page in pdf.pages:
#                 text_content += page.extract_text() or ""
#         if not text_content.strip():
#             raise Exception("No text content found in PDF")
#         file_type = classify_file_type(text_content)
#         preferred_cols = TYPE_COLUMN_RECOMMENDATIONS.get(file_type, [])
#         pc_str = ', '.join(preferred_cols) if preferred_cols else '(none)'
#         prompt = f"""
# You are an expert information extractor. The data type is: {file_type.upper()}.
# Preferred columns for this file type are: [{pc_str}] — USE these columns IF the content matches, else create a new abstract noun column. These columns should be prioritized if meaning fits.
# 1. Find the best possible primary identifier for row-blocks.
# 2. For each block, assign columns ONLY as abstract nouns.
# 3. Table name must be a proper noun or entity title.
# NO commentary.
# Strict JSON only:
# {{{{
#   "table_name": "...",
#   "primary_identifier": "...",
#   "rows": [{{{{...}}}}, ...]
# }}}}
# Input Text (up to 5000 chars):\n{text_content[:5000]}
# """
#         response = llm.invoke(prompt)
#         content = response.content.strip()
#         json_match = re.search(r'\{.*\}', content, re.DOTALL)
#         if json_match:
#             try:
#                 result = json.loads(json_match.group())
#                 # Require identifier and at least one abstract-noun column
#                 if result.get("primary_identifier") and any(k for row in result.get("rows",[]) for k in row if k not in [result['primary_identifier'], 'description', 'column1','value','field']):
#                     return result
#             except Exception as e:
#                 print("[Gemini PDF (abstract noun) RAW OUTPUT]:", content)
#                 print("[Gemini PDF] PARSE ERROR:", e)
#         # Fallback
#         try:
#             tables = []
#             with pdfplumber.open(file_path) as pdf:
#                 for page in pdf.pages:
#                     for table in page.extract_tables():
#                         tables.append(table)
#             if tables:
#                 first_table = tables[0]
#                 import pandas as pd
#                 df = pd.DataFrame(first_table[1:], columns=first_table[0])
#                 cols = list(df.columns)
#                 return {"table_name": sanitize_name(os.path.basename(file_path).replace(".pdf", "")),
#                         "primary_identifier": cols[0] if cols else None,
#                         "columns": {col: f"Data column: {col}" for col in cols},
#                         "rows": [row._asdict() if hasattr(row, '_asdict') else dict(zip(df.columns, r)) for r in df.itertuples(index=False)]}
#         except Exception as e2:
#             print("[PDF literal fallback parse error]", e2)
#         return {"table_name": sanitize_name(os.path.basename(file_path).replace(".pdf", "")),
#                 "primary_identifier": None, "rows": []}
            
#     except Exception as e:
#         print(f"[Gemini PDF Analysis] Error: {e}")
#         traceback.print_exc()
#         return {"table_name": sanitize_name(os.path.basename(file_path).replace(".pdf", "")),
#                 "primary_identifier": None, "rows": []}


# # Helper: Extract intro/fingerprint from any document (list of lines)
# def extract_intro_fingerprint(lines, num_lines=3, char_limit=500):
#     intro_lines = []
#     for line in lines:
#         l = line.strip()
#         if l:
#             intro_lines.append(l)
#         if len(intro_lines) >= num_lines:
#             break
#     intro = ' '.join(intro_lines)
#     if not intro:
#         intro = ' '.join(lines)[:char_limit]
#     return intro.strip()

# # Helper: Register/Store intro fingerprint in Chroma (as doc type: table_intro, with metadata table=table_name)
# def store_table_intro_fingerprint(db_name: str, table_name: str, intro_text: str):
#     store = sync_chroma_schema_embeddings(db_name)
#     store.add_texts([f"TABLE_INTRO: {intro_text}"], metadatas=[{'type':'table_intro','table':table_name}])

# # Helper: Find matching table by context fingerprint
# # Returns: best table (if sim >= threshold), else None
# def find_table_by_intro_similarity(context_intro: str, db_name: str):
#     store = sync_chroma_schema_embeddings(db_name)
#     # fetch all table_intro docs from Chroma
#     found = store.get()
#     intros = []
#     intros_meta = []
#     for i, doc in enumerate(found.get('documents', [])):
#         meta = found.get('metadatas', [])[i]
#         if meta and meta.get('type') == 'table_intro':
#             intros.append(doc)
#             intros_meta.append(meta)
#     # Compare
#     best_table = None
#     best_sim = 0.0
#     for intro, meta in zip(intros, intros_meta):
#         table = meta.get('table')
#         docsims = store.similarity_search_with_score(f"TABLE_INTRO: {context_intro}", k=10)
#         for doc, d in docsims:
#             content = getattr(doc, 'page_content', str(doc)).lower()
#             if intro.lower() in content:
#                 sim = 1.0 - (d/2.0)
#                 if sim > best_sim:
#                     best_sim = sim
#                     best_table = {'table_name': table, 'intro_similarity': sim}
#     if best_table and best_sim >= INTRO_SIMILARITY_THRESHOLD:
#         print(f"[FINGERPRINT MATCH] Table {best_table['table_name']} (intro sim: {best_sim:.2f})")
#         return best_table
#     print("[FINGERPRINT MATCH] No close table. New one will be created.")
#     return None

# def _fallback_match_by_name(suggested_table_name: str, db_name: str) -> Optional[Dict]:
#     """When cosine similarity fails, try nearest table by name similarity only."""
#     try:
#         if not ENABLE_NAME_FALLBACK:
#             return None
#         store = sync_chroma_schema_embeddings(db_name)
#         engine = get_engine_for_db(db_name)
#         inspector = inspect(engine)
#         existing_tables = set(inspector.get_table_names())
#         if not existing_tables:
#             return None
#         search_text = f"Table: {suggested_table_name}"
#         results = store.similarity_search_with_score(search_text, k=10)
#         top_name = None
#         top_distance = None
#         for doc, distance in results:
#             content = getattr(doc, 'page_content', str(doc))
#             if "Table:" in content:
#                 try:
#                     nm = content.split("Table:")[1].split("\n")[0].strip()
#                     if nm in existing_tables:
#                         top_name = nm
#                         top_distance = distance
#                         break
#                 except:
#                     continue
#         if top_name:
#             sim_ratio = name_similarity(suggested_table_name, top_name)
#             if sim_ratio >= NAME_MATCH_THRESHOLD:
#                 cos_sim = 1.0 - (float(top_distance) / 2.0) if top_distance is not None else 0.0
#                 print(f"[Name Fallback] '{suggested_table_name}' ~ '{top_name}' = {sim_ratio:.2f} (cos={cos_sim:.2f})")
#                 return {"table_name": top_name, "similarity": cos_sim, "name_similarity": sim_ratio}
#         return None
#     except Exception as e:
#         print("[Name Fallback] Error:", e)
#         return None


# def analyze_excel_schema_with_gemini(file_name: str, df: pd.DataFrame) -> Dict:
#     """
#     Ask Gemini to infer a clean column schema from a small sample of Excel rows.
#     Returns: { column_mapping: {original_header: clean_column_name} }
#     """
#     try:
#         headers = df.columns.tolist()
#         sample_rows = df.head(10).astype(str).fillna("").values.tolist()
#         preview = {
#             "file_name": file_name,
#             "headers": headers,
#             "rows": sample_rows
#         }
#         prompt = f"""
# You are normalizing Excel column headers for database ingestion.
# Given the JSON payload with "headers" and first "rows" (strings), produce a JSON with a mapping from ORIGINAL HEADER to a CLEAN, ABSTRACT-NOUN column name.
# Rules:
# - Use only lowercase snake_case for names.
# - Prefer meaningful abstract nouns (e.g., 'year', 'project', 'milestone', 'owner').
# - Do NOT include columns that are entirely empty or 'unnamed' unless they clearly contain data.
# - Only output JSON, no commentary.
# Input JSON:
# {json.dumps(preview)[:12000]}
# Output JSON format:
# {{
#   "column_mapping": {{"original_header": "clean_column_name", ...}}
# }}
# """
#         response = llm.invoke(prompt)
#         content = response.content.strip()
#         json_match = re.search(r'\{.*\}', content, re.DOTALL)
#         if json_match:
#             try:
#                 result = json.loads(json_match.group())
#                 mapping = result.get("column_mapping", {})
#                 if isinstance(mapping, dict) and mapping:
#                     # sanitize mapping values
#                     clean_mapping = {}
#                     for k, v in mapping.items():
#                         if k in headers and v:
#                             clean_mapping[k] = sanitize_name(v)
#                     return {"column_mapping": clean_mapping}
#             except Exception as e:
#                 print("[Gemini Excel Schema RAW OUTPUT]:", content)
#                 print("[Gemini Excel Schema] PARSE ERROR:", e)
#         # Fallback: identity mapping on non-empty, non-unnamed columns
#         mapping = {}
#         for c in headers:
#             if not str(c).lower().startswith("unnamed"):
#                 mapping[c] = sanitize_name(c)
#         return {"column_mapping": mapping}
#     except Exception as e:
#         print("[Gemini Excel Schema] Exception:", e)
#         mapping = {c: sanitize_name(c) for c in df.columns if not str(c).lower().startswith("unnamed")}
#         return {"column_mapping": mapping}


# async def ingest_excel_file(file: UploadFile, db_name: str) -> Dict:
#     """
#     Intelligently ingest Excel file with table/column matching.
#     """
#     try:
#         def _drop_header_like_rows(df_in: pd.DataFrame) -> pd.DataFrame:
#             if df_in.empty:
#                 return df_in
#             mask = []
#             for _, row in df_in.iterrows():
#                 is_header = False
#                 for c in df_in.columns:
#                     v = row.get(c)
#                     if v is None:
#                         continue
#                     vs = str(v).strip().lower()
#                     if vs == c.strip().lower():
#                         is_header = True
#                         break
#                 mask.append(not is_header)
#             return df_in[pd.Series(mask, index=df_in.index)]

#         def _coerce_df_to_table_schema(df_in: pd.DataFrame, engine, table_name: str) -> pd.DataFrame:
#             try:
#                 insp = inspect(engine)
#                 columns = {c['name']: str(c.get('type', '')).lower() for c in insp.get_columns(table_name)}
#                 df_out = df_in.copy()
#                 # Replace common string sentinels with None
#                 df_out = df_out.replace({'nan': None, 'NaN': None, 'NONE': None, 'None': None}, regex=False)
#                 # Coerce numeric columns
#                 for col, t in columns.items():
#                     if col in df_out.columns:
#                         if 'int' in t or 'decimal' in t or 'numeric' in t or 'float' in t or 'double' in t or 'real' in t:
#                             df_out[col] = pd.to_numeric(df_out[col], errors='coerce')
#                 # Drop header-like rows and fully empty rows
#                 df_out = _drop_header_like_rows(df_out)
#                 df_out = df_out.dropna(how='all')
#                 return df_out
#             except Exception as e:
#                 print("[Schema Coerce] Warning:", e)
#                 return df_in

#         def _clean_excel_columns(df_in: pd.DataFrame) -> pd.DataFrame:
#             df_out = df_in.copy()
#             # Drop 'Unnamed:' columns if they are entirely empty/null
#             drop_cols = []
#             for c in df_out.columns:
#                 if str(c).lower().startswith("unnamed"):
#                     col_series = df_out[c]
#                     # consider empty if all null or blank strings
#                     if col_series.isna().all() or (col_series.astype(str).str.strip().replace({'nan': ''}).eq('').all()):
#                         drop_cols.append(c)
#             if drop_cols:
#                 df_out = df_out.drop(columns=drop_cols, errors='ignore')
#             # Sanitize again
#             df_out.columns = [sanitize_name(c) for c in df_out.columns]
#             return df_out

#         # Save file temporarily
#         suffix = ".csv" if file.filename.lower().endswith(".csv") else ".xlsx"
#         tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
#         content = await file.read()
#         tmp.write(content)
#         tmp.flush()
#         tmp.close()
#         tmp_path = tmp.name
        
#         try:
#             # Read Excel file
#             if file.filename.lower().endswith(".csv"):
#                 df = pd.read_csv(tmp_path)
#             else:
#                 df = pd.read_excel(tmp_path, engine="openpyxl")
            
#             # Clean data
#             df = clean_dataframe(df)
#             df = df.where(pd.notnull(df), None)
#             df.columns = [sanitize_name(c) for c in df.columns]
#             df = _clean_excel_columns(df)
            
#             # Analyze with Gemini for table naming (lightweight) and schema mapping for Excel
#             analysis = analyze_excel_with_gemini(file.filename, df)
#             suggested_table_name = sanitize_name(analysis.get("table_name", file.filename))
#             schema_info = analyze_excel_schema_with_gemini(file.filename, df)
#             column_mapping_from_gemini = schema_info.get("column_mapping", {})
#             # Apply column mapping to full DataFrame
#             df_mapped_by_gemini = df.rename(columns=column_mapping_from_gemini)
#             # Any columns not in mapping keep sanitized names (already sanitized)
#             column_descriptions = {}  # descriptions not needed; using names directly for similarity
#             primary_identifier = df_mapped_by_gemini.columns[0] if len(df_mapped_by_gemini.columns) else None
#             primary_description = ""
            
#             # Ensure database exists
#             with root_engine.connect() as conn:
#                 conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
            
#             engine = get_engine_for_db(db_name)
#             inspector = inspect(engine)
            
#             # Build intro text from Excel content (filename, columns, top rows)
#             preview_lines = [
#                 f"File: {file.filename}",
#                 "Columns: " + ", ".join(df.columns.tolist())
#             ]
#             head_rows = df.head(3).astype(str).values.tolist()
#             for row in head_rows:
#                 preview_lines.append(" | ".join(row))
#             context_intro = extract_intro_fingerprint(preview_lines)
#             print(f"Extracted intro for Excel: {context_intro}")

#             # 2. table_match = find_table_by_intro_similarity(context_intro, db_name)
#             table_match = find_table_by_intro_similarity(context_intro, db_name)

#             # 3. If match, use table for upsert; else, create new table and call store_table_intro_fingerprint(db_name, new_table_name, context_intro).
#             if table_match:
#                 matched_table_name = table_match["table_name"]
#                 intro_similarity = table_match["intro_similarity"]
#                 # Verify the matched table exists
#                 table_exists = matched_table_name in inspector.get_table_names()
#                 if table_exists:
#                     target_table = matched_table_name
#                     was_new_table = False
#                 else:
#                     # Match was found but table doesn't exist (shouldn't happen, but handle it)
#                     target_table = suggested_table_name
#                     intro_similarity = 0.0
#                     was_new_table = True
#                     table_match = None  # Reset match since table doesn't exist
#             else:
#                 # Try name-based fallback if enabled
#                 fb = _fallback_match_by_name(suggested_table_name, db_name)
#                 if fb:
#                     target_table = fb["table_name"]
#                     intro_similarity = fb.get("similarity", 0.0)
#                     was_new_table = False
#                     table_match = {"table_name": target_table, "intro_similarity": intro_similarity}
#                 else:
#                     target_table = suggested_table_name
#                     intro_similarity = 0.0
#                     was_new_table = True
            
#             # 4. Downstream column/row code unchanged.
#             # Check if target table exists
#             table_exists = target_table in inspector.get_table_names()
            
#             # Match columns
#             column_matches = []
#             new_columns = []
#             existing_columns = []
            
#             if table_exists:
#                 existing_cols = [col["name"] for col in inspector.get_columns(target_table)]
#                 existing_columns = existing_cols
#             else:
#                 existing_columns = []
            
#             for col in df_mapped_by_gemini.columns:
#                 col_desc = f"Excel column: {col}"
                
#                 if table_exists:
#                     # Try to match with existing column
#                     col_match = find_matching_columns(col, col_desc, target_table, db_name)
                    
#                     if col_match:
#                         column_matches.append({
#                             "source_column": col,
#                             "target_column": col_match["column_name"],
#                             "similarity": col_match["similarity"]
#                         })
#                     else:
#                         # New column needed if not an empty unnamed column
#                         if not str(col).lower().startswith("unnamed"):
#                             series = df_mapped_by_gemini[col]
#                             if not (series.isna().all() or (series.astype(str).str.strip().replace({'nan': ''}).eq('').all())):
#                                 new_columns.append(col)
#                 else:
#                     # New table, all columns are new
#                     new_columns.append(col)
            
#             # Create or update table
#             if not table_exists:
#                 # Create new table
#                 dtype_map = {col: infer_sql_type(dtype) for col, dtype in df.dtypes.items()}
#                 df.to_sql(target_table, con=engine, if_exists="replace", index=False, dtype=dtype_map)
#                 rows_added = len(df)
#                 # 5. Update ChromaDB embeddings
#                 store_table_intro_fingerprint(db_name, target_table, context_intro)
#             else:
#                 # Update existing table
#                 # Create column mapping: source -> target
#                 column_mapping = {match["source_column"]: match["target_column"] for match in column_matches}
                
#                 # Add new columns to table if any
#                 if new_columns:
#                     with engine.connect() as conn:
#                         for col in new_columns:
#                             if col not in existing_columns:
#                                 dtype = infer_sql_type(df[col].dtype)
#                                 sql_type = "VARCHAR(255)" if isinstance(dtype, String) else "INT" if isinstance(dtype, Integer) else "FLOAT" if isinstance(dtype, Float) else "DATETIME"
#                                 try:
#                                     conn.execute(text(f"ALTER TABLE `{target_table}` ADD COLUMN `{sanitize_name(col)}` {sql_type};"))
#                                     conn.commit()
#                                     # Update existing_columns list
#                                     existing_columns.append(sanitize_name(col))
#                                 except SQLAlchemyError as e:
#                                     print(f"Error adding column {col}: {e}")
                
#                 # Prepare dataframe with column mapping
#                 df_mapped = df_mapped_by_gemini.copy()
                
#                 # Rename matched columns
#                 for src, tgt in column_mapping.items():
#                     if src in df_mapped.columns:
#                         df_mapped = df_mapped.rename(columns={src: tgt})
                
#                 # Rename new columns to sanitized names
#                 for col in new_columns:
#                     if col in df_mapped.columns:
#                         sanitized_col = sanitize_name(col)
#                         if sanitized_col != col:
#                             df_mapped = df_mapped.rename(columns={col: sanitized_col})
                
#                 # Ensure all columns in df_mapped exist in the table
#                 final_columns = [col["name"] for col in inspector.get_columns(target_table)]
#                 df_mapped = df_mapped[[col for col in df_mapped.columns if col in final_columns]]
                
#                 # Append data
#                 if not df_mapped.empty:
#                     dtype_map = {col: infer_sql_type(dtype) for col, dtype in df_mapped.dtypes.items()}
#                     # Align dataframe with existing table schema to avoid type errors (e.g., 'nan' into INT)
#                     df_ready = _coerce_df_to_table_schema(df_mapped, engine, target_table)
#                     if not df_ready.empty:
#                         df_ready.to_sql(target_table, con=engine, if_exists="append", index=False, dtype=dtype_map)
#                         rows_added = len(df_ready)
#                     else:
#                         rows_added = 0
#                 else:
#                     rows_added = 0
            
#             # Update ChromaDB embeddings
#             sync_chroma_schema_embeddings(db_name)
            
#             # Get final column list
#             final_columns = [col["name"] for col in inspector.get_columns(target_table)]
            
#             return {
#                 "status": "success",
#                 "table_name": target_table,
#                 "rows_added": rows_added,
#                 "columns": final_columns,
#                 "matches": {
#                     "table_match": {
#                         "table_name": target_table,
#                         "similarity": intro_similarity,
#                         "was_new": was_new_table
#                     } if table_match else {
#                         "table_name": target_table,
#                         "similarity": 0.0,
#                         "was_new": True
#                     },
#                     "column_matches": column_matches,
#                     "new_columns": new_columns
#                 }
#             }
            
#         finally:
#             try:
#                 os.remove(tmp_path)
#             except:
#                 pass
                
#     except Exception as e:
#         traceback.print_exc()
#         return {"status": "error", "error": str(e)}


# async def ingest_pdf_file(file: UploadFile, db_name: str) -> Dict:
#     """
#     Intelligently ingest PDF file with Gemini analysis and table/column matching.
#     """
#     try:
#         def _drop_header_like_rows(df_in: pd.DataFrame) -> pd.DataFrame:
#             if df_in.empty:
#                 return df_in
#             mask = []
#             for _, row in df_in.iterrows():
#                 is_header = False
#                 for c in df_in.columns:
#                     v = row.get(c)
#                     if v is None:
#                         continue
#                     vs = str(v).strip().lower()
#                     if vs == c.strip().lower():
#                         is_header = True
#                         break
#                 mask.append(not is_header)
#             return df_in[pd.Series(mask, index=df_in.index)]

#         def _coerce_df_to_table_schema(df_in: pd.DataFrame, engine, table_name: str) -> pd.DataFrame:
#             try:
#                 insp = inspect(engine)
#                 columns = {c['name']: str(c.get('type', '')).lower() for c in insp.get_columns(table_name)}
#                 df_out = df_in.copy()
#                 df_out = df_out.replace({'nan': None, 'NaN': None, 'NONE': None, 'None': None}, regex=False)
#                 for col, t in columns.items():
#                     if col in df_out.columns:
#                         if 'int' in t or 'decimal' in t or 'numeric' in t or 'float' in t or 'double' in t or 'real' in t:
#                             df_out[col] = pd.to_numeric(df_out[col], errors='coerce')
#                 df_out = _drop_header_like_rows(df_out)
#                 df_out = df_out.dropna(how='all')
#                 return df_out
#             except Exception as e:
#                 print("[Schema Coerce] Warning:", e)
#                 return df_in

#         # Save file temporarily
#         tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
#         content = await file.read()
#         tmp.write(content)
#         tmp.flush()
#         tmp.close()
#         tmp_path = tmp.name
        
#         try:
#             # Analyze PDF with Gemini
#             analysis = analyze_pdf_with_gemini(tmp_path)
#             suggested_table_name = sanitize_name(analysis.get("table_name", file.filename))
#             description = analysis.get("description", "")
#             rows_data = analysis.get("rows", [])
#             primary_identifier = analysis.get("primary_identifier") or (pd.DataFrame(rows_data).columns[0] if len(pd.DataFrame(rows_data).columns) else None)
#             primary_description = description
            
#             if not rows_data:
#                 raise Exception("No structured data found in PDF")
            
#             # Convert to DataFrame
#             df = pd.DataFrame(rows_data)
#             df = clean_dataframe(df)
#             df = df.where(pd.notnull(df), None)
#             df.columns = [sanitize_name(c) for c in df.columns]
            
#             # Ensure database exists
#             with root_engine.connect() as conn:
#                 conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
            
#             engine = get_engine_for_db(db_name)
#             inspector = inspect(engine)
            
#             # Build intro text from PDF content
#             pdf_text_intro = ""
#             try:
#                 with pdfplumber.open(tmp_path) as _pdf:
#                     for page in _pdf.pages[:1]:
#                         pdf_text_intro += (page.extract_text() or "")[:1000]
#             except Exception as e:
#                 print("[PDF Intro Extraction] Error:", e)
#             lines = [l for l in (pdf_text_intro.splitlines() if pdf_text_intro else []) if l.strip()][:5]
#             if not lines and not df.empty:
#                 # fallback to table preview
#                 preview = ["PDF (table) preview:"] + [" | ".join([str(x) for x in r]) for r in df.head(3).values.tolist()]
#                 lines = preview
#             context_intro = extract_intro_fingerprint(lines or ["PDF file", file.filename])
#             print(f"Extracted intro for PDF: {context_intro}")

#             # 2. table_match = find_table_by_intro_similarity(context_intro, db_name)
#             table_match = find_table_by_intro_similarity(context_intro, db_name)

#             # 3. If match, use table for upsert; else, create new table and call store_table_intro_fingerprint(db_name, new_table_name, context_intro).
#             if table_match:
#                 matched_table_name = table_match["table_name"]
#                 intro_similarity = table_match["intro_similarity"]
#                 # Verify the matched table exists
#                 table_exists = matched_table_name in inspector.get_table_names()
#                 if table_exists:
#                     target_table = matched_table_name
#                     was_new_table = False
#                 else:
#                     # Match was found but table doesn't exist (shouldn't happen, but handle it)
#                     target_table = suggested_table_name
#                     intro_similarity = 0.0
#                     was_new_table = True
#                     table_match = None  # Reset match since table doesn't exist
#             else:
#                 # Try name-based fallback if enabled
#                 fb = _fallback_match_by_name(suggested_table_name, db_name)
#                 if fb:
#                     target_table = fb["table_name"]
#                     intro_similarity = fb.get("similarity", 0.0)
#                     was_new_table = False
#                     table_match = {"table_name": target_table, "intro_similarity": intro_similarity}
#                 else:
#                     target_table = suggested_table_name
#                     intro_similarity = 0.0
#                     was_new_table = True
            
#             # 4. Downstream column/row code unchanged.
#             # Check if target table exists
#             table_exists = target_table in inspector.get_table_names()
            
#             # Match columns
#             column_matches = []
#             new_columns = []
#             existing_columns = []
            
#             if table_exists:
#                 existing_cols = [col["name"] for col in inspector.get_columns(target_table)]
#                 existing_columns = existing_cols
#             else:
#                 existing_columns = []
            
#             for col in df.columns:
#                 if table_exists:
#                     # Try to match with existing column
#                     col_match = find_matching_columns(col, f"Column from PDF: {col}", target_table, db_name)
                    
#                     if col_match:
#                         column_matches.append({
#                             "source_column": col,
#                             "target_column": col_match["column_name"],
#                             "similarity": col_match["similarity"]
#                         })
#                     else:
#                         new_columns.append(col)
#                 else:
#                     new_columns.append(col)
            
#             # Create or update table
#             if not table_exists:
#                 # Create new table
#                 dtype_map = {col: infer_sql_type(dtype) for col, dtype in df.dtypes.items()}
#                 df.to_sql(target_table, con=engine, if_exists="replace", index=False, dtype=dtype_map)
#                 rows_added = len(df)
#                 # 5. Update ChromaDB embeddings
#                 store_table_intro_fingerprint(db_name, target_table, context_intro)
#             else:
#                 # Update existing table
#                 # Create column mapping: source -> target
#                 column_mapping = {match["source_column"]: match["target_column"] for match in column_matches}
                
#                 # Add new columns to table if any
#                 if new_columns:
#                     with engine.connect() as conn:
#                         for col in new_columns:
#                             if col not in existing_columns:
#                                 dtype = infer_sql_type(df[col].dtype)
#                                 sql_type = "VARCHAR(255)" if isinstance(dtype, String) else "INT" if isinstance(dtype, Integer) else "FLOAT" if isinstance(dtype, Float) else "DATETIME"
#                                 try:
#                                     conn.execute(text(f"ALTER TABLE `{target_table}` ADD COLUMN `{sanitize_name(col)}` {sql_type};"))
#                                     conn.commit()
#                                     # Update existing_columns list
#                                     existing_columns.append(sanitize_name(col))
#                                 except SQLAlchemyError as e:
#                                     print(f"Error adding column {col}: {e}")
                
#                 # Prepare dataframe with column mapping
#                 df_mapped = df.copy()
                
#                 # Rename matched columns
#                 for src, tgt in column_mapping.items():
#                     if src in df_mapped.columns:
#                         df_mapped = df_mapped.rename(columns={src: tgt})
                
#                 # Rename new columns to sanitized names
#                 for col in new_columns:
#                     if col in df_mapped.columns:
#                         sanitized_col = sanitize_name(col)
#                         if sanitized_col != col:
#                             df_mapped = df_mapped.rename(columns={col: sanitized_col})
                
#                 # Ensure all columns in df_mapped exist in the table
#                 final_columns = [col["name"] for col in inspector.get_columns(target_table)]
#                 df_mapped = df_mapped[[col for col in df_mapped.columns if col in final_columns]]
                
#                 # Append data
#                 if not df_mapped.empty:
#                     dtype_map = {col: infer_sql_type(dtype) for col, dtype in df_mapped.dtypes.items()}
#                     df_ready = _coerce_df_to_table_schema(df_mapped, engine, target_table)
#                     if not df_ready.empty:
#                         df_ready.to_sql(target_table, con=engine, if_exists="append", index=False, dtype=dtype_map)
#                         rows_added = len(df_ready)
#                     else:
#                         rows_added = 0
#                 else:
#                     rows_added = 0
            
#             # Update ChromaDB embeddings
#             sync_chroma_schema_embeddings(db_name)
            
#             # Get final column list
#             final_columns = [col["name"] for col in inspector.get_columns(target_table)]
            
#             return {
#                 "status": "success",
#                 "table_name": target_table,
#                 "rows_added": rows_added,
#                 "columns": final_columns,
#                 "matches": {
#                     "table_match": {
#                         "table_name": target_table,
#                         "similarity": intro_similarity,
#                         "was_new": was_new_table
#                     } if table_match else {
#                         "table_name": target_table,
#                         "similarity": 0.0,
#                         "was_new": True
#                     },
#                     "column_matches": column_matches,
#                     "new_columns": new_columns
#                 }
#             }
            
#         finally:
#             try:
#                 os.remove(tmp_path)
#             except:
#                 pass
                
#     except Exception as e:
#         traceback.print_exc()
#         return {"status": "error", "error": str(e)}


# async def intelligent_ingest_file(file: UploadFile, db_name: str) -> Dict:
#     """
#     Main entry point for intelligent file ingestion.
#     Routes to Excel or PDF handler based on file type.
#     """
#     file_ext = os.path.splitext(file.filename)[1].lower()
    
#     if file_ext in [".xlsx", ".xls", ".csv"]:
#         return await ingest_excel_file(file, db_name)
#     elif file_ext == ".pdf":
#         return await ingest_pdf_file(file, db_name)
#     else:
#         return {"status": "error", "error": f"Unsupported file type: {file_ext}"}

