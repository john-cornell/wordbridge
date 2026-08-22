import random
import re

from gensim.models import KeyedVectors

_TOKEN_RE = re.compile(r"^[a-z]+$")


class WordVectorModel:
    """Wraps a gensim KeyedVectors instance with the operations Wordbridge needs."""

    def __init__(self, keyed_vectors, vocab_limit=200000):
        filtered_words = [word for word in keyed_vectors.index_to_key if _TOKEN_RE.match(word)][:vocab_limit]

        # Rebuild as a real, much smaller KeyedVectors instead of just
        # filtering a Python list — vocab_limit previously only trimmed
        # candidate selection while the full multi-million-word matrix (plus
        # a same-sized normalized copy gensim lazily builds on the first
        # similarity/most_similar call) stayed resident regardless. That
        # combination OOM-killed an 8GB production VPS on its first real
        # game. This cuts actual memory from ~7GB to well under 1GB by
        # never holding more vectors than the app can ever use.
        #
        # Index the underlying array directly rather than keyed_vectors[words]
        # — that goes through gensim's __getitem__, which does one Python-level
        # get_vector() call per word. At 200k+ words that's ~170 SECONDS of
        # pure interpreter overhead (confirmed: consistent gunicorn worker
        # startup timeouts in production, every single boot). A single
        # vectorized numpy index is milliseconds regardless of vocab size.
        indices = [keyed_vectors.key_to_index[word] for word in filtered_words]
        small_kv = KeyedVectors(vector_size=keyed_vectors.vector_size)
        small_kv.add_vectors(filtered_words, keyed_vectors.vectors[indices])

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
        if to_word not in exclude and current_similarity >= win_threshold:
            return [to_word]

        visited = {from_word} | set(exclude)
        path = []
        for _ in range(max_hops):
            neighbors = [word for word, _ in self._kv.most_similar(current, topn=neighbors_per_hop)]

            # A candidate must actually clear win_threshold against the word
            # we're hopping FROM — matching the same threshold the graph
            # itself uses to draw an edge. Being one of current's nearest
            # neighbors by rank doesn't imply that; picking on rank alone
            # produced routes the graph would never actually connect.
            candidates = [
                w
                for w in neighbors
                if w in self._filtered_vocab_set
                and w not in visited
                and self._kv.similarity(current, w) >= win_threshold
            ]
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
            if best == to_word or best_similarity >= win_threshold:
                # Reaching threshold-similarity to the target counts as a
                # win even if `best` isn't literally the target word — make
                # that explicit in the returned path instead of stopping one
                # word short of the word the player was actually aiming for.
                if best != to_word:
                    path.append(to_word)
                return path

            visited.add(best)
            current = best
            current_similarity = best_similarity
        return None


def load_google_news_model(vocab_limit=200000):
    import gensim.downloader as api

    keyed_vectors = api.load("word2vec-google-news-300")
    return WordVectorModel(keyed_vectors, vocab_limit=vocab_limit)
