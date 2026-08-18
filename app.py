import os

from wordbridge import create_app
from wordbridge.model import load_google_news_model

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "wordbridge.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

print("Loading word2vec-google-news-300 into memory (this can take 30-60s)...")
vector_model = load_google_news_model()
print("Model loaded.")

app = create_app(vector_model=vector_model, db_path=DB_PATH, secret_key=os.urandom(24))

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
