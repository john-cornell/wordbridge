"""One-time download of word2vec-google-news-300 into gensim's local cache.

Run this once before starting the app for the first time:
    python scripts/download_model.py
"""
import gensim.downloader as api


def main():
    print("Downloading word2vec-google-news-300 (~1.6GB)... this can take a few minutes.")
    api.load("word2vec-google-news-300")
    print("Done. The model is cached locally; app.py will still take ~30-60s to load it into RAM on each run.")


if __name__ == "__main__":
    main()
