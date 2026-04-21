import streamlit as st
import requests
import json
import plotly.graph_objects as go

BASE_URL = "http://localhost:8000/api"

def show_result_summary(sql_query, db_selected):
    if st.button("🧠 Generate Natural Language Summary"):
        with st.spinner("Generating summary..."):
            try:
                payload = {"sql_query": sql_query, "db_name": db_selected["db_name"]}
                res = requests.post(f"{BASE_URL}/summarize/", json=payload)

                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "success":
                        st.session_state.last_summary = data.get("summary")
                        st.session_state.last_chart = data.get("chart_json")
                        st.success("Summary generated successfully!")
                    else:
                        st.error(f"Error: {data.get('detail', 'Unknown error')}")
                elif res.status_code == 429:
                    # Handle quota exceeded error
                    try:
                        error_data = res.json()
                        detail = error_data.get("detail", {})
                        if isinstance(detail, dict):
                            error_msg = detail.get("error", "API quota exceeded")
                            error_details = detail.get("details", "")
                        else:
                            error_msg = str(detail)
                            error_details = ""
                        st.warning(f"⚠️ {error_msg}")
                        if error_details:
                            st.info(f"ℹ️ {error_details}")
                    except:
                        st.warning("⚠️ API quota exceeded. You've reached the daily limit for Gemini API requests. Please try again later.")
                else:
                    try:
                        error_data = res.json()
                        error_msg = error_data.get("detail", f"API request failed with status {res.status_code}")
                        st.error(f"Error: {error_msg}")
                    except:
                        st.error(f"API request failed with status {res.status_code}")
            except Exception as e:
                st.error(f"Error generating summary: {str(e)}")
               
    if st.session_state.get("last_summary"):
        st.markdown("### 🧠 Summary")
        st.write(st.session_state.last_summary)           
              
    if st.session_state.get("last_chart"):
        try:
            import plotly.graph_objects as go
            import json
            chart_data = st.session_state.last_chart
            if chart_data:
                fig = go.Figure(json.loads(chart_data))
                st.markdown("### 📊 Visualization")
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Could not display chart: {str(e)}")