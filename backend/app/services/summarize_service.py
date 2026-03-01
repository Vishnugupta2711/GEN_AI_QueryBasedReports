from utils.db import get_engine_for_db
from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd
import json
import traceback
import plotly.express as px
import os
from google.api_core import exceptions as google_exceptions

# Initialize your internal / Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

def summarize_sql_result(sql_query: str, db_name: str):
    """
    Run a SQL query, summarize its meaning, and suggest a chart if relevant.
    """
    try:
        engine = get_engine_for_db(db_name)
        query = sql_query
        print("FINAL QUERY:", query)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            return {"summary": "No data returned for this query.", "chart_json": None}

        # Limit size for LLM input
        sample_df = df.head(50)

        # Build summarization prompt
        prompt = f"""
        You are a data analyst. A SQL query was executed:

        {sql_query}

        Here are the first 50 rows of the result (JSON format):
        {sample_df.to_json(orient='records')}

        Summarize the key trends, patterns, and insights in plain English.
        Be concise and clear.
        """

        try:
            response = llm.invoke(prompt)
            summary_text = response.content.strip()
        except google_exceptions.ResourceExhausted as quota_error:
            # Handle API quota/rate limit errors gracefully
            error_msg = str(quota_error)
            if "quota" in error_msg.lower() or "429" in error_msg:
                return {
                    "error": "API quota exceeded. You've reached the daily limit for Gemini API requests. Please try again later or check your API plan.",
                    "quota_exceeded": True,
                    "details": "The free tier allows 20 requests per day per model. Please wait a few minutes before retrying."
                }
            else:
                return {"error": f"API rate limit error: {error_msg}"}
        except Exception as llm_error:
            traceback.print_exc()
            return {"error": f"Error generating summary: {str(llm_error)}"}

        # Auto chart suggestion (basic heuristic)
        chart_json = None
        if len(df.columns) >= 2:
            x_col, y_col = df.columns[0], df.columns[1]
            try:
                fig = px.line(df, x=x_col, y=y_col, title=f"{y_col} vs {x_col}")
                chart_json = fig.to_json()
            except Exception:
                pass

        return {
            "summary": summary_text,
            "chart_json": chart_json,
            "rows": len(df),
            "columns": list(df.columns),
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}