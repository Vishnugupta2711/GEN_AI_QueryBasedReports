# utils/fewshot_utils.py
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import os, traceback

# Predefined examples (you can add more later)
FEWSHOT_EXAMPLES = [
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
        "input": "For each mobile model, show total quantity sold and average sale price.",
        "sql": """SELECT m.model,
                         SUM(sa.quantity) AS total_sold,
                         AVG(sa.total_amount / sa.quantity) AS avg_price_per_unit
                  FROM sales sa
                  JOIN mobiles m ON sa.mobile_id = m.mobile_id
                  GROUP BY m.model;"""
    }, # Movies / Cast / Ratings Examples
{
    "input": "List all movies released after 2015 with a rating above 8.",
    "sql": """SELECT m.title, m.release_year, r.avg_rating
              FROM movies m
              JOIN ratings r ON m.movie_id = r.movie_id
              WHERE m.release_year > 2015 AND r.avg_rating > 8;"""
},
{
    "input": "Find the top 3 highest-rated action movies.",
    "sql": """SELECT m.title, r.avg_rating
              FROM movies m
              JOIN ratings r ON m.movie_id = r.movie_id
              WHERE m.genre = 'Action'
              ORDER BY r.avg_rating DESC
              LIMIT 3;"""
},
{
    "input": "Which actor appeared in the most movies?",
    "sql": """SELECT c.person_name, COUNT(*) AS movie_count
              FROM moviecast c
              GROUP BY c.person_name
              ORDER BY movie_count DESC
              LIMIT 1;"""
},
{
    "input": "List all actors who appeared in more than one genre of movies.",
    "sql": """SELECT c.person_name
              FROM moviecast c
              JOIN movies m ON c.movie_id = m.movie_id
              GROUP BY c.person_name
              HAVING COUNT(DISTINCT m.genre) > 1;"""
},
{
    "input": "Show each genre with its average rating and number of movies.",
    "sql": """SELECT m.genre, AVG(r.avg_rating) AS avg_rating, COUNT(m.movie_id) AS total_movies
              FROM movies m
              JOIN ratings r ON m.movie_id = r.movie_id
              GROUP BY m.genre
              ORDER BY avg_rating DESC;"""
},
# T-Shirts / Discounts Examples
{
    "input": "Show all t-shirts currently in stock with a discount applied.",
    "sql": """SELECT t.brand, t.color, t.size, t.price, d.pct_discount
              FROM t_shirts t
              JOIN discounts d ON t.t_shirt_id = d.t_shirt_id
              WHERE t.stock_quantity > 0;"""
},
{
    "input": "Which t-shirt brand offers the highest average discount?",
    "sql": """SELECT t.brand, AVG(d.pct_discount) AS avg_discount
              FROM t_shirts t
              JOIN discounts d ON t.t_shirt_id = d.t_shirt_id
              GROUP BY t.brand
              ORDER BY avg_discount DESC
              LIMIT 1;"""
},
{
    "input": "List the total number of t-shirts per size and color combination.",
    "sql": """SELECT size, color, COUNT(*) AS total_count
              FROM t_shirts
              GROUP BY size, color;"""
},
{
    "input": "Find t-shirts priced above 1000 with less than 10% discount.",
    "sql": """SELECT t.brand, t.price, d.pct_discount
              FROM t_shirts t
              JOIN discounts d ON t.t_shirt_id = d.t_shirt_id
              WHERE t.price > 1000 AND d.pct_discount < 10;"""
},
{
    "input": "Show average price per brand after applying discounts.",
    "sql": """SELECT t.brand,
                     AVG(t.price * (1 - d.pct_discount / 100)) AS avg_discounted_price
              FROM t_shirts t
              JOIN discounts d ON t.t_shirt_id = d.t_shirt_id
              GROUP BY t.brand;"""
}


]

def build_fewshot_example_store():
    """Build a persistent Chroma store of few-shot examples."""
    persist_dir = "./chroma_examples/fewshot_examples"
    os.makedirs(persist_dir, exist_ok=True)

    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    store = Chroma(
        collection_name="fewshot_examples",
        embedding_function=embedding_model,
        persist_directory=persist_dir
    )

    try:
        # Only populate if empty
        if len(store.get().get("documents", [])) == 0:
            docs = [f"Q: {ex['input']}\nSQL: {ex['sql']}" for ex in FEWSHOT_EXAMPLES]
            metadatas = [{"id": i} for i in range(len(docs))]
            store.add_texts(docs, metadatas=metadatas)
            print(f"[FewShot] ✅ Populated {len(docs)} examples into Chroma at {persist_dir}")
        else:
            print(f"[FewShot] ⚙️ Existing examples already found at {persist_dir}")

    except Exception as e:
        print(f"[FewShot] ❌ Error building example store: {e}")
        traceback.print_exc()

    return store
