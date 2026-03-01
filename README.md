<div align="center">
  
<img 
  src="https://github.ecodesamsung.com/SRIB-PRISM/QueryBasedReports/assets/38888/67317990-5725-47a7-a277-cbe0e6ffe8b5" 
  width="500"
/>
</div>


<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Syne&weight=700&size=18&pause=1200&color=38BDF8&center=true&vCenter=true&width=700&lines=Ask+questions.+Get+SQL.;Turn+data+into+insights+instantly.;AI-powered+NL2SQL+with+RAG.;From+raw+files+to+queryable+databases." />

<br/>

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-4285F4?style=flat-square&logo=google&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-8E44AD?style=flat-square)
![MySQL](https://img.shields.io/badge/MySQL-00758F?style=flat-square&logo=mysql&logoColor=white)

</div>

<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%">

<div align="center">

## 🤖 Intelligent NL2SQL & Data Ingestion System

*Transform unstructured data into structured databases and query them using natural language.*

</div>

---
# Query Based Report

*Transform your Excel data into intelligent, queryable insights*

---
## Complete Project Demo and Explanation
![mqdefault](https://github.ecodesamsung.com/SRIB-PRISM/QueryBasedReports/assets/38880/4db00dd3-6754-4ba0-99c6-798ecf3d0e3a)

https://youtu.be/5Ied6-Ck5FE

Access to .tar files : https://drive.google.com/file/d/1MHhmeR5JtGZzQrHKU5jnFkd43a_EIXAQ/view?usp=sharing

Technical setup document link : https://drive.google.com/file/d/101YWyKTGp1RJCcqk1uew6-lLHLHbXtcm/view?usp=sharing

---

## What This Does?

Ever wished you could just ask your spreadsheets questions and get smart answers back? That's exactly what this project does. Drop in an Excel, PDF amd the data will be stored dynamically in the relevant table and column and Ask any query and right data for the answer will be retrieved from the DB . 

---

## How It Works

**1. Data Ingestion** → Your Excel files get processed and stored in a proper SQL database. 
  So any Data in Pdf or Excel (csv , xlsxx etc) can be interpretted and stored in their relevant tables in that database matching the content and primary identifiers and then actual data can be stored based on similairty with the existing column of the table or new      column. 
  
**2. AI Analysis** → Ask questions in plain English and get intelligent answers about your data
  So any NLP query sent by the user , first relevant tables are found by the ChromaDB vectordb based similarity matching then inside the relevant tables the relevant columns for the query are checked , after which the sql query is formed to retireve the result data      which then can also be converted back to NLP 

Think of it as giving your spreadsheets a brain.

---

## 📂 Dataset Format Requirements & Supported Patterns

```
Testing Data is in the folder 

root
|-- Testing Dataset
|   |-- Main_Test_Dataset
|   |   |-- chrome
|   |   |   |-- Chrome_Dataset.csv
|   |   |   |-- File1_2008_2011.csv
|   |   |   |-- File1_2008_2011.pdf

```

### 📌 Overview

The system supports multiple data formats, but its performance depends heavily on how structured the input data is.

> ⚠️ For best results, datasets should follow a **clear tabular structure** similar to relational database schemas.

---

### ✅ 1. Preferred Format (Highly Recommended)

Structured tabular data (e.g., Excel/CSV) with clearly defined columns.

#### ✔️ Example (Supported Format)

| Year | Key Achievement | Adoption/Usage | Technical Challenges | Business/Cost Impact |
|------|----------------|---------------|---------------------|----------------------|
| 2012 | Became most-used browser | Market share increased | Memory footprint | Increased ad revenue |
| 2013 | Chrome Apps launched | Improved adoption | Offline limitations | Ecosystem growth |

✔ This format ensures:
- Accurate schema inference  
- Better embedding generation  
- Reliable NL → SQL conversion  

---

### ✅ 2. Supported Semi-Structured Format (Conditionally Supported)

The system can also process narrative or timeline-style data, such as:

#### ✔️ Example

``` 

Google Chrome 
In recent years, Chrome emphasized privacy controls and AI-enhanced productivity.

2020 — Introduced tab grouping and performance throttling.
2021 — Improved privacy controls and launched Manifest V3.
2022 — Enhanced memory efficiency and introduced Journeys feature.
2023 — Wider adoption among students and professionals.

```


✔ This works because:
- The system uses **LLM-based parsing + chunking**
- Temporal patterns (years, events) can be inferred into structured form

---

### ⚠️ Important Limitation

> Semi-structured formats are **less reliable** than tabular formats.

Possible issues:
- Incorrect column inference  
- Missing attributes (e.g., cost, adoption not clearly stated)  
- Inconsistent schema across chunks  

---

### ❌ Unsupported / High-Risk Inputs

- Completely unstructured paragraphs without patterns  
- Data without consistent entities (e.g., mixed topics)  
- Missing temporal or categorical structure  
- No identifiable schema or repeated structure  

---

### 🧠 How the System Interprets Different Formats

| Input Type | Processing Behavior | Reliability |
|-----------|------------------|------------|
| Structured Tables | Direct schema mapping | ⭐⭐⭐⭐⭐ |
| Semi-Structured (Timelines, Logs) | Chunking + LLM inference | ⭐⭐⭐ |
| Unstructured Text | Weak schema inference | ⭐ |

---

### 🛠️ Recommendation

For **best accuracy and stability**:

- ✔ Use Excel/CSV with clear columns  
- ✔ Ensure consistent formatting across rows  
- ✔ Avoid mixing multiple data types in one file  
- ✔ Use semi-structured text only when necessary  

---

### 💡 Key Insight

> The system is not just format-driven — it is **structure-driven**.  
> The clearer the structure, the better the performance.


---

## Project Workflow
<img width="1393" alt="image" src="https://github.ecodesamsung.com/SRIB-PRISM/QueryBasedReports/assets/38888/05c1005e-b915-4501-8275-b33b5f08e141">

## User Query Flow
<img width="715" alt="image" src="https://github.ecodesamsung.com/SRIB-PRISM/QueryBasedReports/assets/38888/ef691bd8-ca86-44e7-ba7f-e80ebaa4c871">

---

## 4.1 Data Ingestion Pipeline

When a user uploads a file, a **multi-stage intelligent ingestion pipeline** is triggered to transform unstructured or semi-structured data into queryable database schemas.

### 🔄 Pipeline Overview (Enhanced with Chunking & Embedding Optimization)

| Stage | Step | Detail |
|------|------|--------|
| 1 | File Upload | User uploads file (Excel / CSV / PDF ) via Streamlit UI |
| 2 | Text Extraction | Format-specific parsers (e.g., pdfplumber, pandas) extract raw content, headers, and structure |
| 3 | Chunking (NEW) | Large documents are split into semantic chunks to preserve context and improve LLM understanding |
| 4 | Schema Inference | Gemini LLM analyzes extracted chunks to infer table name, column names, and data types |
| 5 | Schema Consolidation (NEW) | Chunk-level schemas are merged into a unified global schema representation |
| 6 | Schema Embedding | MiniLM model generates vector embeddings from the inferred schema description |
| 7 | Schema Matching | Embedding is compared (cosine similarity) against existing schema embeddings in ChromaDB |
| 8a | Existing Table Path | If similarity ≥ `TABLE_THRESHOLD`: <br>• Insert data into existing table <br>• Detect schema drift → apply `ALTER TABLE` if needed |
| 8b | New Table Path | If similarity < `TABLE_THRESHOLD`: <br>• Create new table using inferred schema <br>• Insert data via SQLAlchemy |
| 9 | Data Insertion Optimization (NEW) | Batch inserts + type normalization for efficient storage |
| 10 | Schema Refresh | Final schema re-read from DB and embeddings updated in ChromaDB |
| 11 | Metadata Logging (NEW) | Store ingestion metadata (source, timestamp, schema version) for traceability |

---

## 4.2 NL2SQL Query Pipeline

When a user submits a natural language query, a **robust AI-powered query pipeline** executes to generate, validate, and return results.

### ⚡ Pipeline Overview (Enhanced with RAG, Validation & Voice Input)

| Stage | Step | Detail |
|------|------|--------|
| 1 | Query Input | User enters query via text |
| 2 | Auth / RBAC | Role-Based Access Control validates user permissions and restricts accessible databases |
| 3 | Query Preprocessing (NEW) | Clean and normalize input (remove noise, handle synonyms, basic intent shaping) |
| 4 | Query Embedding | MiniLM model converts user query into a 384-dimensional vector embedding |
| 5 | Schema Retrieval (RAG) | Top-k relevant tables and columns retrieved from ChromaDB using cosine similarity |
| 6 | Few-Shot Retrieval (RAG) | Top-k similar historical NL→SQL examples retrieved from few-shot vector store |
| 7 | Context Chunk Selection (NEW) | Relevant schema chunks are selected to reduce token usage and improve accuracy |
| 8 | Prompt Construction | RAG Prompt Builder assembles: <br>• User query <br>• Retrieved schema context <br>• Few-shot examples |
| 9 | SQL Generation | Prompt sent to Gemini 2.5 Flash → LLM generates SQL query |
| 10 | SQL Validation (Guardrails) | Enforces read-only constraints: <br>• Blocks DROP / DELETE / UPDATE <br>• Fixes syntax via retry <br>• Prevents unsafe queries |
| 11 | SQL Execution | Validated SQL executed via SQLAlchemy on MySQL |
| 12 | Result Serialization | DataFrame cleaned (NaN, datetime, types) and converted to JSON-safe format |
| 13 | Post-Processing | Optional SQL→NL summarization using LLM |
| 14 | Visualization | Results displayed via tables + Plotly charts |
| 15 | Feedback Loop (NEW) | Query + SQL pair stored for improving few-shot retrieval over time |

---

## 🔐 Safety & Optimization Layers

### ✅ Query Safety
- Read-only SQL enforcement (SELECT / SHOW / EXPLAIN only)
- Multi-layer validation (regex + execution guardrails)

### ⚡ Performance Optimizations
- Global embedding model loading (avoids repeated initialization)
- Chunk-based RAG (reduces token usage)
- Cached schema embeddings (ChromaDB)

### 🧠 Intelligence Enhancements
- Few-shot learning with dynamic retrieval
- Schema-aware prompt construction
- Automatic schema evolution handling

---

## Project Structure

```
QueryBasedReports/
│
|-- .env
|-- .gitignore
|-- Meeting_ppts.zip
|-- README.md
|-- Testing Dataset
|   |-- Main_Test_Dataset
|   |   |-- chrome
|   |   |   |-- Chrome_Dataset.csv
|   |   |   |-- File1_2008_2011.csv
|   |   |   |-- File1_2008_2011.pdf
|   |   |   |-- File2_2012_2015.csv
|   |   |   |-- File2_2012_2015.pdf
|   |   |   |-- File3_2016_2019.csv
|   |   |   |-- File3_2016_2019.pdf
|   |   |   |-- File4_2020_2023.csv
|   |   |   |-- File4_2020_2023.pdf
|   |   |   |-- chrome_dataset_v2.pdf
|   |   |-- teams
|   |   |   |-- Book1.xlsx
|   |   |   |-- Book2.xlsx
|   |   |   |-- Book3.xlsx
|   |   |   |-- Book4.xlsx
|   |   |   |-- File1.pdf
|   |   |   |-- File2.pdf
|   |   |   |-- File3.pdf
|   |   |   |-- File4.pdf
|   |   |   |-- Teams_Dataset.csv
|   |   |   |-- teams_dataset_v2.pdf
|   |   |-- whatsapp
|   |   |   |-- Book1.xlsx
|   |   |   |-- Book2.xlsx
|   |   |   |-- Book3.xlsx
|   |   |   |-- Book4.xlsx
|   |   |   |-- File1_2009_2012.pdf
|   |   |   |-- File2_2013_2016.pdf
|   |   |   |-- File3_2017_2020.pdf
|   |   |   |-- File4_2021_2024.pdf
|   |   |   |-- Whatsapp_Dataset.csv
|-- backend
|   |-- app
|   |   |-- models
|   |   |   |-- query.py
|   |   |-- routes
|   |   |   |-- db_meta.py
|   |   |   |-- debug_chroma.py
|   |   |   |-- execute_query.py
|   |   |   |-- intelligent_ingest.py
|   |   |   |-- nl2sql.py
|   |   |   |-- refresh_schema.py
|   |   |   |-- summarize.py
|   |   |   |-- upload_excel.py
|   |   |-- services
|   |   |   |-- intelligent_ingestion_service.py
|   |   |   |-- nl2sql_service.py
|   |   |   |-- summarize_service.py
|   |   |   |-- upload_service.py
|   |-- chroma_examples
|   |   |-- fewshot_examples
|   |-- chroma_schemas
|   |-- main.py
|   |-- utils
|   |   |-- chroma_utils.py
|   |   |-- db.py
|   |   |-- db_utils.py
|   |   |-- fewshot_utils.py
|   |   |-- sql_readonly_validator.py
|-- docker-compose.yml
|-- frontend
|   |-- app.py
|   |-- assets
|   |   |-- styles.css
|   |-- components
|   |   |-- data_ingestion.py
|   |   |-- file_upload.py
|   |   |-- followup.py
|   |   |-- nl_query.py
|   |   |-- result_viewer.py
|   |   |-- sidebar.py
|   |   |-- sql_editor.py
|   |   |-- voice_input_component
|   |-- utils
|   |   |-- api.py
|-- requirements.txt

```
---

# 📦 SETUP GUIDE

## GenAI | Query-Based Reports

This document provides **complete setup instructions** for running the system using three different methods:

1. 🌐 Docker Hub (Recommended)
2. 📦 Offline `.tar` Deployment
3. 🔧 Local Development Setup

---

# 🔷 Prerequisites

Ensure the following are installed:

* Docker & Docker Compose
* MySQL Server (local or Docker)
* Gemini API Key
* Python 3.10+ (only for local setup)

---

# 📁 Required File Structure

```text
nl2sql/
│
├── docker-compose.yml
├── .env
├── 25TS09SRM_docker_backend.tar   (optional)
├── 25TS09SRM_docker_frontend.tar  (optional)
```

---

# 🌐 METHOD 1: Docker Hub Deployment (Recommended)

---

## Step 1 — Create Folder

```bash
mkdir nl2sql
cd nl2sql
```

---

## Step 2 — Create `.env`

```env
DB_USER=root
DB_PASS=your_password
DB_HOST=host.docker.internal
DB_PORT=3306
DB_NAME=your_database

GEMINI_API_KEY=your_gemini_api_key
```

---

## 🧠 Database Configuration Notes

You can use either:

### 🔹 Local MySQL (Recommended)

```env
DB_HOST=host.docker.internal
DB_PORT=3306
```

👉 Ensure MySQL is running locally.

---

### 🔹 Docker MySQL

```env
DB_HOST=mysql
DB_PORT=3306
```

👉 Use only if MySQL is added as a Docker service.

---

⚠️ Do NOT use:

```env
DB_HOST=localhost
```

(inside Docker, this refers to the container itself)

---

## Step 3 — Create `docker-compose.yml`

```yaml
version: "3.9"

services:

  backend:
    image: abhay2kumar/25ts09srm-nl2sql-backend
    container_name: fastapi_backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped

  frontend:
    image: abhay2kumar/25ts09srm-nl2sql-frontend
    container_name: streamlit_frontend
    ports:
      - "8501:8501"
    env_file:
      - .env
    environment:
      - BACKEND_URL=http://backend:8000
    depends_on:
      - backend
    restart: unless-stopped
```

---

## Step 4 — Run

```bash
docker-compose up
```

---

## Step 5 — Access

* Frontend → http://localhost:8501
* Backend → http://localhost:8000

---

---

# 📦 METHOD 2: Offline Deployment (.tar)

---

## Step 1 — Place Files

```text
25TS09SRM_docker_backend.tar
25TS09SRM_docker_frontend.tar
docker-compose.yml
.env
```

---

## Step 2 — Load Images

```bash
docker load -i 25TS09SRM_docker_backend.tar
docker load -i 25TS09SRM_docker_frontend.tar
```

---

## Step 3 — Verify

```bash
docker images
```

Expected:

```text
abhay2kumar/25ts09srm-nl2sql-backend
abhay2kumar/25ts09srm-nl2sql-frontend
```

---

## Step 4 — Update docker-compose.yml

```yaml
version: "3.9"

services:

  backend:
    image: abhay2kumar/25ts09srm-nl2sql-backend:latest
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped

  frontend:
    image: abhay2kumar/25ts09srm-nl2sql-frontend:latest
    ports:
      - "8501:8501"
    env_file:
      - .env
    environment:
      - BACKEND_URL=http://backend:8000
    depends_on:
      - backend
    restart: unless-stopped
```

---

## Step 5 — Run

```bash
docker-compose up
```

---

---

# 🔧 METHOD 3: Local Development Setup

---

## Step 1 — Clone Repository

```bash
git clone https://github.ecodesamsung.com/SRIB-PRISM/QueryBasedReports.git
cd QueryBasedReports
```

---

## Step 2 — Setup Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=query_reports
DB_USER=root
DB_PASS=your_password

GEMINI_API_KEY=your_key_here
```

---

## Step 3 — Virtual Environment

```bash
python3.10 -m venv venv

# Activate
source venv/bin/activate
```

---

## Step 4 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Step 5 — Setup Database

```bash
mysql -u root -p -e "CREATE DATABASE query_reports;"
```

---

## Step 6 — Run Backend

```bash
cd backend
uvicorn main:app --reload
```

---

## Step 7 — Run Frontend

```bash
cd frontend
streamlit run app.py
```

---

---

# 🧪 TROUBLESHOOTING

---

## Port already in use

```bash
lsof -i :8501
kill <PID>
```

---

## Backend not connecting

* Check `.env`
* Ensure MySQL is running
* Ensure correct `DB_HOST`

---

## YAML errors

```bash
docker-compose config
```

---

## Gemini API Error

* Free tier limit reached
* Wait or reduce requests

---

## Usage

### 1. Upload Data Files

Navigate to the frontend UI and upload your data files:

- **Supported formats:** Excel (.xlsx, .xls), CSV, PDF, PPT, Images, Text files
- Files are automatically processed and stored in SQL tables
- Schema is extracted and indexed for intelligent querying

### 2. Query Your Data in Natural Language

Simply type questions in plain English:

```
"Show me sales for Q3"
"List all employees who joined after 2021"
"Top 10 products by revenue last month"
"Find orders where amount > 5000 and status = pending"
"What is the average salary by department?"
```

### 3. View Results

- **Tables:** Clean, formatted data tables
- **Charts:** Visual representations of data
- **Summaries:** AI-generated insights
- **SQL Editor:** View and edit generated SQL (advanced users)

---

## 🛠️ Technology Stack

The system is built using a modern, scalable, and modular technology stack that enables efficient data ingestion, intelligent query processing, and interactive visualization.

### 📊 Stack Overview

| Category | Technology | Version | Purpose |
|----------|-----------|--------|--------|
| Backend Framework | FastAPI | Latest | REST API + async processing |
| Frontend | Streamlit | Latest | Interactive web UI |
| LLM | Google Gemini | 2.5 Flash | SQL generation & summarization |
| Embedding Model | HuggingFace MiniLM | all-MiniLM-L6-v2 | Semantic similarity search |
| Vector Database | ChromaDB | Latest | Schema & few-shot storage |
| Relational Database | MySQL | 8.x | Structured data storage |
| ORM | SQLAlchemy | Latest | Database abstraction layer |
| Containerization | Docker | Latest | Service isolation |
| Orchestration | Docker Compose | 3.9 | Multi-service management |
| PDF Parsing | pdfplumber | Latest | Text & table extraction from PDFs |

---

### 🔍 Key Highlights

- ⚡ **FastAPI** enables high-performance asynchronous APIs  
- 🧠 **Gemini 2.5 Flash** powers intelligent SQL generation and summarization  
- 🔎 **MiniLM Embeddings + ChromaDB** enable efficient semantic retrieval (RAG)  
- 🗄️ **MySQL + SQLAlchemy** provide robust and scalable data management  
- 🐳 **Docker & Docker Compose** ensure portability and reproducibility  
- 📊 **Streamlit** delivers a fast and intuitive user interface  

---
## 👥 Team

<br/>

<table align="center">
<tr>

<td align="center" width="160">
<!-- <img src="https://via.placeholder.com/120" width="120" height="120" style="border-radius:50%;" /> -->
<br/><b>Abhay Kumar</b>
<!-- <br/><sub>Backend & AI Systems</sub> -->
</td>

<td align="center" width="160">
<!-- <img src="https://via.placeholder.com/120" width="120" height="120" style="border-radius:50%;" /> -->
<br/><b>Akshit Bhatt</b>
<!-- <br/><sub>Frontend</sub> -->
</td>

<td align="center" width="160">
<!-- <img src="https://via.placeholder.com/120" width="120" height="120" style="border-radius:50%;" /> -->
<br/><b>Vishnu Gupta</b>
<!-- <br/><sub>ML / Data</sub> -->
</td>

<td align="center" width="160">
<!-- <img src="https://via.placeholder.com/120" width="120" height="120" style="border-radius:50%;" /> -->
<br/><b>Akshat Baranwal</b>
<!-- <br/><sub>System Design</sub> -->
</td>

</tr>
</table>

<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%">

<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Syne&weight=700&size=15&pause=2000&color=38BDF8&center=true&vCenter=true&width=700&lines=Upload.+Understand.+Query.;AI+that+turns+data+into+decisions.;From+files+to+insights+in+seconds." />

</div>

