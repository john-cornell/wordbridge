import os

from wordbridge import create_app
from wordbridge.model import load_google_news_model
from wordbridge.version import get_version

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "wordbridge.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

version = get_version()
print(f"Wordbridge version {version}")

print("Loading word2vec-google-news-300 into memory (this can take 30-60s)...")
vector_model = load_google_news_model()
print(f"Model loaded. Vocabulary size: {vector_model.vocab_size()} words.")

app = create_app(
    vector_model=vector_model,
    db_path=DB_PATH,
    secret_key=os.environ.get("SECRET_KEY") or os.urandom(24),
    version=version,
)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
