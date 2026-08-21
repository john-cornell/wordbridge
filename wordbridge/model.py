import random
import re

_TOKEN_RE = re.compile(r"^[a-z]+$")


class WordVectorModel:
    """Wraps a gensim KeyedVectors instance with the operations Wordbridge needs."""

    def __init__(self, keyed_vectors, vocab_limit=50000):
        self._kv = keyed_vectors
        self._filtered_vocab = self._build_filtered_vocab(vocab_limit)
        self._filtered_vocab_set = set(self._filtered_vocab)

    def _build_filtered_vocab(self, vocab_limit):
        filtered = [word for word in self._kv.index_to_key if _TOKEN_RE.match(word)]
        return filtered[:vocab_limit]

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


def load_google_news_model(vocab_limit=50000):
    import gensim.downloader as api

    keyed_vectors = api.load("word2vec-google-news-300")
    return WordVectorModel(keyed_vectors, vocab_limit=vocab_limit)
