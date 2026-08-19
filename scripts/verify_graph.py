"""Regression check for the chain graph view (pairwise edges, threshold slider, drag).

Drives a real headless-Chromium session against a throwaway dev server running the
small synthetic fixture model (never the real word2vec-google-news-300 model).

Requires Playwright (a dev-only browser-automation tool, not a page dependency):
    pip install -r requirements.txt
    playwright install chromium

Run:
    python scripts/verify_graph.py
"""
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

PORT = 5099
BASE_URL = f"http://127.0.0.1:{PORT}"

SERVER_SNIPPET = f"""
import numpy as np
from gensim.models import KeyedVectors

from wordbridge import create_app
from wordbridge.model import WordVectorModel

kv = KeyedVectors(vector_size=3)
words = ["cat", "dog", "car", "auto"]
vectors = np.array([[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0, 0.9, 0.1]])
kv.add_vectors(words, vectors)
model = WordVectorModel(kv, vocab_limit=10)
app = create_app(vector_model=model, db_path=":memory:", secret_key="verify")
app.run(port={PORT}, debug=False, use_reloader=False)
"""


def start_server():
    proc = subprocess.Popen([sys.executable, "-c", SERVER_SNIPPET])
    time.sleep(2)
    return proc


def main():
    proc = start_server()
    failures = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(BASE_URL)

            page.fill("#word1-input", "cat")
            page.fill("#word2-input", "auto")
            page.click("#manual-btn")
            page.wait_for_selector("#game:not([hidden])")

            node_count = page.eval_on_selector_all(".node", "els => els.length")
            if node_count != 2:
                failures.append(f"expected 2 nodes after manual start, got {node_count}")

            page.fill("#word-input", "car")
            page.click("#add-word-btn")
            page.wait_for_timeout(200)

            node_count = page.eval_on_selector_all(".node", "els => els.length")
            if node_count != 3:
                failures.append(f"expected 3 nodes after adding 'car', got {node_count}")

            edge_count = page.eval_on_selector_all(".edge", "els => els.length")
            if edge_count != 3:
                failures.append(
                    f"expected 3 edges (car-cat, car-auto, cat-auto) after one word, got {edge_count}"
                )

            page.fill("#threshold-slider", "0")
            page.dispatch_event("#threshold-slider", "input")
            page.wait_for_timeout(200)
            visible_edges = page.eval_on_selector_all(
                ".edge", "els => els.filter(e => e.style.display !== 'none').length"
            )
            if visible_edges != 3:
                failures.append(
                    f"expected all 3 edges (car-cat, car-auto, cat-auto) visible at threshold 0, got {visible_edges} visible"
                )

            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    if failures:
        print("FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("All graph verification checks passed.")


if __name__ == "__main__":
    main()
