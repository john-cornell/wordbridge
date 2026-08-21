import random
import re

from gensim.models import KeyedVectors

_TOKEN_RE = re.compile(r"^[a-z]+$")


class WordVectorModel:
    """Wraps a gensim KeyedVectors instance with the operations Wordbridge needs."""

    def __init__(self, keyed_vectors, vocab_limit=100000):
        filtered_words = [word for word in keyed_vectors.index_to_key if _TOKEN_RE.match(word)][:vocab_limit]

        # Rebuild as a real, much smaller KeyedVectors instead of just
        # filtering a Python list — vocab_limit previously only trimmed
        # candidate selection while the full multi-million-word matrix (plus
        # a same-sized normalized copy gensim lazily builds on the first
        # similarity/most_similar call) stayed resident regardless. That
        # combination OOM-killed an 8GB production VPS on its first real
        # game. This cuts actual memory from ~7GB to well under 200MB by
        # never holding more vectors than the app can ever use.
        small_kv = KeyedVectors(vector_size=keyed_vectors.vector_size)
        small_kv.add_vectors(filtered_words, keyed_vectors[filtered_words])

        self._kv = small_kv
        self._filtered_vocab = filtered_words
        self._filtered_vocab_set = set(filtered_words)

    def contains(self, word):
        return word in self._kv

    def similarity(self, word_a, word_b):
        return float(self._kv.similarity(word_a, word_b))

    def random_pair(self, rng=random, max_similarity=0.7, max_attempts=20):
        for _ in range(max_attempts):
            word_a, word_b = rng.sample(self._filtered_vocab, 2)
            if self.similarity(word_a, word_b) < max_similarity:
                return word_a, word_b
        return word_a, word_b

    def find_route(
        self, from_word, to_word, max_hops=6, neighbors_per_hop=20, win_threshold=0.7, exclude=frozenset()
    ):
        current = from_word
        current_similarity = self._kv.similarity(current, to_word)
        visited = {from_word} | set(exclude)
        path = []
        for _ in range(max_hops):
            neighbors = [word for word, _ in self._kv.most_similar(current, topn=neighbors_per_hop)]

            if to_word in neighbors and to_word not in exclude:
                path.append(to_word)
                return path

            candidates = [w for w in neighbors if w in self._filtered_vocab_set and w not in visited]
            if not candidates:
                return None

            best = max(candidates, key=lambda w: self._kv.similarity(w, to_word))
            best_similarity = self._kv.similarity(best, to_word)
            if best_similarity <= current_similarity:
                # Nothing reachable from here is any closer than we already
                # are — stop rather than wander sideways through a cluster
                # of near-synonyms or drift backwards.
                return None

            path.append(best)
            if best_similarity >= win_threshold:
                return path

            visited.add(best)
            current = best
            current_similarity = best_similarity
        return None


def load_google_news_model(vocab_limit=100000):
    import gensim.downloader as api

    keyed_vectors = api.load("word2vec-google-news-300")
    return WordVectorModel(keyed_vectors, vocab_limit=vocab_limit)
